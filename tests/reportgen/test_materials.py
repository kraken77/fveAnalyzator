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


# ---------- set_material_price / current_price ----------

def _new_material(db):
    from reportgen.storage import Material

    m = Material(code="X-PRICE", name="Cenověný", unit="ks", price=0)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def test_set_material_price_updates_denormalized_price(db):
    from datetime import date

    from reportgen.materials_service import current_price, set_material_price

    m = _new_material(db)
    set_material_price(db, m.id, 100.0, date(2026, 1, 1), created_by=None)
    db.commit()
    assert current_price(db, m.id, date(2026, 6, 1)) == 100.0

    set_material_price(db, m.id, 130.0, date(2026, 7, 1), created_by=None)
    db.commit()
    assert current_price(db, m.id, date(2026, 6, 1)) == 100.0   # stará cena do 30. 6.
    assert current_price(db, m.id, date(2026, 7, 1)) == 130.0
    db.refresh(m)
    assert m.price == 130.0


def test_set_material_price_closes_previous_open_row(db):
    from datetime import date

    from reportgen.storage import MaterialPrice
    from reportgen.materials_service import set_material_price

    m = _new_material(db)
    set_material_price(db, m.id, 100.0, date(2026, 1, 1))
    set_material_price(db, m.id, 130.0, date(2026, 7, 1))
    db.commit()

    rows = (db.query(MaterialPrice)
            .filter(MaterialPrice.material_id == m.id)
            .order_by(MaterialPrice.valid_from).all())
    assert len(rows) == 2
    assert rows[0].price == 100.0 and rows[0].valid_to == date(2026, 6, 30)
    assert rows[1].price == 130.0 and rows[1].valid_to is None
    assert sum(1 for r in rows if r.valid_to is None) == 1


def test_set_material_price_same_day_reprice_wins(db):
    from datetime import date

    from reportgen.materials_service import current_price, set_material_price

    m = _new_material(db)
    set_material_price(db, m.id, 100.0, date(2026, 1, 1))
    set_material_price(db, m.id, 150.0, date(2026, 1, 1))
    db.commit()
    assert current_price(db, m.id, date(2026, 1, 1)) == 150.0


# ---------- seed ----------

def test_seed_materials_count_and_idempotent(db):
    from reportgen.storage import Material, _seed_materials

    assert db.query(Material).count() == 12
    _seed_materials(db)
    db.expire_all()
    assert db.query(Material).count() == 12


def test_seed_sum_is_exactly_300k(db):
    from reportgen.storage import Material
    from reportgen.materials_service import derive_qty

    by_code = {m.code: m for m in db.query(Material).all()}
    assert len(by_code) == 12
    params = {"kwp": 10.0, "battery_capacity": 10.0}
    total = (
        by_code["PAN-550"].price * derive_qty("panel", by_code["PAN-550"].rating, params)
        + by_code["INV-10"].price * derive_qty("inverter", by_code["INV-10"].rating, params)
        + by_code["BAT-10"].price * derive_qty("battery", by_code["BAT-10"].rating, params)
        + by_code["INS-MONT"].price * derive_qty("install", by_code["INS-MONT"].rating, params)
    )
    assert total == 300_000, f"kontrolní součet je {total}, čekáno 300000"


def test_seed_defaults_and_system_fields(db):
    from reportgen.storage import Material

    by_code = {m.code: m for m in db.query(Material).all()}
    for code in ("PAN-550", "INV-10", "BAT-10", "INS-MONT", "SYS-10-10"):
        assert by_code[code].is_default is True, code
    assert all(m.visibility == "public" for m in by_code.values())
    assert by_code["SYS-10-10"].system_kwp == 10.0
    assert by_code["SYS-10-10"].system_battery_kwh == 10.0
    assert by_code["SYS-15-10"].system_kwp == 15.0


def test_seed_creates_price_rows(db):
    from datetime import date

    from reportgen.storage import Material, MaterialPrice
    from reportgen.materials_service import current_price

    for m in db.query(Material).all():
        count = db.query(MaterialPrice).filter(MaterialPrice.material_id == m.id).count()
        assert count >= 1, f"{m.code} nemá cenový řádek"
        assert current_price(db, m.id, date(2026, 10, 6)) == m.price


def test_seed_materials_idempotent_on_second_init(db_path):
    from reportgen import storage
    from reportgen.storage import Material
    from sqlalchemy.orm import sessionmaker

    storage.init_db(db_path)
    storage.init_db(db_path)
    Session = sessionmaker(bind=storage.get_engine(db_path))
    s = Session()
    try:
        assert s.query(Material).count() == 12
    finally:
        s.close()


# ---------- compute_investment_cost ----------

def test_compute_investment_cost_prefers_snapshot():
    from reportgen.materials_service import compute_investment_cost

    bom = [{"line_total": 250000.0}, {"line_total": 50000.0}]
    assert compute_investment_cost({"fve_materials": bom,
                                    "investment_cost": 999999}) == 300000.0


def test_compute_investment_cost_explicit_when_no_snapshot():
    from reportgen.materials_service import compute_investment_cost

    assert compute_investment_cost({"investment_cost": 275000.0}) == 275000.0


def test_compute_investment_cost_legacy_fallback():
    from reportgen.materials_service import compute_investment_cost

    assert compute_investment_cost({}) == 350000.0
    # prázdný snímek NENÍ nula — spadne na explicitní/legacy
    assert compute_investment_cost({"fve_materials": []}) == 350000.0

# ---------- GET /fve-analysis/materials ----------

def _insert_material(db_path, code, name, price=100.0, visibility="public",
                     category="other", rating=None):
    """Vloží materiál přímo do DB — testuje endpoint nezávisle na CRUD (Task 7)."""
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "INSERT INTO materials (code, name, unit, price, active, category, "
            "visibility, rating, is_default) VALUES (?, ?, 'ks', ?, 1, ?, ?, ?, 0)",
            (code, name, price, category, visibility, rating))
        mid = con.execute("SELECT id FROM materials WHERE code = ?", (code,)).fetchone()[0]
        con.commit()
    finally:
        con.close()
    return mid


def test_fve_materials_customer_sees_only_public(client, admin_token, customer_token, db_path):
    _insert_material(db_path, "X-PUB", "Veřejný", visibility="public")
    _insert_material(db_path, "X-INT", "Interní", visibility="internal")

    adm = {m["code"] for m in client.get("/api/v1/fve-analysis/materials",
                                         headers=_auth(admin_token)).json()["materials"]}
    cus = {m["code"] for m in client.get("/api/v1/fve-analysis/materials",
                                         headers=_auth(customer_token)).json()["materials"]}
    assert {"X-PUB", "X-INT"} <= adm
    assert "X-PUB" in cus
    assert "X-INT" not in cus


def test_fve_materials_excludes_inactive(client, admin_token, db_path):
    mid = _insert_material(db_path, "X-OFF", "Vypnutý")
    con = sqlite3.connect(db_path)
    try:
        con.execute("UPDATE materials SET active = 0 WHERE id = ?", (mid,))
        con.commit()
    finally:
        con.close()
    codes = {m["code"] for m in client.get("/api/v1/fve-analysis/materials",
                                           headers=_auth(admin_token)).json()["materials"]}
    assert "X-OFF" not in codes


def test_fve_materials_response_shape(client, admin_token):
    rows = client.get("/api/v1/fve-analysis/materials",
                      headers=_auth(admin_token)).json()["materials"]
    assert rows, "seed musí nabídnout materiály"
    assert set(rows[0].keys()) == {
        "id", "code", "name", "category", "visibility", "rating", "unit",
        "price", "is_default", "system_kwp", "system_battery_kwh",
    }


# ---------- CRUD materiálů a RBAC ----------

def _add_user(db_path, email, role):
    """Uživatel mimo seed — API na vytvoření uživatele neexistuje."""
    from reportgen.auth import hash_password

    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "INSERT INTO users (email, password_hash, role, roles_json) "
            "VALUES (?, ?, ?, ?)",
            (email, hash_password("Xx123456!"), role, json.dumps([role])))
        con.commit()
    finally:
        con.close()


def _create_material(client, token, code="X-NEW", **over):
    body = {"code": code, "name": "Nový materiál", "unit": "ks",
            "price": 1234.0, "category": "panel", "rating": 550}
    body.update(over)
    return client.post("/api/v1/materials", json=body, headers=_auth(token))


def test_buyer_cannot_write_materials(client, admin_token, db_path):
    _add_user(db_path, "buyer-mat@test.local", "buyer")
    tok = _login(client, "buyer-mat@test.local", "Xx123456!")
    assert _create_material(client, tok, code="X-BUY").status_code == 403


def test_admin_creates_material_with_price_history(client, admin_token, db_path):
    r = _create_material(client, admin_token, code="X-ADM", visibility="internal")
    assert r.status_code == 200, r.text
    assert r.json()["id"]
    assert r.json()["category"] == "panel"
    assert r.json()["visibility"] == "internal"

    con = sqlite3.connect(db_path)
    try:
        mid = r.json()["id"]
        price = con.execute("SELECT price FROM materials WHERE id = ?", (mid,)).fetchone()[0]
        rows = con.execute("SELECT COUNT(*) FROM material_prices WHERE material_id = ?",
                           (mid,)).fetchone()[0]
    finally:
        con.close()
    assert price == 1234.0
    assert rows == 1


def test_admin_updates_and_soft_deletes_material(client, admin_token, db_path):
    mid = _create_material(client, admin_token, code="X-UPD").json()["id"]

    upd = client.put(f"/api/v1/materials/{mid}",
                     json={"name": "Přejmenováno", "visibility": "internal"},
                     headers=_auth(admin_token))
    assert upd.status_code == 200, upd.text
    assert upd.json()["name"] == "Přejmenováno"

    dele = client.delete(f"/api/v1/materials/{mid}", headers=_auth(admin_token))
    assert dele.status_code == 200, dele.text

    listed = client.get("/api/v1/materials", headers=_auth(admin_token)).json()
    row = next(m for m in listed if m["id"] == mid)
    assert row["active"] is False
    # soft-smazaný materiál se nenabízí ve FVE formuláři
    fve = client.get("/api/v1/fve-analysis/materials",
                     headers=_auth(admin_token)).json()["materials"]
    assert all(m["id"] != mid for m in fve)


def test_price_endpoint_closes_previous_row(client, admin_token, db_path):
    mid = _create_material(client, admin_token, code="X-PR", price=1000.0).json()["id"]

    r = client.post(f"/api/v1/materials/{mid}/price",
                    json={"price": 2000.0, "valid_from": "2026-08-01"},
                    headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["price"] == 2000.0

    con = sqlite3.connect(db_path)
    try:
        price = con.execute("SELECT price FROM materials WHERE id = ?", (mid,)).fetchone()[0]
        open_rows = con.execute(
            "SELECT COUNT(*) FROM material_prices WHERE material_id = ? AND valid_to IS NULL",
            (mid,)).fetchone()[0]
    finally:
        con.close()
    assert price == 2000.0
    assert open_rows == 1


def test_buyer_cannot_set_price_or_delete(client, admin_token, db_path):
    mid = _create_material(client, admin_token, code="X-BUY2").json()["id"]
    _add_user(db_path, "buyer2-mat@test.local", "buyer")
    tok = _login(client, "buyer2-mat@test.local", "Xx123456!")
    assert client.post(f"/api/v1/materials/{mid}/price", json={"price": 1.0},
                       headers=_auth(tok)).status_code == 403
    assert client.delete(f"/api/v1/materials/{mid}",
                         headers=_auth(tok)).status_code == 403
    assert client.put(f"/api/v1/materials/{mid}", json={"name": "x"},
                      headers=_auth(tok)).status_code == 403
