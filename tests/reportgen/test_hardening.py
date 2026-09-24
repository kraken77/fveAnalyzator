"""Hardening po fresh-context review (P1–P6).

- P1/P2: multi-role RBAC — interní role (sales…) mají přístup ke všem zakázkám;
         uživatel s roles ["sales","admin"] se chová jako admin (has_role).
- P3: remove_step maže jen notifikace daného kroku (ne celého projektu).
- P4: review-ai odmítne AI výsledek cizího projektu/kroku (IDOR).
- P5: AI krok s neschváleným draftem nejde dokončit přes complete.
- P6: seed fáze/est_work souhlasí s tabulkou plánu M1.2.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "backend"))

from reportgen.storage import Notification, PipelineStep, Project, ProjectStep, User
from reportgen.pipeline_seed import attach_template
from reportgen.pipeline import can_transition, transition


@pytest.fixture
def admin_token(client):
    resp = client.post("/api/v1/auth/login",
                       json={"email": "admin@test.local", "password": "Admin123!"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
def sales_token(client, admin_token):
    resp = client.post("/api/v1/auth/register",
                       json={"email": "sales@test.local", "password": "Sales123!", "role": "customer"})
    assert resp.status_code == 200, resp.text
    uid = resp.json()["user"]["id"]
    auth = {"Authorization": f"Bearer {admin_token}"}
    r = client.put(f"/api/v1/admin/users/{uid}/roles", json={"roles": ["sales"]}, headers=auth)
    assert r.status_code == 200, r.text
    login = client.post("/api/v1/auth/login",
                        json={"email": "sales@test.local", "password": "Sales123!"})
    return login.json()["access_token"]


def attach(client, token, pid, template="rd"):
    auth = {"Authorization": f"Bearer {token}"}
    resp = client.post(f"/api/v1/projects/{pid}/pipeline/attach",
                       json={"template_code": template}, headers=auth)
    assert resp.status_code == 200, resp.text
    return client.get(f"/api/v1/projects/{pid}/pipeline", headers=auth).json()


def mk_project_via_api(client, token, name="Hard test"):
    resp = client.post("/api/v1/projects", headers={"Authorization": f"Bearer {token}"},
                       json={"name": name, "customer_name": "Zákazník"})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


# ---------- P1/P2: RBAC ----------

def test_sales_can_open_pipeline_and_see_all_projects(client, admin_token, sales_token):
    pid1 = mk_project_via_api(client, admin_token, "Zakazka A")
    pid2 = mk_project_via_api(client, admin_token, "Zakazka B")
    auth = {"Authorization": f"Bearer {sales_token}"}

    # tabule: sales vidí obě zakázky
    resp = client.get("/api/v1/projects", headers=auth)
    assert resp.status_code == 200, resp.text
    names = [p["name"] for p in resp.json()]
    assert "Zakazka A" in names and "Zakazka B" in names

    # a otevře pipeline detail (attach dělá admin, sales jen čte)
    attach(client, admin_token, pid1)
    resp = client.get(f"/api/v1/projects/{pid1}/pipeline", headers=auth)
    assert resp.status_code == 200, resp.text
    view = resp.json()
    assert len(view["steps"]) >= 55

    # přiřazení kroku dělá admin -> assigned_name v pohledu
    s0 = view["steps"][0]
    auth_admin = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(f"/api/v1/projects/{pid1}/steps/{s0['id']}/transition",
                       json={"action": "plan", "assigned_user_id": 1},
                       headers=auth_admin)
    assert resp.status_code == 200, resp.text
    view2 = client.get(f"/api/v1/projects/{pid1}/pipeline", headers=auth).json()
    assert view2["steps"][0]["assigned_user_id"] == 1
    assert "assigned_name" in view2["steps"][0]


def test_multi_role_user_with_admin_role_gets_admin_capabilities(client, admin_token):
    resp = client.post("/api/v1/auth/register",
                       json={"email": "dual@test.local", "password": "Dual123!", "role": "customer"})
    assert resp.status_code == 200, resp.text
    uid = resp.json()["user"]["id"]
    auth_admin = {"Authorization": f"Bearer {admin_token}"}
    r = client.put(f"/api/v1/admin/users/{uid}/roles",
                   json={"roles": ["sales", "admin"]}, headers=auth_admin)
    assert r.status_code == 200, r.text
    login = client.post("/api/v1/auth/login",
                        json={"email": "dual@test.local", "password": "Dual123!"})
    token = login.json()["access_token"]
    assert login.json()["user"]["roles"] == ["sales", "admin"]

    # primární role je sales, ale has_role("admin") platí -> admin operace fungují
    resp = client.post("/api/v1/projects", headers={"Authorization": f"Bearer {token}"},
                       json={"name": "DualAdmin", "customer_name": "Z"})
    assert resp.status_code == 200, resp.text
    resp = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text


def test_customer_still_isolated_to_owned(client, admin_token):
    pid = mk_project_via_api(client, admin_token, "Cizi projekt")
    resp = client.post("/api/v1/auth/register",
                       json={"email": "zak@test.local", "password": "Zak12345!", "role": "customer"})
    assert resp.status_code == 200, resp.text
    login = client.post("/api/v1/auth/login",
                        json={"email": "zak@test.local", "password": "Zak12345!"})
    token = login.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/v1/projects", headers=auth)
    assert resp.status_code == 200
    assert all(p["name"] != "Cizi projekt" for p in resp.json())

    resp = client.get(f"/api/v1/projects/{pid}/pipeline", headers=auth)
    assert resp.status_code == 403, resp.text  # cizí projekt zákazníkovi nepřístupný


# ---------- P3: remove_step ----------

def test_remove_step_keeps_notifications_of_other_steps(client, admin_token, db):
    pid = mk_project_via_api(client, admin_token)
    view = attach(client, admin_token, pid)
    auth = {"Authorization": f"Bearer {admin_token}"}
    s0, s1 = view["steps"][0], view["steps"][1]
    admin_id = db.query(User).filter(User.role == "admin").first().id

    # plan s0, begin s0, complete s0 → plan s1
    resp = client.post(f"/api/v1/projects/{pid}/steps/{s0['id']}/transition",
                       json={"action": "plan", "assigned_user_id": admin_id}, headers=auth)
    assert resp.status_code == 200, resp.text
    resp = client.post(f"/api/v1/projects/{pid}/steps/{s0['id']}/transition",
                       json={"action": "begin"}, headers=auth)
    assert resp.status_code == 200, resp.text
    resp = client.post(f"/api/v1/projects/{pid}/steps/{s0['id']}/transition",
                       json={"action": "complete"}, headers=auth)
    assert resp.status_code == 200, resp.text
    resp = client.post(f"/api/v1/projects/{pid}/steps/{s1['id']}/transition",
                       json={"action": "plan", "assigned_user_id": admin_id}, headers=auth)
    assert resp.status_code == 200, resp.text

    # notifikace nesou step_id
    step_linked = [n for n in db.query(Notification).all() if n.step_id is not None]
    assert len(step_linked) >= 2

    # odstranění kroku s0 nesmaže notifikaci kroku s1
    resp = client.post(f"/api/v1/projects/{pid}/steps/{s0['id']}/admin",
                       json={"action": "remove_step"}, headers=auth)
    assert resp.status_code == 200, resp.text
    remaining = db.query(Notification).filter(Notification.step_id.isnot(None)).all()
    assert len(remaining) == 1
    assert remaining[0].step_id == s1["id"]


# ---------- P4: review-ai IDOR ----------

def test_review_ai_rejects_result_of_other_project(client, admin_token):
    pid_a = mk_project_via_api(client, admin_token, "Projekt A")
    pid_b = mk_project_via_api(client, admin_token, "Projekt B")
    auth = {"Authorization": f"Bearer {admin_token}"}

    view_a = attach(client, admin_token, pid_a)
    view_b = attach(client, admin_token, pid_b)
    navrh_a = next(s for s in view_a["steps"] if s["code"] == "navrh_fve")
    navrh_b = next(s for s in view_b["steps"] if s["code"] == "navrh_fve")

    res = client.post(f"/api/v1/projects/{pid_a}/steps/{navrh_a['id']}/run-ai",
                      json={}, headers=auth)
    assert res.status_code == 200, res.text
    result_id = res.json()["id"]
    assert result_id is not None

    # cizí projekt: stejný result_id -> 404 (result nepatří do projektu B)
    resp = client.post(f"/api/v1/projects/{pid_b}/steps/{navrh_b['id']}/review-ai",
                       json={"result_id": result_id, "approved": True}, headers=auth)
    assert resp.status_code == 404, resp.text

    # vlastní projekt/step: projde
    resp = client.post(f"/api/v1/projects/{pid_a}/steps/{navrh_a['id']}/review-ai",
                       json={"result_id": result_id, "approved": True}, headers=auth)
    assert resp.status_code == 200, resp.text


# ---------- P5: AI complete gating ----------

def _mk_project(db, name):
    project = Project(name=name, customer_name="Z", share_code=f"S-{name}",
                      type="rd", status="active")
    db.add(project)
    db.commit()
    db.refresh(project)
    attach_template(db, project, "rd")
    return project


def _step(db, project, code):
    return (db.query(ProjectStep, PipelineStep)
            .join(PipelineStep, ProjectStep.step_id == PipelineStep.id)
            .filter(ProjectStep.project_id == project.id, PipelineStep.code == code)
            .one())


def test_ai_complete_blocked_while_draft_pending(db):
    from reportgen.ai_service import run_ai, review_ai
    project = _mk_project(db, "AI gate")
    admin = db.query(User).filter(User.role == "admin").first()

    ps, s = _step(db, project, "navrh_fve")
    res = run_ai(db, project, ps, admin, trigger="manual")
    assert res.status == "draft"
    db.refresh(ps)
    assert ps.status == "in_progress"

    # draft čeká -> complete zakázán
    ok, blockers, err = can_transition(db, ps, "complete", admin, project)
    assert ok is False
    assert "schválení" in err

    # schválení -> krok je přímo done (complete se pak nepoužívá)
    review_ai(db, res.id, True, admin, note="ok")
    db.refresh(ps)
    assert ps.status == "done"


def _satisfy_predecessors(db, project, admin, target_code):
    """Označí viditelné předchůdce kroku jako done (simulace postupu)."""
    from reportgen.pipeline import get_pipeline_view
    view = get_pipeline_view(db, project.id, admin)
    for st in view["steps"]:
        if st["code"] == target_code:
            break
        if st["hidden"] or st["status"] == "done":
            continue
        row = db.query(ProjectStep).filter(ProjectStep.id == st["id"]).first()
        row.status = "done"


def test_ai_complete_allowed_after_reject(db):
    from reportgen.ai_service import run_ai, review_ai
    project = _mk_project(db, "AI reject")
    admin = db.query(User).filter(User.role == "admin").first()

    ps, s = _step(db, project, "navrh_fve")
    res = run_ai(db, project, ps, admin, trigger="manual")
    review_ai(db, res.id, False, admin, note="špatný výpočet")
    db.refresh(ps)
    assert ps.status == "in_progress"  # zamítnutí krok nedokončí

    # draft pryč + splněné brány -> manuální complete přípustný a funkční
    _satisfy_predecessors(db, project, admin, "navrh_fve")
    db.flush()
    ok, _, err = can_transition(db, ps, "complete", admin, project)
    assert ok is True, err
    transition(db, project, ps, "complete", admin)
    db.refresh(ps)
    assert ps.status == "done"


def test_ai_complete_allowed_when_ai_never_ran(db):
    project = _mk_project(db, "AI manual")
    admin = db.query(User).filter(User.role == "admin").first()

    _satisfy_predecessors(db, project, admin, "navrh_fve")
    ps, s = _step(db, project, "navrh_fve")
    ps.status = "in_progress"  # simulace stavu po begin bez AI běhu
    db.flush()

    ok, _, err = can_transition(db, ps, "complete", admin, project)
    assert ok is True, err


# ---------- P6: seed fáze a est_work dle plánu M1.2 ----------

def test_seed_rd_phases_and_est_match_plan(db):
    project = _mk_project(db, "Seed check")

    # kroky POUZE této šablony projektu (kódy se v šablonách opakují)
    rows = (db.query(ProjectStep, PipelineStep)
            .join(PipelineStep, ProjectStep.step_id == PipelineStep.id)
            .filter(ProjectStep.project_id == project.id)
            .all())
    steps = {s.code: s for ps, s in rows}

    plan_phase = {
        "sop": "pripojeni", "sledovani_vykonu": "pripojeni",
        "registrace_nzu": "dotace", "administrace_pujcky": "dotace",
        "dolozeni_sfzp": "dotace",
        "zalohova_faktura": "finance", "kontrola_zalohy": "finance",
        "followup_1": "sledovani", "konzultace_navratnost": "sledovani",
        "konzultace_znacky": "sledovani", "planovani_prohlidky": "sledovani",
        "osobni_schuzka": "sledovani",
    }
    for code, phase in plan_phase.items():
        assert steps[code].phase == phase, f"{code}: {steps[code].phase} != {phase}"

    plan_est_work = {
        "elektro_montaz": 360, "mereni_revize": 60, "revizni_zprava": 0,
        "vymena_elektromeru": 0, "prevzeti_odchylky": 0, "povoleni_pretoku": 0,
    }
    for code, minutes in plan_est_work.items():
        assert steps[code].est_work_minutes == minutes, f"{code}: {steps[code].est_work_minutes} != {minutes}"
    assert len(steps) == 57