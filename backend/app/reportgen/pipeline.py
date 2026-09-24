"""Workflow engine dispečinku (M2).

Stavový model per `state_model` kroku (pipeline_steps):
  simple:   not_started -> planned -> in_progress -> done   (akce: plan, begin, complete)
  contract: not_started -> sent -> signed                   (akce: plan, sent, sign)
  ai:       not_started -> in_progress -> done              (complete = schválení výstupu, M3)

Speciální admin akce (jen admin): skip -> skipped, revert -> not_started|planned,
reassign (změní assigned_user_id), cancel -> cancelled, add_step/remove_step (přes API).

Brány: sekvenční kroky se vážou na předchozí blok (jednotlivý krok nebo celá
paralelní skupina); kroky v paralelní skupině se vážou jen na první krok skupiny.
Podmíněné kroky (condition nesplněna) jsou skryté a z bran se vynechávají.
"""

import json
import unicodedata
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .storage import (InvoiceItem, Notification, PipelineStep, Project,
                      ProjectPipeline, ProjectStep, ProjectUser, StepEvent,
                      User)

# Stav považovaný za „hotový/splněný" pro brány.
SATISFIED = {"done", "signed", "skipped", "not_applicable"}

# Admin zásahy mimo běžné brány a role.
ADMIN_ACTIONS = {"skip", "revert", "reassign", "cancel"}


def _now():
    return datetime.utcnow()


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def _crash(msg):
    raise HTTPException(403, msg)


# ---------- podmínky ----------

def _param_map(project, prefix):
    raw = None
    if prefix == "fve_params":
        raw = project.fve_params_json
    elif prefix == "antelon_params":
        raw = project.antelon_params_json
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _condition_met(db, step: PipelineStep, project: Project) -> bool:
    """Vyhodnotí condition_json kroku. Nepřítomná podmínka = splněno.
    project_param_in: {fve_params.dotace: [ano]} — tečka = cesta.
    requires_step: [kody] — kroky instance musí být hotové."""
    if not step.condition_json:
        return True
    try:
        cond = json.loads(step.condition_json)
    except Exception:
        return True
    if not isinstance(cond, dict):
        return True

    for key, spec in cond.items():
        if key == "project_param_in":
            for path, values in spec.items():
                parts = path.split(".")
                prefix, keys = parts[0], parts[1:]
                m = _param_map(project, prefix)
                cur = m
                for k in keys:
                    if not isinstance(cur, dict) or k not in cur:
                        return False
                    cur = cur[k]
                found = cur if isinstance(cur, list) else [cur]
                if not any(_norm(v) in [_norm(x) for x in values] for v in found):
                    return False
        elif key == "requires_step":
            for code in spec:
                ps = _instance_step(db, project.id, code)
                if ps is None or ps.status not in SATISFIED:
                    return False
    return True


def _instance_step(db, project_id, code):
    return (db.query(ProjectStep)
            .join(PipelineStep, ProjectStep.step_id == PipelineStep.id)
            .filter(ProjectStep.project_id == project_id,
                    PipelineStep.code == code)
            .first())


# ---------- brány ----------

def _ordered_items(db, project_id, visible_only=True):
    """Seznam (ProjectStep, PipelineStep) projektu řazený dle order.
    visible_only: vynechá kroky, jejichž podmínka není splněna."""
    rows = (db.query(ProjectStep, PipelineStep)
            .join(PipelineStep, ProjectStep.step_id == PipelineStep.id)
            .filter(ProjectStep.project_id == project_id)
            .order_by(PipelineStep.order).all())
    project = db.query(Project).filter(Project.id == project_id).first()
    out = []
    for ps, s in rows:
        if visible_only and not _condition_met(db, s, project):
            continue
        out.append((ps, s))
    return out


def _blocks(items):
    """Rozdělí viditelné kroky na bloky: souvislý běh stejné parallel_group
    tvoří jeden blok; krok bez group je samostatný blok."""
    blocks = []
    for item in items:
        g = item[1].parallel_group
        if blocks and g is not None and blocks[-1]["group"] == g:
            blocks[-1]["items"].append(item)
        elif g is not None and blocks and blocks[-1]["group"] == g:
            blocks[-1]["items"].append(item)
        else:
            blocks.append({"group": g, "items": [item]})
    return blocks


def _prev_block_code_list(blocks, idx):
    prev = blocks[idx - 1]["items"] if idx > 0 else []
    return [it[1] for it in prev]


def _gate_items(db, all_items, target):
    """Vrátí PipelineStep objekty, které musí být splněny před targetem."""
    ps_t, s_t = target
    blocks = _blocks(all_items)
    idx = next(i for i, b in enumerate(blocks)
               if any(it[0].id == ps_t.id for it in b["items"]))
    g = s_t.parallel_group

    if g is None:
        return _prev_block_code_list(blocks, idx)

    # krok v paralelní skupině
    first = min(blocks[idx]["items"], key=lambda it: it[1].order)
    if first[0].id == ps_t.id:
        # první člen skupiny -> brána = předchozí blok
        return _prev_block_code_list(blocks, idx)
    # ostatní členové -> brána = první člen skupiny
    return [first[1]]


def _blockers(db, project, target_items):
    """Názvy nesplněných povinných předchozích kroků."""
    names = []
    for s in target_items:
        ps = _instance_step(db, project.id, s.code)
        if ps is None or ps.status not in SATISFIED:
            names.append(s.name)
    return names


def _check_gate(db, project, target):
    """Vyhodí 403, pokud povinné předchozí kroky nejsou splněné."""
    all_items = _ordered_items(db, project.id)
    gate = _gate_items(db, all_items, target)
    bad = _blockers(db, project, gate)
    if bad:
        names = ", ".join(sorted(set(bad)))
        _crash(f"Nelze začít — nejsou splněny předchozí potřebné stavy: {names}")


# ---------- stavy a akce ----------

def _new_status(ps: ProjectStep, s: PipelineStep, action: str, to_status=None):
    """Vrátí nový status pro akci, nebo None (akce není přípustná)."""
    sm = s.state_model or "simple"
    cur = ps.status

    if action == "plan":
        return "planned" if cur in ("not_started", "planned") else None
    if action == "begin":
        return "in_progress" if cur in ("not_started", "planned") else None
    if action in ("assign", "reassign"):
        return cur
    # ai krok: complete = schválení výstupu (M3 mu předchází -> in_progress)
    if action == "complete":
        if sm == "contract":
            return None
        return "done" if cur == "in_progress" else None
    if action == "sent":
        return "sent" if sm == "contract" and cur in ("not_started", "planned") else None
    if action == "sign":
        return "signed" if sm == "contract" and cur == "sent" else None
    if action == "skip":
        return "skipped" if cur not in SATISFIED else None
    if action == "cancel":
        return "cancelled" if cur not in ("cancelled",) else None
    if action == "revert":
        return to_status if to_status in ("not_started", "planned", "in_progress") else "not_started"
    return None


def _allowed_roles_of(s: PipelineStep):
    try:
        return json.loads(s.allowed_roles_json) if s.allowed_roles_json else []
    except Exception:
        return []


def _check_role(db, ps, s, action, user):
    if action in ADMIN_ACTIONS:
        if not user.has_role("admin"):
            _crash("Pouze admin může provádět admin zásahy")
        return
    roles = _allowed_roles_of(s)
    if roles and not any(user.has_role(r) for r in roles):
        _crash("Nemáte oprávnění pro tento krok")


def _check_assign_authority(user):
    if not any(user.has_role(r) for r in ("admin", "antelon")):
        _crash("Přiřazení uživatele umí jen admin/antelon")


# ---------- notifikace ----------

def notify(db, user_id, text, project_id=None):
    db.add(Notification(user_id=user_id, project_id=project_id, text=text))


def _team_user_ids(db, project):
    """admin + antelon + uživatelé propojení s projektem/owner."""
    ids = set()
    for u in db.query(User).all():
        if u.has_role("admin") or u.has_role("antelon"):
            ids.add(u.id)
    linked = [r[0] for r in db.query(ProjectUser.user_id)
              .filter(ProjectUser.project_id == project.id).all()]
    ids.update(linked)
    if project.owner_id:
        ids.add(project.owner_id)
    return ids


def _notify_team(db, text, project):
    for uid in _team_user_ids(db, project):
        notify(db, uid, text, project.id)


# ---------- hooky (M2.4) ----------

def _is_rejected_note(note, result):
    if result is not None and _norm(result) == "zamitnuto":
        return True
    return bool(note) and _norm(note).startswith("zamitnuto") or bool(note) and _norm(note).startswith("zamítnuto")


def _hook_invoice_2500(db, project, ps, s, user, result):
    note = ps.note or ""
    if _is_rejected_note(note, result):
        project.status = "cancelled"
        _notify_team(db, f"Zakázka {project.name} byla zamítnuta zákazníkem", project)
        return
    exists = db.query(InvoiceItem).filter(
        InvoiceItem.doc_type == "posouzeni",
        InvoiceItem.step_id == ps.id).first()
    if not exists:
        db.add(InvoiceItem(project_id=project.id, step_id=ps.id,
                           doc_type="posouzeni",
                           description="Posouzení realizace zakázky",
                           amount_czk=2500, status="draft"))
        _notify_team(db, f"Vystavena faktura 2 500 Kč (posouzení) — {project.name}", project)


def _hook_sod_signed(db, project, ps, s, user, result):
    exists = db.query(InvoiceItem).filter(
        InvoiceItem.doc_type == "final_discount",
        InvoiceItem.step_id == ps.id).first()
    if not exists:
        db.add(InvoiceItem(project_id=project.id, step_id=ps.id,
                           doc_type="final_discount",
                           description="Sleva - Posouzení realizace zakázky (2 500 Kč)",
                           amount_czk=-2500, status="draft"))
    _notify_team(db, f"Otevřena realizační větev — {project.name}", project)


def _hook_sop_signed(db, project, ps, s, user, result):
    _notify_team(db, f"Otevřena větev přetoků — {project.name}", project)


def _hook_elektro_done(db, project, ps, s, user, result):
    _notify_team(db, f"Otevřena větev revize — {project.name}", project)


HOOKS = {
    "invoice_2500": _hook_invoice_2500,
    "sod_signed": _hook_sod_signed,
    "sop_signed": _hook_sop_signed,
    "elektro_done": _hook_elektro_done,
}


def _run_hooks(db, project, ps, s, user, result=None):
    if not s.auto_hook:
        return
    hook = HOOKS.get(s.auto_hook)
    if hook:
        hook(db, project, ps, s, user, result)


def _notify_waiting_for_customer(db, project, ps, s):
    _notify_team(db, f"Krok „{s.name}“ čeká na zákazníka — {project.name}", project)


# ---------- hlavní přechod ----------

def can_transition(db, project_step: ProjectStep, action: str, user: User,
                   project: Project):
    """(ok, blockers, error_msg) — kontrola stavu, role a brány."""
    s = db.query(PipelineStep).filter(PipelineStep.id == project_step.step_id).first()
    if s is None:
        return False, [], "Krok šablony nenalezen"

    new_status = _new_status(project_step, s, action)
    if new_status is None:
        return False, [], f"Akce {action!r} není přípustná ve stavu {project_step.status!r}"

    if action in ADMIN_ACTIONS:
        if not user.has_role("admin"):
            return False, [], "Pouze admin může provádět admin zásahy"
        return True, [], None

    roles = _allowed_roles_of(s)
    if roles and not any(user.has_role(r) for r in roles):
        return False, [], "Nemáte oprávnění pro tento krok"

    if action in ("assign",) and not any(user.has_role(r) for r in ("admin", "antelon")):
        return False, [], "Přiřazení uživatele umí jen admin/antelon"

    # brána (jen pro plan/begin/complete/sent/sign)
    if action in ("plan", "begin", "complete", "sent", "sign"):
        try:
            _check_gate(db, project, (project_step, s))
        except HTTPException as e:
            return False, [], str(e.detail)

    return True, [], None


def transition(db, project: Project, project_step: ProjectStep, action: str,
               user: User, note=None, plan_date=None, assigned_user_id=None,
               to_status=None, result=None):
    """Provede přechod kroku. Po complete/sign spouští hooky. Commit venku."""
    if project_step.project_id != project.id:
        _crash("Krok nepatří k projektu")
    if user is None:
        _crash("Neautorizováno")

    s = db.query(PipelineStep).filter(PipelineStep.id == project_step.step_id).first()
    if s is None:
        raise HTTPException(404, "Krok šablony nenalezen")

    ok, blockers, err = can_transition(db, project_step, action, user, project)
    if not ok:
        _crash(err or "Přechod není povolen")

    from_status = project_step.status
    new_status = _new_status(project_step, s, action, to_status)

    if action == "assign":
        if assigned_user_id is not None:
            project_step.assigned_user_id = assigned_user_id
    elif action == "plan":
        if plan_date is not None:
            project_step.plan_date = plan_date
        if assigned_user_id is not None:
            _check_assign_authority(user)
            project_step.assigned_user_id = assigned_user_id
        if from_status == "not_started":
            new_status = "planned"
    elif action == "begin":
        project_step.started_at = project_step.started_at or _now()
    elif action == "reassign":
        project_step.assigned_user_id = assigned_user_id
    elif action == "complete":
        project_step.done_at = _now()
    elif action in ("sent", "sign"):
        if action == "sign":
            project_step.done_at = _now()
    elif action == "skip":
        project_step.note = note or project_step.note

    project_step.status = new_status
    if note is not None:
        _join_note(project_step, note)
    project.updated_at = _now()

    db.add(StepEvent(project_id=project.id, step_id=project_step.id, action=action,
                     from_status=from_status, to_status=new_status,
                     user_id=user.id, at=_now(), note=note))

    if action == "plan":
        if project_step.assigned_user_id:
            text = f"Krok „{s.name}“ naplánován"
            if plan_date:
                text += f" na {plan_date.strftime('%d.%m.%Y')}"
            notify(db, project_step.assigned_user_id, text, project.id)
    elif action == "sent":
        _notify_waiting_for_customer(db, project, project_step, s)

    if action in ("complete", "sign"):
        _run_hooks(db, project, project_step, s, user, result=result)
        if s.state_model == "ai":
            # sign je pro ai kroky nepřípustné — complete zde = vyřešeno uživatelem
            project_step.done_at = _now()

    db.flush()
    return project_step


def _join_note(ps: ProjectStep, note: str):
    if not note:
        return
    if ps.note:
        ps.note = ps.note + "; " + note
    else:
        ps.note = note


# ---------- pohled ----------

def _allowed_actions(db, ps: ProjectStep, s: PipelineStep, user: User):
    sm = s.state_model or "simple"
    cur = ps.status
    acts = []
    if sm == "contract":
        if cur in ("not_started", "planned"):
            acts += ["plan", "sent"]
        elif cur == "sent":
            acts += ["sign"]
    elif sm == "ai":
        if cur in ("not_started", "planned"):
            acts += ["plan", "begin", "run_ai"]
        elif cur == "in_progress":
            acts += ["complete"]
    else:
        if cur in ("not_started", "planned"):
            acts += ["plan", "begin"]
        elif cur == "planned":
            acts += ["begin"]
        elif cur == "in_progress":
            acts += ["complete"]
    if cur not in SATISFIED:
        acts += ["assign"]
    if user.has_role("admin") and cur not in SATISFIED and cur != "cancelled":
        acts += ["skip", "revert", "reassign", "cancel"]
    return acts


def _latest_ai(db, project_step_id):
    from .storage import PipelineAiResult
    ar = (db.query(PipelineAiResult)
          .filter(PipelineAiResult.step_id == project_step_id)
          .order_by(PipelineAiResult.id.desc()).first())
    if ar is None:
        return None
    try:
        out = json.loads(ar.output_json) if ar.output_json else {}
    except Exception:
        out = {}
    return {"id": ar.id, "status": ar.status, "kind": ar.kind, "output": out}


def get_pipeline_view(db, project_id: int, user: User = None):
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(404, "Projekt nenalezen")
    pp = db.query(ProjectPipeline).filter(ProjectPipeline.project_id == project_id).first()

    from .storage import PipelineTemplate
    template = None
    if pp:
        template = db.query(PipelineTemplate).filter(PipelineTemplate.id == pp.template_id).first()
        template = {"id": template.id, "code": template.code, "name": template.name,
                    "zakazka_type": template.zakazka_type, "version": template.version,
                    "active": template.active} if template else None

    items = _ordered_items(db, project_id, visible_only=False)
    steps = []
    for ps, s in items:
        hidden = not _condition_met(db, s, project)
        steps.append({
            "id": ps.id,
            "pipeline_step_id": s.id,
            "code": s.code,
            "name": s.name,
            "phase": s.phase,
            "order": s.order,
            "status": ps.status,
            "plan_date": ps.plan_date.isoformat() if ps.plan_date else None,
            "assigned_user_id": ps.assigned_user_id,
            "note": ps.note,
            "real_admin_minutes": ps.real_admin_minutes,
            "real_work_minutes": ps.real_work_minutes,
            "est_admin_minutes": s.est_admin_minutes,
            "est_work_minutes": s.est_work_minutes,
            "state_model": s.state_model or "simple",
            "hidden": hidden,
            "condition": json.loads(s.condition_json) if s.condition_json else None,
            "auto_hook": s.auto_hook,
            "parallel_group": s.parallel_group,
            "allowed_roles": _allowed_roles_of(s),
            "ai": _latest_ai(db, ps.id),
            "can": _allowed_actions(db, ps, s, user) if user else [],
        })

    events = []
    ev_rows = (db.query(StepEvent, PipelineStep)
               .join(ProjectStep, StepEvent.step_id == ProjectStep.id)
               .join(PipelineStep, ProjectStep.step_id == PipelineStep.id)
               .filter(StepEvent.project_id == project_id)
               .order_by(StepEvent.id.desc()).limit(200).all())
    for ev, s in ev_rows:
        events.append({
            "id": ev.id, "action": ev.action, "step": s.name, "step_code": s.code,
            "from_status": ev.from_status, "to_status": ev.to_status,
            "user_id": ev.user_id, "at": ev.at.isoformat() if ev.at else None,
            "note": ev.note,
        })

    groups = []
    by_group = {}
    for st in steps:
        g = st.get("parallel_group")
        if not g:
            continue
        by_group.setdefault(g, []).append(st)
    for g, sts in by_group.items():
        done = all(st["status"] in SATISFIED for st in sts if not st["hidden"])
        groups.append({"group": g, "steps": [st["id"] for st in sts], "done": done})

    return {
        "project": {"id": project.id, "name": project.name,
                    "customer_name": project.customer_name, "type": project.type,
                    "status": project.status, "tech": project.tech,
                    "owner_id": project.owner_id},
        "template": template,
        "steps": steps,
        "events": events,
        "groups": groups,
    }