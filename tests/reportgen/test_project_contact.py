"""M2 — kontaktni udaje zakazky (customer_email / customer_phone).

Testy jedou na docasne SQLite v tmp_path, ne na data/reportgen.db —
migruje se prazdna/legacy databaze, ne 36 realnych zakazek.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "backend") not in sys.path:
    sys.path.insert(0, str(REPO / "backend"))

from app.reportgen.storage import Project, init_db  # noqa: E402

CONTACT_COLS = ("customer_email", "customer_phone")


def _columns(db_file):
    with sqlite3.connect(db_file) as conn:
        return {r[1] for r in conn.execute("PRAGMA table_info(projects)")}


def test_project_model_has_contact_columns():
    """Kontakt patri zakazce, ne uzivateli — sloupce jsou na Project."""
    names = Project.__table__.columns.keys()
    for col in CONTACT_COLS:
        assert col in names, f"Project chybi sloupec {col}"
    assert Project.__table__.columns[CONTACT_COLS[0]].type.length == 255
    assert all(Project.__table__.columns[c].nullable for c in CONTACT_COLS)


def test_status_comment_mentions_fve_analyza():
    """Stav fve_analyza je petavy stav vedle lead|active|done|cancelled."""
    assert Project.__table__.columns["status"].type.length >= len("fve_analyza")


def test_fresh_db_creates_contact_columns(tmp_path):
    db_file = tmp_path / "fresh.db"
    init_db(str(db_file))
    cols = _columns(db_file)
    for col in CONTACT_COLS:
        assert col in cols, f"chybi {col} v cerstve DB"


def test_migration_adds_contact_columns_to_legacy_db(tmp_path):
    """Legacy tabulka bez sloupcu dostane sloupce, existujici data zustanou."""
    db_file = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_file)
    conn.execute(
        "CREATE TABLE projects (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " name VARCHAR(255) NOT NULL, customer_name VARCHAR(255),"
        " owner_id INTEGER, share_code VARCHAR(16) NOT NULL)"
    )
    conn.execute(
        "INSERT INTO projects (name, customer_name, share_code)"
        " VALUES ('Stara zakazka', 'Petr Novy', 'abc123')"
    )
    conn.commit()
    conn.close()

    assert not (set(CONTACT_COLS) & _columns(db_file)), "predikace selhala"

    init_db(str(db_file))

    cols = _columns(db_file)
    for col in CONTACT_COLS:
        assert col in cols, f"migrace nepridala {col}"

    with sqlite3.connect(db_file) as c:
        row = c.execute(
            "SELECT name, customer_name, share_code, customer_email,"
            " customer_phone FROM projects"
        ).fetchone()
    assert row[0] == "Stara zakazka", "migrace zmenila jmeno"
    assert row[1] == "Petr Novy", "migrace zmenila kontaktni jmeno"
    assert row[2] == "abc123", "migrace zmenila share_code"
    assert row[3] is None, "stary radek musi mit NULL, ne prepisovany udaj"
    assert row[4] is None


def test_migration_is_idempotent(tmp_path):
    """init_db bezi pri kazdem startu — spusteni dvakrat nesmi spadnout."""
    db_file = tmp_path / "twice.db"
    init_db(str(db_file))
    init_db(str(db_file))
    init_db(str(db_file))
    assert set(CONTACT_COLS) <= _columns(db_file)


def test_contact_values_roundtrip(tmp_path):
    """Zapsane udaje se daji precist — jinak by UI nemelo co zobrazit."""
    from app.reportgen.storage import get_session_factory

    db_file = str(tmp_path / "rt.db")
    init_db(db_file)

    db = get_session_factory(db_file)()
    p = Project(name="FVE rozpracovana", share_code="fve0001",
                customer_email="j@example.cz", customer_phone="+420 777 123 456",
                status="fve_analyza")
    db.add(p)
    db.commit()
    db.refresh(p)
    assert p.customer_email == "j@example.cz"
    assert p.customer_phone == "+420 777 123 456"
    assert p.status == "fve_analyza"
    db.close()
