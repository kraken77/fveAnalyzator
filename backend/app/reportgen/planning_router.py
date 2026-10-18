"""API pro plánování montáže a elektro (etapa 1 — backend).

Endpointy:
- GET /api/v1/planning/overview — přehled plánů (interní role)
- POST /api/v1/planning/simulate — what-if simulace (interní role)
- CRUD /api/v1/planning/crews — správa četa (admin/antelon)
"""
import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .auth import get_current_user, is_internal_user, require_roles
from .cz_calendar import holidays_between
from .planning import Crew, Plan, build_plan_input, schedule
from .storage import WorkCrew, get_db

router = APIRouter(prefix="/api/v1/planning", tags=["planovani"])


# ======================== Pydantic modely ========================


class SimulateInput(BaseModel):
    add_crews: dict[str, int] = {}


class WorkCrewIn(BaseModel):
    name: str
    work_type: str
    available_from: str       # ISO date
    available_to: str         # ISO date
    work_days: list[str] = ["po", "ut", "st", "ct", "pa"]
    absent_dates: list[str] = []
    active: bool = True


class WorkCrewUpdate(BaseModel):
    name: str | None = None
    work_type: str | None = None
    available_from: str | None = None
    available_to: str | None = None
    work_days: list[str] | None = None
    absent_dates: list[str] | None = None
    active: bool | None = None


def _plan_to_dict(plan: Plan, projects_meta: list[dict]) -> dict:
    """Převede Plan na slovník pro JSON odpověď."""
    items = []
    for p in plan.items:
        items.append({
            "project_id": p.project_id,
            "project_name": p.project_name,
            "step_code": p.step_code,
            "step_name": p.step_name,
            "work_type": p.work_type,
            "kind": p.kind,
            "duration_days": p.duration_days,
            "start": p.start.isoformat() if p.start else None,
            "end": p.end.isoformat() if p.end else None,
            "crew_name": p.crew_name,
        })

    projects = []
    for pm in plan.projects:
        projects.append({
            "id": pm.id,
            "name": pm.name,
            "kind": pm.kind,
            "lead_age_days": next(
                (m["lead_age_days"] for m in projects_meta if m["id"] == pm.id), 0),
            "reservation_expires": next(
                (m.get("reservation_expires") for m in projects_meta if m["id"] == pm.id),
                None),
            "done_date": pm.done_date.isoformat() if pm.done_date else None,
            "sod_date": next(
                (m.get("sod_date") for m in projects_meta if m["id"] == pm.id),
                None),
        })

    return {
        "items": items,
        "projects": projects,
        "makespan": plan.makespan.isoformat() if plan.makespan else None,
    }


def _crew_dict(c: WorkCrew) -> dict:
    """Četa → JSON (work_days/absent_dates jako seznamy)."""
    return {
        "id": c.id,
        "name": c.name,
        "work_type": c.work_type,
        "available_from": c.available_from.isoformat() if c.available_from else None,
        "available_to": c.available_to.isoformat() if c.available_to else None,
        "work_days": json.loads(c.work_days_json) if c.work_days_json
        else ["po", "ut", "st", "ct", "pa"],
        "absent_dates": json.loads(c.absent_dates_json) if c.absent_dates_json else [],
        "active": c.active,
    }


# ======================== Overview ========================


@router.get("/overview")
def planning_overview(
    from_date: str = Query(..., alias="from"),
    to_date: str = Query(..., alias="to"),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Přehled plánů — filmy + rezervace s termíny.

    Interní role (admin, antelon, sales, ...); zákazník → 403.
    """
    if not is_internal_user(user):
        raise HTTPException(403, "Přístup pouze pro interní uživatele")

    try:
        from_dt = date.fromisoformat(from_date)
        to_dt = date.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(422, f"Neplatné datum: from={from_date!r} to={to_date!r}")

    if from_dt > to_dt:
        raise HTTPException(422, "from musí být ≤ to")

    # Plán se vždy kotví na reálném „dnes“ — from/to je jen rozsah zobrazení.
    today = date.today()
    items, crews, calendar_info, projects_meta = build_plan_input(db, today)
    plan = schedule(items, crews, today)

    overview = _plan_to_dict(plan, projects_meta)
    overview["today"] = today.isoformat()
    overview["holidays_in_range"] = [d.isoformat() for d in holidays_between(from_dt, to_dt)]
    overview["ttl_days"] = calendar_info["ttl_days"]
    overview["crews"] = [_crew_dict(c) for c in db.query(WorkCrew).order_by(WorkCrew.id).all()]
    return overview


# ======================== Simulate ========================


@router.post("/simulate")
def planning_simulate(
    data: SimulateInput,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """What-if simulace: přidá virtuální čety k plánu.

    Dodatečné čety = kopie dostupnosti první aktivní čtety daného typu
    (název „Montáž +1"); pokud typ neexistuje, okno today..today+180 Po–Pá.
    """
    if not is_internal_user(user):
        raise HTTPException(403, "Přístup pouze pro interní uživatele")

    today = date.today()
    items, base_crews, calendar_info, projects_meta = build_plan_input(db, today)

    # Přidej virtuální čety
    all_crews = list(base_crews)
    for work_type, count in data.add_crews.items():
        existing = [c for c in base_crews if c.work_type == work_type]
        base_name = existing[0].name if existing else work_type
        base_from = existing[0].available_from if existing else today
        base_to = existing[0].available_to if existing else today + timedelta(days=180)
        base_work_days = existing[0].work_days if existing else frozenset({0, 1, 2, 3, 4})

        for i in range(count):
            all_crews.append(Crew(
                name=f"{base_name} +{i + 1}",
                work_type=work_type,
                available_from=base_from,
                available_to=base_to,
                work_days=base_work_days,
                absent=frozenset(),
            ))

    plan = schedule(items, all_crews, today)
    return _plan_to_dict(plan, projects_meta)


# ======================== Crews CRUD ========================


@router.get("/crews")
def list_crews(user=Depends(require_roles("admin", "antelon")),
               db: Session = Depends(get_db)):
    """Seznam pracovních četa."""
    rows = db.query(WorkCrew).order_by(WorkCrew.id).all()
    return [_crew_dict(c) for c in rows]


@router.post("/crews")
def create_crew(data: WorkCrewIn, user=Depends(require_roles("admin", "antelon")),
                db: Session = Depends(get_db)):
    """Vytvořit novou pracovní četu."""
    try:
        from_d = date.fromisoformat(data.available_from)
        to_d = date.fromisoformat(data.available_to)
    except ValueError:
        raise HTTPException(422, "Neplatné datum v available_from/available_to")

    absent = frozenset()
    if data.absent_dates:
        try:
            absent = frozenset(date.fromisoformat(d) for d in data.absent_dates)
        except ValueError:
            raise HTTPException(422, "Neplatné datum v absent_dates")

    crew = WorkCrew(
        name=data.name,
        work_type=data.work_type,
        available_from=from_d,
        available_to=to_d,
        work_days_json=json.dumps(data.work_days),
        absent_dates_json=json.dumps(data.absent_dates),
        active=data.active,
    )
    db.add(crew)
    db.commit()
    db.refresh(crew)
    return _crew_dict(crew)


@router.put("/crews/{crew_id}")
def update_crew(crew_id: int, data: WorkCrewUpdate,
                user=Depends(require_roles("admin", "antelon")),
                db: Session = Depends(get_db)):
    """Upravit pracovní četu."""
    crew = db.query(WorkCrew).filter(WorkCrew.id == crew_id).first()
    if not crew:
        raise HTTPException(404, "Četa nenalezena")

    if data.name is not None:
        crew.name = data.name
    if data.work_type is not None:
        crew.work_type = data.work_type
    if data.available_from is not None:
        crew.available_from = date.fromisoformat(data.available_from)
    if data.available_to is not None:
        crew.available_to = date.fromisoformat(data.available_to)
    if data.work_days is not None:
        crew.work_days_json = json.dumps(data.work_days)
    if data.absent_dates is not None:
        crew.absent_dates_json = json.dumps(data.absent_dates)
    if data.active is not None:
        crew.active = data.active

    db.commit()
    db.refresh(crew)
    return _crew_dict(crew)
