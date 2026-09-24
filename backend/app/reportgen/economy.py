"""Ekonomika pipeline (M4) — kalkulace nákladů/marže, časové výkazy,
materiály a fakturace.

Pravidla:
- `admin` a `work` náklady se NIKDY nesčítají do jednoho sloupce — rozlišení
  kind zůstává celou cestou (RateCard.kind, TimeEntry.kind, real_admin_/work_minutes).
- Marže se čte z číselníku `settings` (key=margin, default 0.30); prodní cena
  kroku = náklad × (1 + margin).
- Fakturace: posouzeni 2 500 Kč vzniká hookem (M2) při „pokračujeme" a sleva
  −2 500 Kč při podpisu SoD; kontrolní součet = 0 (platba jen jednou).
"""

import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .storage import (InvoiceItem, Material, PipelineStep, Project,
                      ProjectMaterial, ProjectStep, RateCard, Setting,
                      TimeEntry, User)

DEFAULT_MARGIN = 0.30
DEFAULT_RATE = 500.0


def _margin(db) -> float:
    row = db.query(Setting).filter(Setting.key == "margin").first()
    if row is None:
        return DEFAULT_MARGIN
    try:
        return float(row.value)
    except Exception:
        return DEFAULT_MARGIN


def _rate(rate_cards, role, kind, default=DEFAULT_RATE):
    for r in rate_cards:
        if r.role == role and r.kind == kind and r.active:
            return float(r.rate_czk_h)
    return default


# ---------- M4.1 kalkulace ----------

def calc_step_cost(step, rate_cards, margin=DEFAULT_MARGIN) -> dict:
    """Náklad a doporučená prodejní cena kroku (est.* minuty)."""
    admin_min = float(step.est_admin_minutes or 0)
    work_min = float(step.est_work_minutes or 0)
    admin_rate = _rate(rate_cards, step.admin_rate_role or "sales", "admin")
    work_rate = _rate(rate_cards, step.work_rate_role or "electrician", "work")
    admin_cost = admin_min / 60 * admin_rate
    work_cost = work_min / 60 * work_rate
    total = admin_cost + work_cost
    return {
        "admin_minutes": int(admin_min),
        "admin_cost": round(admin_cost, 2),
        "work_minutes": int(work_min),
        "work_cost": round(work_cost, 2),
        "total_cost": round(total, 2),
        "sell_recommended": round(total * (1 + margin), 2),
    }


def project_economy(db, project_id: int) -> dict:
    """Ekonomika projektu: plán (est_*) vs skutečnost (real_* / time_entries)."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(404, "Projekt nenalezen")
    rate_cards = db.query(RateCard).filter(RateCard.active.is_(True)).all()
    margin = _margin(db)

    plan = {"admin_minutes": 0, "admin_cost": 0.0,
            "work_minutes": 0, "work_cost": 0.0, "total_cost": 0.0}
    actual = {"admin_minutes": 0, "admin_cost": 0.0,
              "work_minutes": 0, "work_cost": 0.0, "total_cost": 0.0}

    steps = db.query(ProjectStep).filter(ProjectStep.project_id == project_id).all()
    for pps in steps:
        s = db.query(PipelineStep).filter(PipelineStep.id == pps.step_id).first()
        if s is None:
            continue
        c = calc_step_cost(s, rate_cards, margin=margin)
        for k in ("admin_minutes", "admin_cost", "work_minutes", "work_cost"):
            plan[k] += c[k]

        a_rate = _rate(rate_cards, s.admin_rate_role or "sales", "admin")
        w_rate = _rate(rate_cards, s.work_rate_role or "electrician", "work")
        a_min = float(pps.real_admin_minutes or 0)
        w_min = float(pps.real_work_minutes or 0)
        actual["admin_minutes"] += a_min
        actual["admin_cost"] += a_min / 60 * a_rate
        actual["work_minutes"] += w_min
        actual["work_cost"] += w_min / 60 * w_rate

    for d in (plan, actual):
        d["total_cost"] = round(d["admin_cost"] + d["work_cost"], 2)

    return {
        "plan": plan,
        "actual": {k: round(v, 2) if k.endswith("cost") else int(v) for k, v in actual.items()},
        "margin": margin,
        "sell": round(plan["total_cost"] * (1 + margin), 2),
        "sell_actual": round(actual["total_cost"] * (1 + margin), 2),
    }


# ---------- M4.2 časové výkazy ----------

def add_time_entry(db, project, step, user, minutes, kind="admin",
                   work_date=None, note=None) -> TimeEntry:
    if minutes <= 0:
        raise HTTPException(400, "minutes musí být větší než 0")
    if kind not in ("admin", "work"):
        raise HTTPException(400, "kind musí být 'admin' nebo 'work'")

    if step is None:
        if not (user.has_role("admin") or user.has_role("antelon")):
            raise HTTPException(403, "Výkaz bez kroku umí jen admin/antelon")
    else:
        s = db.query(PipelineStep).filter(PipelineStep.id == step.step_id).first()
        allowed = json.loads(s.allowed_roles_json) if s and s.allowed_roles_json else []
        ok = (user.has_role("admin") or user.has_role("antelon")) or \
             (allowed and any(user.has_role(r) for r in allowed))
        if not ok:
            raise HTTPException(403, "Nemáte oprávnění zapisovat čas na tento krok")

    te = TimeEntry(project_id=project.id, step_id=step.id if step else None,
                   user_id=user.id, minutes=minutes, work_date=work_date,
                   kind=kind, note=note)
    db.add(te)
    if step is not None:
        if kind == "admin":
            step.real_admin_minutes = (step.real_admin_minutes or 0) + minutes
        else:
            step.real_work_minutes = (step.real_work_minutes or 0) + minutes
    project.updated_at = datetime.utcnow()
    db.flush()
    return te


def time_summary(db, project_id: int) -> dict:
    rows = db.query(TimeEntry).filter(TimeEntry.project_id == project_id).all()
    by_user, by_step, by_type = {}, {}, {}
    total = 0
    for te in rows:
        total += te.minutes
        u = by_user.setdefault(str(te.user_id), {"user_id": te.user_id, "minutes": 0, "count": 0})
        u["minutes"] += te.minutes
        u["count"] += 1
        st = by_step.setdefault(str(te.step_id or "general"),
                                {"step_id": te.step_id, "minutes": 0, "count": 0})
        st["minutes"] += te.minutes
        st["count"] += 1
        t = by_type.setdefault(te.kind, {"kind": te.kind, "minutes": 0, "count": 0})
        t["minutes"] += te.minutes
        t["count"] += 1
    return {"by_user": by_user, "by_step": by_step, "by_type": by_type,
            "total_minutes": total}


def monteri_entries(db, from_d=None, to_d=None) -> list:
    q = db.query(TimeEntry).filter(TimeEntry.project_id.isnot(None))
    if from_d:
        q = q.filter(TimeEntry.work_date >= from_d)
    if to_d:
        q = q.filter(TimeEntry.work_date <= to_d)
    rows = []
    for te in q.order_by(TimeEntry.work_date, TimeEntry.id).all():
        user = db.query(User).filter(User.id == te.user_id).first()
        project = db.query(Project).filter(Project.id == te.project_id).first()
        step_name = None
        if te.step_id:
            row = (db.query(ProjectStep, PipelineStep)
                   .join(PipelineStep, ProjectStep.step_id == PipelineStep.id)
                   .filter(ProjectStep.id == te.step_id).first())
            if row:
                step_name = row[1].name
        rows.append({
            "user": user.email if user else "",
            "project": project.name if project else "",
            "step": step_name or "",
            "date": te.work_date.isoformat() if te.work_date else "",
            "minutes": te.minutes,
            "kind": te.kind,
            "note": te.note or "",
        })
    return rows


# ---------- M4.3 materiály ----------

def add_project_material(db, project, material, qty=1.0, lane="plan",
                         step_id=None, price_snapshot=None) -> ProjectMaterial:
    if lane not in ("plan", "order", "issue", "actual"):
        raise HTTPException(400, "lane musí být plan|order|issue|actual")
    if price_snapshot is None:
        price_snapshot = material.price
    pm = ProjectMaterial(
        project_id=project.id, material_id=material.id,
        price_snapshot=price_snapshot,
        qty_planned=qty if lane != "actual" else 0,
        qty_actual=qty if lane == "actual" else 0,
        lane=lane, step_id=step_id)
    db.add(pm)
    project.updated_at = datetime.utcnow()
    db.flush()
    return pm


def material_balance(db, project_id: int) -> list:
    rows = (db.query(ProjectMaterial, Material)
            .join(Material, ProjectMaterial.material_id == Material.id)
            .filter(ProjectMaterial.project_id == project_id)
            .order_by(Material.code).all())
    agg = {}
    for pm, m in rows:
        r = agg.setdefault(m.id, {
            "material_id": m.id, "code": m.code, "name": m.name, "unit": m.unit,
            "price": m.price, "plan_qty": 0.0, "order_qty": 0.0,
            "issue_qty": 0.0, "actual_qty": 0.0, "total_plan_czk": 0.0})
        if pm.lane == "actual":
            r["actual_qty"] += float(pm.qty_actual or 0)
        else:
            r[f"{pm.lane}_qty"] += float(pm.qty_planned or 0)
    for r in agg.values():
        r["total_plan_czk"] = round(r["plan_qty"] * r["price"], 2)
    return list(agg.values())


# ---------- M4.4 fakturace ----------

def add_invoice_item(db, project, doc_type, description=None, amount_czk=0.0,
                     step=None) -> InvoiceItem:
    if doc_type not in ("posouzeni", "zaloha", "final", "final_discount"):
        raise HTTPException(400, f"Neplatný doc_type {doc_type!r}")
    inv = InvoiceItem(project_id=project.id, step_id=step.id if step else None,
                      doc_type=doc_type, description=description,
                      amount_czk=amount_czk, status="draft")
    db.add(inv)
    db.flush()
    return inv


def issue_invoice(db, inv: InvoiceItem, user) -> InvoiceItem:
    if inv.status == "issued":
        raise HTTPException(400, "Faktura už byla vystavena")
    if inv.doc_number is None:
        seq = db.query(InvoiceItem).filter(
            InvoiceItem.project_id == inv.project_id,
            InvoiceItem.doc_number.isnot(None)).count() + 1
        inv.doc_number = f"inv-{inv.project_id}-{seq}"
    inv.status = "issued"
    db.flush()
    return inv