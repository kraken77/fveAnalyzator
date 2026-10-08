import os
import json
import secrets
from datetime import datetime, date
from sqlalchemy import create_engine, Column, Integer, String, Text, Float, DateTime, Date, ForeignKey, Boolean, UniqueConstraint, Index, text, bindparam
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

Base = declarative_base()

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "..", "data", "reportgen.db")
# Normalize: backend/../data/reportgen.db -> data/reportgen.db
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "reportgen.db"))
# fallback: also support /app/data/reportgen.db inside docker
if not os.path.exists(os.path.dirname(DB_PATH)):
    DB_PATH = "/app/data/reportgen.db"

# Ensure directory exists lazily in init_db

# Registrované role (číselník). users.role = primární role (backward compat),
# users.roles_json = JSON pole rolí; nový kód používá User.roles.
ROLES = ["admin", "antelon", "sales", "designer", "warehouse", "buyer",
         "subsidy", "connection", "roofer", "electrician", "inspector", "customer"]

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="customer")  # primární role (backward compat)
    roles_json = Column(Text, nullable=True)  # JSON pole rolí
    created_at = Column(DateTime, default=datetime.utcnow)

    @property
    def roles(self) -> list:
        try:
            return json.loads(self.roles_json) if self.roles_json else [self.role]
        except Exception:
            return [self.role]

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def set_roles(self, roles: list):
        if not roles:
            roles = ["customer"]
        self.roles_json = json.dumps(list(dict.fromkeys(roles)))
        self.role = roles[0]  # primární role pro zpětnou kompatibilitu

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    customer_name = Column(String(255), nullable=True)
    # Kontakt patří zakázce, ne uživateli: jeden zákazník může mít více
    # zakázek s různými kontakty (jiná manželka, firma) a users telefon nemá.
    customer_email = Column(String(255), nullable=True)
    customer_phone = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    share_code = Column(String(16), unique=True, nullable=False, index=True)
    antelon_params_json = Column(Text, nullable=True)  # JSON string
    fve_params_json = Column(Text, nullable=True)
    type = Column(String(30), nullable=False, default="ostatni")  # zakazka typ (rd, byt, ...)
    status = Column(String(20), nullable=False, default="lead")   # lead|fve_analyza|active|done|cancelled
    tech = Column(String(255), nullable=True)                     # technologie (string z Excelu)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    active = Column(Boolean, nullable=False, default=True, server_default=text("1"))

class ProjectUser(Base):
    __tablename__ = "project_users"
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    joined_at = Column(DateTime, default=datetime.utcnow)

class ProjectFile(Base):
    __tablename__ = "project_files"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(50), nullable=False)  # consumption_daily, voltage, profile_15min
    filename = Column(String(255), nullable=False)
    path = Column(String(500), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

class ProjectPhoto(Base):
    __tablename__ = "project_photos"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    path = Column(String(500), nullable=False)
    caption = Column(String(500), nullable=True)
    position = Column(Integer, default=0)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

class PdfVersion(Base):
    __tablename__ = "pdf_versions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    template = Column(String(50), nullable=False)  # antelon, energy, economic, ote
    version = Column(Integer, nullable=False)
    audience = Column(String(20), default="full")
    file_path = Column(String(500), nullable=False)
    params_snapshot_json = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# ---------- Pipeline (Dispečink) tabulky (M1) ----------

class PipelineTemplate(Base):
    __tablename__ = "pipeline_templates"
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(30), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    zakazka_type = Column(String(30), nullable=False)
    version = Column(Integer, default=1)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class PipelineStep(Base):
    __tablename__ = "pipeline_steps"
    id = Column(Integer, primary_key=True, autoincrement=True)
    template_id = Column(Integer, ForeignKey("pipeline_templates.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    code = Column(String(50), nullable=False)
    name = Column(String(200), nullable=False)
    phase = Column(String(50), nullable=True)
    order = Column(Integer, nullable=False, default=0)
    est_admin_minutes = Column(Integer, default=0)
    est_work_minutes = Column(Integer, default=0)
    admin_rate_role = Column(String(30), default="sales")
    work_rate_role = Column(String(30), default="electrician")
    state_model = Column(String(20), default="simple")  # simple | contract | ai | material
    allowed_roles_json = Column(Text, nullable=True)
    condition_json = Column(Text, nullable=True)
    auto_hook = Column(String(50), nullable=True)
    parallel_group = Column(String(50), nullable=True)

class ProjectPipeline(Base):
    __tablename__ = "project_pipeline"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), unique=True, nullable=False)
    template_id = Column(Integer, ForeignKey("pipeline_templates.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class ProjectStep(Base):
    __tablename__ = "project_steps"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    step_id = Column(Integer, ForeignKey("pipeline_steps.id"), nullable=False)
    status = Column(String(20), default="not_started")  # not_started|planned|in_progress|done|skipped|not_applicable|cancelled
    plan_date = Column(DateTime, nullable=True)
    assigned_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    note = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    done_at = Column(DateTime, nullable=True)
    real_admin_minutes = Column(Integer, default=0)
    real_work_minutes = Column(Integer, default=0)
    __table_args__ = (UniqueConstraint("project_id", "step_id", name="uq_project_step"),)

class StepEvent(Base):
    __tablename__ = "step_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    step_id = Column(Integer, ForeignKey("project_steps.id"), nullable=False)
    action = Column(String(50), nullable=False)
    from_status = Column(String(20), nullable=True)
    to_status = Column(String(20), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    at = Column(DateTime, default=datetime.utcnow)
    note = Column(Text, nullable=True)

class PipelineAiResult(Base):
    __tablename__ = "pipeline_ai_results"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    step_id = Column(Integer, ForeignKey("project_steps.id"), nullable=False)
    kind = Column(String(50), nullable=False)
    input_json = Column(Text, nullable=True)
    output_json = Column(Text, nullable=True)
    pdf_version_id = Column(Integer, ForeignKey("pdf_versions.id"), nullable=True)
    status = Column(String(20), default="draft")  # draft|approved|rejected
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Material(Base):
    __tablename__ = "materials"
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    unit = Column(String(10), default="ks")
    price = Column(Float, default=0)          # denormalizovaná AKTUÁLNÍ cena
    active = Column(Boolean, default=True)
    # panel | inverter | battery | install | system | other
    category = Column(String(30), default="other", server_default=text("'other'"))
    # public = vidí zákazník, internal = jen pracovníci
    visibility = Column(String(20), default="public", server_default=text("'public'"))
    rating = Column(Float, nullable=True)     # Wp u panelů, kW u měničů, kWh u baterií
    supplier = Column(String(120), nullable=True)  # konkrétní typ dodavatele
    is_default = Column(Boolean, default=False, server_default=text("0"))
    system_kwp = Column(Float, nullable=True)            # jen category='system'
    system_battery_kwh = Column(Float, nullable=True)    # jen category='system'
    created_at = Column(DateTime, default=datetime.utcnow)

class ProjectMaterial(Base):
    __tablename__ = "project_materials"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    price_snapshot = Column(Float, default=0)
    qty_planned = Column(Float, default=0)
    qty_actual = Column(Float, default=0)
    lane = Column(String(20), default="plan")  # plan|order|issue|actual
    step_id = Column(Integer, ForeignKey("project_steps.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class MaterialPrice(Base):
    """Historie cen materiálu. Aktuální cena = nejnovější platný řádek.

    Do této tabulky i do `Material.price` smí zapisovat jen
    `materials_service.set_material_price`.
    """
    __tablename__ = "material_prices"
    id = Column(Integer, primary_key=True, autoincrement=True)
    material_id = Column(Integer, ForeignKey("materials.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    price = Column(Float, nullable=False)
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=True)     # NULL = stále platí
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        Index("ix_material_prices_material_valid", "material_id", "valid_from"),
    )

class TimeEntry(Base):
    __tablename__ = "time_entries"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    step_id = Column(Integer, ForeignKey("project_steps.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    minutes = Column(Integer, nullable=False, default=0)
    work_date = Column(Date, nullable=True)
    kind = Column(String(10), default="admin")  # admin|work
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class RateCard(Base):
    __tablename__ = "rate_cards"
    id = Column(Integer, primary_key=True, autoincrement=True)
    role = Column(String(30), nullable=False)
    kind = Column(String(10), default="admin")  # admin|work
    rate_czk_h = Column(Float, default=500)
    active = Column(Boolean, default=True)

class InvoiceItem(Base):
    __tablename__ = "invoice_items"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    step_id = Column(Integer, ForeignKey("project_steps.id"), nullable=True)
    doc_type = Column(String(30), nullable=False)  # posouzeni|zaloha|final|final_discount
    doc_number = Column(String(30), nullable=True)
    description = Column(String(255), nullable=True)
    amount_czk = Column(Float, default=0)
    status = Column(String(20), default="draft")
    created_at = Column(DateTime, default=datetime.utcnow)

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    step_id = Column(Integer, ForeignKey("project_steps.id"), nullable=True)
    text = Column(String(500), nullable=False)
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Setting(Base):
    __tablename__ = "settings"
    key = Column(String(50), primary_key=True)
    value = Column(Text, nullable=True)

_engine = None
_SessionLocal = None

def get_engine(db_path=None):
    global _engine
    if _engine is not None and db_path is None:
        return _engine
    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    url = f"sqlite:///{path}"
    eng = create_engine(url, connect_args={"check_same_thread": False})
    if db_path is None:
        _engine = eng
    return eng

def get_session_factory(db_path=None):
    global _SessionLocal
    if _SessionLocal is not None and db_path is None:
        return _SessionLocal
    eng = get_engine(db_path)
    factory = sessionmaker(bind=eng, autocommit=False, autoflush=False)
    if db_path is None:
        _SessionLocal = factory
    return factory

def _migrate(engine):
    """Migrace původní produkční DB (SQLite) bez ztráty dat.

    Přidá chybějící sloupce na users/projects a provede backfill.
    Nové tabulky vytvoří Base.metadata.create_all (voláno z init_db).
    Je idempotentní — spouští se při každém startu.
    """
    conn = engine.connect()
    try:
        tables = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()}

        def columns_of(tbl):
            return {r[1] for r in conn.execute(text(f"PRAGMA table_info({tbl})")).fetchall()}

        if "users" in tables:
            cols = columns_of("users")
            if "roles_json" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN roles_json TEXT"))
            # backfill roles_json z primární role (single-element pole)
            conn.execute(text("UPDATE users SET roles_json = '[\"' || role || '\"]' WHERE roles_json IS NULL"))

        if "projects" in tables:
            cols = columns_of("projects")
            if "type" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN type VARCHAR(30)"))
            if "status" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN status VARCHAR(20)"))
            if "tech" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN tech VARCHAR(255)"))
            if "customer_email" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN customer_email VARCHAR(255)"))
            if "customer_phone" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN customer_phone VARCHAR(255)"))
            if "active" not in cols:
                # NOT NULL + konstantní default je v SQLite povolený ADD COLUMN
                conn.execute(text(
                    "ALTER TABLE projects ADD COLUMN active BOOLEAN NOT NULL DEFAULT 1"))
            # zadni sloupce bez backfillu — starych 36 zakazek kontakt proste neni
            conn.execute(text("UPDATE projects SET type = 'ostatni' WHERE type IS NULL OR type = ''"))
            conn.execute(text("UPDATE projects SET status = 'lead' WHERE status IS NULL OR status = ''"))

        if "notifications" in tables:
            cols = columns_of("notifications")
            if "step_id" not in cols:
                conn.execute(text("ALTER TABLE notifications ADD COLUMN step_id INTEGER"))

        if "materials" in tables:
            cols = columns_of("materials")
            if "category" not in cols:
                conn.execute(text("ALTER TABLE materials ADD COLUMN category VARCHAR(30) DEFAULT 'other'"))
            if "visibility" not in cols:
                conn.execute(text("ALTER TABLE materials ADD COLUMN visibility VARCHAR(20) DEFAULT 'public'"))
            if "rating" not in cols:
                conn.execute(text("ALTER TABLE materials ADD COLUMN rating FLOAT"))
            if "supplier" not in cols:
                conn.execute(text("ALTER TABLE materials ADD COLUMN supplier VARCHAR(120)"))
            if "is_default" not in cols:
                conn.execute(text("ALTER TABLE materials ADD COLUMN is_default BOOLEAN DEFAULT 0"))
            if "system_kwp" not in cols:
                conn.execute(text("ALTER TABLE materials ADD COLUMN system_kwp FLOAT"))
            if "system_battery_kwh" not in cols:
                conn.execute(text("ALTER TABLE materials ADD COLUMN system_battery_kwh FLOAT"))

        # --- Úklid sirotků -------------------------------------------------
        # SQLite má `PRAGMA foreign_keys` defaultně OFF (backend ho nikde
        # nezapíná), takže `ON DELETE CASCADE` na project_users nikdy nevyplní
        # a `delete_project` nechával řádky odkazující do prázdna. Ty pak
        # blokovaly save_analysis na UNIQUE (project_id, user_id):
        # projects MAX(id)=36 a users MAX(id)=6 -> další INSERT byl přesně
        # sirotek (37, 7). Mažeme VÝHRADNĚ to, co foreign_key_check označí
        # za porušené — nic jiného.
        orphan_rows = conn.execute(text("PRAGMA foreign_key_check")).fetchall()
        if orphan_rows:
            by_table: dict = {}
            for row in orphan_rows:        # (table, rowid, parent, fkid)
                by_table.setdefault(row[0], set()).add(row[1])
            for table, rowids in by_table.items():
                # název tabulky pochází z DB, ne od uživatele — stejně ověř
                if not table.isidentifier():
                    continue
                stmt = text(
                    f"DELETE FROM {table} WHERE rowid IN :rowids"
                ).bindparams(bindparam("rowids", expanding=True))
                conn.execute(stmt, {"rowids": sorted(rowids)})

        conn.commit()
    finally:
        conn.close()


RATE_CARD_SEED = [
    # admin sazby (Kč/h) — pro kancelářské role
    *[{"role": r, "kind": "admin", "rate_czk_h": 500} for r in
      ("sales", "designer", "buyer", "subsidy", "connection", "warehouse")],
    # práce (montáž/revize) — placeholder, kalibruje se
    {"role": "roofer", "kind": "work", "rate_czk_h": 450},
    {"role": "electrician", "kind": "work", "rate_czk_h": 500},
    {"role": "inspector", "kind": "work", "rate_czk_h": 550},
    {"role": "sales", "kind": "work", "rate_czk_h": 500},
]


def _seed_rate_cards(db):
    if db.query(RateCard).count() == 0:
        for row in RATE_CARD_SEED:
            db.add(RateCard(**row))
        db.commit()


# Návrh cen k ruční kalibraci v UI. Výchozí sestava
# 19× PAN-550 + INV-10 + BAT-10 + INS-MONT = 300 000 Kč je nový základ
# ekonomiky (bylo 350 000). Konkrétní typy dodavatelů se neseedují.
MATERIAL_SEED = [
    {"code": "PAN-450", "name": "Panel 450 Wp", "category": "panel",
     "rating": 450, "price": 2000, "visibility": "public", "is_default": False},
    {"code": "PAN-550", "name": "Panel 550 Wp", "category": "panel",
     "rating": 550, "price": 2500, "visibility": "public", "is_default": True},
    {"code": "PAN-615", "name": "Panel 615 Wp", "category": "panel",
     "rating": 615, "price": 2800, "visibility": "public", "is_default": False},
    {"code": "INV-10", "name": "Měnič 10 kW", "category": "inverter",
     "rating": 10, "price": 45000, "visibility": "public", "is_default": True},
    {"code": "INV-15", "name": "Měnič 15 kW", "category": "inverter",
     "rating": 15, "price": 62000, "visibility": "public", "is_default": False},
    {"code": "INV-20", "name": "Měnič 20 kW", "category": "inverter",
     "rating": 20, "price": 78000, "visibility": "public", "is_default": False},
    {"code": "BAT-5", "name": "Baterie 5 kWh", "category": "battery",
     "rating": 5, "price": 48000, "visibility": "public", "is_default": False},
    {"code": "BAT-10", "name": "Baterie 10 kWh", "category": "battery",
     "rating": 10, "price": 87500, "visibility": "public", "is_default": True},
    {"code": "BAT-15", "name": "Baterie 15 kWh", "category": "battery",
     "rating": 15, "price": 125000, "visibility": "public", "is_default": False},
    {"code": "INS-MONT", "name": "Montáž instalace", "category": "install",
     "rating": None, "price": 120000, "visibility": "public", "is_default": True},
    {"code": "SYS-10-10", "name": "FVE 10 kWp / 10 kWh", "category": "system",
     "rating": None, "price": 300000, "visibility": "public", "is_default": True,
     "system_kwp": 10.0, "system_battery_kwh": 10.0},
    {"code": "SYS-15-10", "name": "FVE 15 kWp / 10 kWh", "category": "system",
     "rating": None, "price": 349000, "visibility": "public", "is_default": False,
     "system_kwp": 15.0, "system_battery_kwh": 10.0},
]


def _seed_materials(db):
    """Idempotentní seed ceníku — jen když je tabulka prázdná.

    Ceny jdou přes `set_material_price`, takže vznikne i historie
    (`material_prices`) a `materials.price` je s ní konzistentní.
    """
    if db.query(Material).count() > 0:
        return
    from .materials_service import set_material_price

    for row in MATERIAL_SEED:
        data = dict(row)
        price = data.pop("price")
        m = Material(**data)
        db.add(m)
        db.flush()
        set_material_price(db, m.id, price, date(2020, 1, 1), created_by=None)
    db.commit()


def detach_step_materials(db, step_id: int) -> None:
    """Uvolní vazbu materiálů na rušený krok.

    `project_materials.step_id` je nullable a řádek materiálu patří projektu,
    ne kroku — vazba se tedy jen uvolní a evidence zůstává. Bez toho by po
    smazání kroku zůstal sirotek.
    """
    db.query(ProjectMaterial).filter(ProjectMaterial.step_id == step_id).update(
        {ProjectMaterial.step_id: None}, synchronize_session=False)


def _seed_settings(db):
    if db.query(Setting).filter(Setting.key == "margin").first() is None:
        db.add(Setting(key="margin", value="0.30"))
        db.commit()


def init_db(db_path=None):
    eng = get_engine(db_path)
    _migrate(eng)
    Base.metadata.create_all(bind=eng)
    # seed default users (admin + antelon + customer demo)
    # env overrides, jinak výchozí hodnoty pro snadný test
    defaults = [
        (os.environ.get("RG_ADMIN_EMAIL", "admin@antelon.local"),
         os.environ.get("RG_ADMIN_PASSWORD", "Admin123!"),
         "admin"),
        (os.environ.get("RG_ANTELON_EMAIL", "antelon@antelon.local"),
         os.environ.get("RG_ANTELON_PASSWORD", "Antelon123!"),
         "antelon"),
        (os.environ.get("RG_CUSTOMER_EMAIL", "zakaznik@antelon.local"),
         os.environ.get("RG_CUSTOMER_PASSWORD", "Zakaznik123!"),
         "customer"),
    ]
    Session = get_session_factory(db_path)
    db = Session()
    try:
        for email, passwd, role in defaults:
            if not email or not passwd:
                continue
            exists = db.query(User).filter(User.email == email).first()
            if not exists:
                from .auth import hash_password
                u = User(email=email, password_hash=hash_password(passwd), role=role)
                u.roles_json = json.dumps([role])
                db.add(u)
        db.commit()
        # seed ukázkové projekty pokud prázdné (pro demo)
        if db.query(Project).count() == 0:
            admin = db.query(User).filter(User.role == "admin").first() or db.query(User).first()
            owner_id = admin.id if admin else None
            examples = [
                ("Pentagon - administrativni budova", "Pentagon s.r.o.", "Ukazkovy projekt - Shelly 14.7.-13.8.2026, 25 kWp + 15-20 kWh"),
                ("Lakoplast - provozovna", "Lakoplast s.r.o.", "Ukazkovy projekt - Shelly 01/2025, denne spotreby"),
            ]
            for name, cust, desc in examples:
                if not db.query(Project).filter(Project.name == name).first():
                    p = Project(
                        name=name,
                        customer_name=cust,
                        description=desc,
                        owner_id=owner_id,
                        share_code=generate_share_code(),
                        antelon_params_json=json.dumps({"kwp": 25, "battery_kwh": 15, "soc_min_pct": 30, "texts": {}}),
                        fve_params_json=json.dumps({}),
                    )
                    # ensure unique share_code
                    while db.query(Project).filter(Project.share_code == p.share_code).first():
                        p.share_code = generate_share_code()
                    db.add(p)
            db.commit()
        # sazby (RateCard) — idempotentní seed
        _seed_rate_cards(db)
        # ceník materiálů — idempotentní seed (část 3)
        _seed_materials(db)
        # číselník nastavení (marže ekonomiky) — idempotentní seed (M4)
        _seed_settings(db)
        # šablony pipeline + kroky — idempotentní seed (M1.2)
        from .pipeline_seed import ensure_pipeline_templates
        ensure_pipeline_templates(db)
    except Exception as e:
        print(f"seed users error: {e}")
        import traceback; traceback.print_exc()
    finally:
        db.close()
    return eng

def get_db():
    Session = get_session_factory()
    db = Session()
    try:
        yield db
    finally:
        db.close()

def generate_share_code(length=8):
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))
