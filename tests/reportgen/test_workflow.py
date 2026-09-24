"""Workflow engine M2 — stavy, brány, paralelní větve, podmínky, hooky,
notifikace, admin zásahy, get_pipeline_view a API endpointy."""

import json
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from reportgen.storage import (Project, ProjectPipeline, ProjectStep,
                               PipelineStep, PipelineTemplate, StepEvent,
                               Notification, InvoiceItem, User, generate_share_code)
from reportgen.pipeline_seed import attach_template


# ---------- helpers ----------

def mk_user(db, email, role, roles=None):
    u = User(email=email, password_hash="h", role=role)
    if roles:
        u.set_roles(roles)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def mk_project(db, name="Test", template="ostatni", fve_params=None, user=None):
    p = Project(name=name, customer_name=name, share_code=generate_share_code(),
                type=template, status="active",
                owner_id=user.id if user else None,
                fve_params_json=json.dumps(fve_params or {}))
    db.add(p)
    db.commit()
    db.refresh(p)
    attach_template(db, p, template)
    return p


def ps_by_code(db, project, code):
    row = (db.query(ProjectStep, PipelineStep)
           .join(PipelineStep, ProjectStep.step_id == PipelineStep.id)
           .filter(ProjectStep.project_id == project.id, PipelineStep.code == code)
           .one())
    return row[0]


def s_by_code(db, project, code):
    row = (db.query(ProjectStep, PipelineStep)
           .join(PipelineStep, ProjectStep.step_id == PipelineStep.id)
           .filter(ProjectStep.project_id == project.id, PipelineStep.code == code)
           .one())
    return row[1]


def do(db, project, code, action, user, **kw):
    from reportgen.pipeline import transition
    step = ps_by_code(db, project, code)
    return transition(db, project, step, action, user, **kw)


def finish_simple(db, project, codes, user):
    """Dokončí sekvenci simple/ai kroků (ai se přeskočí jako admin)."""
    for code in codes:
        ps = ps_by_code(db, project, code)
        if ps.status in ("done", "signed", "skipped"):
            continue
        if ps.status == "not_started":
            do(db, project, code, "plan", user,
               plan_date=datetime.utcnow() + timedelta(days=1))
        if ps.status == "planned":
            do(db, project, code, "begin", user)
        if ps.status == "in_progress":
            do(db, project, code, "complete", user)


def admin_user(db):
    return db.query(User).filter(User.role == "admin").first()


# ---------- M2.1 stavy a přechody ----------

def test_simple_chain_plan_begin_complete(db):
    p = mk_project(db)
    user = admin_user(db)
    finish_simple(db, p, ["lead_zaevidovani"], user)

    ps = ps_by_code(db, p, "lead_zaevidovani")
    assert ps.status == "done"
    assert ps.plan_date is not None
    assert ps.started_at is not None
    assert ps.done_at is not None

    evs = (db.query(StepEvent).filter(StepEvent.step_id == ps.id)
           .order_by(StepEvent.id).all())
    assert [e.action for e in evs] == ["plan", "begin", "complete"]
    assert evs[0].from_status == "not_started" and evs[0].to_status == "planned"
    assert evs[1].to_status == "in_progress"
    assert evs[2].to_status == "done"


def test_gate_blocks_second_step_with_message(db):
    p = mk_project(db)
    user = admin_user(db)
    # lead_telefon vyžaduje hotové lead_zaevidovani
    with pytest.raises(HTTPException) as ei:
        do(db, p, "lead_telefon", "begin", user)
    assert ei.value.status_code == 403
    assert "Zaevidování poptávky" in ei.value.detail


def test_gate_allows_after_previous_done(db):
    p = mk_project(db)
    user = admin_user(db)
    finish_simple(db, p, ["lead_zaevidovani"], user)
    do(db, p, "lead_telefon", "plan", user)
    do(db, p, "lead_telefon", "begin", user)
    do(db, p, "lead_telefon", "complete", user)
    assert ps_by_code(db, p, "lead_telefon").status == "done"


def test_contract_sent_sign_and_plan(db):
    p = mk_project(db)
    user = admin_user(db)
    finish_simple(db, p, ["lead_zaevidovani", "lead_telefon", "nabidka_indikativni",
                          "odsouhlaseni_predbezne", "sber_podkladu", "tech_posouzeni"], user)
    # nabidka_podrobna = AI krok -> admin skip (M3 spustí run_ai)
    do(db, p, "nabidka_podrobna", "skip", user, note="bez AI v M2 testu")
    finish_simple(db, p, ["odeslani_nabidky"], user)

    do(db, p, "sod", "sent", user)
    assert ps_by_code(db, p, "sod").status == "sent"
    do(db, p, "sod", "sign", user)
    assert ps_by_code(db, p, "sod").status == "signed"

    evs = [e.action for e in db.query(StepEvent).filter(
        StepEvent.step_id == ps_by_code(db, p, "sod").id).all()]
    assert "sent" in evs and "sign" in evs


def test_transition_wrong_role_forbidden(db):
    p = mk_project(db)
    electrician = mk_user(db, "monter@x.cz", "electrician")
    with pytest.raises(HTTPException) as ei:
        do(db, p, "lead_zaevidovani", "begin", electrician)
    assert ei.value.status_code == 403


# ---------- M2.2 brány, paralelní větve, podmínky ----------

def mk_synthetic(db, code, steps, fve_params=None):
    tpl = PipelineTemplate(code=code, name=code, zakazka_type="rd")
    db.add(tpl)
    db.flush()
    for i, spec in enumerate(steps, 1):
        cond = spec.get("condition")
        db.add(PipelineStep(
            template_id=tpl.id, code=spec["code"], name=spec["code"],
            phase=spec.get("phase", "x"), order=i, est_admin_minutes=0,
            est_work_minutes=0, admin_rate_role="sales", work_rate_role="electrician",
            state_model=spec.get("state_model", "simple"),
            allowed_roles_json=json.dumps(spec.get("allowed", ["admin", "antelon", "sales"])),
            condition_json=json.dumps(cond, ensure_ascii=False) if cond else None,
            auto_hook=spec.get("auto_hook"), parallel_group=spec.get("group"),
        ))
    db.commit()
    p = Project(name=code, customer_name=code, share_code=generate_share_code(),
                type="rd", status="active",
                fve_params_json=json.dumps(fve_params or {}))
    db.add(p)
    db.commit()
    db.refresh(p)
    attach_template(db, p, code)
    return p


def test_parallel_group_gate(db):
    p = mk_synthetic(db, "grp", [
        {"code": "A"},
        {"code": "Ba", "group": "g1"},
        {"code": "Bb", "group": "g1"},
        {"code": "C"},
    ])
    user = admin_user(db)
    finish_simple(db, p, ["A"], user)

    # první krok skupiny jde po A
    do(db, p, "Ba", "begin", user)
    assert ps_by_code(db, p, "Ba").status == "in_progress"
    # druhý člen skupiny se váže jen na první člen (Ba), ne na sebe -> blokováno
    with pytest.raises(HTTPException):
        do(db, p, "Bb", "begin", user)
    do(db, p, "Ba", "complete", user)
    do(db, p, "Bb", "begin", user)
    do(db, p, "Bb", "complete", user)

    # C má bránu = celá skupina (oba členové)
    do(db, p, "C", "plan", user)
    do(db, p, "C", "begin", user)
    do(db, p, "C", "complete", user)
    assert ps_by_code(db, p, "C").status == "done"


def test_condition_hidden_and_excluded_from_gate(db):
    cond = {"project_param_in": {"fve_params.dotace": ["ano"]}}
    p = mk_synthetic(db, "cond", [
        {"code": "A"},
        {"code": "B", "condition": cond},
        {"code": "C"},
    ], fve_params={})

    from reportgen.pipeline import get_pipeline_view
    user = admin_user(db)
    view = get_pipeline_view(db, p.id, user)
    by_code = {s["code"]: s for s in view["steps"]}
    assert by_code["B"]["hidden"] is True

    # B je skryté -> C má bránu jen A
    finish_simple(db, p, ["A"], user)
    do(db, p, "C", "begin", user)
    assert ps_by_code(db, p, "C").status == "in_progress"

    # s dotací "ano" je B viditelné a tvoří bránu pro C
    p2 = mk_synthetic(db, "cond2", [
        {"code": "A"},
        {"code": "B", "condition": cond},
        {"code": "C"},
    ], fve_params={"dotace": "ano"})
    finish_simple(db, p2, ["A"], user)
    with pytest.raises(HTTPException):
        do(db, p2, "C", "begin", user)
    finish_simple(db, p2, ["B"], user)
    do(db, p2, "C", "begin", user)
    assert ps_by_code(db, p2, "C").status == "in_progress"

    view2 = get_pipeline_view(db, p2.id, user)
    by_code2 = {s["code"]: s for s in view2["steps"]}
    assert by_code2["B"]["hidden"] is False


def test_requires_step_condition_visibility(db):
    p = mk_synthetic(db, "reqstep", [
        {"code": "X"},
        {"code": "S", "condition": {"requires_step": ["X"]}},
    ])
    from reportgen.pipeline import get_pipeline_view
    user = admin_user(db)

    view = get_pipeline_view(db, p.id, user)
    by_code = {s["code"]: s for s in view["steps"]}
    assert by_code["S"]["hidden"] is True

    finish_simple(db, p, ["X"], user)
    view = get_pipeline_view(db, p.id, user)
    by_code = {s["code"]: s for s in view["steps"]}
    assert by_code["S"]["hidden"] is False


# ---------- M2.4 hooky ----------

def test_hook_invoice_2500_default(db):
    p = mk_project(db)
    user = admin_user(db)
    finish_simple(db, p, ["lead_zaevidovani", "lead_telefon", "nabidka_indikativni",
                          "odsouhlaseni_predbezne"], user)

    inv = db.query(InvoiceItem).filter(InvoiceItem.project_id == p.id).all()
    assert len(inv) == 1
    assert inv[0].doc_type == "posouzeni"
    assert inv[0].amount_czk == 2500
    assert inv[0].status == "draft"
    # notifikace o faktuře
    texts = [n.text for n in db.query(Notification).all()]
    assert any("2 500" in t for t in texts)


def test_hook_invoice_rejected_cancels_project(db):
    p = mk_project(db)
    user = admin_user(db)
    finish_simple(db, p, ["lead_zaevidovani", "lead_telefon", "nabidka_indikativni"], user)
    do(db, p, "odsouhlaseni_predbezne", "plan", user)
    do(db, p, "odsouhlaseni_predbezne", "begin", user)
    do(db, p, "odsouhlaseni_predbezne", "complete", user, note="Zamítnuto zákazníkem")

    assert ps_by_code(db, p, "odsouhlaseni_predbezne").status == "done"
    assert db.query(InvoiceItem).filter(InvoiceItem.project_id == p.id).count() == 0
    assert p.status == "cancelled"
    texts = [n.text for n in db.query(Notification).all()]
    assert any("zamítnuta" in t.lower() for t in texts)


def test_hook_sod_signed_discount_idempotent(db):
    p = mk_project(db)
    user = admin_user(db)
    finish_simple(db, p, ["lead_zaevidovani", "lead_telefon", "nabidka_indikativni",
                          "odsouhlaseni_predbezne", "sber_podkladu", "tech_posouzeni"], user)
    do(db, p, "nabidka_podrobna", "skip", user)
    finish_simple(db, p, ["odeslani_nabidky"], user)
    do(db, p, "sod", "sent", user)
    do(db, p, "sod", "sign", user)

    discounts = db.query(InvoiceItem).filter(
        InvoiceItem.doc_type == "final_discount").all()
    assert len(discounts) == 1
    assert discounts[0].amount_czk == -2500

    # idempotence: znovu zavolat hák nesmí vytvořit druhou fakturu
    from reportgen.pipeline import _run_hooks
    ps = ps_by_code(db, p, "sod")
    _run_hooks(db, p, ps, s_by_code(db, p, "sod"), user)
    db.commit()
    assert db.query(InvoiceItem).filter(
        InvoiceItem.doc_type == "final_discount").count() == 1


def test_sop_signed_and_elektro_done_notifications(db):
    p = mk_project(db)
    user = admin_user(db)
    finish_simple(db, p, ["lead_zaevidovani", "lead_telefon", "nabidka_indikativni",
                          "odsouhlaseni_predbezne", "sber_podkladu", "tech_posouzeni"], user)
    do(db, p, "nabidka_podrobna", "skip", user)
    finish_simple(db, p, ["odeslani_nabidky"], user)
    do(db, p, "sod", "sent", user)
    do(db, p, "sod", "sign", user)

    texts = " | ".join(n.text for n in db.query(Notification).all())
    assert "realizační" in texts


# ---------- M2.3 notifikace ----------

def test_plan_notifies_assignee(db):
    p = mk_project(db)
    sales = mk_user(db, "obchodnik@x.cz", "sales")
    user = admin_user(db)
    do(db, p, "lead_zaevidovani", "plan", admin_user(db),
       plan_date=datetime.utcnow() + timedelta(days=1), assigned_user_id=sales.id)

    notifs = db.query(Notification).filter(Notification.user_id == sales.id).all()
    assert len(notifs) == 1
    assert "naplánován" in notifs[0].text


def test_contract_sent_notifies_team_and_customer(db):
    p = mk_project(db)
    user = admin_user(db)
    cust = db.query(User).filter(User.role == "customer").first()
    from reportgen.storage import ProjectUser
    db.add(ProjectUser(project_id=p.id, user_id=cust.id))
    db.commit()

    finish_simple(db, p, ["lead_zaevidovani", "lead_telefon", "nabidka_indikativni",
                          "odsouhlaseni_predbezne", "sber_podkladu", "tech_posouzeni"], user)
    do(db, p, "nabidka_podrobna", "skip", user)
    finish_simple(db, p, ["odeslani_nabidky"], user)
    do(db, p, "sod", "sent", user)

    all_texts = [n.text for n in db.query(Notification).all()]
    assert any("čeká na zákazníka" in t for t in all_texts)
    # customer (propojený s projektem) dostal notifikaci
    cust_notifs = db.query(Notification).filter(Notification.user_id == cust.id).all()
    assert any("čeká na zákazníka" in n.text for n in cust_notifs)


# ---------- M2.5 admin zásahy ----------

def test_admin_skip_revert_reassign(db):
    p = mk_project(db)
    admin = admin_user(db)
    sales = mk_user(db, "obchodnik2@x.cz", "sales")

    do(db, p, "lead_telefon", "skip", admin, note="není potřeba")
    assert ps_by_code(db, p, "lead_telefon").status == "skipped"

    do(db, p, "lead_telefon", "revert", admin)
    assert ps_by_code(db, p, "lead_telefon").status == "not_started"

    do(db, p, "lead_telefon", "reassign", admin, assigned_user_id=sales.id)
    assert ps_by_code(db, p, "lead_telefon").assigned_user_id == sales.id


def test_non_admin_cannot_admin_actions(db):
    p = mk_project(db)
    sales = mk_user(db, "obchodnik3@x.cz", "sales")
    with pytest.raises(HTTPException) as ei:
        do(db, p, "lead_telefon", "skip", sales)
    assert ei.value.status_code == 403


# ---------- M2.1.2 get_pipeline_view ----------

def test_get_pipeline_view_shape(db):
    p = mk_project(db)
    user = admin_user(db)
    finish_simple(db, p, ["lead_zaevidovani"], user)

    from reportgen.pipeline import get_pipeline_view
    view = get_pipeline_view(db, p.id, user)
    assert view["project"]["id"] == p.id
    assert view["template"] is not None
    assert len(view["steps"]) >= 15
    step0 = view["steps"][0]
    for k in ("id", "code", "name", "phase", "order", "status", "plan_date",
              "assigned_user_id", "note", "real_admin_minutes", "real_work_minutes",
              "est_admin_minutes", "est_work_minutes", "ai", "can", "allowed_roles"):
        assert k in step0, f"chybí klíč {k}"
    assert "events" in view
    assert isinstance(view["groups"], list)


# ---------- API ----------

@pytest.fixture
def admin_token(client):
    resp = client.post("/api/v1/auth/login",
                       json={"email": "admin@test.local", "password": "Admin123!"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
def sales_token(client, admin_token):
    # vytvořit sales uživatele s rolemi
    resp = client.post("/api/v1/auth/register",
                       json={"email": "sales@test.local", "password": "Sales123!", "role": "customer"})
    assert resp.status_code == 200, resp.text
    # nastavit role přes admin API
    uid = resp.json()["user"]["id"]
    auth = {"Authorization": f"Bearer {admin_token}"}
    r = client.put(f"/api/v1/admin/users/{uid}/roles",
                   json={"roles": ["sales"]}, headers=auth)
    assert r.status_code == 200, r.text
    login = client.post("/api/v1/auth/login",
                        json={"email": "sales@test.local", "password": "Sales123!"})
    return login.json()["access_token"]


def test_auth_me_returns_roles(client, admin_token):
    resp = client.get("/api/v1/auth/me",
                      headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200, resp.text
    assert "roles" in resp.json()


def test_api_templates_list(client, admin_token):
    resp = client.get("/api/v1/admin/pipeline-templates",
                      headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 11


def test_api_template_steps(client, admin_token):
    resp = client.get("/api/v1/admin/pipeline-templates",
                      headers={"Authorization": f"Bearer {admin_token}"})
    tpl_id = resp.json()[0]["id"]
    resp = client.get(f"/api/v1/admin/pipeline-templates/{tpl_id}/steps",
                      headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) > 0


def _mk_project_via_api(client, admin_token):
    resp = client.post("/api/v1/projects",
                       headers={"Authorization": f"Bearer {admin_token}"},
                       json={"name": "API projekt", "customer_name": "Zákazník"})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def test_api_attach_and_pipeline_view(client, admin_token):
    pid = _mk_project_via_api(client, admin_token)
    auth = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(f"/api/v1/projects/{pid}/pipeline/attach",
                       json={"template_code": "rd"}, headers=auth)
    assert resp.status_code == 200, resp.text

    resp = client.get(f"/api/v1/projects/{pid}/pipeline", headers=auth)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project"]["id"] == pid
    assert len(body["steps"]) >= 55


def test_api_transition_gate(client, admin_token):
    pid = _mk_project_via_api(client, admin_token)
    auth = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(f"/api/v1/projects/{pid}/pipeline/attach",
                       json={"template_code": "ostatni"}, headers=auth)
    view = client.get(f"/api/v1/projects/{pid}/pipeline", headers=auth).json()
    s0 = view["steps"][0]  # lead_zaevidovani
    s1 = view["steps"][1]  # lead_telefon

    # gate: dokončit první, pak druhý
    resp = client.post(f"/api/v1/projects/{pid}/steps/{s1['id']}/transition",
                       json={"action": "begin"}, headers=auth)
    assert resp.status_code == 403, resp.text
    assert "Zaevidování poptávky" in resp.json()["detail"]

    for action in ("plan", "begin", "complete"):
        resp = client.post(f"/api/v1/projects/{pid}/steps/{s0['id']}/transition",
                           json={"action": action, "plan_date": "2026-09-25T08:00:00"},
                           headers=auth)
        assert resp.status_code == 200, resp.text

    resp = client.post(f"/api/v1/projects/{pid}/steps/{s1['id']}/transition",
                       json={"action": "begin"}, headers=auth)
    assert resp.status_code == 200, resp.text


def test_api_admin_action_non_admin_forbidden(client, admin_token, sales_token):
    pid = _mk_project_via_api(client, admin_token)
    auth_admin = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(f"/api/v1/projects/{pid}/pipeline/attach",
                       json={"template_code": "ostatni"}, headers=auth_admin)
    assert resp.status_code == 200, resp.text
    view = client.get(f"/api/v1/projects/{pid}/pipeline", headers=auth_admin).json()
    s0 = view["steps"][0]
    resp = client.post(f"/api/v1/projects/{pid}/steps/{s0['id']}/admin",
                       json={"action": "skip"}, headers={"Authorization": f"Bearer {sales_token}"})
    assert resp.status_code == 403


def test_api_admin_action_skip(client, admin_token):
    pid = _mk_project_via_api(client, admin_token)
    auth = {"Authorization": f"Bearer {admin_token}"}
    client.post(f"/api/v1/projects/{pid}/pipeline/attach",
                json={"template_code": "ostatni"}, headers=auth)
    view = client.get(f"/api/v1/projects/{pid}/pipeline", headers=auth).json()
    s0 = view["steps"][0]
    resp = client.post(f"/api/v1/projects/{pid}/steps/{s0['id']}/admin",
                       json={"action": "skip"}, headers=auth)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "skipped"


def test_api_notifications_flow(client, admin_token):
    auth = {"Authorization": f"Bearer {admin_token}"}
    # vytvořit notifikaci přes pipeline (plan)
    pid = _mk_project_via_api(client, admin_token)
    client.post(f"/api/v1/projects/{pid}/pipeline/attach",
                json={"template_code": "ostatni"}, headers=auth)
    me = client.get("/api/v1/auth/me", headers=auth).json()
    view = client.get(f"/api/v1/projects/{pid}/pipeline", headers=auth).json()
    s0 = view["steps"][0]
    client.post(f"/api/v1/projects/{pid}/steps/{s0['id']}/transition",
                json={"action": "plan", "assigned_user_id": me["id"]}, headers=auth)

    resp = client.get("/api/v1/notifications", headers=auth)
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) >= 1
    nid = resp.json()[0]["id"]
    resp = client.post(f"/api/v1/notifications/{nid}/read", headers=auth)
    assert resp.status_code == 200, resp.text
    resp = client.get("/api/v1/notifications", headers=auth)
    assert resp.json()[0]["read"] is True