import os
import json
import secrets
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, Float, DateTime, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

Base = declarative_base()

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "..", "data", "reportgen.db")
# Normalize: backend/../data/reportgen.db -> data/reportgen.db
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "reportgen.db"))
# fallback: also support /app/data/reportgen.db inside docker
if not os.path.exists(os.path.dirname(DB_PATH)):
    DB_PATH = "/app/data/reportgen.db"

# Ensure directory exists lazily in init_db

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="customer")  # admin, antelon, customer
    created_at = Column(DateTime, default=datetime.utcnow)

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    customer_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    share_code = Column(String(16), unique=True, nullable=False, index=True)
    antelon_params_json = Column(Text, nullable=True)  # JSON string
    fve_params_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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

def init_db(db_path=None):
    eng = get_engine(db_path)
    Base.metadata.create_all(bind=eng)
    # seed admin if env provided
    admin_email = os.environ.get("RG_ADMIN_EMAIL")
    admin_pass = os.environ.get("RG_ADMIN_PASSWORD")
    jwt_secret = os.environ.get("RG_JWT_SECRET")
    # Only seed if both provided and no admin exists
    if admin_email and admin_pass:
        Session = get_session_factory(db_path)
        db = Session()
        try:
            exists = db.query(User).filter(User.email == admin_email).first()
            if not exists:
                from .auth import hash_password
                u = User(email=admin_email, password_hash=hash_password(admin_pass), role="admin")
                db.add(u)
                db.commit()
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
