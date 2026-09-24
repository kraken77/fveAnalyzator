"""AI kroky M3 — subsidy, loan rules, run_ai/review_ai, API."""

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest import mock

import pytest
from fastapi import HTTPException

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "backend"))

from reportgen.storage import (Project, ProjectStep, PipelineStep, StepEvent,
                               PipelineAiResult, PdfVersion, User,
                               generate_share_code)
from reportgen.pipeline_seed import attach_template


def mk_project(db, template="ostatni", fve_params=None, project_type=None):
    p = Project(name="AI test", customer_name="Zákazník", share_code=generate_share_code(),
                type=project_type or template, status="active",
                fve_params_json=json.dumps(fve_params or {}))
    db.add(p)
    db.commit()
    db.refresh(p)
    attach_template(db, p, template)
    return p


def ps_by_code(db, project, code):
    return (db.query(ProjectStep, PipelineStep)
            .join(PipelineStep, ProjectStep.step_id == PipelineStep.id)
            .filter(ProjectStep.project_id == project.id, PipelineStep.code == code)
            .one())[0]


def admin_user(db):
    return db.query(User).filter(User.role == "admin").first()


def energy_result(kwp=10.0, battery=10.0, self_pct=0.5, annual_savings=45000):
    total = 5000.0
    self_cons = total * self_pct
    export = kwp * 900.0 - self_cons if kwp * 900.0 > self_cons else 0
    return {
        "kwp": kwp,
        "battery_capacity": battery,
        "financial_balance": {"annual_savings_czk": annual_savings,
                              "cost_without_pv_czk": 60000, "cost_with_pv_czk": 15000},
        "energy_balance_kwh": {"total_consumption": total, "self_consumption": self_cons,
                               "grid_export": export, "grid_import": total - self_cons},
        "economic_balance_czk": {"savings_self_consumption": self_cons * 6},
        "annual_consumption_mwh": total / 1000,
        "monthly_summary": [],
    }


def economic_result():
    return {"metrics": {"npv_czk": 120000.0, "payback_years": 7,
                        "discounted_payback_years": 9,
                        "final_pv_reinvest_gain_czk": 150000.0,
                        "final_sp500_net_czk": 130000.0},
            "plot": "{}", "raw_data": []}


# ---------- M3.1 subsidy / loan ----------

def test_subsidy_dilci_formula_and_limit():
    from reportgen.subsidy import compute_subsidy
    r = compute_subsidy(6, 0, "dilci")
    assert r["castka"] == 6 * 25000
    r2 = compute_subsidy(4, 5, "dilci")
    assert r2["castka"] == 4 * 25000 + 5 * 15000
    assert r2["limit"] == 400000


def test_subsidy_dilci_cap():
    from reportgen.subsidy import compute_subsidy
    r = compute_subsidy(20, 20, "dilci")
    assert r["castka"] == 400000  # cap


def test_subsidy_komplexni_formula():
    from reportgen.subsidy import compute_subsidy
    # <= 5 kWp: všechny kWp za base sazbu (35 000)
    r = compute_subsidy(3, 0, "komplexni")
    assert r["castka"] == 3 * 35000
    # > 5 kWp: 5 * 35000 + (kwp-5) * 40000 + baterie * 15000
    r = compute_subsidy(10, 5, "komplexni")
    assert r["castka"] == 5 * 35000 + 5 * 40000 + 5 * 15000


def test_loan_rules():
    from reportgen.loan_rules import evaluate_loan
    params = {"dotace": "ano", "pujcka": "ano"}
    r = evaluate_loan(params, {"castka": 300000})
    assert r["eligible"] is True
    assert r["amount_czk"] == 300000

    r2 = evaluate_loan({"dotace": "ano", "pujcka": "ne"}, {"castka": 300000})
    assert r2["eligible"] is False
    assert r2["amount_czk"] == 0

    r3 = evaluate_loan(params, {"castka": 900000})
    assert r3["amount_czk"] == 750000  # cap


# ---------- M3.2 run_ai / review_ai ----------

def _run_ai(db, project, code, **kw):
    from reportgen.ai_service import run_ai
    ps = ps_by_code(db, project, code)
    return run_ai(db, project, ps, admin_user(db), **kw)


def test_run_ai_fve_size_draft(db):
    p = mk_project(db, template="rd", fve_params={"kwp": 8, "battery_capacity": 10,
                                                  "annual_consumption_mwh": 5})
    from reportgen.ai_service import run_ai
    ps = ps_by_code(db, p, "navrh_fve")
    with mock.patch("main.run_energy_analysis",
                    return_value=energy_result(kwp=8.0, battery=10.0)) as mock_ea, \
         mock.patch("main.run_economic_analysis", return_value=economic_result()):
        res = run_ai(db, p, ps, admin_user(db), trigger="auto")

    assert res.kind == "fve_size"
    assert res.status == "draft"
    out = json.loads(res.output_json)
    assert out["kwp"] == 8
    assert "vyroba_kwh" in out and "npv_czk" in out and "roi_years" in out
    assert mock_ea.call_count >= 1
    # krok je in_progress a čeká na schválení
    assert ps.status == "in_progress"


def test_review_ai_approve_sets_step_done(db):
    p = mk_project(db, template="rd", fve_params={"kwp": 8, "battery_capacity": 10})
    res = _run_ai(db, p, "navrh_fve")

    from reportgen.ai_service import review_ai
    ps = ps_by_code(db, p, "navrh_fve")
    review_ai(db, res.id, approved=True, user=admin_user(db), note="v pořádku")
    db.commit()
    db.refresh(res)
    assert res.status == "approved"
    assert res.reviewed_by == admin_user(db).id
    assert ps.status == "done"
    assert ps.done_at is not None
    ev = db.query(StepEvent).filter(StepEvent.step_id == ps.id,
                                    StepEvent.action == "done").first()
    assert ev is not None
    # schválená kwp se uloží zpět do projektu pro navazující kroky
    assert json.loads(p.fve_params_json).get("kwp") == 8


def test_review_ai_reject_keeps_in_progress(db):
    p = mk_project(db, template="rd", fve_params={"kwp": 8})
    res = _run_ai(db, p, "navrh_fve")

    from reportgen.ai_service import review_ai
    ps = ps_by_code(db, p, "navrh_fve")
    review_ai(db, res.id, approved=False, user=admin_user(db), note="špatné vstupy")
    db.commit()
    db.refresh(res)
    assert res.status == "rejected"
    assert ps.status == "in_progress"


def test_run_ai_battery_picks_variant(db):
    p = mk_project(db, template="rd", fve_params={"kwp": 8, "battery_capacity": 0,
                                                  "annual_consumption_mwh": 5})

    def fake_energy(inp):
        # nejvyšší samospotřeba = 15 kWh varianta
        pct = {5: 0.3, 10: 0.55, 15: 0.8}
        return energy_result(kwp=8.0, battery=inp.battery_capacity,
                             self_pct=pct.get(int(inp.battery_capacity), 0.5))

    from reportgen.ai_service import run_ai
    ps = ps_by_code(db, p, "kapacita_baterie")
    with mock.patch("main.run_energy_analysis", side_effect=fake_energy):
        res = run_ai(db, p, ps, admin_user(db), trigger="auto")
    out = json.loads(res.output_json)
    assert out["doporuceno_kwh"] == 15
    assert len(out["variants"]) >= 2


def test_run_ai_subsidy_and_loan(db):
    p = mk_project(db, template="rd", fve_params={"kwp": 8, "battery_capacity": 10,
                                                  "dotace": "ano", "pujcka": "ano"})
    res_sub = _run_ai(db, p, "dotacni_uspora")
    out = json.loads(res_sub.output_json)
    assert out["castka_czk"] == 8 * 25000 + 10 * 15000

    res_loan = _run_ai(db, p, "moznost_pujcky")
    out = json.loads(res_loan.output_json)
    assert out["eligible"] is True
    assert out["amount_czk"] == min(out.get("dotace_castka", 350000), 750000)


def test_run_ai_offer_pdf_creates_pdfversion(db, tmp_path):
    p = mk_project(db, template="rd", fve_params={"kwp": 8, "battery_capacity": 10})
    from reportgen.ai_service import run_ai
    ps = ps_by_code(db, p, "nabidka_podrobna")

    with mock.patch("main.run_energy_analysis",
                    return_value=energy_result(kwp=8.0, battery=10.0)), \
         mock.patch("main.run_economic_analysis", return_value=economic_result()):
        # ReportGenerator běžně tiskne do CWD; mockneme generátor
        from app.reporting import ReportGenerator
        with mock.patch.object(ReportGenerator, "generate_energy_report",
                               return_value=b"%PDF-1.4 mock"):
            res = run_ai(db, p, ps, admin_user(db), trigger="manual")

    assert res.pdf_version_id is not None
    pv = db.query(PdfVersion).filter(PdfVersion.id == res.pdf_version_id).first()
    assert pv is not None
    assert pv.template == "energy"


def test_run_ai_failure_raises_500_and_keeps_state(db):
    p = mk_project(db, template="rd", fve_params={"kwp": 8})
    from reportgen.ai_service import run_ai
    ps = ps_by_code(db, p, "navrh_fve")
    before = ps.status
    with mock.patch("main.run_energy_analysis", side_effect=Exception("PVGIS down")), \
         mock.patch("main.run_economic_analysis", return_value=economic_result()):
        with pytest.raises(HTTPException) as ei:
            run_ai(db, p, ps, admin_user(db), trigger="auto")
        assert ei.value.status_code == 500
        assert "AI krok selhal" in ei.value.detail
    assert ps.status == before
    assert db.query(PipelineAiResult).filter(PipelineAiResult.step_id == ps.id).count() == 0


# ---------- M3.3 API ----------

@pytest.fixture
def admin_token(client):
    resp = client.post("/api/v1/auth/login",
                       json={"email": "admin@test.local", "password": "Admin123!"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _api_project(client, admin_token):
    auth = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post("/api/v1/projects",
                       headers=auth, json={"name": "AI API", "customer_name": "Z"})
    pid = resp.json()["id"]
    client.post(f"/api/v1/projects/{pid}/pipeline/attach",
                json={"template_code": "rd"}, headers=auth)
    client.put(f"/api/v1/projects/{pid}/params",
               json={"fve_params": {"kwp": 8, "battery_capacity": 10,
                                    "dotace": "ano", "pujcka": "ano"}}, headers=auth)
    return pid, auth


def test_api_run_ai_and_review(client, admin_token):
    pid, auth = _api_project(client, admin_token)
    view = client.get(f"/api/v1/projects/{pid}/pipeline", headers=auth).json()
    steps = {s["code"]: s for s in view["steps"]}
    fve_step = steps["navrh_fve"]

    with mock.patch("main.run_energy_analysis",
                    return_value=energy_result(kwp=8.0, battery=10.0)), \
         mock.patch("main.run_economic_analysis", return_value=economic_result()):
        resp = client.post(f"/api/v1/projects/{pid}/steps/{fve_step['id']}/run-ai",
                           json={"trigger": "auto"}, headers=auth)
    assert resp.status_code == 200, resp.text
    result_id = resp.json()["id"]
    assert resp.json()["status"] == "draft"

    # seznam výsledků
    resp = client.get(f"/api/v1/projects/{pid}/steps/{fve_step['id']}/ai-results",
                      headers=auth)
    assert resp.status_code == 200 and len(resp.json()) == 1

    # schválení
    resp = client.post(f"/api/v1/projects/{pid}/steps/{fve_step['id']}/review-ai",
                       json={"result_id": result_id, "approved": True}, headers=auth)
    assert resp.status_code == 200, resp.text
    view = client.get(f"/api/v1/projects/{pid}/pipeline", headers=auth).json()
    step = {s["code"]: s for s in view["steps"]}["navrh_fve"]
    assert step["status"] == "done"
    assert step["ai"]["status"] == "approved"


def test_api_review_non_admin_forbidden(client, admin_token):
    pid, auth = _api_project(client, admin_token)
    view = client.get(f"/api/v1/projects/{pid}/pipeline", headers=auth).json()
    fve = {s["code"]: s for s in view["steps"]}["navrh_fve"]

    with mock.patch("main.run_energy_analysis",
                    return_value=energy_result(kwp=8.0, battery=10.0)), \
         mock.patch("main.run_economic_analysis", return_value=economic_result()):
        resp = client.post(f"/api/v1/projects/{pid}/steps/{fve['id']}/run-ai",
                           json={"trigger": "auto"}, headers=auth)
    result_id = resp.json()["id"]

    # customer nemá oprávnění
    login = client.post("/api/v1/auth/login",
                        json={"email": "zakaznik@test.local", "password": "Zakaznik123!"})
    cust_auth = {"Authorization": f"Bearer {login.json()['access_token']}"}
    resp = client.post(f"/api/v1/projects/{pid}/steps/{fve['id']}/review-ai",
                       json={"result_id": result_id, "approved": True}, headers=cust_auth)
    assert resp.status_code == 403