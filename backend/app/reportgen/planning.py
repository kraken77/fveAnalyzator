"""Scheduler pro plánování montáže a elektro (etapa 1 — backend).

Čistá funkce `schedule()` bez závislosti na DB ani FastAPI.
Jediná funkce se DB: `build_plan_input()`.
"""
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from .cz_calendar import is_cz_workday
from .storage import (PipelineStep, Project, ProjectPipeline, ProjectStep,
                      Setting, User, WorkCrew)

# ======================== Data model ========================


@dataclass(frozen=True)
class WorkItem:
    project_id: int
    project_name: str
    step_code: str
    step_name: str
    work_type: str
    duration_days: int   # >= 1
    kind: str            # "firm" | "reserve" | "expired"
    priority: Optional[date] = None  # film: SoD/created_at, rezervace: created_at


@dataclass(frozen=True)
class Crew:
    name: str
    work_type: str
    available_from: date
    available_to: date
    work_days: frozenset[int]   # weekday(), 0=Po
    absent: frozenset[date]


@dataclass
class PlanItem:
    project_id: int
    project_name: str
    step_code: str
    step_name: str
    work_type: str
    kind: str
    duration_days: int
    start: Optional[date] = None
    end: Optional[date] = None
    crew_name: Optional[str] = None


@dataclass
class ProjectMeta:
    id: int
    name: str
    kind: str        # "firm" | "reserve" | "expired"
    lead_age_days: int
    reservation_expires: Optional[date]
    done_date: Optional[date] = None
    sod_date: Optional[date] = None


@dataclass
class Plan:
    items: list[PlanItem]
    projects: list[ProjectMeta]
    makespan: Optional[date] = None


# ======================== Scheduler core ========================

_WORKDAY_MAP = {"po": 0, "ut": 1, "st": 2, "ct": 3, "pa": 4}


def work_days_for(crew: Crew, from_date: date, count: int):
    """Najde `count` po sobě jdoucích pracovních dnů dané čtety od `from_date`.

    Vrací iterator date — přeskočí víkend, svátky, absence, work_days.
    """
    found = 0
    current = from_date
    limit = current + timedelta(days=365 * count + 365)
    while current <= crew.available_to and current <= limit and found < count:
        if _is_crew_workday(crew, current):
            found += 1
            yield current
        current += timedelta(days=1)


def _is_crew_workday(crew: Crew, d: date) -> bool:
    """Je daný den pracovním dnem čtety?

    Podmínky:
    - available_from ≤ d ≤ available_to
    - d.weekday() ∈ work_days
    - d ∉ absent
    - is_cz_workday(d) (pondělí–pátek, není svátek)
    """
    if d < crew.available_from or d > crew.available_to:
        return False
    if d.weekday() not in crew.work_days:
        return False
    if d in crew.absent:
        return False
    if not is_cz_workday(d):
        return False
    return True


def schedule(items: Sequence[WorkItem], crews: Sequence[Crew], today: date) -> Plan:
    """Plánuje pracovní kroky do dostupných čteta.

    Pravidla:
    1. Nic se neplánuje do minulosti (start ≥ today).
    2. Řazení: filmy (dle SoD/created_at), pak rezervace (dle project_id).
    3. Návaznost kroků ve stejném projektu.
    4. Kapacita: max 1 krok/četa/den.
    5. Přiřazení čtety: ta, která krok dokončí dříve.
    6. start=None když žádná četa nedosáhne.
    """
    # --- Filtrujeme expired ---
    active_items = [i for i in items if i.kind != "expired"]

    # --- Seřadíme podle priority: filmy dříve než rezervace ---
    firm_items = [i for i in active_items if i.kind == "firm"]
    reserve_items = [i for i in active_items if i.kind == "reserve"]

    # filmy dle data potvrzení (SoD/created_at), pak rezervace; tiebreak project_id
    firm_items.sort(key=lambda i: (i.priority or date.max, i.project_id))
    reserve_items.sort(key=lambda i: (i.priority or date.max, i.project_id))

    sorted_items = firm_items + reserve_items

    # --- Plánování ---
    # crew_last_end[crew_name] = posledni_pracovni_den (dalni krok muze zacit az od next day)
    crew_last_end: dict[str, date] = {}
    # project_last_end[project_id] = end posledního naplánovaného kroku (posledni pracovni den)
    project_last_end: dict[int, date] = {}

    plan_items: list[PlanItem] = []

    for item in sorted_items:
        # Najdi čety správného work_type
        matching_crews = [c for c in crews if c.work_type == item.work_type]

        if not matching_crews:
            # Žádná četa daného typu → start=None
            plan_items.append(PlanItem(
                project_id=item.project_id,
                project_name=item.project_name,
                step_code=item.step_code,
                step_name=item.step_name,
                work_type=item.work_type,
                kind=item.kind,
                duration_days=item.duration_days,
            ))
            continue

        # Nejpozdější konec předchozího kroku téhož projektu
        prev_end = project_last_end.get(item.project_id, None)

        # Nejpozdější konec čtety (pokud byla už použita)
        earliest_start = today

        if prev_end is not None:
            # Krok startuje první den PO skončení předchozího (prev_end je pracovni den)
            earliest_start = prev_end + timedelta(days=1)

        # Pro každou četu najdi nejranější možný start a spočítej end
        crew_candidates: list[tuple[date, date, Crew]] = []

        for crew in matching_crews:
            # Četa musí být dostupná alespoň od today
            if crew.available_to < today:
                continue

            # Kapacita: četa nemůže dělat více než 1 krok/den
            crew_available_from = today
            if crew.name in crew_last_end:
                crew_available_from = crew_last_end[crew.name] + timedelta(days=1)

            candidate_start = max(earliest_start, crew_available_from)

            # Najdi pracovní dny
            day_iter = work_days_for(crew, candidate_start, item.duration_days)
            days = list(day_iter)

            if len(days) < item.duration_days:
                # Četa nedosáhne → skip
                continue

            start = days[0]
            end = days[-1]  # end = posledni pracovni den

            crew_candidates.append((start, end, crew))

        if not crew_candidates:
            # Žádná četa nedosáhne → start=None
            plan_items.append(PlanItem(
                project_id=item.project_id,
                project_name=item.project_name,
                step_code=item.step_code,
                step_name=item.step_name,
                work_type=item.work_type,
                kind=item.kind,
                duration_days=item.duration_days,
            ))
            continue

        # Vyber četu, která skončí dříve; při shodě menší crew_name (deterministicky)
        crew_candidates.sort(key=lambda c: (c[1], c[2].name))
        best_start, best_end, best_crew = crew_candidates[0]

        # Zaznamenej obsazení čtety (posledni pracovni den)
        crew_last_end[best_crew.name] = best_end

        # Aktualizuj konec projektu
        project_last_end[item.project_id] = best_end

        plan_items.append(PlanItem(
            project_id=item.project_id,
            project_name=item.project_name,
            step_code=item.step_code,
            step_name=item.step_name,
            work_type=item.work_type,
            kind=item.kind,
            duration_days=item.duration_days,
            start=best_start,
            end=best_end,
            crew_name=best_crew.name,
        ))

    # --- Projekty metadata ---
    projects: dict[int, ProjectMeta] = {}
    for item in plan_items:
        if item.project_id not in projects:
            projects[item.project_id] = ProjectMeta(
                id=item.project_id,
                name=item.project_name,
                kind=item.kind,
                lead_age_days=0,
                reservation_expires=None,
            )
        # Aktualizuj kind na "firm" pokud nějaký krok je film
        if item.kind == "firm":
            projects[item.project_id].kind = "firm"

    # --- Projdi plán a nastav done_date + makespan ---
    makespan = None
    for pid, pm in projects.items():
        ends = [p.end for p in plan_items if p.project_id == pid and p.end is not None]
        if ends:
            pm.done_date = max(ends)
            if makespan is None or max(ends) > makespan:
                makespan = max(ends)

    return Plan(
        items=plan_items,
        projects=list(projects.values()),
        makespan=makespan,
    )


# ======================== DB integration ========================

def _get_setting_value(db: Session, key: str, default=None):
    """Získej hodnotu nastavení, nebo default."""
    row = db.query(Setting).filter(Setting.key == key).first()
    if row and row.value is not None:
        try:
            return int(row.value)
        except (ValueError, TypeError):
            return row.value
    return default


def build_plan_input(db: Session, today: date):
    """Sestaví vstup pro scheduler z databáze.

    Vrací (items, crews, calendar_info, projects_meta).
    """
    ttl_days = _get_setting_value(db, "planovani_reservation_ttl_days", 30) or 30

    # --- Čety z DB ---
    db_crews = db.query(WorkCrew).filter(WorkCrew.active == True).all()  # noqa: E712
    crews = []
    for wc in db_crews:
        work_days_json = json.loads(wc.work_days_json) if wc.work_days_json else ["po", "ut", "st", "ct", "pa"]
        work_days = frozenset(_WORKDAY_MAP.get(d, -1) for d in work_days_json if _WORKDAY_MAP.get(d) is not None)
        absent_json = json.loads(wc.absent_dates_json) if wc.absent_dates_json else []
        absent = frozenset(date.fromisoformat(d) for d in absent_json)
        crews.append(Crew(
            name=wc.name,
            work_type=wc.work_type,
            available_from=wc.available_from,
            available_to=wc.available_to,
            work_days=work_days,
            absent=absent,
        ))

    # --- Projekty ---
    projects = db.query(Project).filter(
        Project.status.in_(["lead", "active"]),
        Project.active == True,  # noqa: E712
    ).all()

    items: list[WorkItem] = []
    projects_meta: list[dict] = []

    for proj in projects:
        # Zjisti, zda projekt má pipeline
        pp = db.query(ProjectPipeline).filter(
            ProjectPipeline.project_id == proj.id).first()
        if not pp:
            continue  # bez pipeline → mimo plán

        # Zjisti, zda projekt je film (active nebo sod done)
        is_film = proj.status == "active"

        # Zjisti datum SoD
        sod_step = (db.query(ProjectStep).join(PipelineStep, ProjectStep.step_id == PipelineStep.id)
                     .filter(ProjectStep.project_id == proj.id, PipelineStep.code == "sod")
                     .first())
        sod_date = None
        if sod_step and sod_step.done_at:
            sod_date = sod_step.done_at.date()

        if not is_film and sod_date:
            is_film = True

        created = proj.created_at.date() if proj.created_at else None
        priority = sod_date or created

        # Stanov kind
        if is_film:
            kind = "firm"
        else:
            # Rezervace — zkontroluj expiraci
            age = (today - created).days if created else 999
            if age > ttl_days:
                kind = "expired"
            else:
                kind = "reserve"

        # --- Pracovní kroky ---
        steps = (db.query(ProjectStep, PipelineStep)
                 .join(PipelineStep, ProjectStep.step_id == PipelineStep.id)
                 .filter(ProjectStep.project_id == proj.id)
                 .order_by(PipelineStep.order)
                 .all())

        project_items: list[WorkItem] = []

        for ps, pp_step in steps:  # noqa: B007
            # Přeskoč neprovozní kroky
            if ps.status in ("done", "skipped", "not_applicable", "cancelled"):
                continue

            # Pracovní krok má est_work_minutes > 0
            if pp_step.est_work_minutes is None or pp_step.est_work_minutes <= 0:
                continue

            # Výpočet trvání: max(1, ceil(est_work_minutes / 480))
            duration = max(1, (pp_step.est_work_minutes + 479) // 480)

            # work_role určuje typ čtety
            work_type = pp_step.work_rate_role or "roofer"

            project_items.append(WorkItem(
                project_id=proj.id,
                project_name=proj.name,
                step_code=pp_step.code,
                step_name=pp_step.name,
                work_type=work_type,
                duration_days=duration,
                kind=kind,
                priority=priority,
            ))

        # --- Projekty meta ---
        age_days = (today - created).days if created else 0
        exp_date = created + timedelta(days=ttl_days) if created and kind == "reserve" else None

        projects_meta.append({
            "id": proj.id,
            "name": proj.name,
            "kind": kind,
            "lead_age_days": age_days,
            "reservation_expires": exp_date.isoformat() if exp_date else None,
            "sod_date": sod_date.isoformat() if sod_date else None,
        })

        items.extend(project_items)

    return items, crews, {"ttl_days": ttl_days}, projects_meta
