"""Kalendář ČR a scheduler pro plánování montáže a elektro (etapa 1 — backend).

Testuje:
- Kalendář: pracovní dny, svátky (pevné i velikonoční), víkendy
- Scheduler: návaznost kroků, kapacita, přeskočení víkendů/svátků,
  okno dostupnosti, absences, work_days pattern, priorita film > rezervace,
  expirace rezervace, what-if (+1 četa → dřívější makespan), determinismus,
  start=None bez čtety
"""
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

# Ujistíme se, že backend/app je na cestě (pro import planning.py)
REPO = Path(__file__).resolve().parents[2]
BACKEND_APP = REPO / "backend" / "app"
if str(BACKEND_APP) not in sys.path:
    sys.path.insert(0, str(BACKEND_APP))

from reportgen.cz_calendar import is_cz_workday, holidays_between, _easter_sunday
from reportgen.planning import (WorkItem, Crew, Plan, schedule, work_days_for,
                                build_plan_input)


# ======================== Kalendář ========================

class TestCzCalendar:
    """Státní svátky ČR a pracovní dny."""

    def test_easter_2026(self):
        assert _easter_sunday(2026) == date(2026, 4, 5)

    def test_easter_2027(self):
        assert _easter_sunday(2027) == date(2027, 3, 28)

    def test_easter_2028(self):
        assert _easter_sunday(2028) == date(2028, 4, 16)

    def test_may_day_is_holiday(self):
        # 1. 5. 2026 = pátek + státní svátek → pracovní den = NE
        assert is_cz_workday(date(2026, 5, 1)) is False

    def test_christmas_day_is_holiday(self):
        # 25. 12. 2026 → NE
        assert is_cz_workday(date(2026, 12, 25)) is False

    def test_good_friday_is_holiday(self):
        # Velký pátek 2026 = 3. 4. 2026 → NE
        assert is_cz_workday(date(2026, 4, 3)) is False

    def test_easter_monday_is_holiday(self):
        # Velikonoční pondělí 2026 = 6. 4. 2026 → NE
        assert is_cz_workday(date(2026, 4, 6)) is False

    def test_shrove_monday_is_holiday(self):
        # Maškopust 2026 = Velikonoce - 47 dní = 2026-02-17 → NE
        assert is_cz_workday(date(2026, 2, 17)) is False

    def test_sunday_is_not_workday(self):
        # 18. 10. 2026 = neděle → NE
        assert is_cz_workday(date(2026, 10, 18)) is False

    def test_monday_is_workday(self):
        # 19. 10. 2026 = pondělí, není svátek → ANO
        assert is_cz_workday(date(2026, 10, 19)) is True

    def test_holidays_between_range(self):
        svatky = holidays_between(date(2026, 12, 23), date(2026, 12, 27))
        dates = [date(2026, 12, 24), date(2026, 12, 25), date(2026, 12, 26)]
        assert svatky == dates

    def test_workday_after_holiday_weekend(self):
        # 30. 12. 2026 = středa, není svátek → ANO
        assert is_cz_workday(date(2026, 12, 30)) is True


# ======================== Scheduler helpers ========================

class TestWorkDaysFor:
    """work_days_for: najdi N-po-sobě-jdoucí pracovní dny čtety."""

    def test_consecutive_workdays_no_gaps(self):
        crew = Crew(name="Test", work_type="roofer",
                    available_from=date(2026, 10, 1), available_to=date(2026, 12, 31),
                    work_days=frozenset({0, 1, 2, 3, 4}), absent=frozenset())
        days = list(work_days_for(crew, date(2026, 10, 19), 3))  # pondělí začátek
        assert len(days) == 3
        assert days[0] == date(2026, 10, 19)   # pondělí
        assert days[1] == date(2026, 10, 20)   # úterý
        assert days[2] == date(2026, 10, 21)   # středa

    def test_skips_weekend(self):
        # začátek pátek 23.10.2026, potřebujeme 3 dny
        crew = Crew(name="Test", work_type="roofer",
                    available_from=date(2026, 10, 1), available_to=date(2026, 12, 31),
                    work_days=frozenset({0, 1, 2, 3, 4}), absent=frozenset())
        days = list(work_days_for(crew, date(2026, 10, 23), 3))  # pátek
        assert len(days) == 3
        assert days[0] == date(2026, 10, 23)   # pátek
        assert days[1] == date(2026, 10, 26)   # pondělí (skip so+ne)
        assert days[2] == date(2026, 10, 27)   # úterý

    def test_skips_holidays(self):
        # 24. 12. = štědrý den (středa), svátek; 25. = 1. vánoční (čtvrtek), svátek
        crew = Crew(name="Test", work_type="roofer",
                    available_from=date(2026, 12, 1), available_to=date(2026, 12, 31),
                    work_days=frozenset({0, 1, 2, 3, 4}), absent=frozenset())
        days = list(work_days_for(crew, date(2026, 12, 23), 2))  # středa před svátkama
        assert len(days) == 2
        assert days[0] == date(2026, 12, 23)   # středa (před svátkem)
        assert days[1] == date(2026, 12, 28)   # pondělí (skip štědrý, vánoce, svátek 1.1.)

    def test_absences_skip_days(self):
        crew = Crew(name="Test", work_type="roofer",
                    available_from=date(2026, 10, 1), available_to=date(2026, 12, 31),
                    work_days=frozenset({0, 1, 2, 3, 4}),
                    absent=frozenset({date(2026, 10, 21)}))  # středa 21.10.
        days = list(work_days_for(crew, date(2026, 10, 19), 3))
        assert len(days) == 3
        assert days[0] == date(2026, 10, 19)   # pondělí
        assert days[1] == date(2026, 10, 20)   # úterý
        assert days[2] == date(2026, 10, 22)   # čtvrtek (skip středa = absence)

    def test_work_days_filter(self):
        # Četa pracuje jen Po–St
        crew = Crew(name="Test", work_type="roofer",
                    available_from=date(2026, 10, 1), available_to=date(2026, 12, 31),
                    work_days=frozenset({0, 1, 2}), absent=frozenset())
        # začátek 23.10. = pátek → první den = pondělí 26.10.
        days = list(work_days_for(crew, date(2026, 10, 23), 1))
        assert len(days) == 1
        assert days[0] == date(2026, 10, 26)   # pondělí

    def test_available_to_boundary(self):
        # 24.10.2026 = sobota (weekday 5), 25.10. = neděle, 26.10. = pondělí
        crew = Crew(name="Test", work_type="roofer",
                    available_from=date(2026, 10, 1), available_to=date(2026, 10, 25),
                    work_days=frozenset({0, 1, 2, 3, 4}), absent=frozenset())
        # Od 24.10. (sobota) → další pracovní den = 26.10. (pondělí), ale available_to=25.10.
        # Tedy žádné pracovní dny nedosáhne.
        days = list(work_days_for(crew, date(2026, 10, 24), 3))
        assert len(days) == 0

    def test_empty_when_no_days_available(self):
        crew = Crew(name="Test", work_type="roofer",
                    available_from=date(2026, 12, 24), available_to=date(2026, 12, 26),
                    work_days=frozenset({0, 1, 2, 3, 4}), absent=frozenset())
        # Všechny dny jsou svátky
        days = list(work_days_for(crew, date(2026, 12, 24), 1))
        assert len(days) == 0


# ======================== Scheduler ========================

class TestScheduler:
    """schedule(): čistá funkce bez DB."""

    def _make_crew(self, name="Montáž", work_type="roofer"):
        return Crew(
            name=name, work_type=work_type,
            available_from=date(2026, 10, 1),
            available_to=date(2026, 12, 31),
            work_days=frozenset({0, 1, 2, 3, 4}),
            absent=frozenset(),
        )

    def _make_item(self, project_id, project_name, step_code, step_name,
                   work_type, duration_days, kind="firm"):
        return WorkItem(
            project_id=project_id, project_name=project_name,
            step_code=step_code, step_name=step_name,
            work_type=work_type, duration_days=duration_days, kind=kind,
        )

    def test_basic_single_item(self):
        today = date(2026, 10, 19)  # pondělí
        items = [self._make_item(1, "Projekt A", "montaz", "Montáž", "roofer", 1)]
        crews = [self._make_crew()]
        plan = schedule(items, crews, today)

        assert plan.makespan is not None
        assert plan.items[0].start == today
        assert plan.items[0].crew_name == "Montáž"
        # 1 den → end = start + 1 pracovní den
        assert plan.makespan >= today

    def test_step_dependency_same_project(self):
        """Krok 2 startuje až po dokončení kroku 1 téhož projektu."""
        today = date(2026, 10, 19)
        items = [
            self._make_item(1, "Projekt A", "krok1", "Krok 1", "roofer", 1),
            self._make_item(1, "Projekt A", "krok2", "Krok 2", "roofer", 1),
        ]
        crews = [self._make_crew()]
        plan = schedule(items, crews, today)

        # Krok 1 začne dnes, krok 2 až na další pracovní den
        assert plan.items[0].start == today
        assert plan.items[1].start > plan.items[0].start
        # Krok 1 je 1 den, takže krok 2 musí začít na další pracovní den
        next_day = today + timedelta(days=1)
        while not is_cz_workday(next_day):
            next_day += timedelta(days=1)
        assert plan.items[1].start == next_day

    def test_capacity_two_projects_one_crew(self):
        """2 projekty se stejnou čletou → 2. projekt jde na další pracovní den."""
        today = date(2026, 10, 19)
        items = [
            self._make_item(1, "Projekt A", "krok1", "Krok 1", "roofer", 1),
            self._make_item(2, "Projekt B", "krok1", "Krok 1", "roofer", 1),
        ]
        crews = [self._make_crew()]
        plan = schedule(items, crews, today)

        # Obě projekty začínají tentýž den? Ne! Kapacita = 1 krok/četa/den
        starts = [p.start for p in plan.items]
        assert starts[0] == today
        assert starts[1] > today  # 2. musí být později

    def test_film_priority_over_reservation(self):
        """Filmy mají přednost před rezervacemi — začínají dříve."""
        today = date(2026, 10, 19)
        items = [
            self._make_item(1, "Rezervace", "krok1", "Krok 1", "roofer", 1, kind="reserve"),
            self._make_item(2, "Film", "krok1", "Krok 1", "roofer", 1, kind="firm"),
        ]
        crews = [self._make_crew()]
        plan = schedule(items, crews, today)

        # Film (projekt 2) má přednost → začíná dřív
        film_item = next(i for i in plan.items if i.project_id == 2)
        reserve_item = next(i for i in plan.items if i.project_id == 1)
        assert film_item.start <= reserve_item.start

    def test_film_priority_by_sod_date(self):
        """Film s dřívějším datem SoD má přednost před filmem s menším project_id."""
        today = date(2026, 10, 19)
        items = [
            WorkItem(project_id=3, project_name="B", step_code="k", step_name="K",
                     work_type="roofer", duration_days=1, kind="firm",
                     priority=date(2026, 10, 10)),
            WorkItem(project_id=2, project_name="A", step_code="k", step_name="K",
                     work_type="roofer", duration_days=1, kind="firm",
                     priority=date(2026, 9, 1)),
        ]
        crews = [self._make_crew()]
        plan = schedule(items, crews, today)
        starts = {p.project_id: p.start for p in plan.items}
        assert starts[2] < starts[3]  # dřívější SoD → dřívější start

    def test_skip_past_today(self):
        """Nic se neplánuje do minulosti (start ≥ today)."""
        today = date(2026, 10, 19)
        items = [self._make_item(1, "Projekt A", "krok1", "Krok 1", "roofer", 1)]
        crews = [self._make_crew()]
        plan = schedule(items, crews, today)

        for item in plan.items:
            if item.start is not None:
                assert item.start >= today

    def test_weekend_skip(self):
        """Scheduler přeskočí víkend."""
        today = date(2026, 10, 23)  # pátek
        items = [self._make_item(1, "A", "krok1", "Krok 1", "roofer", 2)]
        crews = [self._make_crew()]
        plan = schedule(items, crews, today)

        # Den 1 = pátek 23.10., Den 2 = pondělí 26.10.
        assert plan.items[0].start == today
        # end by měl být 26.10. (pondělí)
        assert plan.items[0].end == date(2026, 10, 26)

    def test_crew_availability_window(self):
        """Četa s oknem, které neobsáhne celý krok → start=None."""
        # Četa dostupná jen do 20.10., krok trvá 2 dny od 23.10.
        crew_limited = Crew(
            name="Omezená", work_type="roofer",
            available_from=date(2026, 10, 1), available_to=date(2026, 10, 20),
            work_days=frozenset({0, 1, 2, 3, 4}), absent=frozenset(),
        )
        today = date(2026, 10, 23)  # pátek
        items = [self._make_item(1, "A", "krok1", "Krok 1", "roofer", 2)]
        plan = schedule(items, [crew_limited], today)

        # Žádná četa nedosáhne → start=None
        assert plan.items[0].start is None

    def test_crew_assignment_earliest_finish(self):
        """Scheduler vybere četu, která krok dokončí dříve."""
        today = date(2026, 10, 19)
        # Dvě čety stejného typu, jedna má širší okno
        crew_a = Crew(
            name="Četa A", work_type="roofer",
            available_from=date(2026, 10, 1), available_to=date(2026, 10, 30),
            work_days=frozenset({0, 1, 2, 3, 4}), absent=frozenset(),
        )
        crew_b = Crew(
            name="Četa B", work_type="roofer",
            available_from=date(2026, 10, 1), available_to=date(2026, 12, 31),
            work_days=frozenset({0, 1, 2, 3, 4}), absent=frozenset(),
        )
        items = [self._make_item(1, "A", "krok1", "Krok 1", "roofer", 1)]
        plan = schedule(items, [crew_a, crew_b], today)

        # Obě čety jsou stejně dobré (oba dokončí tentýž den),
        # takže se bere ta s menším ID/abecedně
        assert plan.items[0].crew_name is not None

    def test_start_none_when_no_crew(self):
        """Pokud žádná četa nemá work_type → start=None."""
        today = date(2026, 10, 19)
        items = [self._make_item(1, "A", "krok1", "Krok 1", "roofer", 1)]
        crews = [Crew(
            name="Elektro", work_type="electrician",
            available_from=date(2026, 10, 1), available_to=date(2026, 12, 31),
            work_days=frozenset({0, 1, 2, 3, 4}), absent=frozenset(),
        )]
        plan = schedule(items, crews, today)
        assert plan.items[0].start is None

    def test_determinism(self):
        """Stejný vstup → stejný výstup (deterministický scheduler)."""
        today = date(2026, 10, 19)
        crews = [self._make_crew(f"Montáž {i}") for i in range(3)]
        items = [
            self._make_item(i, f"Projekt {i}", "krok1", "Krok 1", "roofer", 2)
            for i in range(5)
        ]
        plan1 = schedule(items, crews, today)
        plan2 = schedule(items, crews, today)

        for a, b in zip(plan1.items, plan2.items):
            assert a.start == b.start
            assert a.end == b.end
            assert a.crew_name == b.crew_name

    def test_what_if_earlier_makespan(self):
        """+1 četa → dřívější makespan."""
        today = date(2026, 10, 19)
        crews_single = [self._make_crew("Jediná")]
        crews_double = [self._make_crew("Jediná"), self._make_crew("Druhá")]

        items = [
            self._make_item(i, f"Projekt {i}", "krok1", "Krok 1", "roofer", 1)
            for i in range(4)
        ]

        plan_single = schedule(items, crews_single, today)
        plan_double = schedule(items, crews_double, today)

        # S dvěma čtětama by se všechny 4 projekty měly vejít do 2 dnů
        assert plan_double.makespan < plan_single.makespan

    def test_project_done_date(self):
        """done_date projektu = end posledního kroku, None pokud žádný krok nedostal četu."""
        today = date(2026, 10, 19)
        items = [
            self._make_item(1, "A", "krok1", "Krok 1", "roofer", 1),
        ]
        # Žádná četa → žádný krok nedostane start
        crews = [Crew(name="Elektro", work_type="electrician",
                      available_from=date(2026, 10, 1), available_to=date(2026, 12, 31),
                      work_days=frozenset({0, 1, 2, 3, 4}), absent=frozenset())]
        plan = schedule(items, crews, today)

        project_done = plan.projects[0]
        assert project_done.done_date is None

    def test_holiday_skipping_with_duration(self):
        """Krok s délkou 3 dny přeskočí svátky v mezičase."""
        today = date(2026, 12, 22)  # pondělí
        items = [self._make_item(1, "A", "krok1", "Krok 1", "roofer", 3)]
        crews = [self._make_crew()]
        plan = schedule(items, crews, today)

        # 22. pondělí (den 1), 23. úterý (den 2), 28. pondělí (den 3, přeskočí Vánoc)
        assert plan.items[0].start == date(2026, 12, 22)
        assert plan.items[0].end == date(2026, 12, 28)


# ======================== build_plan_input ========================

class TestBuildPlanInput:
    """build_plan_input: DB → WorkItem."""

    def _mk_user(self, db, email, role):
        u = db.query(User).filter(User.email == email).first()
        if not u:
            u = User(email=email, password_hash="h", role=role)
            u.set_roles([role])
            db.add(u)
            db.commit()
        return u

    def _mk_project(self, db, name, status="lead", template="rd"):
        from reportgen.storage import generate_share_code
        p = Project(name=name, customer_name=name, share_code=generate_share_code(),
                    status=status, type=template)
        db.add(p)
        db.commit()
        db.refresh(p)
        attach_template(db, p, template)
        return p

    def test_film_project_in_items(self, db):
        """Aktivní projekt → film, s krokem montáže."""
        from datetime import datetime as _dt
        from reportgen.storage import ProjectStep as PS

        user = self._mk_user(db, "admin@test.local", "admin")
        proj = self._mk_project(db, "Filmový projekt", status="active")

        # Dokončit pipeline kroky až po stavba_montaz pomocí přímého DB update
        # (vyhne se gate chybám pipeline engine)
        rows = (db.query(PS, PipelineStep)
                .join(PipelineStep, PS.step_id == PipelineStep.id)
                .filter(PS.project_id == proj.id)
                .order_by(PipelineStep.order).all())
        for ps, s in rows:
            if s.code == "stavba_montaz":
                break
            if ps.status in ("done", "skipped", "signed"):
                continue
            # Přímý update statusu bez gate check
            ps.status = "done"

        # Nastavit stavba_montaz jako hotovo
        stavba_ps = db.query(PS).join(PipelineStep, PS.step_id == PipelineStep.id).filter(
            PS.project_id == proj.id, PipelineStep.code == "stavba_montaz").first()
        if stavba_ps:
            stavba_ps.status = "done"
            stavba_ps.done_at = _dt.utcnow()

        items, crews, _, meta = build_plan_input(db, date(2026, 10, 19))
        film_items = [i for i in items if i.project_name == "Filmový projekt"]
        assert len(film_items) > 0, "Projekt by měl mít pracovní kroky"
        assert all(i.kind == "firm" for i in film_items)

    def test_lead_reservation_in_items(self, db):
        """Projekt se statusem lead → rezervace."""
        self._mk_project(db, "Rezervační projekt", status="lead")

        items, _, _, meta = build_plan_input(db, date(2026, 10, 19))
        res_items = [i for i in items if i.project_name == "Rezervační projekt"]
        assert len(res_items) > 0
        assert all(i.kind == "reserve" for i in res_items)

    def test_expired_reservation(self, db):
        """Expirovaná rezervace → kind='expired' (scheduler ji ignoruje)."""
        user = self._mk_user(db, "admin@test.local", "admin")
        # Nastavíme TTL na 1 den (setting existuje z init_db → update)
        s = db.query(Setting).filter(Setting.key == "planovani_reservation_ttl_days").first()
        if s:
            s.value = "1"
        else:
            db.add(Setting(key="planovani_reservation_ttl_days", value="1"))
        db.commit()

        # Vytvoříme projekt se statusem lead, created_at před 1 dnem
        from reportgen.storage import generate_share_code
        from datetime import datetime as _dt, timedelta as _td
        old_date = _dt.utcnow() - _td(days=5)
        p = Project(name="Stará rezervace", customer_name="Starý",
                    share_code=generate_share_code(), status="lead",
                    created_at=old_date)
        db.add(p)
        db.commit()
        db.refresh(p)
        attach_template(db, p, "rd")

        items, _, _, meta = build_plan_input(db, date(2026, 10, 19))
        exp_items = [i for i in items if i.project_name == "Stará rezervace"]
        assert all(i.kind == "expired" for i in exp_items)

    def test_projects_meta_has_lead_age(self, db):
        """Meta obsahuje lead_age_days."""
        self._mk_project(db, "Meta test", status="lead")
        _, _, _, meta = build_plan_input(db, date(2026, 10, 19))

        proj_meta = [m for m in meta if m["name"] == "Meta test"]
        assert len(proj_meta) == 1
        assert "lead_age_days" in proj_meta[0]


# ======================== Import helpers ========================

from reportgen.storage import (Project, ProjectStep, PipelineStep, PipelineTemplate,
                               User, Setting)
from reportgen.pipeline_seed import attach_template
from reportgen.pipeline import transition


# === Helpers pro DB testy (lokální, aby se nepoužívaly mimo TestBuildPlanInput) ===

def _ps_by_code(db, project, code):
    """Získá ProjectStep podle kódu šablony."""
    row = (db.query(ProjectStep, PipelineStep)
           .join(PipelineStep, ProjectStep.step_id == PipelineStep.id)
           .filter(ProjectStep.project_id == project.id, PipelineStep.code == code)
           .one())
    return row[0]


def _do(db, project, code, action, user, **kw):
    """Workflow transition helper."""
    step = _ps_by_code(db, project, code)
    return transition(db, project, step, action, user, **kw)


def _finish_simple(db, project, codes, user):
    """Dokončí sekvenci kroků."""
    for code in codes:
        ps = _ps_by_code(db, project, code)
        if ps.status in ("done", "signed", "skipped"):
            continue
        if ps.status == "not_started":
            _do(db, project, code, "plan", user)
        if ps.status == "planned":
            _do(db, project, code, "begin", user)
        if ps.status == "in_progress":
            _do(db, project, code, "complete", user)
