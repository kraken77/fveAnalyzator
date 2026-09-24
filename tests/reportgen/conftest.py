"""Shared fixtures for reportgen tests (M1 dispecink).

Path setup: adds <repo>/backend/app to sys.path so `reportgen.*` imports work.
DB fixture: temporary SQLite DB on tmp_path via storage.init_db(db_path).
"""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_APP = REPO_ROOT / "backend" / "app"
if str(BACKEND_APP) not in sys.path:
    sys.path.insert(0, str(BACKEND_APP))

# Ensure tests never touch the real dev/prod DB defaults.
os.environ.setdefault("RG_ADMIN_EMAIL", "admin@test.local")
os.environ.setdefault("RG_ADMIN_PASSWORD", "Admin123!")
os.environ.setdefault("RG_ANTELON_EMAIL", "antelon@test.local")
os.environ.setdefault("RG_ANTELON_PASSWORD", "Antelon123!")
os.environ.setdefault("RG_CUSTOMER_EMAIL", "zakaznik@test.local")
os.environ.setdefault("RG_CUSTOMER_PASSWORD", "Zakaznik123!")

import pytest

from sqlalchemy.orm import sessionmaker

from reportgen import storage


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "reportgen.db")


@pytest.fixture
def engine(db_path):
    """Initialized engine on a fresh temporary DB (seeded by init_db)."""
    return storage.init_db(db_path)


@pytest.fixture
def db(engine):
    """Session bound to the temporary DB."""
    Session = sessionmaker(bind=engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client(db_path):
    """TestClient over the main FastAPI app, backed by a temp DB.

    backend/main.py relies on CWD=backend (relativní sys.path.append), proto
    fixture dočasně chdir do backend a importuje `main` (tak, jak app běží).
    Patches storage globals tak, aby Depends(get_db) šlo do temp DB.
    """
    import os
    import sys

    old_cwd = os.getcwd()
    backend_dir = str(REPO_ROOT / "backend")
    sys.path.insert(0, backend_dir)
    os.chdir(backend_dir)
    try:
        import main as main_app
    finally:
        os.chdir(old_cwd)

    engine = storage.init_db(db_path)
    Session = sessionmaker(bind=engine)

    # backend/main.py importuje storage jako `app.reportgen.storage`
    # -> druhý module objekt se stejnojmennými globals. Patch musí jít do OBOJÍ,
    # jinak by Depends(get_db) v endpointu mířilo do dev DB.
    import sys as _sys
    app_storage = _sys.modules.get("app.reportgen.storage")
    if app_storage is not None and app_storage is not storage:
        app_storage._engine = engine
        app_storage._SessionLocal = Session

    storage._engine = engine
    storage._SessionLocal = Session

    from fastapi.testclient import TestClient

    with TestClient(main_app.app) as c:
        yield c

    storage._engine = None
    storage._SessionLocal = None
    if app_storage is not None and app_storage is not storage:
        app_storage._engine = None
        app_storage._SessionLocal = None