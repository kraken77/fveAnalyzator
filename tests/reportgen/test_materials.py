"""Část 3 — ceník materiálů: schéma, ceny s platností, seed, odvození počtů.

Testy sdílejí fixtures z conftest.py (`db`, `db_path`, `client`).
"""
import json
import sqlite3

import pytest


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _login(client, email, password):
    r = client.post("/api/v1/auth/login",
                    json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def admin_token(client):
    return _login(client, "admin@test.local", "Admin123!")


@pytest.fixture
def customer_token(client):
    return _login(client, "zakaznik@test.local", "Zakaznik123!")


def test_material_new_columns_have_defaults(db):
    from reportgen.storage import Material

    m = Material(code="X-1", name="Materiál", unit="ks", price=100)
    db.add(m)
    db.commit()
    db.refresh(m)
    assert m.category == "other"
    assert m.visibility == "public"
    assert m.rating is None
    assert m.supplier is None
    assert m.is_default is False
    assert m.system_kwp is None
    assert m.system_battery_kwh is None


def test_material_price_roundtrip(db):
    from datetime import date

    from reportgen.storage import Material, MaterialPrice

    m = Material(code="X-1", name="Materiál", unit="ks", price=100)
    db.add(m)
    db.commit()
    db.refresh(m)

    row = MaterialPrice(material_id=m.id, price=100.0, valid_from=date(2026, 1, 1))
    db.add(row)
    db.commit()
    db.refresh(row)
    assert row.id
    assert row.valid_to is None
    assert row.created_by is None
    assert row.created_at is not None


def test_migrate_adds_material_columns(db_path):
    """Starší DB s tabulkou materials bez nových sloupců se dorovná v _migrate."""
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE materials (id INTEGER PRIMARY KEY AUTOINCREMENT,
            code VARCHAR(50) NOT NULL UNIQUE, name VARCHAR(200) NOT NULL,
            unit VARCHAR(10), price FLOAT, active BOOLEAN, created_at DATETIME);
    """)
    con.commit()
    con.close()

    from reportgen import storage

    storage.init_db(db_path)

    con = sqlite3.connect(db_path)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(materials)").fetchall()}
    finally:
        con.close()
    for c in ("category", "visibility", "rating", "supplier", "is_default",
              "system_kwp", "system_battery_kwh"):
        assert c in cols, f"chybí sloupec materials.{c}"