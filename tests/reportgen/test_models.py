"""Modely + migrace + seed (M1)."""

import json

import pytest


def test_user_roles_defaults_from_role(db):
    from reportgen.storage import User

    u = User(email="x@x.cz", password_hash="h")
    db.add(u)
    db.commit()
    db.refresh(u)
    assert u.roles == ["customer"]
    assert u.has_role("customer")


def test_set_roles_and_has_role(db):
    from reportgen.storage import User

    u = User(email="x@x.cz", password_hash="h", role="customer")
    u.set_roles(["sales", "designer"])
    db.add(u)
    db.commit()
    db.refresh(u)
    assert u.roles == ["sales", "designer"]
    assert u.has_role("sales")
    assert u.has_role("designer")
    assert not u.has_role("admin")
    # primární role zachována pro zpětnou kompatibilitu
    assert u.role == "sales"
    # roles_json je JSON pole
    assert json.loads(u.roles_json) == ["sales", "designer"]
    # duplicity se vyhazují
    u.set_roles(["sales", "sales", "admin"])
    assert u.roles == ["sales", "admin"]


def test_set_roles_empty_defaults_customer(db):
    from reportgen.storage import User

    u = User(email="x@x.cz", password_hash="h", role="sales")
    u.set_roles([])
    db.add(u)
    db.commit()
    db.refresh(u)
    assert u.roles == ["customer"]
    assert u.role == "customer"


def test_roles_constant_includes_new_roles(db):
    from reportgen.storage import ROLES

    for r in ("admin", "antelon", "sales", "designer", "warehouse", "buyer",
              "subsidy", "connection", "roofer", "electrician", "inspector", "customer"):
        assert r in ROLES


def test_project_default_type_status_tech(db):
    from reportgen.storage import Project, generate_share_code

    p = Project(name="Test", share_code=generate_share_code())
    db.add(p)
    db.commit()
    db.refresh(p)
    assert p.type == "ostatni"
    assert p.status == "lead"
    assert p.tech is None


def test_project_type_status_settable(db):
    from reportgen.storage import Project, generate_share_code

    p = Project(name="Test", share_code=generate_share_code(), type="rd", status="active", tech="GW 10")
    db.add(p)
    db.commit()
    db.refresh(p)
    assert p.type == "rd"
    assert p.status == "active"
    assert p.tech == "GW 10"


def _base_project(db):
    from reportgen.storage import Project, generate_share_code
    p = Project(name="P", share_code=generate_share_code(), type="rd", status="lead")
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def test_pipeline_template_step_roundtrip(db):
    from reportgen.storage import PipelineTemplate, PipelineStep

    tpl = PipelineTemplate(code="tst", name="Test šablona", zakazka_type="rd")
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    assert tpl.id
    assert tpl.version == 1
    assert tpl.active is True

    step = PipelineStep(
        template_id=tpl.id, code="lead_telefon", name="První telefonát (do 24h)",
        phase="lead", order=2, est_admin_minutes=20, est_work_minutes=0,
        admin_rate_role="sales", work_rate_role="electrician", state_model="simple",
        allowed_roles_json=json.dumps(["sales", "admin", "antelon"]),
        condition_json=None, auto_hook=None, parallel_group=None,
    )
    db.add(step)
    db.commit()
    db.refresh(step)
    assert step.id
    assert step.order == 2
    assert json.loads(step.allowed_roles_json) == ["sales", "admin", "antelon"]


def test_project_pipeline_and_step_roundtrip(db):
    from reportgen.storage import (ProjectPipeline, PipelineTemplate, PipelineStep,
                                   ProjectStep, StepEvent, PipelineAiResult)
    from sqlalchemy.exc import IntegrityError

    p = _base_project(db)
    tpl = PipelineTemplate(code="tst2", name="Test šablona", zakazka_type="rd")
    db.add(tpl)
    db.commit()
    step = PipelineStep(template_id=tpl.id, code="lead_telefon", name="Telefon", phase="lead",
                        order=2, allowed_roles_json=json.dumps(["sales"]))
    db.add(step)
    db.commit()

    pp = ProjectPipeline(project_id=p.id, template_id=tpl.id)
    db.add(pp)
    db.commit()
    db.refresh(pp)
    assert pp.id

    ps = ProjectStep(project_id=p.id, step_id=step.id, status="not_started")
    db.add(ps)
    db.commit()
    db.refresh(ps)
    assert ps.status == "not_started"
    assert ps.real_admin_minutes == 0 and ps.real_work_minutes == 0

    ev = StepEvent(project_id=p.id, step_id=ps.id, action="plan",
                   from_status="not_started", to_status="planned", user_id=None, note=None)
    db.add(ev)
    db.commit()
    db.refresh(ev)
    assert ev.action == "plan"
    assert ev.at is not None

    ar = PipelineAiResult(project_id=p.id, step_id=ps.id, kind="fve_size",
                          input_json="{}", output_json="{}", status="draft", created_by=None)
    db.add(ar)
    db.commit()
    db.refresh(ar)
    assert ar.status == "draft"

    # unique (project_id, step_id)
    db.add(ProjectStep(project_id=p.id, step_id=step.id))
    with pytest.raises(IntegrityError):
        db.commit()


def test_materials_time_rate_invoice_notification_roundtrip(db):
    from reportgen.storage import (Material, ProjectMaterial, TimeEntry, RateCard,
                                   InvoiceItem, Notification, User)

    p = _base_project(db)
    u = User(email="u@u.cz", password_hash="h", role="sales")
    db.add(u)
    db.commit()
    db.refresh(u)

    m = Material(code="PANEL-400", name="Panel 400Wp", unit="ks", price=3200, active=True)
    db.add(m)
    db.commit()
    db.refresh(m)
    assert m.code == "PANEL-400"

    pm = ProjectMaterial(project_id=p.id, material_id=m.id, price_snapshot=m.price,
                         qty_planned=10, qty_actual=0, lane="plan")
    db.add(pm)
    db.commit()
    db.refresh(pm)
    assert pm.lane == "plan"

    te = TimeEntry(project_id=p.id, user_id=u.id, minutes=25, kind="admin", note=None)
    db.add(te)
    db.commit()
    db.refresh(te)
    assert te.kind == "admin"

    rc = RateCard(role="sales", kind="admin", rate_czk_h=500, active=True)
    db.add(rc)
    db.commit()
    db.refresh(rc)
    assert rc.rate_czk_h == 500

    inv = InvoiceItem(project_id=p.id, doc_type="posouzeni", description="Posouzení",
                      amount_czk=2500, status="draft")
    db.add(inv)
    db.commit()
    db.refresh(inv)
    assert inv.amount_czk == 2500

    n = Notification(user_id=u.id, project_id=p.id, text="Ahoj")
    db.add(n)
    db.commit()
    db.refresh(n)
    assert n.read is False and n.text == "Ahoj"


NEW_TABLES = ("pipeline_templates", "pipeline_steps", "project_pipeline", "project_steps",
              "step_events", "pipeline_ai_results", "materials", "project_materials",
              "time_entries", "rate_cards", "invoice_items", "notifications")


def test_migrate_old_db_preserves_data(db_path):
    """Legacy DB (users bez roles_json, projects bez type/status/tech) -> init_db muzeji."""
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT,
            email VARCHAR(255) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'customer', created_at DATETIME);
        CREATE TABLE projects (id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(255) NOT NULL, customer_name VARCHAR(255), description TEXT,
            owner_id INTEGER, share_code VARCHAR(16) NOT NULL UNIQUE,
            antelon_params_json TEXT, fve_params_json TEXT,
            created_at DATETIME, updated_at DATETIME);
        INSERT INTO users (email, password_hash, role) VALUES ('old@x.cz', 'hash', 'sales');
        INSERT INTO projects (name, share_code) VALUES ('Starý projekt', 'ABC12345');
    """)
    conn.commit()
    conn.close()

    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    from reportgen import storage

    engine = storage.init_db(db_path)
    Session = sessionmaker(bind=engine)
    s = Session()
    try:
        row = s.execute(text("SELECT email, role, roles_json FROM users WHERE email='old@x.cz'")).fetchone()
        assert row[0] == "old@x.cz"
        assert row[1] == "sales"
        assert json.loads(row[2]) == ["sales"]

        proj = s.query(storage.Project).filter(storage.Project.name == "Starý projekt").first()
        assert proj is not None
        assert proj.share_code == "ABC12345"
        assert proj.type == "ostatni"
        assert proj.status == "lead"

        tables = {r[0] for r in s.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()}
        for t in NEW_TABLES:
            assert t in tables, f"chybí tabulka {t}"
    finally:
        s.close()


def test_seed_templates_count_and_rd_steps(db):
    from reportgen.storage import PipelineTemplate, PipelineStep

    tpls = db.query(PipelineTemplate).all()
    assert len(tpls) == 11
    codes = {t.code for t in tpls}
    assert codes == {"rd", "byt", "firma", "bojler", "rozsireni", "wb", "ostatni",
                     "reklamace", "elektroprace", "carport", "kontrola"}

    rd = db.query(PipelineTemplate).filter(PipelineTemplate.code == "rd").first()
    steps = db.query(PipelineStep).filter(PipelineStep.template_id == rd.id) \
        .order_by(PipelineStep.order).all()
    assert len(steps) >= 55
    # admin časy z Excelu (totál 553 min pro RD)
    assert sum(s.est_admin_minutes for s in steps) == 553

    by_code = {s.code: s for s in steps}
    assert by_code["odsouhlaseni_predbezne"].auto_hook == "invoice_2500"
    assert by_code["sod"].state_model == "contract"
    assert by_code["sod"].auto_hook == "sod_signed"
    assert by_code["sop"].state_model == "contract"
    assert by_code["sop"].auto_hook == "sop_signed"
    assert by_code["elektro_montaz"].auto_hook == "elektro_done"
    assert by_code["navrh_fve"].state_model == "ai"
    assert by_code["nabidka_podrobna"].state_model == "ai"
    # podmíněné kroky mají condition_json ve formátu plánu
    import json as _json
    cond = _json.loads(by_code["registrace_nzu"].condition_json)
    assert "project_param_in" in cond
    # paralelní skupiny
    assert by_code["zalohova_faktura"].parallel_group == "smlouva_after"
    assert by_code["sop"].parallel_group == "smlouva_after"
    # allowed_roles pro elektro montáž
    roles = _json.loads(by_code["elektro_montaz"].allowed_roles_json)
    assert "electrician" in roles


def test_seed_templates_idempotent(db):
    from reportgen.storage import PipelineTemplate, PipelineStep
    from reportgen.pipeline_seed import ensure_pipeline_templates

    n_tpl = db.query(PipelineTemplate).count()
    n_step = db.query(PipelineStep).count()
    assert n_tpl == 11 and n_step > 0

    ensure_pipeline_templates(db)
    db.expire_all()
    assert db.query(PipelineTemplate).count() == n_tpl
    assert db.query(PipelineStep).count() == n_step


def test_attach_template(db):
    from reportgen.storage import Project, ProjectPipeline, ProjectStep, PipelineStep, PipelineTemplate
    from reportgen.pipeline_seed import attach_template

    rd = db.query(PipelineTemplate).filter(PipelineTemplate.code == "rd").first()
    assert rd is not None
    steps = db.query(PipelineStep).filter(PipelineStep.template_id == rd.id).all()
    assert len(steps) >= 55

    p = Project(name="Nový RD", share_code="QWERTYUI", type="rd", status="lead")
    db.add(p)
    db.commit()
    db.refresh(p)

    attach_template(db, p, "rd")
    pp = db.query(ProjectPipeline).filter(ProjectPipeline.project_id == p.id).one()
    assert pp.template_id == rd.id

    inst = db.query(ProjectStep).filter(ProjectStep.project_id == p.id).all()
    assert len(inst) == len(steps)
    assert all(ps.status == "not_started" for ps in inst)
    assert all(ps.assigned_user_id is None for ps in inst)


def test_rate_card_seed(db):
    from reportgen.storage import RateCard

    cards = db.query(RateCard).all()
    assert cards, "sazby musí být seednuté"
    admin_roles = {c.role for c in cards if c.kind == "admin"}
    for r in ("sales", "designer", "buyer", "subsidy", "connection", "warehouse"):
        assert r in admin_roles
    for c in cards:
        if c.kind == "admin":
            assert c.rate_czk_h == 500
    work = {c.role: c.rate_czk_h for c in cards if c.kind == "work"}
    assert work.get("roofer") == 450
    assert work.get("electrician") == 500
    assert work.get("inspector") == 550
    assert work.get("sales") == 500


def test_migrate_is_idempotent(db_path):
    """Druhý init_db na migrované DB nesmí rozbít data."""
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT,
            email VARCHAR(255) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'customer', created_at DATETIME);
        INSERT INTO users (email, password_hash, role) VALUES ('old@x.cz', 'hash', 'sales');
    """)
    conn.commit()
    conn.close()

    from reportgen import storage

    storage.init_db(db_path)
    storage.init_db(db_path)  # druhé volání

    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import text

    Session = sessionmaker(bind=storage.get_engine(db_path))
    s = Session()
    try:
        row = s.execute(text("SELECT email, roles_json FROM users WHERE email='old@x.cz'")).fetchone()
        assert row[1] == '["sales"]'
        # seed uživatelé z původních defaultů nenaběhli duplicitně
        assert s.query(storage.User).filter(storage.User.email == "old@x.cz").count() == 1
    finally:
        s.close()