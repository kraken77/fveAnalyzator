"""M3–M5 — API /api/v1/fve-analysis/*, uložení, převod na zakázku, RBAC.

Autentizace jako v test_m5_admin_api.py: prihlaseni pres /api/v1/auth/login.
"""
import pytest


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
    r = client.post("/api/v1/fve-analysis/geocode", json={"address": "Praha"},
                    headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    assert 49 < r.json()["latitude"] < 51


def test_geocode_rejects_empty(client, admin_token):
    r = client.post("/api/v1/fve-analysis/geocode", json={"address": "  "},
                    headers=_auth(admin_token))
    assert r.status_code == 400
    # „obc" jako kmen — „obec"/„obce"/„obcí" jsou různé tvary
    detail = r.json()["detail"].lower()
    assert "obc" in detail or "měst" in detail, detail


def test_geocode_explains_itself_when_not_found(client, admin_token):
    """Open-Meteo je name search. Ulice nenajde — musí to říct, ne vrátit prázdno.

    Živý endpoint, ne mock: chceme vidět skutečnou hlášku, kterou
    uživatel uvidí.
    """
    r = client.post("/api/v1/fve-analysis/geocode",
                    json={"address": "Vodičkova 5"}, headers=_auth(admin_token))
    assert r.status_code == 404, r.text
    detail = r.json()["detail"].lower()
    assert "obc" in detail or "měst" in detail, detail


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

    Porovnává se název (ID se liší mezi instalacemi). Pokud šablona
    'ostatni' žádný takový krok nemá, test projde — to není chyba.
    """
    pid = _save(client, admin_token, contact={
        "name": "Kroky Test", "email": "kroky@example.cz",
        "phone": "+420 777 888 999"}).json()["id"]
    client.post(f"/api/v1/projects/{pid}/convert-to-order",
                headers=_auth(admin_token))
    steps = client.get(f"/api/v1/projects/{pid}/pipeline",
                       headers=_auth(admin_token)).json()["steps"]
    supplied = ("první indikativní nabídka", "Zjištění roční spotřeby")
    matched = [s for s in steps if s["name"].strip().lower() in supplied]
    assert all(s["status"] == "done" for s in matched), \
        [s for s in matched if s["status"] != "done"]
    for s in matched:
        assert "FVE" in (s.get("note") or "")


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
    r = client.post("/api/v1/fve-analysis/report/energy", json=result,
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
    r = client.post("/api/v1/fve-analysis/report/energy", json=result,
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
