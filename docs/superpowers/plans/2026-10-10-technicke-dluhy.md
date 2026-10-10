# Technické dluhy a robustnost — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Uzavřít šest odložených (deferred) nálezů z dřívějších plánů: robustnost PDF endpointu, bezpečnost `is_internal_user`, názvy komponent v produkčním PDF, hodnoty v legacy ekonomickém PDF, dokumentační drift a verifikaci dvojího započtení teplotní ztráty.

**Architecture:** Jde o cílené, izolované opravy bez nové architektury. Backend drží autoritu (validace vstupů, RBAC, fyzikální model), frontend jen doplní data do snímku sestavy. Každá oprava má vlastní test a commit.

**Tech Stack:** Python 3.11 / FastAPI / pytest; React + TypeScript (Vite); pvlib + PVGIS REST API (jen pro Task 7).

**Spec:** Tento plán nemá jediný spec dokument — uzavírá nálezy odložené v ledgerech:
`docs/superpowers/plans/2026-10-06-2-cenik-materialu.md` (Task 6),
`2026-10-06-3-pdf-a-ekonomika.md` (Task 5, 7),
`2026-10-06-4-produkce-a-geocoder.md` (Task 1, 2)
a v `.superpowers/sdd/2026-10-06-*/progress.md`. Podklady: tento plán + zmíněné ledgery.

## Global Constraints

- Testy se pouští **z kořene repa**: `./venv/bin/python -m pytest tests/reportgen/... -q` (NIKDY z `backend/` — cache je relativní).
- Nikdy `git add -A`; necommitovat `data/reportgen.db`, `data/reportgen.db.bak-*` ani `.superpowers/`.
- Názvy a texty v UI/reportu česky, bez diakritických zkratek v kódu.
- `_format_czk(None)` → `"-"`; `_format_number(None)` → `"-"` (řádek 23–33 `backend/app/reporting.py`).
- Backend defaulty vstupů žijí v `ReportGenerator._PARAM_DEFAULTS` (`backend/app/reporting.py:49`).
- Registrované role: `storage.ROLES = ["admin","antelon","sales","designer","warehouse","buyer","subsidy","connection","roofer","electrician","inspector","customer"]` (`backend/app/reportgen/storage.py:21`).
- `bom_mode`/`*_material_id`/`fve_materials` jsou interní a v PDF „Vstupní parametry" se neuvádějí.

## Review Focus

Pět vstupů/stavů, které spec mlčky předpokládá, ale testy dosud nechytají — každý musí mít test v tasku, který vlastní daný kód:

1. `POST /fve-analysis/report/energy` s `"energy"` jako **ne-dict** (číslo, pole, řetězec) → dnes neologovaná 500; rozumné je 400.
2. Uživatel s **neznámou rolí** (`roles=["customer","neznama"]`) → dnes `is_internal_user=True` (vidí cizí zakázky/interní materiály); rozumné je `False`.
3. Legacy ekonomické PDF (`template="economic"`) → dnes tiskne `annual_savings="-"`, `years` prázdné; rozumné je vypsat reálné (i defaultní) hodnoty.
4. Firemní PDF „Složení investice" pro **produkčně vybrané materiály** → dnes `name` chybí (tiskne kód); rozumné je název komponenty.
5. Dokumentace tvrdící obsah `data/weather_cache.db` → musí odpovídat skutečným řádkům cache.

---

### Task 1: `.gitignore` — ignorovat zálohy DB (`data/*.bak*`)

**Files:**
- Modify: `.gitignore:142-147` (blok `data/`)

**Interfaces:**
- Consumes: nic.
- Produces: nic (jen čistší `git status`).

- [ ] **Step 1: Přidej ignorovací vzory**

Za řádek `data/imports/` vlož:

```gitignore
data/*.bak
data/*.bak-*
```

(Vzory `data/reportgen.db.bak-2026-10-07` a `data/reportgen.db.bak-20261008-144555` tím zmizí z `git status`.)

- [ ] **Step 2: Ověř, že zálohy zmizely a nic živého se neignoruje**

Run: `git status --short && git check-ignore -v data/reportgen.db.bak-2026-10-07`
Expected: v `git status` už nejsou `data/*.bak-*`; `git check-ignore` vypíše řádek s `data/*.bak-*`; `data/reportgen.db` zůstává ignorovaný přes `data/reportgen.db`.

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: ignorovat zalohy DB data/*.bak*"
```

---

### Task 2: Robustnost `report/energy` — ne-dict `energy`/`economic` → 400

**Files:**
- Modify: `backend/app/reportgen/fve_router.py:245-248`
- Test: `tests/reportgen/test_fve_api.py` (za `test_energy_pdf_missing_energy_is_400`, řádek ~627)

**Interfaces:**
- Consumes: `HTTPException`, `ANY_ROLE` (existují).
- Produces: chování endpointu — `energy` musí být `dict`; `economic` je `dict` nebo `None`; jinak 400.

- [ ] **Step 1: Napiš padající testy**

Vlož do `tests/reportgen/test_fve_api.py` hned za `test_energy_pdf_missing_energy_is_400`:

```python
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
```

- [ ] **Step 2: Spusť testy — musí selhat**

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_api.py -q -k "non_dict"`
Expected: FAIL — první test dostane 500 (TypeError `not in` na čísle), druhý 500.

- [ ] **Step 3: Doplň guard**

V `backend/app/reportgen/fve_router.py` nahraď:

```python
    energy = payload.get("energy")
    economic = payload.get("economic")
    if not energy or "energy_balance_kwh" not in energy:
        raise HTTPException(400, "Chybí výsledek analýzy")
```

za:

```python
    energy = payload.get("energy")
    economic = payload.get("economic")
    # `energy` musí být dict — jinak `"energy_balance_kwh" not in energy`
    # vyhodí TypeError a z endpointu se stane neologovaná 500 (třída, kterou
    # u `sections` řešil fix F4).
    if not isinstance(energy, dict) or "energy_balance_kwh" not in energy:
        raise HTTPException(400, "Chybí výsledek analýzy")
    if economic is not None and not isinstance(economic, dict):
        raise HTTPException(400, "Neplatný výsledek ekonomické analýzy")
```

- [ ] **Step 4: Spusť testy — musí projít**

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_api.py -q`
Expected: PASS (všechny včetně nových `non_dict`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/reportgen/fve_router.py tests/reportgen/test_fve_api.py
git commit -m "fix(fve-api): report/energy vraci 400 na ne-dict energy/economic"
```

---

### Task 3: `is_internal_user` — allow-list zaměstnaneckých rolí

**Files:**
- Modify: `backend/app/reportgen/auth.py:75-82`
- Test: `tests/reportgen/test_internal_roles.py` (nový)

**Interfaces:**
- Consumes: `storage.ROLES`.
- Produces: `auth.INTERNAL_ROLES: frozenset[str]`; `is_internal_user(user) -> bool`.

- [ ] **Step 1: Napiš padající test**

Vytvoř `tests/reportgen/test_internal_roles.py`:

```python
"""Interní viditelnost — jen známé zaměstnanecké role, ne „cokoli mimo customer“."""
from reportgen.auth import INTERNAL_ROLES, is_internal_user
from reportgen.storage import ROLES


class _U:
    """Minimální stub Useru — auth funkce čtou jen .roles a .role."""

    def __init__(self, roles, primary=None):
        self.roles = list(roles)
        self.role = primary or (roles[0] if roles else "customer")


def test_allow_list_covers_all_registered_staff_roles():
    # Jediná neinterní registrovaná role je customer; seznam se nesmí rozejít.
    assert set(INTERNAL_ROLES) == set(ROLES) - {"customer"}


def test_known_staff_roles_are_internal():
    for r in ("admin", "antelon", "sales", "buyer", "inspector", "roofer"):
        assert is_internal_user(_U([r])) is True, r


def test_customer_is_not_internal():
    assert is_internal_user(_U(["customer"])) is False
    assert is_internal_user(None) is False


def test_unknown_role_does_not_grant_internal():
    """Dřív stačilo být „cokoli jiného než customer“ — to je bezpečnostní díra."""
    assert is_internal_user(_U(["customer", "neznama"])) is False
    assert is_internal_user(_U(["fuj"])) is False


def test_primary_role_fallback_when_roles_empty():
    assert is_internal_user(_U([], primary="sales")) is True
    assert is_internal_user(_U([], primary="customer")) is False
```

- [ ] **Step 2: Spusť test — musí selhat**

Run: `./venv/bin/python -m pytest tests/reportgen/test_internal_roles.py -q`
Expected: FAIL — `ImportError: cannot import name 'INTERNAL_ROLES'`.

- [ ] **Step 3: Zaveď allow-list**

V `backend/app/reportgen/auth.py` nahraď blok:

```python
def is_internal_user(user: Optional[User]) -> bool:
    """Interní role (ne „customer“) — zaměstnanci vidí všechny zakázky v dispečinku."""
    if user is None:
        return False
    roles = list(user.roles or [])
    if not roles and user.role:
        roles = [user.role]
    return any(r != "customer" for r in roles)
```

za:

```python
# Zaměstnanecké role s interní viditelností (dispečink, interní materiály,
# interní PDF). Drží se synchronně se storage.ROLES mínus "customer" —
# hlídá test_internal_roles. Neznámá/překlepnutá role interní přístup NEDÁVÁ
# (dřív stačilo být „cokoli jiného než customer“, což bylo příliš benevolentní).
INTERNAL_ROLES = frozenset({
    "admin", "antelon", "sales", "designer", "warehouse", "buyer",
    "subsidy", "connection", "roofer", "electrician", "inspector",
})


def is_internal_user(user: Optional[User]) -> bool:
    """Interní rolí vidí zaměstnanec všechny zakázky v dispečinku."""
    if user is None:
        return False
    roles = list(user.roles or [])
    if not roles and user.role:
        roles = [user.role]
    return any(r in INTERNAL_ROLES for r in roles)
```

- [ ] **Step 4: Spusť test — musí projít**

Run: `./venv/bin/python -m pytest tests/reportgen/test_internal_roles.py -q`
Expected: PASS (5 testů).

- [ ] **Step 5: Ověř, že se nerozbily testy závislé na viditelnosti**

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_api.py tests/reportgen/test_materials.py -q`
Expected: PASS (chování pro registrované role je shodné).

- [ ] **Step 6: Commit**

```bash
git add backend/app/reportgen/auth.py tests/reportgen/test_internal_roles.py
git commit -m "fix(auth): is_internal_user jen pro zname zamestnanecke role (allow-list)"
```

---

### Task 4: Legacy ekonomické PDF — zobrazit reálné vstupy místo „-"

**Files:**
- Modify: `backend/app/fve_analysis.py:512-527` (`run_economic_analysis` return)
- Test: `tests/reportgen/test_fve_analysis.py` (echo) + `tests/reportgen/test_report_pdf.py` (render)

**Interfaces:**
- Consumes: `_p(name, default)` uvnitř `run_economic_analysis`.
- Produces: `run_economic_analysis(...)` nově vrací i `annual_savings`, `years`, `sp500_return`, `inflation`, `discount_rate` (float/int).

- [ ] **Step 1: Napiš padající test na echo vstupů**

Přidej do `tests/reportgen/test_fve_analysis.py`:

```python
def test_economic_result_echoes_inputs_for_report():
    """Legacy ekonomické PDF čte `annual_savings`/`years`/`sp500_return`/
    `inflation`/`discount_rate` přímo z výsledku — musí je dostat."""
    from app.fve_analysis import run_economic_analysis

    r = run_economic_analysis({"annual_savings": 25000.0, "years": 25,
                               "sp500_return": 8, "inflation": 3,
                               "discount_rate": 8})
    assert r["annual_savings"] == 25000.0
    assert r["years"] == 25
    assert r["sp500_return"] == 8
    assert r["inflation"] == 3
    assert r["discount_rate"] == 8


def test_economic_result_echo_uses_defaults_when_missing():
    from app.fve_analysis import run_economic_analysis

    r = run_economic_analysis({})
    assert r["years"] == 20
    assert r["sp500_return"] == 8
    assert r["inflation"] == 3
    assert r["discount_rate"] == 8
    assert r["annual_savings"] == 30000  # default shodný s calculate_investment_comparison
```

- [ ] **Step 2: Spusť testy — musí selhat**

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_analysis.py -q -k echo`
Expected: FAIL — `KeyError: 'annual_savings'`.

- [ ] **Step 3: Doplnit echo do návratového dictu**

V `backend/app/fve_analysis.py` ve `return { ... }` (za `"investment_cost": investment_cost,`) přidej:

```python
        # Vstupní hodnoty zpět pro legacy PDF `economic_report.html`, které je
        # čte přímo z výsledku (dřív chyběly → tisklo se "-"/prázdno).
        "annual_savings": float(_p("annual_savings", 30000)),
        "years": years,
        "sp500_return": float(_p("sp500_return", 8)),
        "inflation": float(_p("inflation", 3)),
        "discount_rate": float(_p("discount_rate", 8)),
```

(`years` je už spočítané na řádku 495 jako `int(_p("years", 20))`.)

- [ ] **Step 4: Spusť echo testy — musí projít**

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_analysis.py -q -k echo`
Expected: PASS.

- [ ] **Step 5: Napiš test renderu legacy ekonomického PDF**

Přidej do `tests/reportgen/test_report_pdf.py`:

```python
def test_legacy_economic_report_shows_real_inputs(monkeypatch):
    """Konec-konec: výsledek ekonomiky → HTML legacy PDF má reálné hodnoty."""
    from app.fve_analysis import run_economic_analysis

    captured = {}

    class _FakeHTML:
        def __init__(self, string):
            captured["html"] = string

        def write_pdf(self):
            return b"%PDF-1.4"

    monkeypatch.setattr("app.reporting.HTML", _FakeHTML)
    data = run_economic_analysis({"annual_savings": 25000.0, "years": 20})
    ReportGenerator().generate_economic_report(data)

    html = captured["html"]
    assert "25 000 Kč" in html          # roční úspora
    assert "20 let" in html             # období analýzy
    assert "- %" not in html            # žádné prázdné „- %" u procent
```

- [ ] **Step 6: Spusť test renderu — musí projít**

Run: `./venv/bin/python -m pytest tests/reportgen/test_report_pdf.py -q -k legacy_economic`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/fve_analysis.py tests/reportgen/test_fve_analysis.py tests/reportgen/test_report_pdf.py
git commit -m "fix(report): legacy ekonomicke PDF zobrazuje realne vstupy (echo v run_economic_analysis)"
```

---

### Task 5: Produkční PDF „Složení investice" — název komponenty místo kódu

**Files:**
- Modify: `frontend-web/src/components/fve/FveAnalysisForm.tsx:74-107` (`buildBom`)
- Test: `tests/reportgen/test_report_pdf.py` (kontrakt renderu `name`/`rating`)

**Interfaces:**
- Consumes: `FveMaterial` (má `name: string`, `rating?: number | null`), `FveMaterialLine` (má volitelné `name?: string`, `rating?: number | null`).
- Produces: snímek `fve_materials` ponese `name` i `rating`; tím je ponese `investment_breakdown` a PDF `investment_composition.html` vykreslí názvy.

- [ ] **Step 1: Napiš kontrakt-test renderu (name má přednost, jinak kód)**

Přidej do `tests/reportgen/test_report_pdf.py`:

```python
def _economic_with_breakdown(rows):
    return {
        "investment_cost": 500000.0,
        "investment_breakdown": rows,
        "metrics": {"payback_years": 10, "discounted_payback_years": 12,
                    "npv_czk": 100000.0, "final_pv_gain_czk": 1.0,
                    "final_pv_reinvest_gain_czk": 2.0, "final_sp500_net_czk": 3.0},
        "raw_data": [],
    }


def test_company_composition_prefers_name_over_code():
    rg = ReportGenerator()
    ctx = rg._build_context(_energy_data(), _economic_with_breakdown([
        {"name": "Panel 550 Wp", "code": "PAN-550", "category": "panel",
         "rating": 550, "qty": 19, "unit_price": 3000, "line_total": 57000},
    ]), variant="company")
    assert ctx["investment_breakdown"][0]["name"] == "Panel 550 Wp"
    assert ctx["investment_breakdown"][0]["rating"] == "550"


def test_company_composition_falls_back_to_code_when_name_missing():
    rg = ReportGenerator()
    ctx = rg._build_context(_energy_data(), _economic_with_breakdown([
        {"code": "PAN-550", "category": "panel", "qty": 19,
         "unit_price": 3000, "line_total": 57000},
    ]), variant="company")
    assert ctx["investment_breakdown"][0]["name"] == "PAN-550"
    assert ctx["investment_breakdown"][0]["rating"] == "-"
```

- [ ] **Step 2: Spusť testy — ověř, že projdou (kontrakt už platí)**

Run: `./venv/bin/python -m pytest tests/reportgen/test_report_pdf.py -q -k composition`
Expected: PASS — render už `name` preferuje (`reporting.py:300`). Test zamyká kontrakt, na který naváže frontend fix.

- [ ] **Step 3: Doplň `name`/`rating` do frontendu `buildBom`**

V `frontend-web/src/components/fve/FveAnalysisForm.tsx` ve větvi `bom_mode === "system"` nahraď návrat:

```tsx
    return [{
      material_id: Number(m.id), code: m.code, category: m.category,
      qty: 1, unit_price: price, line_total: Number.isFinite(price) ? price : 0,
    }];
```

za:

```tsx
    return [{
      material_id: Number(m.id), code: m.code, name: m.name,
      category: m.category, rating: m.rating ?? null,
      qty: 1, unit_price: price, line_total: Number.isFinite(price) ? price : 0,
    }];
```

A ve cyklu komponent (`for (const pick of picks)`) nahraď `out.push({ ... })`:

```tsx
    out.push({
      material_id: Number(m.id), code: m.code, category: pick.category,
      qty, unit_price: price,
      // kwp/baterie mohou být během editace NaN (prázdné pole) — živý
      // součet nesmí ukázat NaN; backend je při uložení autoritativní.
      line_total: Number.isFinite(lineTotal) ? lineTotal : 0,
    });
```

za:

```tsx
    out.push({
      material_id: Number(m.id), code: m.code, name: m.name,
      category: pick.category, rating: m.rating ?? null,
      qty, unit_price: price,
      // kwp/baterie mohou být během editace NaN (prázdné pole) — živý
      // součet nesmí ukázat NaN; backend je při uložení autoritativní.
      line_total: Number.isFinite(lineTotal) ? lineTotal : 0,
    });
```

- [ ] **Step 4: Frontend gate**

Run: `cd frontend-web && npx tsc -b && npm run build`
Expected: bez chyb (0), build projde.

- [ ] **Step 5: Ověř produkčně E2E (Playwright, throwaway skript)**

Napiš `/tmp/opencode/pw_bom_names.py`, který: přihlásí admina → `/fve-analysis` → v kartě Sestava zvolí `bom_mode="system"` + nějaký `system_material_id` → spočítá → stáhne „PDF pro firmu" → `pdftotext` výstup musí obsahovat **název** zvoleného materiálu (ne jen jeho kód). Run:

`./venv/bin/python /tmp/opencode/pw_bom_names.py`
Expected: v textu PDF je název materiálu (`m.name` z katalogu). Skript zůstává mimo repo.

- [ ] **Step 6: Commit**

```bash
git add frontend-web/src/components/fve/FveAnalysisForm.tsx tests/reportgen/test_report_pdf.py
git commit -m "fix(fve-web): snimek sestavy nese nazev a rating (PDF misto kodu zobrazi nazev)"
```

---

### Task 6: Dokumentační drift — obsah `weather_cache.db`

**Files:**
- Modify (jen pokud nesedí): `README.md:238-240`, `docs/architektura.md:234,337-339`, `backend/main.py:194-197`

**Interfaces:**
- Consumes: nic.
- Produces: nic (text).

- [ ] **Step 1: Zjisti skutečný stav cache**

Run: `./venv/bin/python -c "import sqlite3; c=sqlite3.connect('data/weather_cache.db'); rows=c.execute('select lat,lon from tmy_cache').fetchall(); print(len(rows), rows)"`
Expected: vypíše reálné (lat, lon) řádky cache.

- [ ] **Step 2: Porovnej s dokumentací**

Run: `grep -n "weather_cache" README.md docs/architektura.md && sed -n '194,197p' backend/main.py`
Expected: všechny zmínky musí odpovídat skutečnému počtu lokalit z Kroku 1 (dnes README/architektura tvrdí Praha + Ústí; pokud cache obsahuje víc lokalit, doplň je nebo zobecni na „několik lokalit včetně …").

> Pozn.: Předchozí revize dokumenty už opravila (už tam není „jen jeden záznam" ani „musí Praha"). Pokud Krok 1 potvrdí shodu, tento task končí bez změny kódu.

- [ ] **Step 3: Případná oprava textu**

Pokud se texty rozcházejí, uprav je takto (příklad pro README):

```markdown
- **Používejte souřadnice přítomné v `data/weather_cache.db`** (v dev cache
  je Praha 50.0880 / 14.4208 a Ústí nad Labem 50.6607 / 14.03227).
  Jakákoli jiná lokalita jde na síť k PVGIS a test timeoutuje.
```

- [ ] **Step 4: Ověř, že zmínky sedí**

Run: `grep -rn "weather_cache\|50.0880\|jediný záznam" README.md docs/architektura.md backend/main.py`
Expected: žádná zmínka neodporuje skutečnému stavu cache.

- [ ] **Step 5: Commit (jen když došlo ke změně)**

```bash
git add README.md docs/architektura.md backend/main.py
git commit -m "docs: srovnat obsah weather_cache v dokumentaci s realitou"
```

Pokud žádná změna nebyla potřeba, commit se nedělá a v ledgeru se zavede záznam „E1 ověřeno — bez změny".

---

### Task 7: Verifikace dvojího započtení teplotní ztráty (PVGIS SARAH3)

**Files:**
- Modify (jen pokud verifikace odhalí double-count): `backend/app/pv_calculator.py:161-166`, případně `backend/app/fve_analysis.py:63`, `backend/app/reporting.py:56`
- Test: `tests/reportgen/test_fve_analysis.py` (pin ročního výkonu)
- Throwaway: `/tmp/opencode/verify_temp_derate.py`

**Interfaces:**
- Consumes: `app.data_loader.load_production_data(kwp, latitude, longitude, surface_tilt, surface_azimuth, system_loss_factor, winter_loss_factor)`.
- Produces: rozhodnutí (a případně test) o hodnotě `system_loss_factor` / teplotním derate.

- [ ] **Step 1: Změř náš roční výkon (Ústí, 10 kWp, tilt 35, az 180)**

Vytvoř `/tmp/opencode/verify_temp_derate.py`:

```python
from app.data_loader import load_production_data

for wl in (None, 10.0):
    _, total = load_production_data(
        kwp=10.0, latitude=50.6607, longitude=14.03227,
        surface_tilt=35, surface_azimuth=180,
        system_loss_factor=14.0, winter_loss_factor=wl)
    print(f"winter_loss={wl}: {total:.0f} kWh/rok  -> {total/10:.0f} kWh/kWp")
```

Run: `cd backend && ../venv/bin/python /tmp/opencode/verify_temp_derate.py` (nebo z kořene s `PYTHONPATH=backend`)
Expected: dva řádky s naším odhadem (očekávej ~1070–1125 kWh/kWp dle designu).

- [ ] **Step 2: Změř referenci PVGIS (stejná konfigurace, loss=14)**

Přidej do skriptu volání PVGIS `PVcalc`:

```python
import requests
r = requests.get("https://re.jrc.ec.europa.eu/api/v5_2/PVcalc",
                 params={"lat": 50.6607, "lon": 14.03227, "peakpower": 10,
                         "loss": 14, "angle": 35, "aspect": 180,
                         "outputformat": "json"}, timeout=30)
e_y = r.json()["outputs"]["totals"]["fixed"]["E_y"]  # kWh/rok pro 10 kWp
print(f"PVGIS loss=14: {e_y:.0f} kWh/rok -> {e_y/10:.0f} kWh/kWp")
```

Run: `cd backend && ../venv/bin/python /tmp/opencode/verify_temp_derate.py`
Expected: reference z PVGIS se stejnými parametry.

- [ ] **Step 3: Rozhodni podle odchylky**

Vyhodnoť `(náš − PVGIS) / PVGIS` pro variantu `winter_loss=None` (ať se izoluje teplotní derate, ne zimní ztráta):

- **|odchylka| ≤ 3 %** → teplotní ztráta se **nedvojí**; `system_loss_factor=14` a `apply_temperature_derate` jsou konzistentní s modelem PVGIS. Zapiš do ledgeru „D1: bez double-count, ±X %" a přejdi na Krok 5 (pin test).
- **odchylka < −5 %** (jsme systematicky níž) → `system_loss_factor` pravděpodobně zahrnuje teplotu duplicitně. Sniž default tak, aby výsledek sedl na PVGIS (např. `14.0 → 8.0`), uprav `pv_calculator.py` komentář a pokračuj Krokem 4.
- **odchylka > +5 %** → chybí ztráta; řeš obdobně (zvyš/zpřesni) a zdokumentuj.

- [ ] **Step 4 (jen při změně): Uprav model a test**

Podle výsledku Kroku 3 změň hodnotu v `pv_calculator.py` (default v signatuře), `fve_analysis.py:63` (`_DEFAULTS`) a `reporting.py:56` (`_PARAM_DEFAULTS`) — **všechny tři musí zůstat shodné**. Pak přidej pin test do `tests/reportgen/test_fve_analysis.py`:

```python
def test_annual_yield_pin_usti_10kwp():
    """Roční výkon Ústí 10 kWp musí odpovídat designu (~1070 kWh/kWp ±5 %)."""
    from app.fve_analysis import run_energy_analysis  # nebo load_production_data
    ...
    assert 1000 <= kwh_per_kwp <= 1130
```

(hranice dolaď podle Kroku 3, ať test není flaky kvůli šumu číselníku.)

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_analysis.py -q -k yield_pin`
Expected: PASS.

- [ ] **Step 5 (pin i bez změny): Zapiš rozhodnutí do ledgeru**

Do `.superpowers/sdd/2026-10-06-4-produkce-a-geocoder/progress.md` doplň sekci:

```markdown
## D1 — verifikace teplotní ztráty vs PVGIS SARAH3 (2026-10-10)
- Náš odhad (Ústí, 10 kWp, tilt 35/az 180, loss 14, winter None): XXX kWh/kWp
- PVGIS PVcalc (loss 14): YYY kWh/kWp
- Odchylka: ±Z %  → [bez double-count | opraveno na loss=NN]
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/pv_calculator.py backend/app/fve_analysis.py backend/app/reporting.py tests/reportgen/test_fve_analysis.py
git commit -m "fix(pv): vyresit dvoji zapocet teplotni ztraty dle PVGIS SARAH3"
```

(Pokud Krok 3 vyjde „bez double-count", commit se dělá jen s ledgerem, resp. se task uzavře záznamem bez změny kódu.)

---

## Self-Review

**1. Spec coverage:** Všech šest vybraných nálezů má task: A1=Task 2, A2=Task 1, B1=Task 3, C1=Task 5, C2=Task 4, E1=Task 6, D1=Task 7. (A1/A2/B1/C1/C2/E1/D1 = 7 bodů; uživatel vybral všech šest skupin označených v nabídce — C1 a C2 jsou dva samostatné, proto 7 tasků.)

**2. Placeholder scan:** Bez „TBD/TODO"; každý kód krok má konkrétní blok. Task 6 a 7 mají vědomé rozhodovací brány (obsah závisí na měření) — to není placeholder, ale explicitní podmínka.

**3. Type consistency:** `INTERNAL_ROLES` (frozenset) konzumuje `is_internal_user`; `run_economic_analysis` vrací `years: int`, `annual_savings/sp500_return/inflation/discount_rate: float`; `FveMaterialLine.name`/`rating` už v `types.ts:283` existují, takže frontend doplnění typově sedí.

**4. Review Focus:** Každá z pěti řádků má test — (1) Task 2 `non_dict`, (2) Task 3 `unknown_role`, (3) Task 4 `legacy_economic_report_shows_real_inputs`, (4) Task 5 `composition` + E2E, (5) Task 6 grep kontrola.

---

## Execution Handoff

Plán je uložený v `docs/superpowers/plans/2026-10-10-technicke-dluhy.md`.
