"""AI kroky pipeline (M3) — run_ai, review_ai, auto-řetězec.

Každý AI krok šablony má state_model='ai' a kód mapovaný na `kind`:
  navrh_fve        -> fve_size          (PVGIS + ekonomika)
  kapacita_baterie -> battery           (varianty 5/10/15 kWh)
  dotacni_uspora   -> subsidy           (NZÚ 2026 C.3)
  moznost_pujcky   -> loan              (bezúročná půjčka)
  nabidka_podrobna -> offer_pdf         (PDF nabídky, manual trigger)
  vizualizace      -> visualization_pdf (placeholder PDF, manual trigger)

run_ai posune krok do in_progress a uloží draft výsledek; review_ai schválí
(done) nebo zamítne (krok zůstává in_progress). Fyzické výpočty jsou
mocking-friendly — volají se přes `app.fve_analysis` (modul načítaný lazy).
"""

import json
import os
import sys
from datetime import datetime

from fastapi import HTTPException

from .storage import (PdfVersion, PipelineAiResult, PipelineStep, Project,
                      ProjectStep, StepEvent)

KIND_BY_CODE = {
    "navrh_fve": "fve_size",
    "kapacita_baterie": "battery",
    "dotacni_uspora": "subsidy",
    "moznost_pujcky": "loan",
    "nabidka_podrobna": "offer_pdf",
    "vizualizace": "visualization_pdf",
}

# Pořadí auto-řetězce po dokončení tech_posouzeni (hook ai_chain).
AI_CHAIN = ["navrh_fve", "kapacita_baterie", "dotacni_uspora", "moznost_pujcky"]


def _now():
    return datetime.utcnow()


def _import_fve():
    """Lazy import app.fve_analysis (cesta resolvovaná od backend/app).

    Voláme přímo výpočetní modul, ne `main.py`. Dřív tady byla vazba na
    `main.*` — legacy HTTP endpointy — což znamenalo kruhový import
    (main → reportgen.router → main) jen proto, že šlo dosáhnout na dvě
    funkce. Teď je `app.fve_analysis` jediné místo, kde analýza žije.
    """
    backend = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app import fve_analysis

    return fve_analysis


def _params(project, prefix):
    raw = getattr(project, f"{prefix}_json", None)
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _instance_step(db, project_id, code):
    return (db.query(ProjectStep)
            .join(PipelineStep, ProjectStep.step_id == PipelineStep.id)
            .filter(ProjectStep.project_id == project_id,
                    PipelineStep.code == code)
            .first())


def _latest_approved_output(db, project_id, code):
    ps = _instance_step(db, project_id, code)
    if ps is None:
        return None
    res = (db.query(PipelineAiResult)
           .filter(PipelineAiResult.step_id == ps.id,
                   PipelineAiResult.status == "approved")
           .order_by(PipelineAiResult.id.desc()).first())
    if res is None:
        return None
    try:
        return json.loads(res.output_json) or {}
    except Exception:
        return {}


def _kwp(db, project):
    out = _latest_approved_output(db, project.id, "navrh_fve")
    if out and out.get("kwp"):
        return float(out["kwp"])
    fve = _params(project, "fve_params")
    return float(fve.get("kwp") or 0)


def _battery(db, project):
    out = _latest_approved_output(db, project.id, "kapacita_baterie")
    if out and out.get("doporuceno_kwh"):
        return float(out["doporuceno_kwh"])
    fve = _params(project, "fve_params")
    for k in ("battery_capacity", "battery_kwh"):
        if fve.get(k):
            return float(fve[k])
    return 0.0


# ---------- handlery ----------

def _run_fve_size(db, project, user):
    fve = _params(project, "fve_params")
    fve_mod = _import_fve()
    keys = fve_mod.analysis_param_keys()
    valid = {k: v for k, v in fve.items() if k in keys}
    res = fve_mod.run_energy_analysis(valid)

    kwp = float(res.get("kwp") or valid.get("kwp") or 10)
    eb = res.get("energy_balance_kwh") or {}
    fb = res.get("financial_balance") or {}
    self_cons = float(eb.get("self_consumption") or 0)
    total = float(eb.get("total_consumption") or 0)
    investice = float(fve.get("investice_czk") or kwp * 45000)

    eco = fve_mod.run_economic_analysis({
        "annual_savings": float(fb.get("annual_savings_czk") or 0),
        "investment_cost": investice,
    })
    metrics = eco.get("metrics") or {}

    return {
        "kwp": kwp,
        "vyroba_kwh": round(self_cons + float(eb.get("grid_export") or 0), 2),
        "vlastni_spotreba_kwh": round(self_cons, 2),
        "samospotreba_pct": round(self_cons / total * 100, 1) if total else 0.0,
        "rocni_uspora_czk": fb.get("annual_savings_czk"),
        "investice_czk": investice,
        "npv_czk": metrics.get("npv_czk"),
        "roi_years": metrics.get("payback_years"),
        "sp500_srovnani": {
            "pv_reinvest_czk": metrics.get("final_pv_reinvest_gain_czk"),
            "sp500_net_czk": metrics.get("final_sp500_net_czk"),
        },
    }


def _run_battery(db, project, user):
    fve = _params(project, "fve_params")
    fve_mod = _import_fve()
    keys = fve_mod.analysis_param_keys()
    kwp = _kwp(db, project) or float(fve.get("kwp") or 10)
    variants = [5.0, 10.0, 15.0]
    rows = []
    for cap in variants:
        valid = {k: v for k, v in fve.items() if k in keys}
        valid["kwp"] = kwp
        valid["battery_capacity"] = cap
        res = fve_mod.run_energy_analysis(valid)
        eb = res.get("energy_balance_kwh") or {}
        fb = res.get("financial_balance") or {}
        self_cons = float(eb.get("self_consumption") or 0)
        total = float(eb.get("total_consumption") or 0)
        rows.append({
            "kwh": cap,
            "samospotreba_pct": round(self_cons / total * 100, 1) if total else 0.0,
            "samospotreba_kwh": round(self_cons, 2),
            "rocni_uspora_czk": fb.get("annual_savings_czk"),
        })
    best = max(rows, key=lambda r: r["samospotreba_pct"])
    return {"doporuceno_kwh": best["kwh"],
            "samospotreba_pct": best["samospotreba_pct"],
            "variants": rows}


def _run_subsidy(db, project, user):
    from .subsidy import compute_subsidy
    kwp = _kwp(db, project)
    bat = _battery(db, project)
    mode = "komplexni" if project.type in ("byt", "firma") else "dilci"
    sub = compute_subsidy(kwp, bat, mode)
    return {"castka_czk": sub["castka"], "kwp": kwp, "battery_kwh": bat,
            "sazby": sub["sazby"], "max": sub["limit"], "mode": mode,
            "podminky": sub["podminky"]}


def _run_loan(db, project, user):
    from .loan_rules import evaluate_loan
    fve = _params(project, "fve_params")
    sub = _run_subsidy(db, project, user)
    return evaluate_loan(fve, {"castka": sub["castka_czk"]})


def _save_pdf(db, project, template, pdf_bytes, user):
    pdf_dir = os.path.join("data", "pdfs")
    os.makedirs(pdf_dir, exist_ok=True)
    count = db.query(PdfVersion).filter(
        PdfVersion.project_id == project.id,
        PdfVersion.template == template).count()
    next_ver = count + 1
    file_path = os.path.join(pdf_dir, f"{template}_v{next_ver}.pdf")
    with open(file_path, "wb") as f:
        f.write(pdf_bytes)
    pv = PdfVersion(project_id=project.id, template=template, version=next_ver,
                    file_path=file_path,
                    params_snapshot_json=json.dumps(_params(project, "fve_params"),
                                                    ensure_ascii=False),
                    created_by=user.id)
    db.add(pv)
    db.flush()
    return pv


def _run_offer_pdf(db, project, user):
    fve = _params(project, "fve_params")
    fve_mod = _import_fve()
    keys = fve_mod.analysis_param_keys()
    valid = {k: v for k, v in fve.items() if k in keys}
    res = fve_mod.run_energy_analysis(valid)
    from app.reporting import ReportGenerator
    pdf_bytes = ReportGenerator().generate_energy_report(res)
    pv = _save_pdf(db, project, "energy", pdf_bytes, user)
    return {"pdf_version_id": pv.id, "template": "energy"}


def _run_visualization_pdf(db, project, user):
    """Placeholder vizualizace — minimální PDF (reportlab)."""
    from reportlab.pdfgen import canvas
    pdf_dir = os.path.join("data", "pdfs")
    os.makedirs(pdf_dir, exist_ok=True)
    count = db.query(PdfVersion).filter(
        PdfVersion.project_id == project.id,
        PdfVersion.template == "visualization").count()
    file_path = os.path.join(pdf_dir, f"visualization_v{count + 1}.pdf")
    c = canvas.Canvas(file_path)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(60, 780, f"Vizualizace projektu: {project.name}")
    c.setFont("Helvetica", 12)
    c.drawString(60, 750, "(placeholder — nahrazeno grafy a fotografiemi v M5)")
    c.save()
    pv = PdfVersion(project_id=project.id, template="visualization",
                    version=count + 1, file_path=file_path,
                    params_snapshot_json=json.dumps(_params(project, "fve_params"),
                                                    ensure_ascii=False),
                    created_by=user.id)
    db.add(pv)
    db.flush()
    return {"pdf_version_id": pv.id, "template": "visualization"}


HANDLERS = {
    "fve_size": _run_fve_size,
    "battery": _run_battery,
    "subsidy": _run_subsidy,
    "loan": _run_loan,
    "offer_pdf": _run_offer_pdf,
    "visualization_pdf": _run_visualization_pdf,
}


# ---------- run_ai / review_ai ----------

def run_ai(db, project, project_step, user, trigger="manual"):
    """Spustí AI krok: vytvoří draft výsledek a posune krok do in_progress."""
    s = db.query(PipelineStep).filter(PipelineStep.id == project_step.step_id).first()
    if s is None:
        raise HTTPException(404, "Krok šablony nenalezen")
    kind = KIND_BY_CODE.get(s.code)
    if not kind:
        raise HTTPException(400, f"Krok „{s.code}“ není AI krok")
    if project_step.status in ("done", "skipped", "cancelled"):
        raise HTTPException(400, "Krok je už dokončen")

    allowed = json.loads(s.allowed_roles_json) if s.allowed_roles_json else []
    if allowed and not any(user.has_role(r) for r in allowed):
        raise HTTPException(403, "Nemáte oprávnění pro tento krok")

    handler = HANDLERS[kind]
    try:
        out = handler(db, project, user)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"AI krok selhal: {e}")

    from_status = project_step.status
    project_step.status = "in_progress"
    if not project_step.started_at:
        project_step.started_at = _now()
    project.updated_at = _now()

    db.add(StepEvent(project_id=project.id, step_id=project_step.id,
                     action="ai_run", from_status=from_status,
                     to_status="in_progress", user_id=user.id, at=_now(),
                     note=f"AI {kind} spuštěno ({trigger})"))
    res = PipelineAiResult(
        project_id=project.id, step_id=project_step.id, kind=kind,
        input_json=json.dumps({"trigger": trigger, "code": s.code},
                              ensure_ascii=False),
        output_json=json.dumps(out, ensure_ascii=False),
        pdf_version_id=out.get("pdf_version_id"),
        status="draft", created_by=user.id)
    db.add(res)
    db.flush()
    return res


def _persist_approved(db, res, project):
    try:
        out = json.loads(res.output_json) or {}
    except Exception:
        return
    fve = json.loads(project.fve_params_json) if project.fve_params_json else {}
    changed = False
    if res.kind == "fve_size" and out.get("kwp"):
        fve["kwp"] = out["kwp"]
        changed = True
    if res.kind == "battery" and out.get("doporuceno_kwh"):
        fve["battery_capacity"] = out["doporuceno_kwh"]
        fve.setdefault("battery_kwh", out["doporuceno_kwh"])
        fve.setdefault("annual_consumption_mwh", out.get("samospotreba_kwh") or 0)
        changed = True
    if changed:
        project.fve_params_json = json.dumps(fve, ensure_ascii=False)


def review_ai(db, result_id, approved, user, note=None):
    """Schválí/zamítne draft AI výsledek. Schválení dokončí krok."""
    res = db.query(PipelineAiResult).filter(PipelineAiResult.id == result_id).first()
    if res is None:
        raise HTTPException(404, "Výsledek AI nenalezen")
    ps = db.query(ProjectStep).filter(ProjectStep.id == res.step_id).first()
    if ps is None:
        raise HTTPException(404, "Krok projektu nenalezen")
    project = db.query(Project).filter(Project.id == res.project_id).first()
    s = db.query(PipelineStep).filter(PipelineStep.id == ps.step_id).first()

    allowed = json.loads(s.allowed_roles_json) if s and s.allowed_roles_json else []
    if allowed and not any(user.has_role(r) for r in allowed):
        raise HTTPException(403, "Nemáte oprávnění pro tento krok")
    if res.status != "draft":
        raise HTTPException(400, "Výsledek už byl zpracován")

    res.status = "approved" if approved else "rejected"
    res.reviewed_by = user.id
    res.reviewed_at = _now()

    if approved:
        res.output_json = res.output_json  # zachováno
        ps.status = "done"
        ps.done_at = _now()
        _persist_approved(db, res, project)
        db.add(StepEvent(project_id=project.id, step_id=ps.id, action="done",
                         from_status="in_progress", to_status="done",
                         user_id=user.id, at=_now(),
                         note=note or "Schválen výstup AI"))
    else:
        db.add(StepEvent(project_id=project.id, step_id=ps.id, action="reject",
                         from_status="in_progress", to_status="in_progress",
                         user_id=user.id, at=_now(),
                         note=note or "Výstup AI zamítnut"))
        if note:
            ps.note = (ps.note + "; " + note) if ps.note else note

    project.updated_at = _now()
    db.flush()
    return res


def run_ai_chain(db, project, user):
    """Auto-řetězec po dokončení tech_posouzeni (hook ai_chain): spustí
    navrh_fve, kapacita_baterie, dotacni_uspora, moznost_pujcky (kroky,
    které jsou viditelné a nejsou spuštěné)."""
    from .pipeline import _condition_met
    items = (db.query(ProjectStep, PipelineStep)
             .join(PipelineStep, ProjectStep.step_id == PipelineStep.id)
             .filter(ProjectStep.project_id == project.id)
             .order_by(PipelineStep.order).all())
    for ps, s in items:
        if s.code not in AI_CHAIN:
            continue
        if ps.status in ("done", "in_progress", "skipped", "cancelled"):
            continue
        if not _condition_met(db, s, project):
            continue
        try:
            run_ai(db, project, ps, user, trigger="auto")
        except HTTPException as e:
            # Selhání jednoho auto-kroku neblokuje dokončení ručního kroku —
            # zapíše se warning event, krok zůstává in_progress (retry ručně).
            db.add(StepEvent(project_id=project.id, step_id=ps.id,
                             action="ai_chain_error", from_status=ps.status,
                             to_status=ps.status, user_id=user.id, at=_now(),
                             note=f"Auto-AI selhalo: {e.detail}"))