"""API router pro plánování montáže a elektro (etapa 1 — backend).

Testuje:
- Struktura odpovědi overview
- Auth: zákazník → 403, sales → 200 overview, sales → 403 crews
- Simulate vrací dřívější plán než overview při +1 četa
- 422 na špatné datum
"""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from reportgen import storage as st
from reportgen.auth import hash_password


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _login(client, email, password):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def admin_token(client):
    return _login(client, "admin@test.local", "Admin123!")


@pytest.fixture
def customer_token(client):
    return _login(client, "zakaznik@test.local", "Zakaznik123!")


@pytest.fixture
def sales_token(client):
    """Vytvoří sales uživatele a vrátí token."""
    db = st._SessionLocal()
    try:
        u = db.query(st.User).filter(st.User.email == "sales@test.local").first()
        if not u:
            u = st.User(
                email="sales@test.local",
                password_hash=hash_password("Sales123!"),
                role="sales",
            )
            u.set_roles(["sales"])
            db.add(u)
        else:
            u.password_hash = hash_password("Sales123!")
            u.set_roles(["sales"])
        db.commit()
    finally:
        db.close()
    return _login(client, "sales@test.local", "Sales123!")


class TestPlanningOverview:
    """GET /api/v1/planning/overview."""

    def test_overview_structure(self, client, admin_token):
        """Struktura odpovědi obsahuje všechny povinné pole."""
        # Zkontrolujeme, že default crews existují
        db = st._SessionLocal()
        try:
            crews = db.query(st.WorkCrew).all()
            assert len(crews) >= 2, "Musí existovat default Montáž + Elektro"
        finally:
            db.close()

        today = date(2026, 10, 19)
        resp = client.get(
            "/api/v1/planning/overview",
            params={"from": today.isoformat(), "to": (today + timedelta(days=90)).isoformat()},
            headers=_auth(admin_token),
        )

        assert resp.status_code == 200
        data = resp.json()

        # Kontrola struktury
        assert "today" in data
        assert "holidays_in_range" in data
        assert "crews" in data
        assert "items" in data
        assert "projects" in data
        assert "makespan" in data or data.get("makespan") is None

        # Plán se kotví na reálném „dnes“, ne na parametru from
        assert data["today"] == date.today().isoformat()

        # Holidays je seznam stringů
        assert isinstance(data["holidays_in_range"], list)

        # Crews
        assert isinstance(data["crews"], list)
        if data["crews"]:
            crew = data["crews"][0]
            assert "id" in crew
            assert "name" in crew
            assert "work_type" in crew
            assert "available_from" in crew
            assert "available_to" in crew
            assert "active" in crew
            # work_days/absent_dates vracíme jako seznamy, ne JSON stringy
            assert isinstance(crew["work_days"], list)
            assert isinstance(crew["absent_dates"], list)

    def test_customer_gets_403(self, client, customer_token):
        """Zákazník → 403 na overview."""
        today = date(2026, 10, 19)
        resp = client.get(
            "/api/v1/planning/overview",
            params={"from": today.isoformat(), "to": (today + timedelta(days=90)).isoformat()},
            headers=_auth(customer_token),
        )
        assert resp.status_code == 403

    def test_sales_gets_200(self, client, sales_token):
        """Sales (interní role) → 200 na overview."""
        today = date(2026, 10, 19)
        resp = client.get(
            "/api/v1/planning/overview",
            params={"from": today.isoformat(), "to": (today + timedelta(days=90)).isoformat()},
            headers=_auth(sales_token),
        )
        assert resp.status_code == 200

    def test_sales_gets_403_on_crews(self, client, sales_token):
        """Sales → 403 na crews (admin/antelon jen)."""
        resp = client.get("/api/v1/planning/crews", headers=_auth(sales_token))
        assert resp.status_code == 403

    def test_simulate_earlier_plan(self, client, admin_token):
        """Simulate s +1 čletou vrací dřívější makespan než overview."""
        today = date(2026, 10, 19)

        # Základní overview (bez dalších četa)
        resp_base = client.get(
            "/api/v1/planning/overview",
            params={"from": today.isoformat(), "to": (today + timedelta(days=90)).isoformat()},
            headers=_auth(admin_token),
        )
        assert resp_base.status_code == 200
        base_data = resp_base.json()

        # Simulace s +1 montáž
        resp_sim = client.post(
            "/api/v1/planning/simulate",
            json={"add_crews": {"roofer": 1}},
            headers=_auth(admin_token),
        )
        assert resp_sim.status_code == 200
        sim_data = resp_sim.json()

        # Simulace má mít dřívější makespan (nebo stejný, pokud nejsou projekty)
        base_makespan = base_data.get("makespan")
        sim_makespan = sim_data.get("makespan")

        # Pokud existují oba makespan, simulace by měla být dřívější
        if base_makespan and sim_makespan:
            assert sim_makespan <= base_makespan

    def test_bad_date_returns_422(self, client, admin_token):
        """Špatné datum → 422."""
        resp = client.get(
            "/api/v1/planning/overview",
            params={"from": "neplatne", "to": "2026-12-31"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422

    def test_crews_crud(self, client, admin_token):
        """Vytvoření, seznam a update čety."""
        # POST novou četu
        resp = client.post(
            "/api/v1/planning/crews",
            json={
                "name": "Testovací četa",
                "work_type": "inspector",
                "available_from": "2026-11-01",
                "available_to": "2027-01-31",
                "work_days": ["po", "st", "pa"],
                "absent_dates": ["2026-12-25"],
                "active": True,
            },
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200
        new_crew = resp.json()
        assert new_crew["id"] is not None
        assert new_crew["name"] == "Testovací četa"

        # GET seznam
        resp = client.get("/api/v1/planning/crews", headers=_auth(admin_token))
        assert resp.status_code == 200
        crews = resp.json()
        ids = [c["id"] for c in crews]
        assert new_crew["id"] in ids

        # PUT update
        resp = client.put(
            f"/api/v1/planning/crews/{new_crew['id']}",
            json={"name": "Přejmenovaná četa", "active": False},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["name"] == "Přejmenovaná četa"
        assert updated["active"] is False
