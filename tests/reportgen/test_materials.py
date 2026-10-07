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


# ---------- derive_qty ----------

def test_derive_qty_panel_rounds_up():
    from reportgen.materials_service import derive_qty

    assert derive_qty("panel", 550, {"kwp": 10.0}) == 19   # ceil(18.18)
    assert derive_qty("panel", 450, {"kwp": 10.0}) == 23   # ceil(22.22)
    assert derive_qty("panel", 615, {"kwp": 10.0}) == 17   # ceil(16.26)


def test_derive_qty_inverter_and_battery():
    from reportgen.materials_service import derive_qty

    assert derive_qty("inverter", 10, {"kwp": 10.0}) == 1
    assert derive_qty("inverter", 10, {"kwp": 15.0}) == 2
    assert derive_qty("battery", 10, {"kwp": 10.0, "battery_capacity": 10.0}) == 1
    assert derive_qty("battery", 5, {"kwp": 10.0, "battery_capacity": 12.0}) == 3


def test_derive_qty_install_system_other_is_one():
    from reportgen.materials_service import derive_qty

    assert derive_qty("install", None, {}) == 1
    assert derive_qty("system", None, {}) == 1
    assert derive_qty("other", None, {}) == 1


def test_derive_qty_missing_rating_is_zero():
    from reportgen.materials_service import derive_qty

    assert derive_qty("panel", None, {"kwp": 10.0}) == 0
    assert derive_qty("inverter", None, {"kwp": 10.0}) == 0
    assert derive_qty("battery", None, {"battery_capacity": 10.0}) == 0


def test_derive_qty_defaults_kwp_to_ten():
    from reportgen.materials_service import derive_qty

    assert derive_qty("panel", 550, {}) == 19