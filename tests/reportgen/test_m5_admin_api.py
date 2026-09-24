"""M5 — API: economy endpoint, rate-cards, template-step edit (admin)."""

import json

import pytest

from reportgen.storage import Project, User, generate_share_code
from reportgen.pipeline_seed import attach_template


@pytest.fixture
def admin_token(client):
    resp = client.post("/api/v1/auth/login",
                       json={"email": "admin@test.local", "password": "Admin123!"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def mk_user(db, email, role):
    u = User(email=email, password_hash="h", role=role)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def mk_project(db, name="Test", user=None):
    p = Project(name=name, customer_name=name, share_code=generate_share_code(),
                type="ostatni", status="active", owner_id=user.id if user else None,
                fve_params_json=json.dumps({}))
    db.add(p)
    db.commit()
    db.refresh(p)
    attach_template(db, p, "ostatni")
    return p


def test_economy_endpoint(client, admin_token):
    auth = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post("/api/v1/projects", json={"name": "Eco", "customer_name": "Z" },
                       headers=auth)
    assert resp.status_code == 200, resp.text
    pid = resp.json()["id"]
    # attach template, aby existovaly kroky s est. minutami
    a = client.post(f"/api/v1/projects/{pid}/pipeline/attach",
                    json={"template_code": "ostatni"}, headers=auth)
    assert a.status_code == 200, a.text

    r = client.get(f"/api/v1/projects/{pid}/economy", headers=auth)
    assert r.status_code == 200, r.text
    eco = r.json()
    assert "plan" in eco and "actual" in eco
    assert eco["margin"] == 0.30
    # klíče admin_*/work_* — nikdy nesloučené
    assert "total" not in eco["plan"]
    assert set(eco["plan"]) >= {"admin_minutes", "admin_cost", "work_minutes", "work_cost", "total_cost"}
    assert eco["sell"] > 0
    assert eco["sell_actual"] >= 0


def test_economy_endpoint_requires_auth(client):
    r = client.get("/api/v1/projects/1/economy")
    assert r.status_code == 401


def test_rate_cards_list_and_update(client, admin_token):
    auth = {"Authorization": f"Bearer {admin_token}"}
    r = client.get("/api/v1/admin/rate-cards", headers=auth)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) >= 10, rows
    target = next(x for x in rows if x["role"] == "sales" and x["kind"] == "admin")
    rid = target["id"]

    r2 = client.put(f"/api/v1/admin/rate-cards/{rid}",
                    json={"rate_czk_h": 555.0}, headers=auth)
    assert r2.status_code == 200, r2.text
    assert r2.json()["rate_czk_h"] == 555.0


def test_rate_cards_requires_admin(client, admin_token, db):
    sales = mk_user(db, "s@x.cz", "sales")
    from reportgen.auth import create_access_token
    tok = create_access_token({"sub": sales.email, "role": sales.role})
    auth = {"Authorization": f"Bearer {tok}"}
    r = client.get("/api/v1/admin/rate-cards", headers=auth)
    assert r.status_code == 403


def test_template_step_edit(client, admin_token):
    auth = {"Authorization": f"Bearer {admin_token}"}
    tpls = client.get("/api/v1/admin/pipeline-templates", headers=auth).json()
    tid = tpls[0]["id"]
    steps = client.get(f"/api/v1/admin/pipeline-templates/{tid}/steps",
                       headers=auth).json()
    sid = steps[0]["id"]
    old_name = steps[0]["name"]

    r = client.put(f"/api/v1/admin/pipeline-templates/{tid}/steps/{sid}",
                   json={"name": "Upravený krok", "est_admin_minutes": 7}, headers=auth)
    assert r.status_code == 200, r.text

    steps2 = client.get(f"/api/v1/admin/pipeline-templates/{tid}/steps",
                        headers=auth).json()
    row = next(s for s in steps2 if s["id"] == sid)
    assert row["name"] == "Upravený krok"
    assert row["est_admin_minutes"] == 7

    # revert
    client.put(f"/api/v1/admin/pipeline-templates/{tid}/steps/{sid}",
               json={"name": old_name}, headers=auth)