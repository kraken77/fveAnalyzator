"""M3–M5 — API /api/v1/fve-analysis/*, uložení, převod na zakázku, RBAC.

Autentizace jako v test_m5_admin_api.py: prihlaseni pres /api/v1/auth/login.
"""
import pytest
from unittest.mock import patch

from reportgen import storage as st


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


def _save(client, token, **over):
    payload = {
        "params": over.pop("params", {"kwp": 10.0}),
        "contact": over.pop("contact", {
            "name": "Jiří Novák",
            "email": "novak@example.cz",
            "phone": "+420 777 123 456",
        }),
    }
    payload.update(over)
    return client.post("/api/v1/fve-analysis", json=payload, headers=_auth(token))


# ---------- M3.2 run ----------

def test_run_returns_full_analysis(client, admin_token):
    r = client.post("/api/v1/fve-analysis/run",
                    json={"kwp": 10.0, "annual_consumption_mwh": 5.0},
                    headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "energy_balance_kwh" in body
    assert "financial_balance" in body
    # plots jako STRING, ne objekt — na tom závisí PlotlyChart v M6
    assert isinstance(body["plots"]["monthly_stats"], str)


def test_run_defaults_when_body_is_empty(client, admin_token):
    """Klient smí poslat jen to, co změnil — zbytek je default."""
    r = client.post("/api/v1/fve-analysis/run", json={}, headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["kwp"] == 10.0


def test_run_rejects_out_of_range(client, admin_token):
    """kwp 500 kWp není FVE, je to chyba v zadání — musí být 422, ne 500."""
    r = client.post("/api/v1/fve-analysis/run", json={"kwp": 500.0},
                    headers=_auth(admin_token))
    assert r.status_code == 422


def test_run_rejects_unknown_sell_scheme(client, admin_token):
    r = client.post("/api/v1/fve-analysis/run", json={"sell_price_scheme": "drahokamy"},
                    headers=_auth(admin_token))
    assert r.status_code == 422
    assert "prodeje" in str(r.json()["detail"])


def test_run_requires_auth(client):
    assert client.post("/api/v1/fve-analysis/run", json={}).status_code in (401, 422)


def test_customer_can_run_analysis(client, customer_token):
    """Nová schopnost z designu: zákazník si analýzu spočítá sám."""
    r = client.post("/api/v1/fve-analysis/run", json={"kwp": 8.0},
                    headers=_auth(customer_token))
    assert r.status_code == 200, r.text
    assert r.json()["kwp"] == 8.0


# ---------- M3.3 geocode / appliances / economic ----------

def test_geocode_finds_city(client, admin_token):
    """Nominatim vrací seznam kandidátů — i pro obec s více shodami."""
    r = client.post("/api/v1/fve-analysis/geocode", json={"address": "Telnice"},
                    headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    assert results, "Nominatim musí pro Telnici vrátit alespoň jeden výsledek"
    first = results[0]
    assert {"latitude", "longitude", "display_name"} <= set(first)
    assert 48.0 < first["latitude"] < 52.0
    assert first["display_name"]


def test_geocode_rejects_empty(client, admin_token):
    r = client.post("/api/v1/fve-analysis/geocode", json={"address": "  "},
                    headers=_auth(admin_token))
    assert r.status_code == 400
    detail = r.json()["detail"].lower()
    assert "adres" in detail or "obec" in detail, detail


def test_geocode_not_found_returns_empty_list(client, admin_token):
    """S Nominatim se adresy najdou, takže „nenalezeno" = 200 + prázdné results.

    Živý endpoint, ne mock — chceme ověřit skutečné chování Nominatim.
    """
    r = client.post("/api/v1/fve-analysis/geocode",
                    json={"address": "qzxwvu12345neexistuje"},
                    headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["results"] == []


def test_appliances_endpoint(client, admin_token):
    r = client.get("/api/v1/fve-analysis/appliances", headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    appliances = r.json()["appliances"]
    # 20 = stav ApplianceManager, ne 17 ze stareho Streamlitu (viz Ruling 2)
    assert len(appliances) == 20
    assert {"name", "power_kw", "type", "description"} == set(appliances[0].keys())


def test_economic_endpoint(client, admin_token):
    r = client.post("/api/v1/fve-analysis/economic",
                    json={"annual_savings": 30000, "investment_cost": 350000,
                          "years": 20}, headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    assert set(r.json()["metrics"]) == {
        "payback_years", "discounted_payback_years", "npv_czk",
        "final_pv_gain_czk", "final_pv_reinvest_gain_czk", "final_sp500_net_czk",
    }
    body = r.json()
    assert body["investment_cost"] == 350000.0  # bez fve_materials = legacy
    assert body["investment_breakdown"] == []


# ---------- M3.4 uložení ----------

def test_save_requires_contact(client, admin_token):
    r = client.post("/api/v1/fve-analysis",
                    json={"params": {"kwp": 10.0}, "contact": {}},
                    headers=_auth(admin_token))
    assert r.status_code == 422


def test_save_validates_phone(client, admin_token):
    r = _save(client, admin_token, contact={
        "name": "Jiří Novák", "email": "novak@example.cz", "phone": "123"})
    assert r.status_code == 422
    assert "číslic" in str(r.json()["detail"])


def test_save_rejects_invalid_email(client, admin_token):
    r = _save(client, admin_token, contact={
        "name": "Jiří Novák", "email": "ne-email", "phone": "+420 777 123 456"})
    assert r.status_code == 422


def test_save_creates_project_in_fve_analyza_state(client, admin_token):
    r = _save(client, admin_token, params={"kwp": 12.0, "annual_consumption_mwh": 6.0},
              name="Novák — FVE 12 kWp")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "fve_analyza"
    assert body["customer_created"] is True
    assert body["share_code"]

    detail = client.get(f"/api/v1/projects/{body['id']}", headers=_auth(admin_token))
    assert detail.status_code == 200, detail.text
    proj = detail.json()
    assert proj["customer_name"] == "Jiří Novák"
    assert proj["customer_email"] == "novak@example.cz"
    assert proj["customer_phone"] == "+420 777 123 456"
    assert proj["fve_params"]["kwp"] == 12.0
    assert "active_appliances" in proj["fve_params"]


def test_save_derives_name_from_contact(client, admin_token):
    r = _save(client, admin_token, contact={
        "name": "Petr Svoboda", "email": "svoboda@example.cz",
        "phone": "+420 777 000 111"})
    detail = client.get(f"/api/v1/projects/{r.json()['id']}",
                        headers=_auth(admin_token)).json()
    assert "Petr Svoboda" in detail["name"]


def test_save_reuses_existing_user_on_second_analysis(client, admin_token):
    """Druhé uložení se stejným e-mailem nesmí vytvořit duplicitního usera."""
    contact = {"name": "Petr Nový", "email": "petr@example.cz",
               "phone": "+420 777 999 000"}
    first = _save(client, admin_token, contact=contact)
    second = _save(client, admin_token, contact=contact)
    assert first.json()["customer_created"] is True
    assert second.json()["customer_created"] is False
    assert second.json()["customer_id"] == first.json()["customer_id"]


def test_save_is_case_insensitive_on_email(client, admin_token):
    """JANA@example.cz a jana@example.cz jsou jeden zákazník, ne dva."""
    first = _save(client, admin_token, contact={
        "name": "Jana Krátká", "email": "Jana@Example.cz", "phone": "+420 777 222 333"})
    second = _save(client, admin_token, contact={
        "name": "Jana Krátká", "email": "jana@example.cz", "phone": "+420 777 222 333"})
    assert second.json()["customer_created"] is False
    assert second.json()["customer_id"] == first.json()["customer_id"]


def test_save_stores_appliances_as_list(client, admin_token):
    r = _save(client, admin_token, params={
        "kwp": 10.0, "active_appliances": ["Bojler - 200l", "Pračka"]})
    proj = client.get(f"/api/v1/projects/{r.json()['id']}",
                      headers=_auth(admin_token)).json()
    assert proj["fve_params"]["active_appliances"] == ["Bojler - 200l", "Pračka"]


def test_saved_params_feed_back_into_run(client, admin_token):
    """Round-trip: co se uloží, to se dá znovu spočítat beze ztráty."""
    r = _save(client, admin_token, params={
        "kwp": 15.0, "battery_capacity": 12.0,
        "active_appliances": ["Bojler - 200l"]})
    proj = client.get(f"/api/v1/projects/{r.json()['id']}",
                      headers=_auth(admin_token)).json()
    again = client.post("/api/v1/fve-analysis/run", json=proj["fve_params"],
                        headers=_auth(admin_token))
    assert again.status_code == 200, again.text
    assert again.json()["kwp"] == 15.0


# ---------- RBAC ----------

def test_customer_can_save_own_analysis_and_see_it(client, customer_token):
    """Nová schopnost: zákazník si analýzu uloží sám a najde ji v seznamu."""
    r = client.post("/api/v1/fve-analysis", json={
        "params": {"kwp": 9.0},
        "contact": {"name": "Zákazník Test", "email": "zakaznik-test@example.cz",
                    "phone": "+420 777 111 222"},
    }, headers=_auth(customer_token))
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    mine = client.get("/api/v1/projects", headers=_auth(customer_token))
    assert mine.status_code == 200
    body = mine.json()
    ids = [p["id"] for p in (body if isinstance(body, list) else body.get("projects", []))]
    assert pid in ids, "zákazník nevidí vlastní analýzu"


def test_customer_cannot_see_other_analysis(client, admin_token, customer_token):
    """Bezpečnostní pravidlo zůstává: cizí analýzu nevidí."""
    created = _save(client, admin_token, contact={
        "name": "Cizí Zákazník", "email": "cizi@example.cz",
        "phone": "+420 777 333 444"}).json()
    r = client.get(f"/api/v1/projects/{created['id']}", headers=_auth(customer_token))
    assert r.status_code == 403


def test_customer_cannot_see_other_analysis_via_run(client, customer_token):
    """Ani přes ?id= parametr se nedá otevřít cizí analýza."""
    created = _save(client, customer_token, contact={
        "name": "Vlastní", "email": "vlastni@example.cz",
        "phone": "+420 777 444 555"}).json()
    admin_view = client.get(f"/api/v1/projects/{created['id']}",
                            headers=_auth(admin_token_of(client))).json()
    # vlastník si ji načíst smí
    own = client.get(f"/api/v1/projects/{created['id']}",
                     headers=_auth(customer_token))
    assert own.status_code == 200
    assert admin_view["id"] == created["id"]


def admin_token_of(client):
    return _login(client, "admin@test.local", "Admin123!")


# ---------- M4.2 převod na zakázku ----------

def test_customer_cannot_convert(client, admin_token, customer_token):
    pid = _save(client, admin_token, contact={
        "name": "Konvert Test", "email": "konvert@example.cz",
        "phone": "+420 777 555 666"}).json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/convert-to-order",
                    headers=_auth(customer_token))
    assert r.status_code == 403


def test_convert_moves_params_and_flip_status(client, admin_token):
    pid = _save(client, admin_token, params={"kwp": 15.0, "battery_capacity": 10.0},
                contact={"name": "Konvert Test", "email": "konvert@example.cz",
                         "phone": "+420 777 555 666"}).json()["id"]

    ok = client.post(f"/api/v1/projects/{pid}/convert-to-order",
                     headers=_auth(admin_token))
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "lead"

    proj = client.get(f"/api/v1/projects/{pid}", headers=_auth(admin_token)).json()
    assert proj["status"] == "lead"
    assert proj["antelon_params"]["kwp"] == 15.0
    assert proj["antelon_params"]["battery_capacity"] == 10.0
    assert proj["antelon_params"]["fve_analysis_source"]["share_code"] == proj["share_code"]
    # původní parametry analýzy zůstávají čitelné — analýza se nepřepisuje
    assert proj["fve_params"]["kwp"] == 15.0


def test_convert_is_idempotent_409(client, admin_token):
    pid = _save(client, admin_token, contact={
        "name": "Idem Test", "email": "idem@example.cz",
        "phone": "+420 777 666 777"}).json()["id"]
    assert client.post(f"/api/v1/projects/{pid}/convert-to-order",
                       headers=_auth(admin_token)).status_code == 200
    again = client.post(f"/api/v1/projects/{pid}/convert-to-order",
                        headers=_auth(admin_token))
    assert again.status_code == 409


def test_convert_attaches_pipeline(client, admin_token):
    """Po převodu musí být pipeline, jinak zakázka nenaběhne."""
    pid = _save(client, admin_token, contact={
        "name": "Pipeline Test", "email": "pipe@example.cz",
        "phone": "+420 777 777 888"}).json()["id"]
    client.post(f"/api/v1/projects/{pid}/convert-to-order",
                headers=_auth(admin_token))
    view = client.get(f"/api/v1/projects/{pid}/pipeline", headers=_auth(admin_token))
    assert view.status_code == 200, view.text
    assert len(view.json()["steps"]) > 0


def test_convert_marks_analysis_supplied_steps_done(client, admin_token):
    """Kroky, které analýza fakticky dodala, nesmí čekat na obchodníka.

    Porovnává se začátek názvu, ne přesná shoda: v šabloně se krok jmenuje
    „první indikativní nabídka dle telefonátu - tel/email", takže přesná
    shoda by nikdy nesedla a funkce by byla mrtvá.

    Test je záměrně ne-vakuový: vyžaduje, aby se alespoň jeden krok
    skutečně omarkoval. Předtím tady bylo `all()` nad prázdným seznamem,
    což prošlo vždycky a neověřovalo nic.
    """
    pid = _save(client, admin_token, contact={
        "name": "Kroky Test", "email": "kroky@example.cz",
        "phone": "+420 777 888 999"}).json()["id"]
    client.post(f"/api/v1/projects/{pid}/convert-to-order",
                headers=_auth(admin_token))
    steps = client.get(f"/api/v1/projects/{pid}/pipeline",
                       headers=_auth(admin_token)).json()["steps"]

    supplied = ("první indikativní nabídka", "Zjištění roční spotřeby")
    matched = [s for s in steps
               if any(s["name"].strip().lower().startswith(w) for w in supplied)]

    assert matched, (
        "žádný krok se neomarkoval — analýza nedodává nic, funkce je mrtvá. "
        f"Názvy v šabloně: {[s['name'] for s in steps]}"
    )
    assert all(s["status"] == "done" for s in matched), \
        [s["name"] for s in matched if s["status"] != "done"]
    for s in matched:
        assert "FVE" in (s.get("note") or ""), s["name"]


def test_convert_marks_nothing_in_unrelated_step(client, admin_token):
    """Ostatní kroky zůstanou nedělané — neoznačíme všechno done."""
    pid = _save(client, admin_token, contact={
        "name": "Ostatni Test", "email": "ostatni@example.cz",
        "phone": "+420 777 111 000"}).json()["id"]
    client.post(f"/api/v1/projects/{pid}/convert-to-order",
                headers=_auth(admin_token))
    steps = client.get(f"/api/v1/projects/{pid}/pipeline",
                       headers=_auth(admin_token)).json()["steps"]
    done = [s for s in steps if s["status"] == "done"]
    assert 0 < len(done) < len(steps), (
        f"označené kroky: {len(done)} z {len(steps)} — buď nic, nebo všechno"
    )
    # Montáž analýza nedodává, obchodník ji musí naplánovat sám
    assert any("Montáž" in s["name"] and s["status"] != "done" for s in steps)


def test_convert_404_on_missing_project(client, admin_token):
    r = client.post("/api/v1/projects/999999/convert-to-order",
                    headers=_auth(admin_token))
    assert r.status_code == 404


# ---------- PDF ----------

def test_energy_pdf_returns_pdf(client, admin_token):
    """Legacy /report/energy je bez /api/v1 a bez auth — client má
    baseURL=/api/v1, takže potřebujeme vlastní cestu pod prefixem."""
    result = client.post("/api/v1/fve-analysis/run", json={"kwp": 10.0},
                         headers=_auth(admin_token)).json()
    r = client.post("/api/v1/fve-analysis/report/energy",
                    json={"energy": result, "economic": None},
                    headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF", "odpověď není PDF"
    assert len(r.content) > 1000, "PDF je podezřele malé"
    assert "attachment" in r.headers["content-disposition"]


def test_energy_pdf_requires_auth(client):
    """Legacy endpoint je bez auth. Nový nesmí být — kdokoli by si
    mohl generovat PDF z cizího výsledku analýzy."""
    r = client.post("/api/v1/fve-analysis/report/energy", json={})
    assert r.status_code in (401, 422)


def test_energy_pdf_customer_allowed(client, customer_token):
    """Zákazník si analýzu spočítá — chce si ji i stáhnout jako PDF."""
    result = client.post("/api/v1/fve-analysis/run", json={"kwp": 8.0},
                         headers=_auth(customer_token)).json()
    r = client.post("/api/v1/fve-analysis/report/energy",
                    json={"energy": result, "economic": None},
                    headers=_auth(customer_token))
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"


def test_energy_pdf_handles_broken_payload(client, admin_token):
    """Prázdný payload je chyba uživatele, ne 500 — a nebere to celý server."""
    r = client.post("/api/v1/fve-analysis/report/energy", json={},
                    headers=_auth(admin_token))
    assert r.status_code in (400, 422, 500)
    # server nezůstal viset
    assert client.post("/api/v1/fve-analysis/run", json={},
                       headers=_auth(admin_token)).status_code == 200


def test_convert_requires_auth(client):
    r = client.post("/api/v1/projects/1/convert-to-order")
    assert r.status_code in (401, 422)


def test_save_after_delete_reuses_ids_without_collision(client, admin_token, db_path):
    """Bod 1: uložit -> smazat -> znovu uložit (stejný zákazník) musí projít.

    Před opravou: smazání nechalo sirotky v project_users; další projekt dostal
    stejné id jako smazaný a stejný zákazník (stejný e-mail -> stejné user_id)
    -> UNIQUE constraint failed: project_users.project_id, project_users.user_id.
    Restart init_db mezi smazáním a dalším uložením spustí sweep z Tasku 1.
    """
    contact = {"name": "První", "email": "opakovany@example.cz",
               "phone": "+420777111222"}
    first = _save(client, admin_token, contact=contact)
    assert first.status_code == 200, first.text
    pid = first.json()["id"]

    r = client.delete(f"/api/v1/projects/{pid}", headers=_auth(admin_token))
    assert r.status_code == 200, r.text

    # Restart init_db spustí sweep sirotků z Tasku 1.
    st.init_db(db_path)

    second = _save(client, admin_token, contact=contact)
    assert second.status_code == 200, second.text


# ---------- RBAC: buyer smí uložit, převod jen admin/antelon/sales ----------

def _add_user(db_path, email, role):
    """Vytvoří uživatele přímo v DB — API na vytvoření uživatele neexistuje."""
    import json
    import sqlite3
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


def test_buyer_can_save_analysis(client, admin_token, db_path):
    _add_user(db_path, "buyer1@test.local", "buyer")
    token = _login(client, "buyer1@test.local", "Xx123456!")
    r = _save(client, token, contact={
        "name": "Kupující", "email": "kupujici@example.cz",
        "phone": "+420777123456"})
    assert r.status_code == 200, r.text


def test_buyer_cannot_convert_to_order(client, admin_token, db_path):
    r = _save(client, admin_token, contact={
        "name": "Ke Konverzi", "email": "kkonverze@example.cz",
        "phone": "+420777123456"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    _add_user(db_path, "buyer@test.local", "buyer")
    token = _login(client, "buyer@test.local", "Xx123456!")
    r = client.post(f"/api/v1/projects/{pid}/convert-to-order",
                    headers=_auth(token))
    assert r.status_code == 403, r.text


def test_sales_can_convert_to_order(client, admin_token, db_path):
    _add_user(db_path, "sales@test.local", "sales")
    token = _login(client, "sales@test.local", "Xx123456!")

    pid = _save(client, admin_token, contact={
        "name": "Prodejce", "email": "prodej@example.cz",
        "phone": "+420777123456"}).json()["id"]

    r = client.post(f"/api/v1/projects/{pid}/convert-to-order",
                    headers=_auth(token))
    assert r.status_code == 200, r.text


# ---------- M4 — investice ze snímku materiálů (část 3) ----------

def test_economic_uses_bom_snapshot(client, admin_token):
    """Snímek fve_materials má přednost před legacy 350 000 Kč."""
    legacy = client.post("/api/v1/fve-analysis/economic",
                         json={"annual_savings": 30000},
                         headers=_auth(admin_token)).json()
    with_bom = client.post("/api/v1/fve-analysis/economic",
                           json={"annual_savings": 30000,
                                 "fve_materials": [{"line_total": 300000.0}]},
                           headers=_auth(admin_token)).json()
    assert with_bom["metrics"]["npv_czk"] != legacy["metrics"]["npv_czk"]


def test_economic_pdf_uses_bom_snapshot(client, admin_token, monkeypatch):
    """`eco_keys` musí propustit `fve_materials` (ruling R6 z Tasku 5).

    `/projects/{id}/generate` filtruje uložené fve_params na `eco_keys`.
    Kdyby tam `fve_materials` chybělo, vytisklo by se ekonomické PDF
    mlčky s legacy investicí 350 000 Kč místo se snímkem BOM.
    """
    captured: dict = {}

    def spy_economic(valid):
        captured.update(valid)
        return {"metrics": {}, "investment_cost": 300000.0, "annual_savings": 30000.0}

    # analogy k úspěšně spočítané analýze — ať endpoint nemusí chodit do PVGIS
    monkeypatch.setattr(
        "app.fve_analysis.run_energy_analysis",
        lambda p: {"financial_balance": {"annual_savings_czk": 30000.0}})
    monkeypatch.setattr("app.fve_analysis.run_economic_analysis", spy_economic)
    monkeypatch.setattr(
        "app.reporting.ReportGenerator.generate_economic_report",
        lambda self, data: b"%PDF-1.4 fake economic report")

    snapshot = [{"material_id": 5, "code": "SYS-10-10", "category": "system",
                 "qty": 1, "unit_price": 300000.0, "line_total": 300000.0}]
    pid = _save(client, admin_token, params={
        "kwp": 10.0, "bom_mode": "system", "system_material_id": 5,
        "fve_materials": snapshot,
    }).json()["id"]

    r = client.post(f"/api/v1/projects/{pid}/generate",
                    json={"template": "economic"}, headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    # snímek se dostal přes eco_keys až k ekonomické analýze
    assert captured["fve_materials"] == snapshot
    # annual_savings se dopočítá z energetické větve, než se filtruje
    assert captured["annual_savings"] == 30000.0


# ---------- FveParams — přepínač sestavy (část 3) ----------

def test_save_persists_bom_fields(client, admin_token):
    params = {
        "kwp": 10.0,
        "bom_mode": "system",
        "system_material_id": 5,
        "fve_materials": [{
            "material_id": 5, "code": "SYS-10-10", "category": "system",
            "qty": 1, "unit_price": 300000.0, "line_total": 300000.0,
        }],
    }
    r = _save(client, admin_token, params=params)
    assert r.status_code == 200, r.text
    proj = client.get(f"/api/v1/projects/{r.json()['id']}",
                      headers=_auth(admin_token)).json()
    fp = proj["fve_params"]
    assert fp["bom_mode"] == "system"
    assert fp["system_material_id"] == 5
    assert fp["fve_materials"][0]["line_total"] == 300000.0


def test_save_rejects_unknown_bom_mode(client, admin_token):
    r = _save(client, admin_token, params={"bom_mode": "drak"})
    assert r.status_code == 422
    assert "sestavy" in str(r.json()["detail"])


def test_save_defaults_bom_mode_to_components(client, admin_token):
    r = _save(client, admin_token, params={"kwp": 10.0})
    proj = client.get(f"/api/v1/projects/{r.json()['id']}",
                      headers=_auth(admin_token)).json()
    assert proj["fve_params"]["bom_mode"] == "components"
    assert proj["fve_params"]["fve_materials"] == []


def test_energy_pdf_with_economic_contains_economics(client, admin_token):
    """Ekonomika v payloadu → PDF obsahuje její sekci (kontrola přes log-free cestu)."""
    result = client.post("/api/v1/fve-analysis/run", json={"kwp": 10.0},
                         headers=_auth(admin_token)).json()
    economic = client.post("/api/v1/fve-analysis/economic",
                           json={"annual_savings": 25000.0},
                           headers=_auth(admin_token)).json()
    r = client.post("/api/v1/fve-analysis/report/energy",
                    json={"energy": result, "economic": economic},
                    headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"


def test_energy_pdf_missing_energy_is_400(client, admin_token):
    r = client.post("/api/v1/fve-analysis/report/energy",
                    json={"energy": None, "economic": None},
                    headers=_auth(admin_token))
    assert r.status_code == 400


def test_energy_pdf_non_dict_energy_is_400(client, admin_token):
    """Číslo/místo dictu nesmí shodit endpoint neologovanou 500."""
    for bad in (5, [1, 2], "textbook"):
        r = client.post("/api/v1/fve-analysis/report/energy",
                        json={"energy": bad, "economic": None},
                        headers=_auth(admin_token))
        assert r.status_code == 400, (bad, r.status_code)


def test_energy_pdf_non_dict_economic_is_400(client, admin_token):
    r = client.post("/api/v1/fve-analysis/report/energy",
                    json={"energy": {"energy_balance_kwh": {}}, "economic": [1, 2]},
                    headers=_auth(admin_token))
    assert r.status_code == 400


def test_energy_pdf_logs_exception_type(client, admin_token, caplog):
    """Selhání generátoru musí být v logu i v hlášce s typem výjimky."""
    import logging
    from unittest.mock import patch

    with patch("app.reporting.ReportGenerator.generate_energy_report",
               side_effect=RuntimeError("boom")):
        with caplog.at_level(logging.ERROR):
            r = client.post(
                "/api/v1/fve-analysis/report/energy",
                json={"energy": {"energy_balance_kwh": {}}, "economic": None},
                headers=_auth(admin_token))
    assert r.status_code == 500
    assert "RuntimeError" in r.json()["detail"]
    assert "RuntimeError" in caplog.text


# ---------- PDF: metadata oddílů + varianty ----------

def test_report_sections_metadata(client, admin_token):
    r = client.get("/api/v1/fve-analysis/report/sections",
                   headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    sections = r.json()["sections"]
    ids = [s["id"] for s in sections]
    assert ids[0] == "intro" and ids[-1] == "glossary"
    assert {"summary", "economic_metrics", "investment_composition"} <= set(ids)
    by_id = {s["id"]: s for s in sections}
    assert by_id["summary"]["base"] is True
    assert by_id["appendix_a"]["base"] is False
    assert by_id["summary"]["label"] and by_id["summary"]["description"]


def test_report_sections_metadata_requires_auth(client):
    r = client.get("/api/v1/fve-analysis/report/sections")
    assert r.status_code in (401, 422)


def test_sales_can_access_report_sections(client, db_path):
    """`sales` je firemní role (vidí tlačítka firmy) → nesmí dostat 403."""
    _add_user(db_path, "salesrep@test.local", "sales")
    token = _login(client, "salesrep@test.local", "Xx123456!")
    r = client.get("/api/v1/fve-analysis/report/sections",
                   headers=_auth(token))
    assert r.status_code == 200, r.text


def _spy_energy_pdf(captured):
    """Zachytí argumenty, se kterými endpoint volá generátor PDF."""
    def fake(self, data, economic=None, variant="company",
             sections=None, params=None):
        captured.update(data=data, economic=economic, variant=variant,
                        sections=sections, params=params)
        return b"%PDF-1.4 fake"
    return fake


def test_energy_pdf_company_is_default_variant(client, admin_token):
    captured = {}
    with patch("app.reporting.ReportGenerator.generate_energy_report",
               _spy_energy_pdf(captured)):
        r = client.post("/api/v1/fve-analysis/report/energy",
                        json={"energy": {"energy_balance_kwh": {}}, "economic": None},
                        headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    assert captured["variant"] == "company"


def test_energy_pdf_customer_cannot_request_company_variant(client, customer_token):
    """Zákazník nesmí vynutit firemní variantu ani když ji pošle."""
    captured = {}
    with patch("app.reporting.ReportGenerator.generate_energy_report",
               _spy_energy_pdf(captured)):
        r = client.post("/api/v1/fve-analysis/report/energy",
                        json={"energy": {"energy_balance_kwh": {}},
                              "economic": None, "variant": "company"},
                        headers=_auth(customer_token))
    assert r.status_code == 200, r.text
    assert captured["variant"] == "customer"


def test_energy_pdf_admin_respects_requested_variant(client, admin_token):
    captured = {}
    with patch("app.reporting.ReportGenerator.generate_energy_report",
               _spy_energy_pdf(captured)):
        r = client.post("/api/v1/fve-analysis/report/energy",
                        json={"energy": {"energy_balance_kwh": {}},
                              "economic": None, "variant": "customer"},
                        headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    assert captured["variant"] == "customer"


def test_energy_pdf_unknown_section_ids_ignored(client, admin_token):
    captured = {}
    with patch("app.reporting.ReportGenerator.generate_energy_report",
               _spy_energy_pdf(captured)):
        r = client.post("/api/v1/fve-analysis/report/energy",
                        json={"energy": {"energy_balance_kwh": {}}, "economic": None,
                              "sections": ["summary", "neexistuje", "glossary"]},
                        headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    assert "neexistuje" not in captured["sections"]
    # pevný základ se doplní (chování resolve_sections)
    assert "summary" in captured["sections"]


def test_energy_pdf_passes_params_through(client, admin_token):
    captured = {}
    with patch("app.reporting.ReportGenerator.generate_energy_report",
               _spy_energy_pdf(captured)):
        r = client.post("/api/v1/fve-analysis/report/energy",
                        json={"energy": {"energy_balance_kwh": {}}, "economic": None,
                              "params": {"price_power": 4.5}},
                        headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    assert captured["params"] == {"price_power": 4.5}


def test_energy_pdf_drops_economic_sections_without_economic(client, admin_token):
    captured = {}
    with patch("app.reporting.ReportGenerator.generate_energy_report",
               _spy_energy_pdf(captured)):
        r = client.post("/api/v1/fve-analysis/report/energy",
                        json={"energy": {"energy_balance_kwh": {}}, "economic": None},
                        headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    assert "economic_metrics" not in captured["sections"]
    assert "appendix_a" not in captured["sections"]
