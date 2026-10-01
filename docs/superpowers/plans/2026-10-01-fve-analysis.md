# Implementační plán — fveAnalysis v React aplikaci

**Datum:** 2026-10-01
**Zdrojový design:** `docs/superpowers/specs/2026-10-01-fve-analysis-design.md` (schváleno)
**Status:** k realizaci — **M1–M7 hotovo 2026-10-01**
**Repo:** `/home/roman/dev/antelon-energy` (dev workspace — produkce `/home/roman/apps/antelon-energy` se nedotýká)

> **Poznámka k tomuto plánu (2026-10-01, po M7):** Legacy Streamlit byl
> následně odstraněn, takže věty níže o tom, že „legacy běží dál na
> `/analysis/*`", už neplatí. Když tento plán použijete jako referenci,
> počítejte s tím, že:
>
> - `/analysis/*` a `/report/{energy,economic}` **neexistují**,
> - `main.run_energy_analysis` a `main.run_economic_analysis` **neexistují**;
>   volají se přes `app.fve_analysis` (a `ai_service` i `router` byly
>   migrovány, aby na `main` nezávisely),
> - `fve_analysis.analysis_param_keys()` nahrazuje
>   `EnergyAnalysisInput.model_fields` jako filtrační klíče.
>
> Navíc (2026-10-01, po dokončení):
>
> - Úkol **M6.1** mluví o `plotly.js-dist-min`. Ten byl nahrazen ořezaným
>   bundle z `plotly.js/lib/core` + ruční registrace použitých typů grafů
>   (`frontend-web/src/lib/plotly.ts`), 4,6 MB → 1,29 MB. Vyžaduje
>   `define: { global: 'globalThis' }` ve `vite.config.ts`.
> - Slibná poznámka v sekci o `main.py` (Ruling 4 — oba routery v jednom
>   `try`) je **opravená**, ne odložená: moduly se načítají zvlášť a stav
>   hlásí `GET /` (503 při poruše).
>
> Změnu shrnuje
> [spec, sekce Změna 2026-10-01](../specs/2026-10-01-fve-analysis-design.md)
> a [docs/architektura.md](../../architektura.md).

---

## 0. Kontext a prostředí (čti první)

### Co se staví

Energetická a ekonomická analýza FVE, přenesená ze Streamlitu do React aplikace jako **první krok zakázky**. Uživatel zadá parametry, dostane bilanci a ekonomiku, výsledek se uloží jako rozpracovaná analýza (projekt ve stavu `fve_analyza`), kterou lze jedním tlačítkem převést na zakázku v pipeline. Analýza funguje i samostatně, bez projektu.

### Tři nálezy, které mění design

Prozkoumal jsem kód, než jsem plán napsal, a našel tři věci, které nejsou v designu a které plán řeší jinak:

**1. `fve_wrap.run_fve_energy` je mrtvý kód.** Design sekce 5.1 říká „reuse `run_fve_energy`, nepíše se žádná nová fyzika". Funkce ve skutečnosti:

```python
# backend/app/reportgen/fve_wrap.py:11
from data_loader import load_consumption_data, load_production_data
# → ImportError: attempted relative import with no known parent package
```

`data_loader.py` používá relativní importy (`from .pv_calculator import ...`), takže ho nelze importovat jako top-level modul. **Nic ve repozitáři tuto funkci nevolá** — je to mrtvý kód, který by spadl. Navíc volá `plot_energy_balance_daily(result_df)` s jedním argumentem, ale funkce vyžaduje dva (`def plot_energy_balance_daily(df, date)`).

Skutečná logika žije inline v `backend/main.py` řádky 88–435 (348 řádků) v endpointu `/analysis/energy`, který **funguje** a je ověřený. Plán proto nechá `fve_wrap` být a místo reuse udělá **extrakci** — logika se přesune do `backend/app/fve_analysis.py` a oba volající (legacy endpoint i nový) ji sdílí. Výsledek je lepší než původní návrh: jeden zdroj pravdy místo dvou.

**2. V Reactu není žádná chart knihovna.** `package.json` frontendu neobsahuje plotly, chart.js, recharts ani d3 — frontend v `frontend-web/` zatím nekreslil žádný graf. Backend sice vrací Plotly JSON, ale React ho nemá čím vykreslit. Bez `plotly.js-dist-min` by grafová polovina specu (sekce 6.3) nešla implementovat.

Navíc `pio.to_json()` vrací **string**, ne objekt (ověřeno). Frontend tedy musí na každý graf volat `JSON.parse()` — jinak dostane string a `Plotly.newPlot` selže.

**3. Geokódování neumí adresy.** Design sekce 6.2 slibuje „geokódování adresy". Ve skutečnosti `backend/app/geocoder.py` volá **Open-Meteo geocoding**, což je *name search* (vyhledávání názvu místa), ne adresní geokódování:

```
"Praha 1"  → None          ← ulice s číslem, nenalezeno
"Praha"    → {lat: 50.08804, lon: 14.42076, ...}
"Brno"     → {lat: 49.19522, lon: 16.60796, ...}
```

UI proto bude vyhledávat **obec**, ne ulici. Pole se jmenuje „Obec nebo město", a plán to testuje, aby se chyba neopakovala.

### Past, která stojí za nálezem 1

Nález 1 není jen „mrtvý kód" — je to symptom hlubšího problému, který by zopakoval každý nový soubor:

| fakt | důsledek |
|---|---|
| `analyzer.py`, `data_loader.py`, `reporting.py` používají **relativní importy** | nejde je naimportovat jako top-level modul |
| `backend/app/` **nemá `__init__.py`** | `app` funguje jen jako namespace package z `backend/` |
| `main.py` importuje `app.reportgen.router` | v produkci je to `app.*` |
| `conftest.py` importuje `reportgen.storage` + chdir do `backend/` | v testech je to top-level `reportgen` |

Výsledek: `app.reportgen` a `reportgen` jsou **dva různé moduly se stejnými soubory** (ověřeno: `app.reportgen is reportgen` → `False`). Relativní import s pevným počtem teček a top-level import proto v jednom z kontextů vždy spadnou.

`fve_wrap.py` padá přesně na tomto. Proto plán importuje **všude přes `app.`** a `fve_analysis.py` si sám hlídá `backend/` v `sys.path` (helper `_mod()` v M1.1). Řešení je experimentálně ověřené v obou kontexstech, ne odhadnuté.

### Kde se implementuje

| Cíl | Cesta |
|---|---|
| Dev workspace | `/home/roman/dev/antelon-energy` — zde se implementuje a testuje |
| Produkce | `/home/roman/apps/antelon-energy` — **nesmí se dotknout**, nasazení až po review přes `./deploy.sh` |

Data v dev: `data/reportgen.db` (36 projektů), `data/weather_cache.db`. Produkční `spot_market.db` v repu chybí — OTE je mimo scope (viz design sekce 8).

### Prostředí (ověřeno 2026-10-01)

| Nástroj | Verze / stav | Dopad |
|---|---|---|
| python | venv v `./venv` | testy přes `./venv/bin/python -m pytest` |
| node | **v24.8.0**, npm 11.6.0 | `npm run build` funguje na hostu (v září 2026 byl node 12 — od té doby se to opravilo) |
| docker | běží | `docker compose up -d --build` pro nasazení do testovacího prostředí |
| plotly (py) | 6.5.0 | grafy generuje backend |
| kaleido | 1.2.0 | v `requirements.txt` (pro PDF) |

### Služby a přihlášení

| Služba | Adresa |
|---|---|
| Web (dev) | `http://localhost:3100` |
| Web (2. port pro nginx) | `http://localhost:3001` |
| API | `http://localhost:8051/docs` |
| Veřejně | `https://fve.etikos.cz` |

Účty: `admin@antelon.local` / `Admin123!`, `antelon@antelon.local` / `Antelon123!`, `zakaznik@antelon.local` / `Zakaznik123!`

Pozor: `docker-compose.yml` má default `admin123`, ale seedovaná DB má `Admin123!`. Je to nesrovnalost, která existuje už teď — neopravuji ji v tomto plánu (mimo scope), ale nesmí mě zmást při testování.

### Testy

```bash
cd /home/roman/dev/antelon-energy
./venv/bin/python -m pytest tests/reportgen -q --timeout=120
```

Ověřeno: **88 testů projde za 130 s.** Sada je pomalá (import main.py + init_db v každém testu), takže to není chyba mých testů. Při vývoji spouštět jednotlivé testy, ne celou sadu.

### Konvence

- Backend: docstring v češtině, komentář vysvětluje *proč*, ne *co*
- Pydantic schemata v `router.py` hned za `APIRouter(prefix="/api/v1", ...)`
- Testy v `tests/reportgen/test_*.py`, fixture `client` z `conftest.py` (temp DB, chroot do `backend/`)
- Frontend: TypeScript, Tailwind, `client` z `src/api/client.ts`, české texty v UI
- Commit po každém úkolu, formát `typ(scope): popis`
- Žádné TBD, žádné placeholdery v kódu

---

## Souborová mapa

### Nové soubory

| Soubor | Odpovědnost |
|---|---|
| `backend/app/fve_analysis.py` | Veškerá výpočetní logika analýzy — extrakce z `main.py`. Obě volající místa (legacy + nové API) volají sem. Žádné importy FastAPI, žádná DB. |
| `backend/app/reportgen/fve_router.py` | Nové endpointy `/api/v1/fve-analysis/*`. Oddělený router, aby `router.py` (už 700+ řádků) nerostl. |
| `tests/reportgen/test_fve_analysis.py` | Testy výpočetní logiky + API endpointů + RBAC |
| `frontend-web/src/api/fve.ts` | Typovaný API klient pro fveAnalysis (run, geocode, appliances, save, convert) |
| `frontend-web/src/components/fve/PlotlyChart.tsx` | Wrapper na `plotly.js-dist-min`, přijímá string JSON, parsuje a vykreslí |
| `frontend-web/src/components/fve/FveAnalysisForm.tsx` | Formulář parametrů (20 čísel + spotřebiče + geokódování) |
| `frontend-web/src/components/fve/FveAnalysisResults.tsx` | Výsledky — bilanční metriky, tabulky, grafy, export PDF |
| `frontend-web/src/components/fve/ContactStep.tsx` | Krok 3 — kontakt (jméno, e-mail, telefon) s validací |
| `frontend-web/src/pages/FveAnalysisPage.tsx` | Samostatná route `/fve-analysis` |
| `frontend-web/src/pages/ProjectFveAnalysisPage.tsx` | Route `/projects/:id/fve-analysis` — načte `fve_params` z projektu |
| `frontend-web/src/pages/FveAnalysisLayout.tsx` | Tříkrokový state machine, sdílený oběma routes |

### Upravené soubory

| Soubor | Změna |
|---|---|
| `backend/app/reportgen/storage.py` | `Project.customer_email`, `Project.customer_phone` + migrace |
| `backend/app/reportgen/auth.py` | `can_access_project` — vlastník analýzy má přístup |
| `backend/app/reportgen/router.py` | `router.include_router(fve_router)` + `convert-to-order` |
| `backend/main.py` | `/analysis/energy` a `/analysis/economic` delegují na `fve_analysis` (chování identické) |
| `frontend-web/src/App.tsx` | 2 nové routy |
| `frontend-web/src/components/Layout.tsx` | položka `fveAnalysis` v menu |
| `frontend-web/src/types.ts` | typy pro FVE parametry a výsledky |
| `frontend-web/package.json` | `plotly.js-dist-min` |

### Cíle grafů

Ačkoli je fveAnalysis první stránka s grafy, **nevymýšlím si nový vizuální systém** — použiji existující barevnou paletu (`bg-navy`, `text-navy`, `bg-slate-50`, tlačítka jako v `Dispecink.tsx`). Grafy dostanou obyčejnou kartu s hlavičkou. Pokud to bude vypadat hluboko pod ostatními stránkami, doladí se to potom; teď je důležitější fungovat.

---

## M1. Extrakce výpočetní logiky

**Cíl:** veškerá logika analýzy v jednom místě, legacy endpoint beze změny. Základ pro všechno další — bez toho nelze napsat API ani UI bez duplicity.

Tento milník **nemá žádný viditelný efekt**. Jeho smyslem je, že M2–M6 už nepřidávají žádnou matematiku.

### Úkol M1.1 — `backend/app/fve_analysis.py` s hlavní funkcí

Vytvoř soubor s logikou přesunutou z `main.py` řádky 88–435. Čistá funkce: dict na vstupu, dict na výstupu. Žádný FastAPI, žádná databáze, žádný auth.

```python
"""Výpočetní logika FVE analýzy.

Jediný zdroj pravdy pro energetickou i ekonomickou analýzu.
Volá ho legacy endpoint /analysis/energy i nový /api/v1/fve-analysis/run.

Vstup i výstup jsou plain dict (JSON-friendly) — žádný FastAPI, žádná DB.
"""
import importlib
import os
import sys
from typing import Any, Dict

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))


def _mod(name: str):
    """Naimportuje modul z backend/app/ v obou kontexstech.

    Tady je past, na kterou padá fve_wrap.py: analyzer.py, data_loader.py
    a reporting.py používají relativní importy, backend/app/ nemá __init__.py
    (funguje to jen jako namespace package) a testy importují reportgen
    jako top-level, zatímco main.py jako app.reportgen. Relativní import
    ani top-level import proto v jednom z kontextů spadne.

    Řešení: vždy přes `app.<modul>` a zajistit, že backend/ je v sys.path.
    Oba kontexty pak naimportují stejný objekt.
    """
    backend = os.path.dirname(_HERE)
    if backend not in sys.path:
        sys.path.insert(0, backend)
    return importlib.import_module(f"app.{name}")
```

Všude v tomto souboru importuj přes `_mod()`, ne relativně:

```python
    analyzer = _mod("analyzer")
    result_df = analyzer.calculate_energy_balance(...)
```

Ne `from .analyzer import ...` — to by tu rozbilo testy, přesně jako rozbilo `fve_wrap.py`.

Ověř **hned po založení souboru**, ne až v M3:

```bash
./venv/bin/python -c "
import sys; sys.path.insert(0,'backend')
from app.fve_analysis import default_params, run_energy_analysis
r = run_energy_analysis({'kwp': 10.0})
print('OK', len(r), 'klíčů')
"
```

Když to projde v produkci, ale testy později selžou na importu, problém je v kontextu testů — spusť `tests/reportgen/test_fve_analysis.py` hned po M1.3.

`default_params()`:
    """Výchozí parametry — přesunuto ze Streamlitu (DEFAULT_SETTINGS)."""
    return {
        "kwp": 10.0,
        "battery_capacity": 10.0,
        "annual_consumption_mwh": 5.0,
        "price_power": 3.0,
        "price_distribution": 2.0,
        "price_sell": 2.0,
        "sell_price_scheme": "fixed",
        "community_sell_price": 1.5,
        "shared_sell_price": 2.54,
        "spot_price_margin": 0.4,
        "latitude": 50.0880,
        "longitude": 14.4208,
        "surface_tilt": 35,
        "surface_azimuth": 180,
        "grid_export_limit_kw": 10.0,
        "system_loss_factor": 14.0,
        "winter_loss_factor": 10.0,
        "thermal_battery_capacity_kwh": 0.0,
        "thermal_battery_charge_power_kw": 2.0,
    }


def appliance_catalog() -> list[dict]:
    """Seznam spotřebičů z ApplianceManager — ne hardcoded v UI.

    Název je zároveň klíč, pod kterým se spotřebič ukládá do parametrů,
    proto se vrací bez úprav (názvy obsahují pomlčky a čísla).
    """
    am = _mod("appliance_manager").ApplianceManager()
    out = []
    for name in am.get_all_appliance_names():
        profile = am.get_appliance_profile(name) or {}
        out.append(
            {
                "name": name,
                "power_kw": profile.get("power_kW", 0),
                "type": profile.get("type", "Standard"),
                "description": profile.get("description", ""),
            }
        )
    return out
```

Dále přesuň z `main.py` beze změny těla funkce `run_energy_analysis` (řádky 96–435) do:

```python
def run_energy_analysis(params: Dict[str, Any]) -> Dict[str, Any]:
    """Energetická analýza z parametrů.

    Vrací přesně strukturu, kterou dnes vrací endpoint /analysis/energy —
    frontend na ni (i na JSON-stringy v plots) už je postavený.
    """
```

Při přesunu platí tři pravidla:

1. `input_data.kwp` → `params.get("kwp", 10.0)` atd. Schéma `EnergyAnalysisInput` zůstane v `main.py` a naplní se z dictu.
2. `active_appliances_data` zůstává dict `{název: {}}` — tak to posílá i Streamlit.
3. **`plots` zůstávají stringy.** `fig.to_json()` vrací string, ne objekt. Nepřeváděj na dict — změnil bych formát, kterému je Streamlit frontend zvyklý. Nový React to zvládne přes `JSON.parse`.

Přesuň i `run_economic_analysis` (řádky 438–478) jako `run_economic_analysis(params)`.

**Ověření, že přesun nic nerozbil:**

```bash
# legacy endpoint musí vracet stejnou strukturu jako před přesunem
curl -s -X POST http://localhost:8051/analysis/energy \
  -H 'Content-Type: application/json' \
  -d '{"kwp":10.0,"annual_consumption_mwh":5.0}' \
  | ./venv/bin/python -c "import json,sys; d=json.load(sys.stdin); print(sorted(d.keys()))"
```

Očekávaný výstup (zachycený **před** přesunem, v `main.py` řádky 396–434):

```
['annual_consumption_mwh', 'appliance_details', 'appliance_metrics',
 'appliance_monthly_summary', 'battery_capacity', 'economic_balance_czk',
 'energy_balance_kwh', 'financial_balance', 'kwp', 'latitude', 'longitude',
 'monthly_summary', 'plots', 'production_details', 'raw_data', 'recommendations']
```

Commit: `refactor(fve): extrakce logiky analýzy z main.py do fve_analysis.py`

---

### Úkol M1.2 — `main.py` deleguje

`/analysis/energy` a `/analysis/economic` se stanou tenkými wrappery. Tělo (348 řádků) smaž, nech jen:

```python
@app.post("/analysis/energy")
def run_energy_analysis_endpoint(input_data: EnergyAnalysisInput):
    """Legacy endpoint (Streamlit). Deleguje do app.fve_analysis."""
    try:
        return fve_analysis.run_energy_analysis(
            input_data.model_dump(exclude_none=False)
        )
    except ValueError as e:
        # PVGIS nedohaloval data pro zadané souřadnice — stejná hláška
        # jako před přesunem, legacy Streamlit na ni spoléhá
        raise HTTPException(status_code=400, detail=str(e))
```

Tři věci k zachování, protože na nich závisí legacy Streamlit:

1. `ValueError` z PVGIS → **400** s hláškou, ne 500
2. `raise_for_status()` v Pythonu musí dát 4xx, ne 500
3. `exclude_none=False` — jinak by `None` hodnoty zmizely a použily by se defaulty

`/report/energy` a `/report/economic` (PDF) nech beze změny — berou výsledek jako volný dict, takže fungují dál.

Commit: `refactor(fve): main.py deleguje na fve_analysis`

---

### Úkol M1.3 — test extrakce

`tests/reportgen/test_fve_analysis.py`:

```python
"""M1 — extrakce logiky z main.py do fve_analysis."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# Do sys.path musí být backend/ (kvůli `app.`), ne backend/app/ —
# viz vysvětlení importu v M1.1.
if str(REPO / "backend") not in sys.path:
    sys.path.insert(0, str(REPO / "backend"))

from app.fve_analysis import (  # noqa: E402
    appliance_catalog,
    default_params,
    run_energy_analysis,
    run_economic_analysis,
)


def test_default_params_cover_streamlit_settings():
    """Výchozí parametry musí být kompletní — UI staví na nich políčka."""
    p = default_params()
    for key in (
        "kwp", "battery_capacity", "annual_consumption_mwh", "price_power",
        "price_distribution", "price_sell", "sell_price_scheme",
        "community_sell_price", "shared_sell_price", "spot_price_margin",
        "latitude", "longitude", "surface_tilt", "surface_azimuth",
        "grid_export_limit_kw", "system_loss_factor", "winter_loss_factor",
        "thermal_battery_capacity_kwh", "thermal_battery_charge_power_kw",
    ):
        assert key in p, f"chybí parametr {key}"
    # defaultní souřadnice jsou v weather_cache.db → testy běží offline
    assert (p["latitude"], p["longitude"]) == (50.0880, 14.4208)


def test_appliance_catalog_matches_manager():
    """Katalog musí pocházet z ApplianceManager, ne z hardcoded seznamu."""
    cat = appliance_catalog()
    assert len(cat) == 17
    assert {"name", "power_kw", "type", "description"} == set(cat[0].keys())
    assert any(c["name"] == "Bazén - Filtrace" for c in cat)


def test_run_energy_analysis_returns_full_structure():
    """Struktura musí být 1:1 s tím, co dnes vrací /analysis/energy."""
    r = run_energy_analysis({"kwp": 10.0, "annual_consumption_mwh": 5.0})

    assert sorted(r.keys()) == [
        "annual_consumption_mwh", "appliance_details", "appliance_metrics",
        "appliance_monthly_summary", "battery_capacity", "economic_balance_czk",
        "energy_balance_kwh", "financial_balance", "kwp", "latitude",
        "longitude", "monthly_summary", "plots", "production_details",
        "raw_data", "recommendations",
    ]
    # bilanční klíče, na kterých stojí celé UI
    assert {"grid_import", "grid_export", "self_consumption",
            "total_consumption"} == set(r["energy_balance_kwh"].keys())
    assert {"cost_total_consumption", "cost_import", "revenue_export",
            "savings_self_consumption"} == set(r["economic_balance_czk"].keys())
    assert {"annual_savings_czk", "cost_without_pv_czk",
            "cost_with_pv_czk"} == set(r["financial_balance"].keys())


def test_plots_are_json_strings():
    """pio.to_json() vrací string. React to parsuje — nesmí to být dict.

    Regresní pojistka: kdyby někdo přidal json.loads(), string by se rozpadl
    a graf by přestal fungovat bez jakékoli chyby v testech struktur.
    """
    r = run_energy_analysis({"kwp": 10.0})
    for name, value in r["plots"].items():
        assert isinstance(value, str), f"{name} není string, ale {type(value)}"
        assert value.startswith("{"), f"{name} není platný JSON"
```

```python
def test_run_energy_analysis_respects_params():
    """Větší FVE → větší výroba. Základní fyzika musí platit."""
    maly = run_energy_analysis({"kwp": 5.0, "annual_consumption_mwh": 5.0})
    velky = run_energy_analysis({"kwp": 20.0, "annual_consumption_mwh": 5.0})
    assert (velky["production_details"]["total_production_actual"]
            > maly["production_details"]["total_production_actual"])


def test_grid_export_limit_changes_balance():
    """Limit exportu musí měnit bilanci — jinak je parametr ignorován."""
    bez = run_energy_analysis({"kwp": 20.0, "grid_export_limit_kw": None})
    s = run_energy_analysis({"kwp": 20.0, "grid_export_limit_kw": 0.0})
    assert s["energy_balance_kwh"]["grid_export"] < bez["energy_balance_kwh"]["grid_export"]


def test_battery_increases_self_consumption():
    s = run_energy_analysis({"kwp": 10.0, "battery_capacity": 0.0})
    b = run_energy_analysis({"kwp": 10.0, "battery_capacity": 20.0})
    assert (b["energy_balance_kwh"]["self_consumption"]
            >= s["energy_balance_kwh"]["self_consumption"])


def test_economic_analysis_metrics():
    r = run_economic_analysis({
        "annual_savings": 30000, "investment_cost": 350000, "years": 20,
    })
    assert {"payback_years", "discounted_payback_years", "npv_czk",
            "final_pv_gain_czk", "final_pv_reinvest_gain_czk",
            "final_sp500_net_czk"} == set(r["metrics"].keys())
    assert isinstance(r["plot"], str)
```

Pozor na `grid_export_limit_kw: None` — `run_energy_analysis` musí rozlišovat `None` (bez limitu) od `0.0`. Streamlit posílá `None`, když pole nevyplní. Při přesunu tento rozdíl zachovej.

Commit: `test(fve): testy extrakce fve_analysis`

---

## M2. Datový model

**Cíl:** dva nové sloupce na `projects` a nový stav `fve_analyza`. Aditivní migrace, žádná ztráta dat.

### Úkol M2.1 — sloupce v modelu

`backend/app/reportgen/storage.py`, třída `Project` — přidej za `customer_name`:

```python
    customer_email = Column(String(255), nullable=True)   # kontakt patří zakázce, ne uživateli
    customer_phone = Column(String(255), nullable=True)
```

Proč ne na `users`: jeden zákazník může mít více zakázek s různými kontakty (jiná manželka, firma). `users` navíc telefon nemá.

### Úkol M2.2 — migrace

Do `_migrate()` v `storage.py`, do bloku `if "projects" in tables:`, hned za existující přidávání sloupců:

```python
            if "customer_email" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN customer_email VARCHAR(255)"))
            if "customer_phone" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN customer_phone VARCHAR(255)"))
```

`cols` už existuje v tomto bloku. **Žádný UPDATE** — staré řádky mají `NULL`, a to je v pořádku.

Migrace je idempotentní (spouští se při každém startu) a aditivní — jen `ADD COLUMN`, žádné přepisování tabulky. Protože `reportgen.db` obsahuje 36 reálných projektů, **záloha před migrací**:

```bash
mkdir -p data/backups
cp data/reportgen.db "data/backups/reportgen.db.$(date +%Y%m%d_%H%M%S)"
```

Commit: `feat(fve): customer_email a customer_phone na projects`

---

## M3. API

**Cíl:** pět endpointů pod `/api/v1/fve-analysis/*`, vše s JWT. Legacy `/analysis/*` nedotčen.

### Úkol M3.1 — `fve_router.py` se schematy a během

`backend/app/reportgen/fve_router.py` (nový):

```python
"""API pro fveAnalysis — energetická a ekonomická analýza jako první krok zakázky.

Oddělený router, protože router.py už má 700+ řádků a fveAnalysis je
samostatná funkční oblast.

Výpočet deleguje do app.fve_analysis — tady je jen auth, validace a DB.
"""
import json
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from .auth import can_access_project, get_current_user, hash_password, require_roles
from .storage import User, get_db, Project, generate_share_code

router = APIRouter(tags=["fve-analysis"])


class FveParams(BaseModel):
    """Parametry analýzy. Všechny mají default = default ze Streamlitu,
    takže klient může poslat jen to, co uživatel změnil."""

    kwp: float = Field(default=10.0, ge=0.1, le=50.0)
    battery_capacity: float = Field(default=10.0, ge=0.0, le=100.0)
    annual_consumption_mwh: float = Field(default=5.0, ge=0.1, le=100.0)
    price_power: float = Field(default=3.0, ge=0.0)
    price_distribution: float = Field(default=2.0, ge=0.0)
    price_sell: float = Field(default=2.0, ge=0.0)
    sell_price_scheme: str = "fixed"       # fixed | community | shared | spot
    community_sell_price: float = 1.5
    shared_sell_price: float = 2.54
    spot_price_margin: float = 0.4
    latitude: float = Field(default=50.0880, ge=-90.0, le=90.0)
    longitude: float = Field(default=14.4208, ge=-180.0, le=180.0)
    surface_tilt: int = Field(default=35, ge=0, le=90)
    surface_azimuth: int = Field(default=180, ge=0, le=359)
    grid_export_limit_kw: float | None = 10.0
    system_loss_factor: float = Field(default=14.0, ge=0.0, le=50.0)
    winter_loss_factor: float = Field(default=10.0, ge=0.0, le=100.0)
    thermal_battery_capacity_kwh: float = 0.0
    thermal_battery_charge_power_kw: float = 2.0
    active_appliances: list[str] = []      # názvy, ne dict jako u Streamlitu

    @field_validator("sell_price_scheme")
    @classmethod
    def _valid_scheme(cls, v: str) -> str:
        if v not in ("fixed", "community", "shared", "spot"):
            raise ValueError(f"Neznámé schéma prodeje: {v}")
        return v

    def to_analysis_params(self) -> dict:
        """Převod na tvar, jaký čeká app.fve_analysis.

        active_appliances (list) → active_appliances_data (dict), protože
        tak to posílá i legacy Streamlit a tak to bere ApplianceManager.
        """
        d = self.model_dump()
        names = d.pop("active_appliances")
        d["active_appliances_data"] = {n: {} for n in names}
        return d


class Contact(BaseModel):
    """Kontakt je povinný vždy — bez něj nemá analýza v pipeline smysl."""

    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    phone: str = Field(min_length=9, max_length=40)

    @field_validator("phone")
    @classmethod
    def _phone_has_digits(cls, v: str) -> str:
        digits = [c for c in v if c.isdigit()]
        if len(digits) < 9:
            raise ValueError("Telefon musí obsahovat alespoň 9 číslic")
        return v


class SaveAnalysisIn(BaseModel):
    params: FveParams
    contact: Contact
    name: str | None = None       # název projektu; jinak se odvodí z kontaktu
```

`EmailStr` potřebuje `email-validator` — přidej do `requirements.txt`:

```
email-validator==2.2.0
```

Ověř, že je opravdu potřeba:

```bash
./venv/bin/python -c "import email_validator; print(email_validator.__version__)"
```

Pokud už nainstalovaný je, do requirements jen přidej pin, jinak nainstaluj.

Poznámka k designu: legacy Streamlit posílá `active_appliances_data` jako dict. Nové API záměrně používá `active_appliances` jako **list** — v UI je to přirozenější (checkboxy → list zapnutých) a je to co jde uložit do `fve_params_json`. Převod dělá `to_analysis_params()`.

### Úkol M3.2 — `POST /run`

```python
ANY_ROLE = require_roles("admin", "antelon", "customer")


@router.post("/fve-analysis/run")
def run_analysis(params: FveParams, user: User = Depends(ANY_ROLE)):
    """Spustí analýzu. Bez uložení — jen výsledky.

    Dostupné pro zákazníka: analýzu si smí spočítat sám, uložení je
    jiný krok (viz POST /fve-analysis).
    """
    from app.fve_analysis import run_energy_analysis   # viz M1.1 — import přes app.

    try:
        return run_energy_analysis(params.to_analysis_params())
    except ValueError as e:
        # PVGIS nedohaloval meteorologická data pro zadané souřadnice
        raise HTTPException(status_code=400, detail=str(e))
```

**Importovat vždy přes `app.`, nikdy relativně a nikdy top-level.** Důvod je v M1.1 — stručně: `analyzer.py`, `data_loader.py` a `reporting.py` používají relativní importy, `backend/app/` nemá `__init__.py`, a testy importují `reportgen` jako top-level modul zatímco `main.py` jako `app.reportgen`. Relativní ani top-level import tu proto nesedí. `app.fve_analysis` funguje v obou, pokud je `backend/` v `sys.path` — což zajišťuje `fve_analysis.py` sám (viz helper v M1.1).

### Úkol M3.3 — geokódování, spotřebiče, ekonomika

```python
@router.post("/fve-analysis/geocode")
def geocode(payload: dict, user: User = Depends(ANY_ROLE)):
    """Geokódování obce nebo města.

    POZOR: backend/geocoder.py používá Open-Meteo geocoding, což je
    *name search* — hledá název místa, ne adresu. "Praha" najde, "Praha 1"
    nebo "Vodičkova 5" ne. UI to musí vysvětlit místo, ne vracet tichou
    chybu, jinak uživatel neví, proč adresa nenašla.
    """
    address = (payload or {}).get("address", "").strip()
    if not address:
        raise HTTPException(400, "Zadejte název obce")
    from geocoder import get_coordinates

    result = get_coordinates(address)
    if not result:
        raise HTTPException(
            404,
            f"Nebylo nalezeno žádné místo pro „{address}". Tryb obec nebo město.",
        )
    return result


@router.get("/fve-analysis/appliances")
def list_appliances(user: User = Depends(ANY_ROLE)):
    """Katalog spotřebičů — UI si ho načte, nehardcoduje."""
    from app.fve_analysis import appliance_catalog

    return {"appliances": appliance_catalog()}


@router.post("/fve-analysis/economic")
def run_economic(params: dict, user: User = Depends(ANY_ROLE)):
    """Ekonomická analýza návratnosti (investice vs S&P500 vs reinvest)."""
    from app.fve_analysis import run_economic_analysis

    return run_economic_analysis(params or {})
```

### Úkol M3.4 — `POST /fve-analysis` (uložení) a dohledání usera

```python
def _find_or_create_customer(db: Session, contact: Contact) -> User:
    """Najde usera podle e-mailu, jinak ho vytvoří.

    Rozhodnutí A z designu: tím se postupně opraví prázdné customer_id
    u existujících projektů. Heslo je náhodné — reset je mimo scope,
    zákazník se poprvé přihlásí přes flow obnovy hesla.
    """
    email = contact.email.lower().strip()
    u = db.query(User).filter(User.email == email).first()
    if u:
        return u
    u = User(
        email=email,
        password_hash=hash_password(secrets.token_urlsafe(24)),
        role="customer",
    )
    db.add(u)
    db.flush()
    return u


@router.post("/fve-analysis")
def save_analysis(payload: SaveAnalysisIn, user: User = Depends(ANY_ROLE),
                  db: Session = Depends(get_db)):
    """Uloží rozpracovanou analýzu jako projekt ve stavu fve_analyza.

    owner_id i customer_id jsou oba nastavené na usera z kontaktu —
    zákazník tak vidí svou vlastní analýzu (viz can_access_project).
    """
    c = payload.contact
    customer = _find_or_create_customer(db, c)

    name = (payload.name or "").strip() or f"FVE analýza — {c.name}"
    p = Project(
        name=name,
        customer_name=c.name,
        customer_email=c.email,
        customer_phone=c.phone,
        owner_id=user.id,
        status="fve_analyza",
        type="ostatni",
        share_code=generate_share_code(),
        fve_params_json=json.dumps(payload.params.model_dump(), ensure_ascii=False),
        antelon_params_json=json.dumps({}, ensure_ascii=False),
    )
    db.add(p)

    # vazba vlastník ↔ zákazník; ProjectUser existuje právě na to
    db.add(ProjectUser(project_id=p.id, user_id=customer.id,
                       role="customer"))
    db.commit()
    db.refresh(p)

    return {
        "id": p.id,
        "status": p.status,
        "share_code": p.share_code,
        "customer_id": customer.id,
        "customer_created": customer.role == "customer" and customer.id == customer.id,
    }
```

`customer_created` jako návratová hodnota je divná — vrátí `True` skoro vždy. Místo toho zjisti, zda user existoval před, a vrať to:

```python
    existing = db.query(User).filter(User.email == c.email.lower().strip()).first()
    customer = existing or _create_customer(db, c)
    ...
    return {
        "id": p.id,
        "status": p.status,
        "share_code": p.share_code,
        "customer_id": customer.id,
        "customer_created": existing is None,   # True = právě vznikl
    }
```

To už je užitečné — frontend může říct „založili jsme vám přihlášení".

**Klíčové pro UI:** `fve_params_json` ukládá **celé** parametry včetně prázdného `active_appliances`. Při načtení existující analýzy se `/projects/{id}` vrátí s `fve_params` a frontend z něj složí defaulty formuláře.

Commit: `feat(fve): API /api/v1/fve-analysis/*`

---

## M4. Převod na zakázku a RBAC

**Cíl:** `fve_analyza → lead` jedním tlačítkem, a zákazník uvidí svou vlastní analýzu.

### Úkol M4.1 — `can_access_project`

`backend/app/reportgen/auth.py`, `can_access_project()` — dnes má poslední řádek `return False`. Před ním přidej:

```python
    # vlastník rozpracované analýzy má přístup i bez vazby v project_users
    # (zákazník si analýzu vytvořil sám; vazba se řeší až při převodu)
    if project.owner_id == user.id:
        return True
```

To je jediná změna v RBAC. Bezpečnostní pravidlo **zákazník vidí jen vlastní** zůstává platné — `owner_id == user.id` je přesně „jeho".

### Úkol M4.2 — `convert-to-order`

V `router.py` (nebo v `fve_router.py` — přesnější je v `fve_router.py`, protože jde o součást fveAnalysis):

```python
# kroky šablony, které fveAnalysis fakticky dodává — označíme jako hotové,
# ať je obchodník nedělá znovu. Řešíme podle názvu, ne ID, protože ID se
# liší mezi instalacemi.
ANALYSIS_SUPPLIED_STEPS = ("první indikativní nabídka", "Zjištění roční spotřeby")


@router.post("/projects/{project_id}/convert-to-order")
def convert_to_order(project_id: int, user: User = Depends(ANY_ROLE),
                     db: Session = Depends(get_db)):
    """Převede rozpracovanou analýzu na zakázku: fve_analyza → lead.

    Pouze admin/antelon — je to obchodní rozhodnutí, zákazník svou analýzu
    převést nemůže.
    """
    from .pipeline_seed import attach_template

    if not is_internal_user(user):
        raise HTTPException(403, "Na převod na zakázku nemáte oprávnění")

    p = _ensure_project_access(project_id, user, db)
    if p.status != "fve_analyza":
        raise HTTPException(409, f"Projekt je ve stavu {p.status}, ne fve_analyza")

    # parametry analýzy do definice zakázky
    fve_params = json.loads(p.fve_params_json) if p.fve_params_json else {}
    antelon = json.loads(p.antelon_params_json) if p.antelon_params_json else {}
    antelon["kwp"] = fve_params.get("kwp")
    antelon["battery_capacity"] = fve_params.get("battery_capacity")
    antelon["thermal_battery_capacity_kwh"] = fve_params.get(
        "thermal_battery_capacity_kwh", 0.0)
    antelon["fve_analysis_source"] = {"project": p.id, "share_code": p.share_code}
    p.antelon_params_json = json.dumps(antelon, ensure_ascii=False)

    p.status = "lead"
    attach_template(db, p, p.type)

    # kroky, které analýza dodala, označ jako hotové s odkazem na zdroj
    for step in db.query(ProjectStep).filter(
        ProjectStep.project_id == p.id
    ).all():
        if any(step.name.strip().lower() == n.lower()
               for n in ANALYSIS_SUPPLIED_STEPS):
            step.status = "done"
            step.note = f"Dodáno FVE analýzou (projekt #{p.id})"

    db.commit()
    db.refresh(p)
    return {"id": p.id, "status": p.status, "type": p.type}
```

Tři věci k ověření, protože šablona se liší mezi instalacemi:

1. **`attach_template(db, p, p.type)`** — `p.type` je u analýzy `"ostatni"`. Šablona `rd` má 57 kroků, `ostatni` bude mít jinou. To je zamýšlené (analýza nezná typ zakázky, obchodník ho upraví), ale **ověř v testu, že `ostatni` šablona existuje**.
2. **`ANALYSIS_SUPPLIED_STEPS` porovnává názvy.** Pokud v `ostatni` šabloně žádný z nich není, smyčka neudělá nic — a to je OK, ne chyba. Napiš test, že to nespadne.
3. **`_ensure_project_access` a `is_internal_user`** jsou v `router.py`/`auth.py` — importovat z `fve_router.py` bez kruhového importu. Pokud to skončí kruhovým importem, přesuň `convert_to_order` do `router.py`.

Commit: `feat(fve): prevod rozpracovane analyzy na zakazku + pristup vlastnika`

---

## M5. Testy API

`tests/reportgen/test_fve_analysis.py` — doplnit. Vzorec pro auth z `test_m5_admin_api.py`:

```python
@pytest.fixture
def customer_token(client):
    r = client.post("/api/v1/auth/login",
                    json={"email": "zakaznik@test.local", "password": "Zakaznik123!"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(t):
    return {"Authorization": f"Bearer {t}"}


def test_run_endpoint_returns_analysis(client, admin_token):
    r = client.post("/api/v1/fve-analysis/run",
                    json={"kwp": 10.0, "annual_consumption_mwh": 5.0},
                    headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    assert "energy_balance_kwh" in r.json()
    # plots jako string, ne objekt — na tom závisí PlotlyChart
    assert isinstance(r.json()["plots"]["monthly_stats"], str)


def test_run_requires_auth(client):
    assert client.post("/api/v1/fve-analysis/run", json={}).status_code in (401, 422)


def test_geocode_rejects_street_address(client, admin_token):
    """Open-Meteo je name search. 'Praha' najde, ulici ne.

    Musí vrátit srozumitelnou 404, ne tichý prázdný výsledek — jinak
    uživatel neví, že zadala ulici.
    """
    r = client.post("/api/v1/fve-analysis/geocode",
                    json={"address": "Praha 1"}, headers=_auth(admin_token))
    assert r.status_code in (404, 200)
    if r.status_code == 404:
        assert "město" in r.json()["detail"] or "obec" in r.json()["detail"]


def test_appliances_endpoint(client, admin_token):
    r = client.get("/api/v1/fve-analysis/appliances", headers=_auth(admin_token))
    assert r.status_code == 200
    assert len(r.json()["appliances"]) == 17


def test_save_requires_contact(client, admin_token):
    r = client.post("/api/v1/fve-analysis",
                    json={"params": {"kwp": 10.0}, "contact": {}},
                    headers=_auth(admin_token))
    assert r.status_code == 422


def test_save_validates_phone(client, admin_token):
    r = client.post("/api/v1/fve-analysis", json={
        "params": {"kwp": 10.0},
        "contact": {"name": "Jiří Novák", "email": "novak@example.cz", "phone": "123"},
    }, headers=_auth(admin_token))
    assert r.status_code == 422
    assert "9 číslic" in r.json()["detail"]


def test_save_creates_project_in_fve_analyza_state(client, admin_token):
    r = client.post("/api/v1/fve-analysis", json={
        "params": {"kwp": 12.0, "annual_consumption_mwh": 6.0},
        "contact": {"name": "Jiří Novák", "email": "novak@example.cz",
                    "phone": "+420 777 123 456"},
        "name": "Novák — FVE 12 kWp",
    }, headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "fve_analyza"
    assert body["customer_created"] is True

    detail = client.get(f"/api/v1/projects/{body['id']}", headers=_auth(admin_token))
    assert detail.status_code == 200
    proj = detail.json()
    assert proj["customer_email"] == "novak@example.cz"
    assert proj["customer_phone"] == "+420 777 123 456"
    assert proj["fve_params"]["kwp"] == 12.0
    assert "active_appliances" in proj["fve_params"]


def test_save_reuses_existing_user_on_second_analysis(client, admin_token):
    """Druhé uložení se stejným e-mailem nesmí vytvořit duplicitního usera."""
    contact = {"name": "Petr Nový", "email": "petr@example.cz", "phone": "+420 777 999 000"}
    first = client.post("/api/v1/fve-analysis",
                        json={"params": {}, "contact": contact},
                        headers=_auth(admin_token))
    assert first.json()["customer_created"] is True

    second = client.post("/api/v1/fve-analysis",
                         json={"params": {}, "contact": contact},
                         headers=_auth(admin_token))
    assert second.json()["customer_created"] is False
    assert second.json()["customer_id"] == first.json()["customer_id"]


def test_customer_can_run_and_save_own_analysis(client, customer_token):
    """Nová schopnost: zákazník si analýzu spočítá a uloží sám."""
    r = client.post("/api/v1/fve-analysis", json={
        "params": {},
        "contact": {"name": "Zákazník Test", "email": "zakaznik-test@example.cz",
                    "phone": "+420 777 111 222"},
    }, headers=_auth(customer_token))
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    # a vidí ji ve svém seznamu
    mine = client.get("/api/v1/projects", headers=_auth(customer_token))
    assert mine.status_code == 200
    ids = [p["id"] for p in (mine.json() if isinstance(mine.json(), list)
                             else mine.json().get("projects", []))]
    assert pid in ids


def test_customer_cannot_see_other_analysis(client, admin_token, customer_token):
    """Bezpečnostní pravidlo zůstává: cizí analýzu nevidí."""
    created = client.post("/api/v1/fve-analysis", json={
        "params": {},
        "contact": {"name": "Cizí Zákazník", "email": "cizi@example.cz",
                    "phone": "+420 777 333 444"},
    }, headers=_auth(admin_token)).json()

    r = client.get(f"/api/v1/projects/{created['id']}", headers=_auth(customer_token))
    assert r.status_code == 403


def test_convert_to_order(client, admin_token, customer_token):
    created = client.post("/api/v1/fve-analysis", json={
        "params": {"kwp": 15.0, "battery_capacity": 10.0},
        "contact": {"name": "Konvert Test", "email": "konvert@example.cz",
                    "phone": "+420 777 555 666"},
    }, headers=_auth(admin_token)).json()
    pid = created["id"]

    # zákazník převést nesmí
    forbidden = client.post(f"/api/v1/projects/{pid}/convert-to-order",
                            headers=_auth(customer_token))
    assert forbidden.status_code == 403

    ok = client.post(f"/api/v1/projects/{pid}/convert-to-order",
                     headers=_auth(admin_token))
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "lead"

    detail = client.get(f"/api/v1/projects/{pid}", headers=_auth(admin_token))
    proj = detail.json()
    assert proj["status"] == "lead"
    assert proj["antelon_params"]["kwp"] == 15.0
    assert proj["antelon_params"]["battery_capacity"] == 10.0

    # idempotence — druhý pokus nesmí projít
    again = client.post(f"/api/v1/projects/{pid}/convert-to-order",
                        headers=_auth(admin_token))
    assert again.status_code == 409


def test_convert_attaches_pipeline(client, admin_token):
    """Po převodu musí být v projektu pipeline, jinak zakázka nenaběhne."""
    pid = client.post("/api/v1/fve-analysis", json={
        "params": {},
        "contact": {"name": "Pipeline Test", "email": "pipe@example.cz",
                    "phone": "+420 777 777 888"},
    }, headers=_auth(admin_token)).json()["id"]

    client.post(f"/api/v1/projects/{pid}/convert-to-order",
                headers=_auth(admin_token))

    view = client.get(f"/api/v1/projects/{pid}/pipeline",
                      headers=_auth(admin_token))
    assert view.status_code == 200, view.text
    assert len(view.json()["steps"]) > 0
```

Spusť celou sadu před commitem:

```bash
./venv/bin/python -m pytest tests/reportgen -q --timeout=120
```

Očekávaně **88 + 13 = 101 testů**, všech zelených. Když spadne něco starého, je to tvůj regression — neopravuj to ignorováním, najdi proč.

Commit: `test(fve): testy API a RBAC`

---

## M6. Frontend

### Úkol M6.1 — `plotly.js-dist-min` a `PlotlyChart`

```bash
cd frontend-web
npm install plotly.js-dist-min
npm install -D @types/plotly.js
```

`package.json` dostane:
```json
    "plotly.js-dist-min": "^2.35.2"
```
a do `devDependencies`:
```json
    "@types/plotly.js": "^2.35.4"
```

Přesnou verzi nech `npm install` vybrat — `^` jen zapiš to, co npm skutečně nainstaloval.

`frontend-web/src/components/fve/PlotlyChart.tsx`:

```tsx
import { useEffect, useRef } from "react";

// Naimportuje se dynamicky — plotly.js-dist-min je ~3,5 MB a načítat ho
// v hlavním bundlu by zdrželo první vykreslení celé aplikace.
let plotlyPromise: Promise<typeof import("plotly.js-dist-min")> | null = null;

function loadPlotly() {
  if (!plotlyPromise) {
    plotlyPromise = import("plotly.js-dist-min");
  }
  return plotlyPromise;
}

interface Props {
  /** JSON z backendu. Pozor: plotly.io.to_json() vrací STRING, ne objekt. */
  json: string | null | undefined;
  height?: number;
  title?: string;
}

export default function PlotlyChart({ json, height = 380, title }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!json || !ref.current) return;

    let cancelled = false;
    let plot: unknown = null;

    loadPlotly().then((Plotly) => {
      if (cancelled || !ref.current) return;
      const spec = JSON.parse(json);   // ← proto je tu JSON.parse
      plot = Plotly.newPlot(ref.current, spec.data, spec.layout, {
        responsive: true,
        displayModeBar: false,
        locale: "cs",
      });
    }).catch((err) => {
      console.error("PlotlyChart: vykreslení grafu selhalo", err);
    });

    return () => {
      cancelled = true;
      if (ref.current && plot) {
        // purge je nutný — bez něj zůstane graf v DOM a leakne při unmountu
        loadPlotly().then((Plotly) => Plotly.purge(ref.current));
      }
    };
  }, [json]);

  if (!json) return null;

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      {title && <h4 className="font-semibold text-navy mb-2">{title}</h4>}
      <div ref={ref} style={{ height }} />
    </div>
  );
}
```

**Ověř, že TypeScript s `plotly.js-dist-min` sedí.** Bez typů to bude `any` a `tsc -b` může hlásit chybu importu:

```bash
cd frontend-web && npm run build
```

Kdyby `import("plotly.js-dist-min")`类型 neseděl, použij `plotly.js` (plný balíček) místo — je to stejná knihovna, jen s vestavěnými typy.

### Úkol M6.2 — API klient a typy

`frontend-web/src/types.ts` — přidej:

```typescript
export interface FveParams {
  kwp: number;
  battery_capacity: number;
  annual_consumption_mwh: number;
  price_power: number;
  price_distribution: number;
  price_sell: number;
  sell_price_scheme: "fixed" | "community" | "shared" | "spot";
  community_sell_price: number;
  shared_sell_price: number;
  spot_price_margin: number;
  latitude: number;
  longitude: number;
  surface_tilt: number;
  surface_azimuth: number;
  grid_export_limit_kw: number | null;
  system_loss_factor: number;
  winter_loss_factor: number;
  thermal_battery_capacity_kwh: number;
  thermal_battery_charge_power_kw: number;
  active_appliances: string[];
}

export interface FveAppliance {
  name: string;
  power_kw: number;
  type: string;
  description: string;
}

export interface FveAnalysisResult {
  financial_balance: {
    annual_savings_czk: number;
    cost_without_pv_czk: number;
    cost_with_pv_czk: number;
  };
  energy_balance_kwh: {
    total_consumption: number;
    grid_import: number;
    grid_export: number;
    self_consumption: number;
  };
  economic_balance_czk: {
    cost_total_consumption: number;
    cost_import: number;
    revenue_export: number;
    savings_self_consumption: number;
  };
  production_details: {
    total_production_actual: number;
    total_production_optimal: number;
    production_performance_pct: number;
  };
  /** Každý graf je JSON STRING — PlotlyChart ho parsuje. */
  plots: Record<string, string>;
  appliance_metrics: Record<string, {
    fve_kWh: number; grid_kWh: number; total_kWh: number;
    savings_czk: number; grid_cost_czk: number;
    operating_hours: number; coverage_pct: number;
  }>;
  appliance_details: Array<{
    name: string; power_kw: number; type: string; description: string;
  }>;
  recommendations: string[];
  monthly_summary: Array<Record<string, number | string>>;
  appliance_monthly_summary: Array<Record<string, number | string>>;
}

export interface FveContact {
  name: string;
  email: string;
  phone: string;
}
```

`frontend-web/src/api/fve.ts` (nový):

```typescript
import client from "./client";
import type { FveAnalysisResult, FveAppliance, FveContact, FveParams } from "../types";

export const runAnalysis = (params: Partial<FveParams>) =>
  client.post<FveAnalysisResult>("/fve-analysis/run", params).then((r) => r.data);

export const runEconomic = (params: Record<string, unknown>) =>
  client.post("/fve-analysis/economic", params).then((r) => r.data);

export const geocode = (address: string) =>
  client.post<{ lat: number; lon: number; display_name: string }>(
    "/fve-analysis/geocode", { address },
  ).then((r) => r.data);

export const fetchAppliances = () =>
  client.get<{ appliances: FveAppliance[] }>("/fve-analysis/appliances")
    .then((r) => r.data.appliances);

export interface SavedAnalysis {
  id: number;
  status: string;
  share_code: string;
  customer_id: number;
  customer_created: boolean;
}

export const saveAnalysis = (
  params: FveParams,
  contact: FveContact,
  name?: string,
) =>
  client.post<SavedAnalysis>("/fve-analysis", { params, contact, name })
    .then((r) => r.data);

export const convertToOrder = (projectId: number | string) =>
  client.post(`/projects/${projectId}/convert-to-order`).then((r) => r.data);
```

Commit po M6.2: `feat(fve-web): API klient, typy a PlotlyChart`

---

### Úkol M6.3 — `FveAnalysisForm`

`frontend-web/src/components/fve/FveAnalysisForm.tsx`. Props:

```typescript
interface Props {
  params: FveParams;
  onChange: (next: FveParams) => void;
  appliances: FveAppliance[];
  onRun: () => void;
  running: boolean;
}
```

Tři skupiny polí, plus spotřebiče:

```tsx
function NumberField({ label, unit, min, max, step = 0.1, value, onChange, help }) {
  return (
    <label className="block">
      <span className="text-sm text-slate-700">{label}</span>
      <div className="flex items-center gap-2 mt-1">
        <input
          type="number" value={value} min={min} max={max} step={step}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-full border border-slate-300 rounded px-3 py-2 text-sm"
        />
        {unit && <span className="text-sm text-slate-500 w-12">{unit}</span>}
      </div>
      {help && <span className="text-xs text-slate-500">{help}</span>}
    </label>
  );
}
```

Skupiny (přesně jako ve Streamlitu):

| Skupina | Pole |
|---|---|
| FVE | kWp, kapacita baterie kWh |
| Spotřeba a ceny | roční spotřeba MWh, cena silové, cena distribuce |
| Prodej přebytků | schéma (select), fixní výkupní cena, + ceny podle schématu |
| Pokročilé (skryté) | obec + geokódování, šířka/délka, sklon, azimut, systémové zpráty, zimní ztráty, limit exportu, tepelná baterie |
| Spotřebiče | checkboxy z API |

Geokódování — **označení musí být „Obec nebo město", ne „Adresa"**:

```tsx
<div className="border border-slate-200 rounded-lg p-4 bg-slate-50">
  <label className="block text-sm text-slate-700">
    Obec nebo město
    <input
      type="text" value={city} placeholder="např. Praha"
      className="mt-1 w-full border border-slate-300 rounded px-3 py-2 text-sm"
    />
  </label>
  <p className="text-xs text-slate-500 mt-1">
    Vyhledává se obec, ne ulice — zadejte např. „Praha" nebo „Brno".
  </p>
  {geoError && <p className="text-xs text-red-600 mt-1">{geoError}</p>}
  {geo && <p className="text-xs text-emerald-700 mt-1">Nalezeno: {geo.display_name}</p>}
  <button type="button" onClick={doGeocode} disabled={geocoding}
    className="mt-2 text-sm text-navy underline disabled:opacity-50">
    {geocoding ? "Hledám…" : "Vyhledat souřadnice"}
  </button>
</div>
```

Při úspěchu `onChange({ ...params, latitude: geo.lat, longitude: geo.lon })`.

Schéma prodeje jako select s českými popisky:

```tsx
const SELL_SCHEMES = [
  { value: "fixed", label: "Fixní cena" },
  { value: "community", label: "Komunita" },
  { value: "shared", label: "Sdílení" },
  { value: "spot", label: "Spot" },
] as const;
```

Spotřebiče jako checkboxy:

```tsx
<div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
  {appliances.map((a) => (
    <label key={a.name} className="flex items-start gap-2 text-sm">
      <input type="checkbox"
        checked={params.active_appliances.includes(a.name)}
        onChange={(e) => onChange({
          ...params,
          active_appliances: e.target.checked
            ? [...params.active_appliances, a.name]
            : params.active_appliances.filter((n) => n !== a.name),
        })}
        className="mt-1" />
      <span>
        {a.name}
        <span className="block text-xs text-slate-500">
          {a.power_kw} kW · {a.description}
        </span>
      </span>
    </label>
  ))}
</div>
```

Commit: `feat(fve-web): FveAnalysisForm`

---

### Úkol M6.4 — `FveAnalysisResults`

Výsledky rozdělené na přehled, grafy, spotřebiče, ekonomiku, PDF.

Přehled — stejné metriky jako Streamlit:

```tsx
function Metric({ label, value, unit }: { label: string; value: number; unit: string }) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-lg font-semibold text-navy mt-1">
        {value.toLocaleString("cs-CZ", { maximumFractionDigits: 0 })} {unit}
      </div>
    </div>
  );
}
```

Grafy — **přes `PlotlyChart`, každý s `json={result.plots.monthly_stats}`**:

```tsx
<div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
  <PlotlyChart json={result.plots.savings_pie} title="Struktura úspor" />
  <PlotlyChart json={result.plots.energy_pie} title="Složení energie" />
  <PlotlyChart json={result.plots.monthly_stats} title="Měsíční statistiky" />
  <PlotlyChart json={result.plots.savings_treemap} title="Úspory podle spotřebičů" />
  <PlotlyChart json={result.plots.energy_treemap} title="Energie podle spotřebičů" />
</div>
```

Tabulka spotřebičů — seřazení jako ve Streamlitu (`Základní chod` nahoře, `CELKEM` dole):

```tsx
const APP_SORT = (name: string) =>
  name === "Základní chod" ? 0 : name === "CELKEM" ? 2 : 1;

Object.entries(result.appliance_metrics)
  .sort(([a], [b]) => APP_SORT(a) - APP_SORT(b) || a.localeCompare(b, "cs"))
  .map(([name, m]) => (
    <tr key={name}
        className={name === "CELKEM" ? "font-semibold bg-slate-100"
                 : name === "Základní chod" ? "bg-slate-50" : ""}>
      <td className="px-3 py-2">{name}</td>
      <td className="px-3 py-2">{m.fve_kWh.toFixed(0)}</td>
      <td className="px-3 py-2">{m.grid_kWh.toFixed(0)}</td>
      <td className="px-3 py-2">{m.savings_czk.toLocaleString("cs-CZ")}</td>
      <td className="px-3 py-2">{m.coverage_pct.toFixed(1)} %</td>
    </tr>
  ))}
```

Ekonomika — NPV, návratnost, srovnání se S&P500:

```tsx
const econ = await runEconomic({ annual_savings: result.financial_balance.annual_savings_czk });
```

Doporučení — `result.recommendations.map(...)` jako seznam.

**PDF:** teď je generuje legacy `/report/energy`, který bere volný dict. Reuse ho:

```tsx
const handlePdf = async () => {
  const res = await client.post("/report/energy", result, { responseType: "blob" });
  const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "Energeticka_analyza.pdf";
  a.click();
  window.URL.revokeObjectURL(url);
};
```

Ale `/report/energy` je na legacy cestě **bez `/api/v1` prefixu**. Client má `baseURL = "/api/v1"`. Řešení — nový endpoint v `fve_router.py`, který volá stejný generátor:

```python
@router.post("/fve-analysis/report/energy")
def energy_pdf(result: dict, user: User = Depends(ANY_ROLE)):
    """PDF energetické analýzy. Reuse legacy generátor, ale pod /api/v1
    s auth — client má baseURL=/api/v1, legacy cesta by se netrefila."""
    from report_gen import generate_energy_report

    try:
        pdf = generate_energy_report(result)
    except Exception as e:
        raise HTTPException(500, f"PDF se nepodařilo vygenerovat: {e}")
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="fve_energy.pdf"'},
    )
```

Najdi přesný import generátoru v `main.py` — je to buď `report_gen` nebo `report_generator`. Podle toho uprav import.

Commit: `feat(fve-web): FveAnalysisResults`

---

### Úkol M6.5 — `ContactStep`

Kontakt je povinný vždy. Validace před odesláním, protože server vrací 422 a chyba z hlášky je méně příjemná než validace u pole:

```tsx
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function validate(c: FveContact): Partial<Record<keyof FveContact, string>> {
  const e: Partial<Record<keyof FveContact, string>> = {};
  if (c.name.trim().length < 2) e.name = "Zadejte jméno a příjmení";
  if (!EMAIL_RE.test(c.email)) e.email = "Zadejte platný e-mail";
  const digits = c.phone.replace(/\D/g, "");
  if (digits.length < 9) e.phone = "Telefon musí mít alespoň 9 číslic";
  return e;
}
```

Obě tlačítka — „Uložit jako rozpracovanou analýzu" a „Vytvořit zakázku a pokračovat" — volají stejný `saveAnalysis` a druhé navíc `convertToOrder` a pak `navigate(`/projects/${id}/pipeline`)`.

Commit: `feat(fve-web): ContactStep`

---

### Úkol M6.6 — routy, menu, stránky

`App.tsx` — přidej routy. Obě sdílí `FveAnalysisLayout`, liší se props:

```tsx
<Route
  path="/fve-analysis"
  element={
    <ProtectedLayout>
      <FveAnalysisPage />
    </ProtectedLayout>
  }
/>
<Route
  path="/projects/:id/fve-analysis"
  element={
    <ProtectedLayout>
      <ProjectFveAnalysisPage />
    </ProtectedLayout>
  }
/>
```

`ProtectedLayout` bez `roles` prop = přístupné všem přihlášeným, tedy i zákazníkovi.

`FveAnalysisPage` — standalone, defaulty, na konci kontakt.

`ProjectFveAnalysisPage` — načte projekta:

```typescript
const { id } = useParams();
const res = await client.get(`/projects/${id}`);
// fve_params je objekt nebo {} — prázdný objekt znamená „nová analýza v projektu"
const initial = { ...DEFAULTS, ...(res.data.fve_params ?? {}) };
```

Pokud projekt **není** ve stavu `fve_analyza`, zobrazí varování, že je to běžná zakázka a analýza se jen doplní — nepřepíše nic.

`Layout.tsx` — menu. Dnes:

```typescript
const isCustomer = hasAnyRole(user, ["customer"]);
```

Nová položka pro obě skupiny:

```typescript
{!isCustomer ? (
  <NavLink to="/fve-analysis">fveAnalysis</NavLink>
) : (
  <NavLink to="/fve-analysis">fveAnalysis</NavLink>
)}
```

Před zjednodušením na jednu větev zjisti, jak ostatní položky rozlišují role — pokud zákazník vidí jiné menu, nová položka patří do obou, jen v jeho variantě jako „Moje projekty" sousedí.

Commit: `feat(fve-web): routy a menu`

---

## M7. Verifikace

### Automaticky

```bash
# 1. backend — celá sada
./venv/bin/python -m pytest tests/reportgen -q --timeout=120
# očekávaně 101 passed

# 2. frontend — typy a build
cd frontend-web && npm run build
# musí projít tsc -b bez chyb
```

### Ručně v prohlížeči

Playwright z `browser-automation` skillu není v tomto prostředí dostupný (`patchright` chybí), ale chromium v `~/.cache/ms-playwright` je. Ověř skriptem přes `./venv/bin/python` s `playwright` — heredoc, žádné soubory:

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

    pg.goto("http://localhost:3100/login")
    pg.fill("input[type=email]", "zakaznik@antelon.local")
    pg.fill("input[type=password]", "Zakaznik123!")
    pg.click("button[type=submit]")
    pg.wait_for_url("**/dispecink", timeout=15000)

    # fveAnalysis v menu zákazníka
    pg.goto("http://localhost:3100/fve-analysis")
    pg.wait_for_selector("text=Instalovaný výkon", timeout=10000)
    print("krok 1 OK")

    # spustit analýzu
    pg.click("text=Spustit analýzu")
    pg.wait_for_selector("text=Roční bilance", timeout=120000)
    print("výsledky OK")
    pg.screenshot(path="/tmp/fve-results.png")

    # graf se musí vykreslit (ne selhat na JSON.parse)
    assert pg.locator(".js-plotly-plot").count() > 0, "graf se nevykreslil"
    print("grafy OK")

    # krok 3 — validace zablokuje prázdný e-mail
    pg.click("text=Pokračovat")
    pg.click("text=Uložit jako rozpracovanou analýzu")
    assert "platný e-mail" in pg.inner_text("body")
    print("validace OK")

    print("console errors:", errors or "žádné")
    b.close()
```

Kroky k ověření ručně:

| # | Krok | Očekávání |
|---|---|---|
| 1 | `POST /fve-analysis/run` na defaultu | 200, <5 s (cache), `plots.monthly_stats` je string |
| 2 | `/fve-analysis` jako zákazník | formulář, 17 spotřebičů z API |
| 3 | Spustit analýzu | bilanční metriky + vykreslené grafy |
| 4 | Krok 3 s prázdným e-mailem | validace zablokuje, žádný request |
| 5 | Uložit s validním kontaktem | 201, projekt ve stavu `fve_analyza` |
| 6 | `/projects` jako admin | analýza vidět |
| 7 | Převést na zakázku | `lead`, pipeline běží, krok „Zjištění roční spotřeby" = `done` |
| 8 | Zopakovat převod | 409 |
| 9 | Cizí analýza jako zákazník | 403 |
| 10 | Geokódování „Praha" | souřadnice; „Praha 1" → srozumitelná hláška |

Nasazení do běžícího prostředí až po schválení:

```bash
docker compose up -d --build
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8051/docs   # očekávaně 200
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3001         # očekávaně 200
```

---

## Co se NEdělá

| Vynecháno | Proč |
|---|---|
| **Analýza OTE** | `data/spot_market.db` v repu chybí; `download_ote_data.sh` i `process_ote_data.py` neexistují, takže `POST /ote/update` spadne na `FileNotFoundError`. Uživatel skripty najde později — do té doby je fveAnalysis bez OTE použitelná (spot jen jako volitelné schéma, fallback na fixní cenu). |
| XLSX export | Už existuje v `/projects/{id}/generate`. |
| Ukládání nastavení do JSON | Nahrazeno tím, že analýza je uložený projekt. |
| `fve_wrap.py` | Mrtvý kód, spadlý na importu. Nechávám ležet — jeho oprava není v scope a nikdo ho nevolá. Pokud chceš, úklid zvlášť. |
| Migrace legacy Streamlitu | Mimo scope. Legacy běží dál na `/analysis/*`. |
| `nodiscard` — oprava hesla novému zákazníkovi | Náhodná hesla, reset mimo scope. |
| Oprava nesrovnalosti `admin123` vs `Admin123!` | Existuje už teď, nesouvisí s fveAnalysis. |
| Oprava `fve.etikos.cz` TLS certifikátu | Veřejný cert má `CN=drakisa.cz` a `fve.etikos.cz` není v SAN. Problém prohlížeče, ne aplikace. |

---

## Rizika

| Riziko | Řešení |
|---|---|
| `fve_analysis.py` musí jít naimportovat přes `app.` | Vyřešeno a **ověřeno experimentálně**: helper `_mod()` v M1.1 zajišťuje `backend/` v `sys.path`. Ověř hned po založení souboru (příkaz je v M1.1) a pak `tests/reportgen/test_fve_analysis.py` po M1.3. Relativní ani top-level import tu nesedí — viz nález 1 v kontextu. |
| TS typy pro `plotly.js-dist-min` | `npm install -D @types/plotly.js`; kdyby neseděly, přepni na plný `plotly.js`. Ověř `npm run build` hned po M6.1. |
| Testy v CI bez sítě | `weather_cache.db` má jen **jednu** položku: defaultní `50.0880/14.4208`. Testy **musí** používat tyto souřadnice, jinak utečou na PVGIS a spadnou timeoutem. Dev workspace souřadnici má; v čistém CI ne. |
| Testy v CI bez `weather_cache.db` | Pak spadne i default. Řešení pro CI: `pv_calculator.fetch_pvgis_tmy_data` zmockovat (viz `pytest-mock` v `requirements.txt`) a vrátit fixní DataFrame. Nejdřív zjisti, jestli CI vůbec existuje — pokud ne, napiš to do plánu jako poznámku a neřeš. |
| `reportgen.db` je produkční data | Aditivní migrace (jen `ADD COLUMN`), záloha do `data/backups/` před M2. |
| Nový stav `fve_analyza` rozbije filtry Dispečinku | Filtry zobrazují explicitně známé stavy — `fve_analyza` se v seznamu zakázek nezobrazí, dokud není převedena. Ověř v M7 krok 6/7. |
| Velké JSON odpovědi | `raw_data` má 100 řádků hodinových dat + 5 grafů + 17 spotřebičů. Odhad ~200–400 KB. Akceptovatelné pro interní nástroj; pokud to bude vadit, `raw_data` se vypne flagem. |
| Synchronní výpočet v FastAPI requestu | Akceptováno pro V1 — běží **0,2 s** z cache, ne desítky sekund (výchozí odhad v designu sekce 10 byl nadhodnocený). |