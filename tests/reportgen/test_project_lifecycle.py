"""Bod 1 — ukládání FVE analýzy padá na UNIQUE constraint v project_users.

Kořenová příčina: `PRAGMA foreign_keys` je v SQLite defaultně `OFF` a backend
ho nikde nezapíná, takže `ON DELETE CASCADE` na `project_users` nikdy nevyplní;
`delete_project` nechával sirotčí řádky a ty zablokovaly další uložení.

Task 1 zavádí generický sweep: v `_migrate` smažeme přesně ty řádky, které
`PRAGMA foreign_key_check` označí za porušené.
"""
import json
import sqlite3

import pytest

from reportgen import storage as st


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


def _orphan_counts(db_path):
    """Vrátí {tabulka: počet} sirotčích ŘÁDKŮ s neexistujícím rodičem.

    `PRAGMA foreign_key_check` vrací jedno porušení na každý porušený FK, takže
    jeden řádek se dvěma neplatnými FK se objeví dvakrát. Počítáme proto
    distinct (table, rowid), ne počet porušení.
    """
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        con.close()
    seen = set()
    counts = {}
    for row in rows:            # (table, rowid, parent, fkid)
        key = (row[0], row[1])
        if key in seen:
            continue
        seen.add(key)
        counts[row[0]] = counts.get(row[0], 0) + 1
    return counts


def test_delete_project_deactivates(client, admin_token, db_path):
    """DELETE nesmí projekt smazat — jen deaktivovat.

    Tvrdé mazání by zničilo invoice_items, time_entries a pdf_versions
    (fakturační a docházkové záznamy) a navíc uvolnilo ID, které by znovu
    kolidovalo v project_users.
    """
    r = client.post("/api/v1/fve-analysis", json={
        "params": {"kwp": 10.0},
        "contact": {"name": "Smaž Mě", "email": "smaz@example.cz",
                    "phone": "+420777111222"},
    }, headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    r = client.delete(f"/api/v1/projects/{pid}", headers=_auth(admin_token))
    assert r.status_code == 200, r.text

    con = sqlite3.connect(db_path)
    try:
        row = con.execute("SELECT active FROM projects WHERE id = ?",
                          (pid,)).fetchone()
    finally:
        con.close()
    assert row is not None, "řádek projektu musí zůstat v DB"
    assert row[0] == 0


def test_migrate_sweeps_orphans(db_path):
    """Sirotci v project_users i project_steps zmizí při dalším init_db."""
    st.init_db(db_path)

    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO project_users (project_id, user_id) VALUES (9001, 9001)")
    con.execute("INSERT INTO project_users (project_id, user_id) VALUES (9002, 9002)")
    con.execute("INSERT INTO project_steps (project_id, step_id, status) "
                "VALUES (9003, 9003, 'not_started')")
    con.commit()
    con.close()

    before = _orphan_counts(db_path)
    assert before.get("project_users") == 2
    assert "project_steps" in before

    # další start aplikace
    st.init_db(db_path)

    assert _orphan_counts(db_path) == {}


def test_migrate_does_not_touch_valid_rows(client, admin_token, db_path):
    """Sweep nesmí smazat nic, co má rodiče."""
    st.init_db(db_path)
    r = client.post("/api/v1/fve-analysis", json={
        "params": {"kwp": 10.0},
        "contact": {"name": "Platný", "email": "platny@example.cz",
                    "phone": "+420777123456"},
    }, headers=_auth(admin_token))
    assert r.status_code == 200, r.text

    before = _orphan_counts(db_path)
    st.init_db(db_path)
    after = _orphan_counts(db_path)

    con = sqlite3.connect(db_path)
    left = con.execute("SELECT COUNT(*) FROM project_users").fetchone()[0]
    con.close()
    assert left >= 1
    assert before == after == {}


def test_init_db_on_fresh_path_does_not_crash(tmp_path):
    """Sweep nesmí spadnout na DB, kde ještě žádné tabulky nejsou.

    `_migrate` běží PŘED `create_all`, takže na prvním startu je seznam
    tabulek prázdný.
    """
    fresh = str(tmp_path / "fresh" / "reportgen.db")
    st.init_db(db_path=fresh)
    con = sqlite3.connect(fresh)
    try:
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        con.close()


def _saved_project(client, token, email="seznam@example.cz", name="Test"):
    r = client.post("/api/v1/fve-analysis", json={
        "params": {"kwp": 10.0},
        "contact": {"name": name, "email": email, "phone": "+420777123456"},
    }, headers=_auth(token))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_deactivated_project_disappears_from_list(client, admin_token):
    pid = _saved_project(client, admin_token)
    listed = client.get("/api/v1/projects", headers=_auth(admin_token)).json()
    assert any(p["id"] == pid for p in listed)

    client.delete(f"/api/v1/projects/{pid}", headers=_auth(admin_token))

    listed = client.get("/api/v1/projects", headers=_auth(admin_token)).json()
    assert all(p["id"] != pid for p in listed)


def test_deactivated_project_detail_is_404(client, admin_token):
    pid = _saved_project(client, admin_token, email="detail@example.cz")
    client.delete(f"/api/v1/projects/{pid}", headers=_auth(admin_token))

    r = client.get(f"/api/v1/projects/{pid}", headers=_auth(admin_token))
    assert r.status_code == 404, r.text


def test_deactivated_project_hidden_from_customer(client, admin_token,
                                                   customer_token, db_path):
    """Zákazník vidí svůj projekt přes project_users — i tam musí filtr platit.

    Kontaktní e-mail analyzuje `EmailStr`, který odmítá rezervovanou doménu
    `.local` (konfigurační e-mail zákazníka v conftest). Vazbu zákazník↔projekt
    proto založíme přímo v `project_users`, stejně jako to dělá produkční
    `POST /fve-analysis`.
    """
    pid = _saved_project(client, admin_token, email="zakaznik@example.cz",
                         name="Zákazníkův")
    con = sqlite3.connect(db_path)
    try:
        uid = con.execute("SELECT id FROM users WHERE email = ?",
                          ("zakaznik@test.local",)).fetchone()[0]
        con.execute("INSERT INTO project_users (project_id, user_id) "
                    "VALUES (?, ?)", (pid, uid))
        con.commit()
    finally:
        con.close()

    assert any(p["id"] == pid for p in
               client.get("/api/v1/projects", headers=_auth(customer_token)).json())

    client.delete(f"/api/v1/projects/{pid}", headers=_auth(admin_token))

    assert all(p["id"] != pid for p in
               client.get("/api/v1/projects", headers=_auth(customer_token)).json())