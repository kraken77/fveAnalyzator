"""Ekonomika, časové výkazy, materiály, fakturace (M4)."""

import json
from datetime import date

import pytest

from reportgen.storage import (InvoiceItem, Material, PipelineStep, Project,
                               ProjectMaterial, ProjectStep, RateCard,
                               TimeEntry, User, generate_share_code)
from reportgen.pipeline_seed import attach_template


def mk_user(db, email, role):
    u = User(email=email, password_hash="h", role=role)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def mk_project(db, template="ostatni"):
    p = Project(name="Eko", customer_name="Zákazník", share_code=generate_share_code(),
                type=template, status="active")
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


def do_chain(db, project, codes, user):
    from reportgen.pipeline import transition
    for code in codes:
        ps = ps_by_code(db, project, code)
        for action in ("plan", "begin", "complete"):
            if ps.status == "done":
                break
            ps = transition(db, project, ps, action, user)
        if ps.status == "skipped":
            continue


# ---------- M4.1 kalkulace ----------

def _step(est_admin=60, est_work=120, admin_role="sales", work_role="electrician"):
    return PipelineStep(code="x", name="x", phase="x", order=1,
                        est_admin_minutes=est_admin, est_work_minutes=est_work,
                        admin_rate_role=admin_role, work_rate_role=work_role)


def test_calc_step_cost_with_rate_cards_and_margin():
    from reportgen.economy import calc_step_cost
    cards = [RateCard(role="sales", kind="admin", rate_czk_h=800, active=True),
             RateCard(role="electrician", kind="work", rate_czk_h=1000, active=True)]
    r = calc_step_cost(_step(), cards, margin=0.30)
    assert r["admin_minutes"] == 60
    assert r["admin_cost"] == 800.0
    assert r["work_cost"] == 2000.0
    assert r["total_cost"] == 2800.0
    assert r["sell_recommended"] == 3640.0


def test_calc_step_cost_defaults():
    from reportgen.economy import calc_step_cost
    r = calc_step_cost(_step(), [])  # bez sazeb -> default 500 Kč/h
    assert r["total_cost"] == 1500.0
    assert r["sell_recommended"] == 1950.0  # default marže 30 %
    assert r["admin_cost"] == 500.0 and r["work_cost"] == 1000.0


def test_project_economy_separates_admin_and_work(db):
    from reportgen.economy import add_time_entry, project_economy
    p = mk_project(db)
    user = admin_user(db)
    ps = ps_by_code(db, p, "lead_zaevidovani")
    add_time_entry(db, p, ps, user, minutes=120, kind="admin", work_date=date(2026, 9, 1))
    add_time_entry(db, p, ps, user, minutes=60, kind="work", work_date=date(2026, 9, 2))

    eco = project_economy(db, p.id)
    assert eco["margin"] == 0.30
    # plán: lead_zaevidovani = 1 min admin
    assert eco["plan"]["admin_minutes"] >= 1
    # skutečnost z time_entries (120 min * 500 Kč/h = 1000; 60 min * 500 = 500)
    assert eco["actual"]["admin_cost"] == 1000.0
    assert eco["actual"]["work_cost"] == 500.0
    # admin a work se nikdy nesčítají do jednoho sloupce
    assert "total" not in eco["plan"]
    assert "total" not in eco["actual"]
    assert eco["sell"] == round(eco["plan"]["total_cost"] * 1.3, 2)


# ---------- M4.2 časové výkazy ----------

def test_time_entry_increments_real_minutes(db):
    from reportgen.economy import add_time_entry
    p = mk_project(db)
    ps = ps_by_code(db, p, "lead_zaevidovani")
    user = admin_user(db)

    add_time_entry(db, p, ps, user, 90, "admin", date(2026, 9, 1))
    assert ps.real_admin_minutes == 90
    add_time_entry(db, p, ps, user, 30, "work", date(2026, 9, 2))
    assert ps.real_work_minutes == 30
    assert ps.real_admin_minutes == 90  # zůstává oddělené


def test_time_summary_by_user_and_type(db):
    from reportgen.economy import add_time_entry, time_summary
    p = mk_project(db)
    u1 = admin_user(db)
    u2 = mk_user(db, "monter@x.cz", "electrician")
    ps = ps_by_code(db, p, "lead_zaevidovani")
    montaz = ps_by_code(db, p, "montaz")  # elektrikář má roli na montáži
    add_time_entry(db, p, ps, u1, 120, "admin", date(2026, 9, 1))
    add_time_entry(db, p, montaz, u2, 60, "work", date(2026, 9, 1))

    s = time_summary(db, p.id)
    assert s["by_user"][str(u1.id)]["minutes"] == 120
    assert s["by_user"][str(u2.id)]["minutes"] == 60
    assert s["by_type"]["admin"]["minutes"] == 120
    assert s["by_type"]["work"]["minutes"] == 60
    assert s["total_minutes"] == 180


def test_time_entry_role_restriction(db):
    from reportgen.economy import add_time_entry
    p = mk_project(db)
    ps = ps_by_code(db, p, "lead_zaevidovani")  # allowed: admin/antelon/sales
    roofer = mk_user(db, "klempir@x.cz", "roofer")
    with pytest.raises(Exception):
        add_time_entry(db, p, ps, roofer, 30, "work", date(2026, 9, 1))


# ---------- M4.3 materiály ----------

def test_material_price_snapshot_defaults(db):
    from reportgen.economy import add_project_material
    p = mk_project(db)
    mat = Material(code="PAN-400", name="Panel 400 Wp", unit="ks", price=2500)
    db.add(mat)
    db.commit()
    db.refresh(mat)

    pm = add_project_material(db, p, mat, qty=4, lane="plan")
    assert pm.price_snapshot == 2500
    # pokud je cenovka zadána, nepřepíše se
    pm2 = add_project_material(db, p, mat, qty=2, lane="order", price_snapshot=2200)
    assert pm2.price_snapshot == 2200


def test_material_balance_by_lanes(db):
    from reportgen.economy import add_project_material, material_balance
    p = mk_project(db)
    mat = Material(code="BAT-10", name="Baterie 10 kWh", unit="ks", price=120000)
    db.add(mat)
    db.commit()
    db.refresh(mat)

    add_project_material(db, p, mat, qty=2, lane="plan")
    add_project_material(db, p, mat, qty=1, lane="order")
    add_project_material(db, p, mat, qty=1, lane="issue")
    add_project_material(db, p, mat, qty=1, lane="actual")

    bal = material_balance(db, p.id)
    row = bal[0]
    assert row["code"] == "BAT-10"
    assert row["plan_qty"] == 2.0
    assert row["order_qty"] == 1.0
    assert row["issue_qty"] == 1.0
    assert row["actual_qty"] == 1.0
    assert row["price"] == 120000


# ---------- M4.4 fakturace ----------

def _to_invoice_phase(db, p, user):
    do_chain(db, p, ["lead_zaevidovani", "lead_telefon", "nabidka_indikativni",
                     "odsouhlaseni_predbezne"], user)


def _sign_sod(db, p, user):
    from reportgen.pipeline import transition
    # nabidka_podrobna je AI krok -> přeskočit, aby šel dokončit odeslani_nabidky
    np_ps = ps_by_code(db, p, "nabidka_podrobna")
    if np_ps.status == "not_started":
        transition(db, p, np_ps, "skip", user)
    do_chain(db, p, ["sber_podkladu", "tech_posouzeni", "odeslani_nabidky"], user)
    sod = ps_by_code(db, p, "sod")
    for action in ("sent", "sign"):
        sod = transition(db, p, sod, action, user)
    return sod


def test_invoice_hooks_2500_and_discount(db):
    p = mk_project(db)
    user = admin_user(db)
    _to_invoice_phase(db, p, user)

    items = db.query(InvoiceItem).filter(InvoiceItem.project_id == p.id).all()
    assert len(items) == 1
    assert items[0].doc_type == "posouzeni"
    assert items[0].amount_czk == 2500

    _sign_sod(db, p, user)
    items = db.query(InvoiceItem).filter(InvoiceItem.project_id == p.id).all()
    by_type = {i.doc_type: i for i in items}
    assert by_type["final_discount"].amount_czk == -2500

    # kontrolní součet: posouzeni + sleva = 0 (zákazník platí 2 500 jen jednou)
    total = sum(i.amount_czk for i in items if i.doc_type in ("posouzeni", "final_discount"))
    assert total == 0


def test_invoice_issue_sets_doc_number(db):
    from reportgen.economy import issue_invoice
    p = mk_project(db)
    user = admin_user(db)
    _to_invoice_phase(db, p, user)
    inv = db.query(InvoiceItem).filter(InvoiceItem.doc_type == "posouzeni").first()

    issue_invoice(db, inv, user)
    assert inv.status == "issued"
    assert inv.doc_number == f"inv-{p.id}-1"

    # druhá faktura dostane sekvenci 2
    from reportgen.economy import add_invoice_item
    inv2 = add_invoice_item(db, p, "zaloha", "Zálohová faktura", 15000)
    issue_invoice(db, inv2, user)
    assert inv2.doc_number == f"inv-{p.id}-2"


# ---------- API ----------

@pytest.fixture
def admin_token(client):
    resp = client.post("/api/v1/auth/login",
                       json={"email": "admin@test.local", "password": "Admin123!"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _api_project(client, admin_token):
    auth = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post("/api/v1/projects", headers=auth,
                       json={"name": "Eko API", "customer_name": "Z"})
    pid = resp.json()["id"]
    client.post(f"/api/v1/projects/{pid}/pipeline/attach",
                json={"template_code": "ostatni"}, headers=auth)
    return pid, auth


def test_api_time_entries_flow(client, admin_token):
    pid, auth = _api_project(client, admin_token)
    view = client.get(f"/api/v1/projects/{pid}/pipeline", headers=auth).json()
    s0 = view["steps"][0]

    resp = client.post(f"/api/v1/projects/{pid}/time-entries",
                       json={"step_id": s0["id"], "minutes": 90, "kind": "admin",
                             "work_date": "2026-09-05", "note": "telefon"},
                       headers=auth)
    assert resp.status_code == 200, resp.text

    resp = client.get(f"/api/v1/projects/{pid}/time-entries/summary", headers=auth)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_minutes"] == 90

    resp = client.get("/api/v1/admin/reports/monteri-csv?from=2026-09-01&to=2026-09-30",
                      headers=auth)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    text = resp.text
    assert "user" in text.lower()
    assert "admin@test.local" in text


def test_api_materials_balance(client, admin_token):
    pid, auth = _api_project(client, admin_token)

    resp = client.post("/api/v1/materials",
                       json={"code": "STR-10", "name": "Střídač 10 kW", "unit": "ks",
                             "price": 32000},
                       headers=auth)
    assert resp.status_code == 200, resp.text
    mat_id = resp.json()["id"]

    for lane, qty in (("plan", 2), ("order", 1), ("issue", 1), ("actual", 1)):
        resp = client.post(f"/api/v1/projects/{pid}/materials",
                           json={"material_id": mat_id, "qty": qty, "lane": lane},
                           headers=auth)
        assert resp.status_code == 200, resp.text
        assert resp.json()["price_snapshot"] == 32000

    resp = client.get(f"/api/v1/projects/{pid}/materials/balance", headers=auth)
    assert resp.status_code == 200, resp.text
    row = resp.json()[0]
    assert row["plan_qty"] == 2.0 and row["actual_qty"] == 1.0


def test_api_invoice_items_and_issue(client, admin_token):
    pid, auth = _api_project(client, admin_token)
    view = client.get(f"/api/v1/projects/{pid}/pipeline", headers=auth).json()
    s0 = view["steps"][0]

    resp = client.post(f"/api/v1/projects/{pid}/invoice-items",
                       json={"doc_type": "zaloha", "description": "ZF", "amount_czk": 15000},
                       headers=auth)
    assert resp.status_code == 200, resp.text
    item_id = resp.json()["id"]

    resp = client.post(f"/api/v1/projects/{pid}/invoice-items/{item_id}/status",
                       json={"status": "issued"}, headers=auth)
    assert resp.status_code == 200, resp.text
    assert resp.json()["doc_number"] == f"inv-{pid}-1"

    resp = client.get(f"/api/v1/projects/{pid}/invoice-items", headers=auth)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["doc_number"] == f"inv-{pid}-1"