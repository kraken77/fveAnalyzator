"""Dispečink — API (M1.3.3 import, M2.5 workflow, notifikace)."""

import os
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
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
    if user.has_role("admin") or user.has_role("antelon"):
        return p
    from .storage import ProjectUser
    if p.owner_id == user.id:
        return p
    link = db.query(ProjectUser).filter(
        ProjectUser.project_id == p.id, ProjectUser.user_id == user.id).first()
    if link:
        return p
    raise HTTPException(403, "Bez přístupu k projektu")


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
             "state_model": s.state_model or "simple"} for s in steps]


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
        db.query(Notification).filter(Notification.project_id == project_id).delete()
        from .storage import StepEvent
        db.query(StepEvent).filter(StepEvent.step_id == ps.id).delete()
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