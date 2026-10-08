"""Dispečink — API (M1.3.3 import, M2.5 workflow, notifikace)."""

import os
import json
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .auth import get_current_user, require_roles
from .storage import (Notification, PipelineAiResult, PipelineStep,
                      PipelineTemplate, Project, ProjectStep, User, get_db)

router = APIRouter(tags=["dispecink"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


def _ensure_project_access(project_id: int, user: User, db: Session) -> Project:
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Projekt nenalezen")
    from .auth import can_access_project
    if not can_access_project(user, p, db):
        raise HTTPException(403, "Bez přístupu k projektu")
    return p


def _get_project_step(db, project_id, step_id) -> ProjectStep:
    ps = db.query(ProjectStep).filter(
        ProjectStep.id == step_id, ProjectStep.project_id == project_id).first()
    if not ps:
        raise HTTPException(404, "Krok projektu nenalezen")
    return ps


# ---------- Import (M1.3.3) ----------

@router.post("/admin/import/dispecink")
async def import_dispecink_endpoint(
    file: UploadFile = File(...),
    user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """Import historických zakázek z Excelu „PROCESNÍ DISPEČINK" (idempotentní)."""
    content = await file.read()
    if not content:
        raise HTTPException(400, "Prázdný soubor")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Soubor je příliš velký (max 10 MB)")

    os.makedirs("data/imports", exist_ok=True)
    fname = f"dispecink_{datetime.utcnow():%Y%m%d%H%M%S}.xlsx"
    path = os.path.join("data", "imports", fname)
    with open(path, "wb") as f:
        f.write(content)

    from .import_dispecink import import_dispecink

    try:
        result = import_dispecink(path, db)
    except Exception as e:
        raise HTTPException(400, f"Import selhal: {e}")
    result["saved_as"] = fname
    return result


# ---------- Šablony (M2.5) ----------

@router.get("/admin/pipeline-templates")
def list_templates(user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    tpls = db.query(PipelineTemplate).order_by(PipelineTemplate.id).all()
    return [{"id": t.id, "code": t.code, "name": t.name, "zakazka_type": t.zakazka_type,
             "version": t.version, "active": t.active} for t in tpls]


@router.get("/admin/pipeline-templates/{template_id}/steps")
def list_template_steps(template_id: int, user: User = Depends(require_roles("admin")),
                        db: Session = Depends(get_db)):
    steps = (db.query(PipelineStep).filter(PipelineStep.template_id == template_id)
             .order_by(PipelineStep.order).all())
    if not steps:
        raise HTTPException(404, "Šablona nenalezena nebo bez kroků")
    return [{"id": s.id, "code": s.code, "name": s.name, "phase": s.phase, "order": s.order,
             "est_admin_minutes": s.est_admin_minutes, "est_work_minutes": s.est_work_minutes,
             "state_model": s.state_model or "simple",
             "allowed_roles": json.loads(s.allowed_roles_json) if s.allowed_roles_json else [],
             "auto_hook": s.auto_hook, "parallel_group": s.parallel_group} for s in steps]


class TemplateStepUpdate(BaseModel):
    name: Optional[str] = None
    est_admin_minutes: Optional[int] = None
    est_work_minutes: Optional[int] = None
    allowed_roles: Optional[list] = None


@router.put("/admin/pipeline-templates/{template_id}/steps/{step_id}")
def update_template_step(template_id: int, step_id: int, data: TemplateStepUpdate,
                         user: User = Depends(require_roles("admin")),
                         db: Session = Depends(get_db)):
    s = db.query(PipelineStep).filter(
        PipelineStep.id == step_id, PipelineStep.template_id == template_id).first()
    if not s:
        raise HTTPException(404, "Krok nenalezen")
    if data.name is not None:
        s.name = data.name
    if data.est_admin_minutes is not None:
        s.est_admin_minutes = data.est_admin_minutes
    if data.est_work_minutes is not None:
        s.est_work_minutes = data.est_work_minutes
    if data.allowed_roles is not None:
        s.allowed_roles_json = json.dumps(data.allowed_roles, ensure_ascii=False)
    db.commit()
    return {"status": "ok", "id": s.id, "name": s.name}


class AttachIn(BaseModel):
    template_code: str


@router.post("/projects/{project_id}/pipeline/attach")
def attach_pipeline(project_id: int, data: AttachIn,
                    user: User = Depends(require_roles("admin", "antelon")),
                    db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    from .pipeline_seed import attach_template
    try:
        pp = attach_template(db, p, data.template_code)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "ok", "template_code": data.template_code, "project_id": project_id}


# ---------- Pipeline view a přechody (M2.5) ----------

@router.get("/projects/{project_id}/pipeline")
def project_pipeline(project_id: int, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    _ensure_project_access(project_id, user, db)
    from .pipeline import get_pipeline_view
    return get_pipeline_view(db, project_id, user)


class TransitionIn(BaseModel):
    action: str
    note: Optional[str] = None
    plan_date: Optional[str] = None          # ISO datetime, posílá frontend
    assigned_user_id: Optional[int] = None
    to_status: Optional[str] = None          # pro revert
    result: Optional[str] = None             # 'zamitnuto' pro hook invoice_2500


@router.post("/projects/{project_id}/steps/{step_id}/transition")
def step_transition(project_id: int, step_id: int, data: TransitionIn,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    ps = _get_project_step(db, project_id, step_id)
    from .pipeline import transition

    plan_date = None
    if data.plan_date:
        from datetime import datetime as _dt
        try:
            plan_date = _dt.fromisoformat(data.plan_date.replace("Z", "+00:00"))
            if plan_date.tzinfo is not None:
                plan_date = plan_date.replace(tzinfo=None)
        except ValueError:
            raise HTTPException(400, "Neplatný plan_date")

    ps = transition(db, p, ps, data.action, user, note=data.note, plan_date=plan_date,
                    assigned_user_id=data.assigned_user_id, to_status=data.to_status,
                    result=data.result)
    db.commit()
    return {"status": ps.status, "id": ps.id}


class AdminIn(BaseModel):
    action: str  # skip|revert|reassign|add_step|remove_step|cancel
    note: Optional[str] = None
    assigned_user_id: Optional[int] = None
    to_status: Optional[str] = None
    step_code: Optional[str] = None   # pro add_step


@router.post("/projects/{project_id}/steps/{step_id}/admin")
def step_admin(project_id: int, step_id: int, data: AdminIn,
               user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    ps = _get_project_step(db, project_id, step_id)

    if data.action == "remove_step":
        from .storage import StepEvent, detach_step_materials
        db.query(Notification).filter(Notification.step_id == ps.id).delete()
        db.query(StepEvent).filter(StepEvent.step_id == ps.id).delete()
        # materiály patří projektu — jen uvolníme vazbu na rušený krok
        detach_step_materials(db, ps.id)
        db.delete(ps)
        db.commit()
        return {"status": "removed"}

    if data.action == "add_step":
        if not data.step_code:
            raise HTTPException(400, "step_code povinný pro add_step")
        from .storage import ProjectPipeline
        pp = db.query(ProjectPipeline).filter(ProjectPipeline.project_id == project_id).first()
        if not pp:
            raise HTTPException(400, "Projekt nemá pipeline")
        st = db.query(PipelineStep).filter(
            PipelineStep.template_id == pp.template_id,
            PipelineStep.code == data.step_code).first()
        if not st:
            raise HTTPException(404, "Krok šablony nenalezen")
        exists = db.query(ProjectStep).filter(
            ProjectStep.project_id == project_id, ProjectStep.step_id == st.id).first()
        if exists:
            raise HTTPException(400, "Krok už v projektu je")
        ps = ProjectStep(project_id=project_id, step_id=st.id, status="not_started",
                         real_admin_minutes=0, real_work_minutes=0)
        db.add(ps)
        db.commit()
        return {"status": "added", "id": ps.id}

    from .pipeline import transition
    ps = transition(db, p, ps, data.action, user, note=data.note,
                    assigned_user_id=data.assigned_user_id, to_status=data.to_status)
    db.commit()
    return {"status": ps.status, "id": ps.id}


# ---------- AI kroky (M3.3) ----------

class RunAiIn(BaseModel):
    trigger: str = "manual"  # auto|manual


@router.post("/projects/{project_id}/steps/{step_id}/run-ai")
def step_run_ai(project_id: int, step_id: int, data: RunAiIn,
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    ps = _get_project_step(db, project_id, step_id)
    from .ai_service import run_ai
    res = run_ai(db, p, ps, user, trigger=data.trigger)
    db.commit()
    db.refresh(res)
    return {"id": res.id, "status": res.status, "kind": res.kind,
            "project_id": project_id, "step_id": step_id}


class ReviewAiIn(BaseModel):
    result_id: int
    approved: bool
    note: Optional[str] = None


@router.post("/projects/{project_id}/steps/{step_id}/review-ai")
def step_review_ai(project_id: int, step_id: int, data: ReviewAiIn,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    ps = _get_project_step(db, project_id, step_id)
    # IDOR: výsledek musí patřit tomuto kroku tohoto projektu
    res = db.query(PipelineAiResult).filter(PipelineAiResult.id == data.result_id).first()
    if res is None or res.step_id != ps.id or res.project_id != project_id:
        raise HTTPException(404, "Výsledek AI k tomuto kroku nenalezen")
    from .ai_service import review_ai
    res = review_ai(db, data.result_id, data.approved, user, note=data.note)
    db.commit()
    db.refresh(res)
    db.refresh(ps)
    return {"id": res.id, "status": res.status, "step_status": ps.status}


@router.get("/projects/{project_id}/steps/{step_id}/ai-results")
def ai_results(project_id: int, step_id: int, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    ps = _get_project_step(db, project_id, step_id)
    rows = (db.query(PipelineAiResult)
            .filter(PipelineAiResult.step_id == ps.id)
            .order_by(PipelineAiResult.id.desc()).all())
    return [{"id": r.id, "kind": r.kind, "status": r.status,
             "input": json.loads(r.input_json) if r.input_json else None,
             "output": json.loads(r.output_json) if r.output_json else None,
             "pdf_version_id": r.pdf_version_id,
             "created_by": r.created_by, "reviewed_by": r.reviewed_by,
             "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows]


# ---------- Ekonomika (M4) ----------

class TimeEntryIn(BaseModel):
    step_id: Optional[int] = None
    minutes: int
    work_date: Optional[str] = None
    kind: str = "admin"
    note: Optional[str] = None


@router.post("/projects/{project_id}/time-entries")
def add_time_entry_endpoint(project_id: int, data: TimeEntryIn,
                            user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    step = _get_project_step(db, project_id, data.step_id) if data.step_id else None
    wd = date.fromisoformat(data.work_date) if data.work_date else date.today()
    from .economy import add_time_entry
    te = add_time_entry(db, p, step, user, data.minutes, data.kind, wd, data.note)
    db.commit()
    db.refresh(te)
    return {"id": te.id, "step_id": te.step_id, "minutes": te.minutes,
            "kind": te.kind, "work_date": te.work_date.isoformat()
            if te.work_date else None}


@router.get("/projects/{project_id}/time-entries")
def list_time_entries(project_id: int, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    from .storage import TimeEntry
    rows = db.query(TimeEntry).filter(TimeEntry.project_id == project_id) \
        .order_by(TimeEntry.id.desc()).all()
    out = []
    for te in rows:
        u = db.query(User).filter(User.id == te.user_id).first()
        step_name = None
        if te.step_id:
            row = (db.query(ProjectStep, PipelineStep)
                   .join(PipelineStep, ProjectStep.step_id == PipelineStep.id)
                   .filter(ProjectStep.id == te.step_id).first())
            if row:
                step_name = row[1].name
        out.append({"id": te.id, "step_id": te.step_id, "step_name": step_name,
                    "user_email": u.email if u else None, "minutes": te.minutes,
                    "kind": te.kind, "work_date": te.work_date.isoformat()
                    if te.work_date else None, "note": te.note or ""})
    return out


@router.get("/projects/{project_id}/time-entries/summary")
def time_entries_summary(project_id: int, user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    from .economy import time_summary
    return time_summary(db, project_id)


@router.get("/admin/reports/monteri-csv")
def monteri_csv_report(start: str = Query(None, alias="from"),
                       end: str = Query(None, alias="to"),
                       user: User = Depends(require_roles("admin", "antelon")),
                       db: Session = Depends(get_db)):
    from .economy import monteri_entries
    from_d = date.fromisoformat(start) if start else None
    to_d = date.fromisoformat(end) if end else None
    rows = monteri_entries(db, from_d, to_d)
    import csv as _csv
    import io
    buf = io.StringIO()
    w = _csv.writer(buf, delimiter=";")
    w.writerow(["user", "project", "step", "date", "minutes", "kind", "note"])
    for r in rows:
        w.writerow([r["user"], r["project"], r["step"], r["date"],
                    r["minutes"], r["kind"], r["note"]])
    return Response(content=buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=monteri.csv"})


# ---------- Materiály (M4.3) ----------

class MaterialIn(BaseModel):
    code: str
    name: str
    unit: str = "ks"
    price: float = 0.0
    category: str = "other"
    visibility: str = "public"
    rating: float | None = None
    supplier: str | None = None
    is_default: bool = False
    system_kwp: float | None = None
    system_battery_kwh: float | None = None


@router.get("/materials")
def list_materials(user: User = Depends(require_roles("admin", "antelon", "buyer", "warehouse")),
                   db: Session = Depends(get_db)):
    from .storage import Material
    rows = db.query(Material).order_by(Material.code).all()
    return [{"id": m.id, "code": m.code, "name": m.name, "unit": m.unit,
             "price": m.price, "active": m.active} for m in rows]


@router.post("/materials")
def create_material(data: MaterialIn,
                    user: User = Depends(require_roles("admin", "antelon")),
                    db: Session = Depends(get_db)):
    from .materials_service import set_material_price
    from .storage import Material

    if db.query(Material).filter(Material.code == data.code).first():
        raise HTTPException(400, f"Materiál s kódem {data.code!r} už existuje")
    m = Material(code=data.code, name=data.name, unit=data.unit,
                 category=data.category, visibility=data.visibility,
                 rating=data.rating, supplier=data.supplier,
                 is_default=data.is_default, system_kwp=data.system_kwp,
                 system_battery_kwh=data.system_battery_kwh)
    db.add(m)
    db.flush()
    set_material_price(db, m.id, data.price, date.today(), user.id)
    db.commit()
    db.refresh(m)
    return {"id": m.id, "code": m.code, "name": m.name, "unit": m.unit,
            "price": m.price, "category": m.category, "visibility": m.visibility,
            "rating": m.rating, "is_default": m.is_default,
            "system_kwp": m.system_kwp, "system_battery_kwh": m.system_battery_kwh}


class MaterialUpdateIn(BaseModel):
    name: str | None = None
    unit: str | None = None
    category: str | None = None
    visibility: str | None = None
    rating: float | None = None
    supplier: str | None = None
    is_default: bool | None = None
    system_kwp: float | None = None
    system_battery_kwh: float | None = None
    active: bool | None = None
    price: float | None = None
    valid_from: date | None = None


@router.put("/materials/{material_id}")
def update_material(material_id: int, data: MaterialUpdateIn,
                    user: User = Depends(require_roles("admin", "antelon")),
                    db: Session = Depends(get_db)):
    from .materials_service import set_material_price
    from .storage import Material

    m = db.query(Material).filter(Material.id == material_id).first()
    if not m:
        raise HTTPException(404, "Materiál nenalezen")
    for field in ("name", "unit", "category", "visibility", "rating",
                  "supplier", "is_default", "system_kwp", "system_battery_kwh",
                  "active"):
        value = getattr(data, field)
        if value is not None:
            setattr(m, field, value)
    if data.price is not None:
        set_material_price(db, m.id, data.price,
                           data.valid_from or date.today(), user.id)
    db.commit()
    db.refresh(m)
    return {"id": m.id, "code": m.code, "name": m.name, "unit": m.unit,
            "price": m.price, "active": m.active, "category": m.category,
            "visibility": m.visibility}


@router.delete("/materials/{material_id}")
def delete_material(material_id: int,
                    user: User = Depends(require_roles("admin", "antelon")),
                    db: Session = Depends(get_db)):
    """Měkké smazání — `active=0`. Řádek i historie cen zůstávají."""
    from .storage import Material

    m = db.query(Material).filter(Material.id == material_id).first()
    if not m:
        raise HTTPException(404, "Materiál nenalezen")
    m.active = False
    db.commit()
    return {"status": "ok"}


class MaterialPriceIn(BaseModel):
    price: float
    valid_from: date | None = None


@router.post("/materials/{material_id}/price")
def set_material_price_endpoint(material_id: int, data: MaterialPriceIn,
                                user: User = Depends(require_roles("admin", "antelon")),
                                db: Session = Depends(get_db)):
    from .materials_service import set_material_price
    from .storage import Material

    m = db.query(Material).filter(Material.id == material_id).first()
    if not m:
        raise HTTPException(404, "Materiál nenalezen")
    row = set_material_price(db, material_id, data.price,
                             data.valid_from or date.today(), user.id)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "material_id": material_id, "price": row.price,
            "valid_from": row.valid_from.isoformat(),
            "valid_to": row.valid_to.isoformat() if row.valid_to else None}


class ProjectMaterialIn(BaseModel):
    material_id: int
    qty: float = 1.0
    lane: str = "plan"
    step_id: Optional[int] = None
    price_snapshot: Optional[float] = None


@router.post("/projects/{project_id}/materials")
def add_project_material_endpoint(project_id: int, data: ProjectMaterialIn,
                                  user: User = Depends(require_roles("admin", "antelon", "buyer", "warehouse")),
                                  db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    from .storage import Material
    mat = db.query(Material).filter(Material.id == data.material_id).first()
    if not mat:
        raise HTTPException(404, "Materiál nenalezen")
    step = _get_project_step(db, project_id, data.step_id) if data.step_id else None
    from .economy import add_project_material
    pm = add_project_material(db, p, mat, qty=data.qty, lane=data.lane,
                              step_id=step.id if step else None,
                              price_snapshot=data.price_snapshot)
    db.commit()
    db.refresh(pm)
    return {"id": pm.id, "material_id": pm.material_id, "qty_planned": pm.qty_planned,
            "qty_actual": pm.qty_actual, "lane": pm.lane,
            "price_snapshot": pm.price_snapshot}


@router.get("/projects/{project_id}/materials")
def list_project_materials(project_id: int, user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    from .storage import Material, ProjectMaterial
    rows = (db.query(ProjectMaterial, Material)
            .join(Material, ProjectMaterial.material_id == Material.id)
            .filter(ProjectMaterial.project_id == project_id)
            .order_by(Material.code, ProjectMaterial.id).all())
    return [{"id": pm.id, "material_id": m.id, "code": m.code, "name": m.name,
             "lane": pm.lane, "qty_planned": pm.qty_planned,
             "qty_actual": pm.qty_actual, "price_snapshot": pm.price_snapshot,
             "step_id": pm.step_id} for pm, m in rows]


@router.get("/projects/{project_id}/materials/balance")
def materials_balance(project_id: int, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    from .economy import material_balance
    return material_balance(db, project_id)


# ---------- Fakturace (M4.4) ----------

class InvoiceItemIn(BaseModel):
    doc_type: str
    description: Optional[str] = None
    amount_czk: float = 0.0


@router.get("/projects/{project_id}/invoice-items")
def list_invoice_items(project_id: int, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    from .storage import InvoiceItem
    rows = db.query(InvoiceItem).filter(InvoiceItem.project_id == project_id) \
        .order_by(InvoiceItem.id).all()
    return [{"id": i.id, "doc_type": i.doc_type, "doc_number": i.doc_number,
             "description": i.description, "amount_czk": i.amount_czk,
             "status": i.status, "step_id": i.step_id,
             "created_at": i.created_at.isoformat() if i.created_at else None}
            for i in rows]


@router.post("/projects/{project_id}/invoice-items")
def add_invoice_item_endpoint(project_id: int, data: InvoiceItemIn,
                              user: User = Depends(require_roles("admin", "antelon", "sales")),
                              db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    from .economy import add_invoice_item
    inv = add_invoice_item(db, p, data.doc_type, data.description, data.amount_czk)
    db.commit()
    db.refresh(inv)
    return {"id": inv.id, "doc_type": inv.doc_type, "amount_czk": inv.amount_czk,
            "status": inv.status}


class InvoiceStatusIn(BaseModel):
    status: str


@router.post("/projects/{project_id}/invoice-items/{item_id}/status")
def invoice_item_status(project_id: int, item_id: int, data: InvoiceStatusIn,
                        user: User = Depends(require_roles("admin", "antelon")),
                        db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    from .storage import InvoiceItem
    inv = db.query(InvoiceItem).filter(
        InvoiceItem.id == item_id, InvoiceItem.project_id == project_id).first()
    if not inv:
        raise HTTPException(404, "Faktura nenalezena")
    if data.status == "issued":
        if inv.status == "issued":
            raise HTTPException(400, "Faktura už byla vystavena")
        from .economy import issue_invoice
        issue_invoice(db, inv, user)
        db.commit()
    elif data.status == "paid":
        inv.status = "paid"
        db.commit()
    else:
        raise HTTPException(400, "Neplatný status (issued|paid)")
    db.refresh(inv)
    return {"id": inv.id, "status": inv.status, "doc_number": inv.doc_number}


@router.get("/projects/{project_id}/economy")
def project_economy_endpoint(project_id: int, user: User = Depends(get_current_user),
                             db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    from .economy import project_economy
    return project_economy(db, project_id)


# ---------- Sazby (RateCard) — admin (M5.3) ----------

@router.get("/admin/rate-cards")
def list_rate_cards(user: User = Depends(require_roles("admin")),
                    db: Session = Depends(get_db)):
    from .storage import RateCard
    rows = db.query(RateCard).order_by(RateCard.role, RateCard.kind).all()
    return [{"id": r.id, "role": r.role, "kind": r.kind, "rate_czk_h": r.rate_czk_h,
             "active": r.active} for r in rows]


class RateCardUpdate(BaseModel):
    rate_czk_h: Optional[float] = None
    active: Optional[bool] = None


@router.put("/admin/rate-cards/{rate_id}")
def update_rate_card(rate_id: int, data: RateCardUpdate,
                     user: User = Depends(require_roles("admin")),
                     db: Session = Depends(get_db)):
    from .storage import RateCard
    r = db.query(RateCard).filter(RateCard.id == rate_id).first()
    if not r:
        raise HTTPException(404, "Sazba nenalezena")
    if data.rate_czk_h is not None:
        r.rate_czk_h = data.rate_czk_h
    if data.active is not None:
        r.active = data.active
    db.commit()
    db.refresh(r)
    return {"id": r.id, "role": r.role, "kind": r.kind, "rate_czk_h": r.rate_czk_h,
            "active": r.active}


# ---------- Notifikace (M2.3) ----------

@router.get("/notifications")
def my_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(Notification).filter(Notification.user_id == user.id)
            .order_by(Notification.read.asc(), Notification.id.desc())
            .limit(100).all())
    return [{"id": n.id, "text": n.text, "project_id": n.project_id, "read": n.read,
             "created_at": n.created_at.isoformat() if n.created_at else None} for n in rows]


@router.post("/notifications/{notification_id}/read")
def read_notification(notification_id: int, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    n = db.query(Notification).filter(
        Notification.id == notification_id, Notification.user_id == user.id).first()
    if not n:
        raise HTTPException(404, "Notifikace nenalezena")
    n.read = True
    db.commit()
    return {"status": "ok", "id": n.id, "read": True}