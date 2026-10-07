# Výpočet produkce FVE a geocoder — implementační plán

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Opravit nadhodnocenou produkci FVE (bod 4) zavedením teplotní ztráty, reálného optima a výchozí GPS Ústí nad Labem, a nahradit geocoder Open-Meteo za Nominatim s výběrem z více výsledků (bod 5).

**Architecture:** Čtyři izolované změny. (1) Výchozí souřadnice Ústí (50.6607, 14.03227) na osmi runtime místech + test shody defaultů mezi `frontend-web/src/api/fve.ts`, `app/fve_analysis._DEFAULTS` a `reportgen.fve_router.FveParams`, který zároveň odhalí jediný reálný drift (`grid_export_limit_kw`). (2) Čistá funkce `apply_temperature_derate`, zapojená do `get_pv_production` mezi DC výkon a `system_loss_factor` (a tím automaticky i do optima, protože to volá tutéž funkci). (3) `get_optimal_pv_production` přestane používat `surface_tilt=latitude` a prohledá sklon 10–70° po 5°; `winter_loss_factor` se propustí, aby se reál a optimum lišily jen orientací a poměr nikdy nepřekročil 100 %. (4) `geocoder.py` se přepíše na Nominatim (`search` vrací `list[dict]`), endpoint vrátí `200 + {"results": [...]}` a frontend v kartě *Umístění a pokročilé parametry* vykreslí tlačítka k výběru.

**Tech Stack:** Python 3.12, FastAPI, pvlib, pandas, requests, pytest. React 19 + TypeScript (Vite).

**Spec:** `docs/superpowers/specs/2026-10-06-fve-analyza-opravy-a-cenik-design.md` (kapitola 8 — „Část 5 — Výpočet produkce a geocoder", body 8.1–8.4, a bod 5 spec)

**Závislosti:** Tento plán se aplikuje **po** `docs/superpowers/plans/2026-10-06-2-cenik-materialu.md` — ten rozdělil `FveAnalysisForm.tsx` na karty a přidal do `FveParams` pole `bom_mode`, `fve_materials`, `*_material_id`. Geocode picker se přidává **obsahově** do karty „Umístění a pokročilé parametry"; struktura karet se nemění. Plán 1 (`2026-10-06-1-ukladani-a-opravneni.md`) řeší `ANY_ROLE` a `convert_to_order`, proto se jich tento plán nedotýká.

## Global Constraints

- Backend se spouští z kořene repa, aby cache padla do `data/`. Testy: `./venv/bin/python -m pytest tests/reportgen -q`.
- Testy běží **offline z `data/weather_cache.db`**. Cache už obsahuje Ústí `(50.6607, 14.0323)` (shoda do 0.001), takže změna defaultu testy nerozbije — viz Task 1.
- `verify_tmy.py` a `verify_tmy_full.py` jsou vývojové skripty — **neměnit**.
- Živé geocode testy (Nominatim) zůstávají živé — osvědčený vzor v repu. K nim přibývá unit test s mocknutým `requests.get`.
- Politika OSM: vlastní `User-Agent` (`antelon-energy/1.0`), max ~1 req/s → v UI tlačítko `disabled` po dobu `geocoding`, v geocoderu malá mezipaměť.
- `apply_temperature_derate` **není** parametr v UI — konstanta v modulu (`TEMP_COEFF_PER_C`).
- Commit messages v konvenci repa: `feat(...)`, `fix(...)`, `test(...)`, `chore(...)`.
- Vývoj běží v dev workspace, **ne** v produkci `/home/roman/apps/antelon-energy`.

## Review Focus

Než začneš, přečti si kapitolu 8 spec. Těchto pět míst je nejpravděpodobnější, že je někdo rozbije — každé má vlastní test:

1. **Shoda defaultů na všech osmi místech** — nový parity test (Task 1) parsuje `DEFAULT_FVE_PARAMS` z `.ts`. Kromě GPS odhalí i jediný reálný drift: `_DEFAULTS["grid_export_limit_kw"]=None` vs `FveParams=10.0`. Plan ho záměrně **sjednocuje na 10.0** (UI je zdrojem pravdy pro defaulty) — ověřeno, že to nerozbije existující testy bilance, které limit zadávají explicitně.
2. **Teplotní ztráta se nesmí započítat dvakrát a musí se projevit v reálu i optimu** — aplikuje se uvnitř `get_pv_production` (před `system_loss_factor`), takže ji optimum dostane automaticky. Test porovnává produkci pro `temp_air=5` vs `temp_air=45`. Task 2.
3. **Optimum nikdy nesmí přesáhnout 100 %** — sken zahrnuje `35°` (defaultní sklon), takže `optimal >= actual` platí vždy. Kdyby sken začínal jinde nebo optimum nebralo `winter_loss_factor`, poměr by mohl přesáhnout 100 %. Task 3.
4. **Nominatim kontrakt a hlavičky** — `User-Agent`, `limit=6`, `format=jsonv2`, mezipaměť; prázdný vstup → 400, nenalezeno → 200 s prázdným `results`. Staré testy čekající 404 se přepisují. Task 4 + Task 5.
5. **Frontend picker** — `FveGeocodeResult[]`, tlačítka, zvýraznění výběru, odstraněná nápověda „Hledá se obec, ne ulice", `disabled` během hledání. Task 6.

**Nové testy (spec 10.1):** defaulty shoda, `apply_temperature_derate`, optimum (syntetické počasí), geocode kontrakt 200/400, geocode unit (mock: hlavička, `limit=6`, parsování dvou výsledků), přepsaný `test_fve_analysis.py:33` na Ústí.

---

## Souborová mapa

| Soubor | Odpovědnost | Změna |
|---|---|---|
| `backend/app/fve_analysis.py` | `_DEFAULTS` | GPS Ústí, `grid_export_limit_kw` → 10.0 |
| `backend/app/reportgen/fve_router.py` | `FveParams`, geocode endpoint | GPS Ústí, kontrakt 200 + `results` |
| `backend/app/reporting.py` | fallback šablony | GPS Ústí |
| `backend/app/reportgen/fve_wrap.py` | fallbacky parametrů | GPS Ústí (2×) |
| `backend/app/data_loader.py` | signatura + optimum | GPS Ústí, `winter_loss_factor` do optima |
| `backend/main.py` | spot-profitabilita | GPS Ústí |
| `backend/app/pv_calculator.py` | výpočet produkce | `apply_temperature_derate`, sken optima |
| `backend/app/geocoder.py` | geokódování | přepis na Nominatim |
| `frontend-web/src/api/fve.ts` | volání API | GPS Ústí, `geocode` → `results` |
| `frontend-web/src/types.ts` | typy | `FveGeocodeResult`, zrušit `FveGeocode` |
| `frontend-web/src/components/fve/FveAnalysisForm.tsx` | karta Umístění | picker s tlačítky |
| `tests/reportgen/test_fve_analysis.py` | defaulty | řádek 33 → Ústí |
| `tests/reportgen/test_fve_api.py` | geocode testy | přepis na 200 + `results` |
| `tests/reportgen/test_fve_defaults.py` | **nový** | shoda defaultů z `.ts` |
| `tests/reportgen/test_pv_calculator.py` | **nový** | teplotní derate + optimum |
| `tests/reportgen/test_geocoder.py` | **nový** | Nominatim mock |

---

### Task 1: Výchozí GPS Ústí nad Labem + test shody defaultů

**Files:**
- Modify: `backend/app/fve_analysis.py:55-56`
- Modify: `backend/app/reportgen/fve_router.py:54-55`
- Modify: `frontend-web/src/api/fve.ts:63-64`
- Modify: `backend/app/reporting.py:80-81`
- Modify: `backend/app/reportgen/fve_wrap.py:24-25` a `:140`
- Modify: `backend/app/data_loader.py:45`
- Modify: `backend/main.py:197`
- Test: `tests/reportgen/test_fve_defaults.py` (nový), `tests/reportgen/test_fve_analysis.py:33`

**Interfaces:**
- Produces: `_DEFAULTS["latitude"]==50.6607`, `_DEFAULTS["longitude"]==14.03227`, stejně `FveParams` a `DEFAULT_FVE_PARAMS`.

- [ ] **Step 1: Přepiš assert na Ústí (padající test)**

V `tests/reportgen/test_fve_analysis.py` nahraď řádek 32–33:

```python
    # defaultní souřadnice jsou v weather_cache.db → testy běží offline
    assert (p["latitude"], p["longitude"]) == (50.0880, 14.4208)
```

za:

```python
    # defaultní souřadnice jsou v weather_cache.db → testy běží offline
    # (cache obsahuje i Ústí 50.6607, 14.0323; shoda do 0.001)
    assert (p["latitude"], p["longitude"]) == (50.6607, 14.03227)
```

- [ ] **Step 2: Vytvoř nový parity test**

Vytvoř `tests/reportgen/test_fve_defaults.py`:

```python
"""Shoda výchozích parametrů FVE mezi frontendem a backendem.

`DEFAULT_FVE_PARAMS` (frontend) se parsuje z TypeScriptu, aby se drift
projevil jako padající test — ne až tím, že formulář pošle jiné defaulty
než výpočet.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FVE_TS = REPO / "frontend-web" / "src" / "api" / "fve.ts"

from app.fve_analysis import _DEFAULTS  # noqa: E402
from reportgen.fve_router import FveParams  # noqa: E402


def _parse_ts_defaults(path: Path) -> dict:
    """Přečte `DEFAULT_FVE_PARAMS` z `.ts` jako dict.

    Záměrně hloupý řádkový parser (žádný TS parser): hodnoty jsou jednořádkové.
    Pole a objekty se přeskočí (řeší je až porovnání společných klíčů).
    """
    text = path.read_text(encoding="utf-8")
    match = re.search(
        r"DEFAULT_FVE_PARAMS\s*:\s*FveParams\s*=\s*\{(.*?)\n\};", text, re.S)
    assert match, "DEFAULT_FVE_PARAMS nenalezen v fve.ts"
    out: dict = {}
    for raw in match.group(1).splitlines():
        line = raw.split("//")[0].strip().rstrip(",")
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if value.startswith("[") or value.startswith("{"):
            continue
        if value in ("null", "None"):
            out[key] = None
        elif value == "true":
            out[key] = True
        elif value == "false":
            out[key] = False
        elif value[:1] in ('"', "'"):
            out[key] = value[1:-1]
        else:
            out[key] = float(value)
    return out


def test_defaults_match_across_frontend_and_backend():
    """Společné skalární klíče musí mít ve všech třech zdrojích stejnou hodnotu."""
    ts = _parse_ts_defaults(FVE_TS)
    fields = FveParams.model_fields
    common = [
        k for k in ts
        if k in _DEFAULTS and k in fields and "appliance" not in k
    ]
    assert common, "parser nenačetl žádné klíče — zkontroluj vzor v fve.ts"
    for key in common:
        assert ts[key] == _DEFAULTS[key], (
            f"{key}: .ts={ts[key]!r} != _DEFAULTS={_DEFAULTS[key]!r}")
        assert ts[key] == fields[key].default, (
            f"{key}: .ts={ts[key]!r} != FveParams={fields[key].default!r}")


def test_default_gps_is_usti_nad_labem():
    """Defaultní GPS je Ústí — jinak analýza počítá pro Prahu."""
    ts = _parse_ts_defaults(FVE_TS)
    for source in (_DEFAULTS, ts):
        assert (source["latitude"], source["longitude"]) == (50.6607, 14.03227)
    assert FveParams.model_fields["latitude"].default == 50.6607
    assert FveParams.model_fields["longitude"].default == 14.03227
```

- [ ] **Step 3: Spusť testy — musí padat**

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_defaults.py tests/reportgen/test_fve_analysis.py::test_default_params_cover_streamlit_settings -q`
Expected: FAIL — `test_default_gps_is_usti_nad_labem` hlásí Prahu a `test_defaults_match_...` hlásí `grid_export_limit_kw` a `latitude`/`longitude`.

- [ ] **Step 4: Změň `_DEFAULTS` + sjednoť `grid_export_limit_kw`**

V `backend/app/fve_analysis.py` nahraď v `_DEFAULTS`:

```python
    "grid_export_limit_kw": None,
```

za:

```python
    # UI default je 10 kW (FveParams i DEFAULT_FVE_PARAMS). Původní None
    # ("bez limitu") byl drift, který odhalil parity test v test_fve_defaults.
    "grid_export_limit_kw": 10.0,
```

a nahraď:

```python
    "latitude": 50.088,
    "longitude": 14.4208,
```

za:

```python
    "latitude": 50.6607,
    "longitude": 14.03227,
```

- [ ] **Step 5: Změň `FveParams`**

V `backend/app/reportgen/fve_router.py` nahraď:

```python
    latitude: float = Field(default=50.0880, ge=-90.0, le=90.0)
    longitude: float = Field(default=14.4208, ge=-180.0, le=180.0)
```

za:

```python
    latitude: float = Field(default=50.6607, ge=-90.0, le=90.0)
    longitude: float = Field(default=14.03227, ge=-180.0, le=180.0)
```

- [ ] **Step 6: Změň `DEFAULT_FVE_PARAMS`**

V `frontend-web/src/api/fve.ts` nahraď:

```ts
  latitude: 50.0880,
  longitude: 14.4208,
```

za:

```ts
  latitude: 50.6607,
  longitude: 14.03227,
```

- [ ] **Step 7: Změň fallback v `reporting.py`**

V `backend/app/reporting.py` nahraď:

```python
            "latitude": data.get("latitude", 50.0880),
            "longitude": data.get("longitude", 14.4208),
```

za:

```python
            "latitude": data.get("latitude", 50.6607),
            "longitude": data.get("longitude", 14.03227),
```

- [ ] **Step 8: Změň dva fallbacky ve `fve_wrap.py`**

V `backend/app/reportgen/fve_wrap.py` nahraď (řádky 24–25):

```python
    lat = float(params.get("latitude", 50.088))
    lon = float(params.get("longitude", 14.4208))
```

za:

```python
    lat = float(params.get("latitude", 50.6607))
    lon = float(params.get("longitude", 14.03227))
```

a dále nahraď (řádek 140):

```python
    prod_df, _, _ = load_production_data(kwp=1.0, latitude=50.088, longitude=14.4208)
```

za:

```python
    prod_df, _, _ = load_production_data(kwp=1.0, latitude=50.6607, longitude=14.03227)
```

- [ ] **Step 9: Změň signaturu `load_production_data`**

V `backend/app/data_loader.py` řádek 45 nahraď:

```python
def load_production_data(kwp=10, latitude=50.088, longitude=14.4208, surface_tilt=35, surface_azimuth=180, system_loss_factor=14.0, winter_loss_factor=10.0):
```

za:

```python
def load_production_data(kwp=10, latitude=50.6607, longitude=14.03227, surface_tilt=35, surface_azimuth=180, system_loss_factor=14.0, winter_loss_factor=10.0):
```

- [ ] **Step 10: Změň spot-profitabilitu v `main.py`**

V `backend/main.py` řádek 197 nahraď:

```python
        prod_df, _, _ = load_production_data(kwp=1.0, latitude=50.0880, longitude=14.4208)
```

za:

```python
        prod_df, _, _ = load_production_data(kwp=1.0, latitude=50.6607, longitude=14.03227)
```

- [ ] **Step 11: Ověř, že nikde nezůstaly staré souřadnice (kromě `verify_tmy*.py`)**

Run: `grep -rn "50.088\|14.4208" backend/app backend/main.py frontend-web/src`
Expected: prázdný výstup. (`backend/verify_tmy*.py` se záměrně nezměnil.)

- [ ] **Step 12: Spusť cílené testy**

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_defaults.py tests/reportgen/test_fve_analysis.py -q`
Expected: PASS (parity testy + všech 8 původních).

- [ ] **Step 13: Spusť celou sadu**

Run: `./venv/bin/python -m pytest tests/reportgen -q`
Expected: PASS

- [ ] **Step 14: Commit**

```bash
git add backend/app/fve_analysis.py backend/app/reportgen/fve_router.py backend/app/reporting.py backend/app/reportgen/fve_wrap.py backend/app/data_loader.py backend/main.py frontend-web/src/api/fve.ts tests/reportgen/test_fve_defaults.py tests/reportgen/test_fve_analysis.py
git commit -m "fix(fve): vychozi GPS Usti nad Labem a shoda defaultu (bod 4)"
```

---

### Task 2: Teplotní ztráta — `apply_temperature_derate`

**Files:**
- Modify: `backend/app/pv_calculator.py` (nová konstanta + funkce za importy ~řádek 15; zapojení za výpočet DC výkonu ~řádek 151)
- Test: `tests/reportgen/test_pv_calculator.py` (nový)

**Interfaces:**
- Produces: `pv_calculator.apply_temperature_derate(production, cell_temp, coeff=TEMP_COEFF_PER_C) -> same shape`.
- Consumes: `get_pv_production(...)` — teplotní korekce se stává jeho součástí.

- [ ] **Step 1: Napiš padající testy**

Vytvoř `tests/reportgen/test_pv_calculator.py`:

```python
"""Produkce FVE: teplotní ztráta a optimum (body 4a/4b).

`get_pv_production` i `get_optimal_pv_production` umí dostat syntetické
počasí přes `weather_data`, takže testy nepotřebují síť ani cache.
"""
import pandas as pd

from pv_calculator import (
    apply_temperature_derate,
    get_optimal_pv_production,
    get_pv_production,
)


def _weather(temp_air):
    """Tři polední hodiny — deterministické a bez nočních NaN."""
    times = pd.date_range("2024-06-21 10:00", periods=3, freq="h", tz="UTC")
    return pd.DataFrame(
        {
            "ghi": [800.0, 900.0, 850.0],
            "dni": [600.0, 700.0, 650.0],
            "dhi": [120.0, 130.0, 125.0],
            "temp_air": [temp_air, temp_air, temp_air],
            "wind_speed": [1.0, 1.0, 1.0],
        },
        index=times,
    )


def test_apply_temperature_derate_formula():
    """−0,4 %/°C nad 25 °C: při 45 °C je výkon 92 %."""
    assert apply_temperature_derate(1000.0, 25.0) == 1000.0
    assert apply_temperature_derate(1000.0, 45.0) == 920.0
    assert apply_temperature_derate(1000.0, 5.0) == 1080.0


def test_get_pv_production_applies_temperature_derate():
    """Vyšší teplota vzduchu musí snížit produkci — důkaz, že se derate volá."""
    _, cold = get_pv_production(
        50.0, 14.0, 35, 180, 10.0, weather_data=_weather(5.0))
    _, hot = get_pv_production(
        50.0, 14.0, 35, 180, 10.0, weather_data=_weather(45.0))
    assert hot < cold
```

- [ ] **Step 2: Spusť testy — musí padat**

Run: `./venv/bin/python -m pytest tests/reportgen/test_pv_calculator.py -q`
Expected: FAIL — `ImportError: cannot import name 'apply_temperature_derate'`.

- [ ] **Step 3: Implementuj konstantu a funkci**

V `backend/app/pv_calculator.py` za `warnings.simplefilter(...)` (řádek 15) vlož:

```python
# Teplotní koeficient Pmax pro monokrystalický PERC panel: −0,4 %/°C nad 25 °C.
# Není to parametr v UI — konstanta modulu (design 8.2).
TEMP_COEFF_PER_C = -0.004


def apply_temperature_derate(production, cell_temp, coeff=TEMP_COEFF_PER_C):
    """Teplotní korekce DC výkonu podle teploty článku.

    `production` i `cell_temp` mohou být pandas Series nebo skaláry —
    operace je elementwise. Aplikuje se PŘED systémovými ztrátami.
    """
    return production * (1 + coeff * (cell_temp - 25.0))
```

- [ ] **Step 4: Zapoj derate do `get_pv_production`**

V `backend/app/pv_calculator.py` nahraď blok (řádky ~145–154):

```python
    # Calculate PV system output (DC power)
    # Using simple PVWatts-like efficiency model
    # Assume reference efficiency at 1000 W/m^2 and 25C
    # Power_output = kWp * (POA_global / 1000) * (1 + alpha * (cell_temp - 25))
    # Where alpha is temperature coefficient (e.g. -0.004 /C)
    # For now, stick to the simpler model without explicit temperature correction in this layer
    production = poa_irradiance['poa_global'] / 1000 * kwp
    
    # Apply general system loss factor
    production *= (1 - system_loss_factor / 100)
```

za:

```python
    # DC výkon při referenčních podmínkách (1000 W/m^2, 25 °C).
    production = poa_irradiance['poa_global'] / 1000 * kwp

    # Teplotní ztráta PŘED systémovými ztrátami (design 8.2). Riziko
    # dvojího započtení se měří proti PVGIS SARAH3 — viz závěrečné ověření.
    production = apply_temperature_derate(production, cell_temp)

    # Apply general system loss factor
    production *= (1 - system_loss_factor / 100)
```

- [ ] **Step 5: Spusť testy**

Run: `./venv/bin/python -m pytest tests/reportgen/test_pv_calculator.py -q`
Expected: PASS (2 testy).

- [ ] **Step 6: Spusť sadu produkce a analýzy**

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_analysis.py tests/reportgen/test_pv_calculator.py -q`
Expected: PASS — produkce pro Ústí se sníží, struktura výsledku se nemění.

- [ ] **Step 7: Commit**

```bash
git add backend/app/pv_calculator.py tests/reportgen/test_pv_calculator.py
git commit -m "fix(pv): teplotni ztrata -0.4 %/C nad 25 C (bod 4a)"
```

---

### Task 3: Reálné optimum — sken sklonu 10–70° a propuštění `winter_loss_factor`

**Files:**
- Modify: `backend/app/pv_calculator.py` (`get_optimal_pv_production` ~řádek 166)
- Modify: `backend/app/data_loader.py` (`get_optimal_pv_production` volání ~řádek 66)
- Test: `tests/reportgen/test_pv_calculator.py` (přidat), `tests/reportgen/test_fve_analysis.py` (přidat)

**Interfaces:**
- Consumes: `get_pv_production(..., winter_loss_factor=...)` z Tasku 2.
- Produces: `get_optimal_pv_production(..., winter_loss_factor=None)`.

- [ ] **Step 1: Napiš padající testy**

Přidej do `tests/reportgen/test_pv_calculator.py` (využij `_weather` z Tasku 2):

```python
def test_optimum_finds_best_tilt_and_never_exceeds_actual():
    """Optimum = maximum přes sklon 10–70° po 5°, azimut 180°.

    Sken zahrnuje i defaultní sklon 35°, takže optimum nikdy nesmí být
    menší než skutečná výroba pro tytéž podmínky → poměr ≤ 100 %.
    """
    weather = _weather(25.0)
    actual = get_pv_production(
        50.6607, 14.03227, 35, 180, 10.0,
        winter_loss_factor=10.0, weather_data=weather)[1]
    optimum = get_optimal_pv_production(
        50.6607, 14.03227, 10.0,
        winter_loss_factor=10.0, weather_data=weather)

    brute = max(
        get_pv_production(50.6607, 14.03227, tilt, 180, 10.0,
                          winter_loss_factor=10.0, weather_data=weather)[1]
        for tilt in range(10, 71, 5)
    )
    assert abs(optimum - brute) < 1e-9
    assert optimum >= actual - 1e-9


def test_optimum_accepts_winter_loss_factor():
    """Zimní ztráta se propouští, aby se reál a optimum lišily jen orientací.

    Počasí obsahuje leden i červenec; při 100% zimní ztrátě musí být
    prosinec/leden/únor nulový, takže optimum klesne.
    """
    times = (
        pd.date_range("2024-01-15 12:00", periods=3, freq="h", tz="UTC")
        .append(pd.date_range("2024-07-15 12:00", periods=3, freq="h", tz="UTC"))
    )
    weather = pd.DataFrame(
        {
            "ghi": [500.0] * 6, "dni": [400.0] * 6, "dhi": [100.0] * 6,
            "temp_air": [25.0] * 6, "wind_speed": [1.0] * 6,
        },
        index=times,
    )
    bez = get_optimal_pv_production(
        50.6607, 14.03227, 10.0, winter_loss_factor=None, weather_data=weather)
    se = get_optimal_pv_production(
        50.6607, 14.03227, 10.0, winter_loss_factor=100.0, weather_data=weather)
    assert se < bez
```

Přidej do `tests/reportgen/test_fve_analysis.py` na konec:

```python
def test_production_performance_never_exceeds_100_pct():
    """Optimum hledá přes sklon a bere winter_loss → poměr ≤ 100 % (bod 4b)."""
    r = run_energy_analysis({"kwp": 10.0})
    pct = r["production_details"]["production_performance_pct"]
    assert pct <= 100.0 + 1e-6, f"production_performance_pct={pct}"
```

- [ ] **Step 2: Spusť testy — musí padat**

Run: `./venv/bin/python -m pytest tests/reportgen/test_pv_calculator.py -q -k optimum`
Expected: FAIL — `get_optimal_pv_production() got an unexpected keyword argument 'winter_loss_factor'` (a poměr může být > 100 %).

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_analysis.py::test_production_performance_never_exceeds_100_pct -q`
Expected: FAIL — `production_performance_pct` je > 100.

- [ ] **Step 3: Přepiš `get_optimal_pv_production`**

V `backend/app/pv_calculator.py` nahraď celou funkci (řádky 166–196):

```python
def get_optimal_pv_production(latitude, longitude, kwp, tz='UTC',
                              system_loss_factor=14.0, winter_loss_factor=None,
                              weather_data=None):
    """Nejlepší roční výroba přes sklon 10–70° při azimutu 180° (jih).

    Původní `surface_tilt=latitude` dávalo pro 50°N nesmyslných ~102 %.
    Prohledáme sklon po 5° a vezmeme maximum. `winter_loss_factor`
    propouštíme, aby se reálná výroba a optimum lišily POUZE orientací —
    jinak by poměr mohl přesáhnout 100 %.
    """
    best = None
    for tilt in range(10, 71, 5):
        _, total = get_pv_production(
            latitude=latitude,
            longitude=longitude,
            surface_tilt=tilt,
            surface_azimuth=180,
            kwp=kwp,
            tz=tz,
            system_loss_factor=system_loss_factor,
            winter_loss_factor=winter_loss_factor,
            weather_data=weather_data,
        )
        if best is None or total > best:
            best = total
    return best
```

- [ ] **Step 4: Propusť `winter_loss_factor` z `data_loader`**

V `backend/app/data_loader.py` nahraď volání optima (řádky 66–72):

```python
    optimal_production = get_optimal_pv_production(
        latitude=latitude,
        longitude=longitude,
        kwp=kwp,
        system_loss_factor=system_loss_factor,
        weather_data=weather_data
    )
```

za:

```python
    optimal_production = get_optimal_pv_production(
        latitude=latitude,
        longitude=longitude,
        kwp=kwp,
        system_loss_factor=system_loss_factor,
        winter_loss_factor=winter_loss_factor,
        weather_data=weather_data
    )
```

- [ ] **Step 5: Spusť testy**

Run: `./venv/bin/python -m pytest tests/reportgen/test_pv_calculator.py tests/reportgen/test_fve_analysis.py -q`
Expected: PASS (optimum ≤ 100 %, všechny původní testy zelené).

- [ ] **Step 6: Spusť celou sadu**

Run: `./venv/bin/python -m pytest tests/reportgen -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/pv_calculator.py backend/app/data_loader.py tests/reportgen/test_pv_calculator.py tests/reportgen/test_fve_analysis.py
git commit -m "fix(pv): optimum skenem sklonu 10-70 a winter_loss (bod 4b)"
```

---

### Task 4: Geocoder na Nominatim

**Files:**
- Modify: `backend/app/geocoder.py` (celý přepis)
- Test: `tests/reportgen/test_geocoder.py` (nový)

**Interfaces:**
- Produces: `geocoder.search(address: str, limit: int = 6) -> list[dict]`, každý dict `{"lat": float, "lon": float, "display_name": str}`. `get_coordinates` se ruší (jediný volající je `fve_router.geocode`, upravený v Tasku 5).

- [ ] **Step 1: Napiš padající testy (mock `requests.get`)**

Vytvoř `tests/reportgen/test_geocoder.py`:

```python
"""Geocoder Nominatim — unit testy s mocknutým `requests.get`.

Živé testy zůstávají v test_fve_api.py; tady ověřujeme kontrakt a hlavičky
bez sítě (User-Agent je povinný podle politiky OSM).
"""
import requests

from app import geocoder


def _fake_response(payload):
    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    return _Resp()


def test_search_parses_results_and_sends_headers(monkeypatch):
    geocoder._CACHE.clear()
    captured: dict = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return _fake_response([
            {"lat": "50.6812", "lon": "13.9876",
             "display_name": "Telnice, okres Ústí nad Labem, Česko"},
            {"lat": "49.1234", "lon": "16.5678",
             "display_name": "Telnice, okres Brno-venkov, Česko"},
        ])

    monkeypatch.setattr(requests, "get", fake_get)
    results = geocoder.search("Telnice")

    assert captured["url"] == "https://nominatim.openstreetmap.org/search"
    assert captured["params"]["q"] == "Telnice"
    assert captured["params"]["format"] == "jsonv2"
    assert captured["params"]["limit"] == 6
    assert captured["params"]["addressdetails"] == 1
    assert captured["headers"]["User-Agent"] == "antelon-energy/1.0"
    assert captured["headers"]["Accept-Language"] == "cs"
    assert captured["timeout"] == 10
    assert len(results) == 2
    assert results[0] == {
        "lat": 50.6812,
        "lon": 13.9876,
        "display_name": "Telnice, okres Ústí nad Labem, Česko",
    }


def test_search_is_cached(monkeypatch):
    geocoder._CACHE.clear()
    calls: list = []

    def fake_get(url, **kwargs):
        calls.append(1)
        return _fake_response(
            [{"lat": "1.0", "lon": "2.0", "display_name": "X"}])

    monkeypatch.setattr(requests, "get", fake_get)
    geocoder.search("Cache test")
    geocoder.search("Cache test")
    assert len(calls) == 1


def test_search_empty_input_does_not_hit_network(monkeypatch):
    geocoder._CACHE.clear()

    def fake_get(*args, **kwargs):
        raise AssertionError("prázdný vstup nesmí volat síť")

    monkeypatch.setattr(requests, "get", fake_get)
    assert geocoder.search("   ") == []
```

- [ ] **Step 2: Spusť testy — musí padat**

Run: `./venv/bin/python -m pytest tests/reportgen/test_geocoder.py -q`
Expected: FAIL — `AttributeError: module 'app.geocoder' has no attribute 'search'`.

- [ ] **Step 3: Přepiš `geocoder.py`**

Nahraď celý obsah `backend/app/geocoder.py`:

```python
"""Geokódování přes Nominatim (OpenStreetMap).

Nominatim umí adresy i obce a vrací více kandidátů; UI si z nich vybere.
Politika OSM vyžaduje vlastní `User-Agent` a max ~1 req/s — proto držíme
malou mezipaměť a tlačítko v UI je během hledání zamčené.
"""
import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "antelon-energy/1.0"

_CACHE: dict[str, list[dict]] = {}


def search(address: str, limit: int = 6) -> list[dict]:
    """Vrátí kandidáty z Nominatim. Prázdný vstup i nenalezeno → []."""
    address = (address or "").strip()
    if not address:
        return []

    key = f"{address.lower()}|{limit}"
    if key in _CACHE:
        return _CACHE[key]

    response = requests.get(
        NOMINATIM_URL,
        params={
            "q": address,
            "format": "jsonv2",
            "limit": limit,
            "addressdetails": 1,
        },
        headers={"User-Agent": USER_AGENT, "Accept-Language": "cs"},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json() or []

    results = [
        {
            "lat": float(item["lat"]),
            "lon": float(item["lon"]),
            "display_name": item.get("display_name", ""),
        }
        for item in data
    ]
    _CACHE[key] = results
    return results
```

- [ ] **Step 4: Spusť testy**

Run: `./venv/bin/python -m pytest tests/reportgen/test_geocoder.py -q`
Expected: PASS (3 testy).

- [ ] **Step 5: Commit**

```bash
git add backend/app/geocoder.py tests/reportgen/test_geocoder.py
git commit -m "feat(fve): geocoder na Nominatim s vice vysledky (bod 5)"
```

---

### Task 5: Geocode endpoint — kontrakt 200 + `results`, přepis testů

**Files:**
- Modify: `backend/app/reportgen/fve_router.py` (`geocode` ~řádky 125–150)
- Test: `tests/reportgen/test_fve_api.py` (řádky 90–116)

**Interfaces:**
- Consumes: `geocoder.search` z Tasku 4.
- Produces: `POST /api/v1/fve-analysis/geocode` → 200 `{"results": [{"latitude", "longitude", "display_name"}]}`, 400 prázdný vstup. `get_coordinates` se už nevolá.

- [ ] **Step 1: Přepiš testy (padající)**

V `tests/reportgen/test_fve_api.py` nahraď tři funkce `test_geocode_finds_city`, `test_geocode_rejects_empty`, `test_geocode_explains_itself_when_not_found` (řádky 90–116) za:

```python
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
```

- [ ] **Step 2: Spusť testy — musí padat**

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_api.py -q -k geocode`
Expected: FAIL — `test_geocode_finds_city` padá na `KeyError: 'results'`; `test_geocode_not_found_returns_empty_list` na 404.

- [ ] **Step 3: Přepiš endpoint**

V `backend/app/reportgen/fve_router.py` nahraď funkci `geocode` (řádky 125–150):

```python
@router.post("/fve-analysis/geocode")
def geocode(payload: dict, user: User = Depends(ANY_ROLE)):
    """Geokódování adresy nebo obce přes Nominatim.

    Vrací VÍC kandidátů; UI si z nich vybere tlačítkem. Nenalezeno je
    prázdný seznam (200), ne 404 — s Nominatim se „nenalezeno" nedá
    spolehlivě odlišit od „málo konkrétní dotaz".
    """
    address = (payload or {}).get("address", "").strip()
    if not address:
        raise HTTPException(400, "Zadejte adresu nebo obec")
    from app.geocoder import search

    results = search(address)
    # Nominatim vrací klíče lat/lon; FveParams má latitude/longitude.
    return {
        "results": [
            {
                "latitude": r["lat"],
                "longitude": r["lon"],
                "display_name": r["display_name"],
            }
            for r in results
        ]
    }
```

- [ ] **Step 4: Spusť geocode testy**

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_api.py -q -k geocode`
Expected: PASS (3 testy, živé volání Nominatim).

- [ ] **Step 5: Spusť celou sadu API**

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_api.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/reportgen/fve_router.py tests/reportgen/test_fve_api.py
git commit -m "fix(fve): geocode vraci 200 + seznam vysledku (bod 5)"
```

---

### Task 6: Frontend — typ `FveGeocodeResult` a picker v kartě Umístění

**Files:**
- Modify: `frontend-web/src/types.ts:255-259`
- Modify: `frontend-web/src/api/fve.ts:7,23-27`
- Modify: `frontend-web/src/components/fve/FveAnalysisForm.tsx` (import ~řádek 3, stav ~68–72, `doGeocode` ~77–94, blok karty Umístění ~166–195)

**Interfaces:**
- Consumes: `FveParams` z plánu 2 (obsahuje už `bom_mode`, `fve_materials`, `*_material_id`). Karty formuláře z plánu 2 — zde se mění jen obsah karty „Umístění a pokročilé parametry".
- Produces: `geocode(address): Promise<FveGeocodeResult[]>`.

- [ ] **Step 1: Změň typy (rozbitý stav = padající typecheck)**

V `frontend-web/src/types.ts` nahraď:

```ts
export interface FveGeocode {
  latitude: number;
  longitude: number;
  display_name: string;
}
```

za:

```ts
export interface FveGeocodeResult {
  latitude: number;
  longitude: number;
  display_name: string;
}
```

- [ ] **Step 2: Změň API volání**

V `frontend-web/src/api/fve.ts` nahraď v importu `FveGeocode,` za `FveGeocodeResult,` a nahraď:

```ts
/** Hledá NÁZEV OBCE, ne adresu (Open-Meteo je name search). */
export const geocode = (address: string) =>
  client
    .post<FveGeocode>("/fve-analysis/geocode", { address })
    .then((r) => r.data);
```

za:

```ts
/** Nominatim hledá adresu i obec a vrací VÍC kandidátů k výběru. */
export const geocode = (address: string) =>
  client
    .post<{ results: FveGeocodeResult[] }>("/fve-analysis/geocode", { address })
    .then((r) => r.data.results);
```

- [ ] **Step 3: Spusť typecheck — musí padat**

Run: `cd frontend-web && npx tsc -b`
Expected: FAIL — `FveAnalysisForm.tsx` importuje zrušený `FveGeocode` a používá `r.latitude`/`r.longitude` na jiném typu.

- [ ] **Step 4: Přepiš stav a handler ve `FveAnalysisForm.tsx`**

Nahraď import (řádek 3):

```tsx
import type { FveAppliance, FveGeocode, FveParams } from "../../types";
```

za:

```tsx
import type { FveAppliance, FveGeocodeResult, FveParams } from "../../types";
```

Nahraď stav (řádky 68–72):

```tsx
  const [city, setCity] = useState("");
  const [geo, setGeo] = useState<FveGeocode | null>(null);
  const [geoError, setGeoError] = useState("");
  const [geocoding, setGeocoding] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
```

za:

```tsx
  const [city, setCity] = useState("");
  const [geoResults, setGeoResults] = useState<FveGeocodeResult[]>([]);
  const [geoIndex, setGeoIndex] = useState<number | null>(null);
  const [geoAttempted, setGeoAttempted] = useState(false);
  const [geoError, setGeoError] = useState("");
  const [geocoding, setGeocoding] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
```

Nahraď `doGeocode` (řádky 77–94):

```tsx
  const doGeocode = async () => {
    if (!city.trim()) {
      setGeoError("Zadejte název obce");
      return;
    }
    setGeocoding(true);
    setGeoError("");
    try {
      const r = await geocode(city.trim());
      setGeo(r);
      onChange({ ...params, latitude: r.latitude, longitude: r.longitude });
    } catch (e: any) {
      setGeo(null);
      setGeoError(e?.response?.data?.detail || "Místo se nepodařilo najít");
    } finally {
      setGeocoding(false);
    }
  };
```

za:

```tsx
  const doGeocode = async () => {
    if (!city.trim()) {
      setGeoError("Zadejte adresu nebo obec");
      return;
    }
    setGeocoding(true);
    setGeoError("");
    setGeoResults([]);
    setGeoIndex(null);
    try {
      const results = await geocode(city.trim());
      setGeoResults(results);
      setGeoAttempted(true);
    } catch (e: any) {
      setGeoResults([]);
      setGeoAttempted(true);
      setGeoError(e?.response?.data?.detail || "Místo se nepodařilo najít");
    } finally {
      setGeocoding(false);
    }
  };

  // Výběr konkrétní varianty nastaví souřadnice a zvýrazní ji.
  const selectGeocode = (r: FveGeocodeResult, index: number) => {
    setGeoIndex(index);
    onChange({ ...params, latitude: r.latitude, longitude: r.longitude });
  };
```

- [ ] **Step 5: Přepiš blok karty Umístění**

V `frontend-web/src/components/fve/FveAnalysisForm.tsx` nahraď blok (za `Section title="Umístění a pokročilé parametry"`, aktuálně řádky 166–195):

```tsx
        <div className="border border-slate-200 rounded-lg p-4 bg-slate-50">
          <label className="block text-sm text-slate-700">
            Obec nebo město
            <input
              type="text"
              value={city}
              onChange={(e) => setCity(e.target.value)}
              placeholder="např. Praha"
              className="mt-1 w-full border border-slate-300 rounded px-3 py-2 text-sm bg-white"
            />
          </label>
          {/* Open-Meteo je name search — „adresa" by lalo lidi zbytečně hledat ulici */}
          <p className="text-xs text-slate-500 mt-1">
            Vyhledává se obec, ne ulice — zadejte např. „Praha" nebo „Brno".
          </p>
          {geoError && <p className="text-xs text-red-600 mt-1">{geoError}</p>}
          {geo && (
            <p className="text-xs text-emerald-700 mt-1">
              Nalezeno: {geo.display_name} ({geo.latitude.toFixed(4)}, {geo.longitude.toFixed(4)})
            </p>
          )}
          <button
            type="button"
            onClick={doGeocode}
            disabled={geocoding}
            className="mt-2 text-sm text-navy underline disabled:opacity-50"
          >
            {geocoding ? "Hledám…" : "Vyhledat souřadnice"}
          </button>
        </div>
```

za:

```tsx
        <div className="border border-slate-200 rounded-lg p-4 bg-slate-50">
          <label className="block text-sm text-slate-700">
            Adresa nebo obec
            <input
              type="text"
              value={city}
              onChange={(e) => setCity(e.target.value)}
              placeholder="např. Varvažov 210 Telnice"
              className="mt-1 w-full border border-slate-300 rounded px-3 py-2 text-sm bg-white"
            />
          </label>
          {geoError && <p className="text-xs text-red-600 mt-1">{geoError}</p>}
          <button
            type="button"
            onClick={doGeocode}
            disabled={geocoding}
            className="mt-2 text-sm text-navy underline disabled:opacity-50"
          >
            {geocoding ? "Hledám…" : "Vyhledat souřadnice"}
          </button>
          {geoAttempted && !geoError && geoResults.length === 0 && (
            <p className="text-xs text-slate-500 mt-2">
              Nebylo nalezeno žádné místo pro „{city}".
            </p>
          )}
          {geoResults.length > 0 && (
            <ul className="mt-2 space-y-1">
              {geoResults.map((r, i) => (
                <li key={`${r.latitude},${r.longitude}`}>
                  <button
                    type="button"
                    onClick={() => selectGeocode(r, i)}
                    className={
                      "w-full text-left text-xs rounded px-2 py-1 border " +
                      (geoIndex === i
                        ? "border-emerald-500 bg-emerald-50 text-emerald-800"
                        : "border-slate-200 bg-white hover:bg-slate-100")
                    }
                  >
                    {r.display_name} ({r.latitude.toFixed(4)}, {r.longitude.toFixed(4)})
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
```

- [ ] **Step 6: Typecheck a build**

Run: `cd frontend-web && npx tsc -b`
Expected: bez chyb.

Run: `cd frontend-web && npm run build`
Expected: build projde.

- [ ] **Step 7: Commit**

```bash
git add frontend-web/src/types.ts frontend-web/src/api/fve.ts frontend-web/src/components/fve/FveAnalysisForm.tsx
git commit -m "feat(fve-web): vyber z vice geocode vysledku v karte Umisteni (bod 5)"
```

---

### Task 7: Závěrečné ověření

**Files:**
- Žádné zdrojové změny — jen ověření.

**Interfaces:**
- Consumes: vše z Tasků 1–6.
- Produces: ověřený stav pro nasazení.

- [ ] **Step 1: Celá testovací sada**

Run: `./venv/bin/python -m pytest tests/reportgen -q`
Expected: PASS — 154 původních + nové (defaulty, pv_calculator, geocoder, optimum).

- [ ] **Step 2: Frontend typecheck a build**

Run: `cd frontend-web && npx tsc -b && npm run build`
Expected: bez chyb.

- [ ] **Step 3: Změř produkci pro Ústí a porovnej s očekáváním**

Run z kořene repa (cache obsahuje Ústí → offline):

```bash
./venv/bin/python -c "
import sys; sys.path.insert(0,'backend/app'); sys.path.insert(0,'backend')
from pv_calculator import fetch_pvgis_tmy_data, get_pv_production, get_optimal_pv_production
w = fetch_pvgis_tmy_data(50.6607, 14.03227)
_, actual = get_pv_production(50.6607, 14.03227, 35, 180, 10.0, weather_data=w)
opt = get_optimal_pv_production(50.6607, 14.03227, 10.0, winter_loss_factor=10.0, weather_data=w)
print('actual  kWh/kWp:', round(actual/10, 1))
print('optimal kWh/kWp:', round(opt/10, 1))
print('performance %   :', round(actual/opt*100, 1))
"
```

Expected: `performance %` < 100. `actual kWh/kWp` klesne proti stavu před teplotní ztrátou (předpoklad designu: z ~1125 na ~1070). **Ruční ověření proti PVGIS SARAH3** pro tytéž souřadnice a sklon — potvrdí/vyvrátí dvojí započtení teploty v `system_loss_factor`.

- [ ] **Step 4: Ověření v prohlížeči (playwright, aserce na DOM, ne screenshoty)**

Backend 8051, web 3100. Přihlášení: `admin@antelon.local` / `Admin123!`.

1. Nová FVE analýza → pole Zeměpisná šířka/délka (pokročilé) ukazují `50.6607` a `14.03227`.
2. Karta Umístění: zadat „Telnice" → po hledání se objeví **≥ 1 tlačítko** s `display_name` a souřadnicemi.
3. Klik na tlačítko → pole latitude/longitude se nastaví na souřadnice varianty a tlačítko je zvýrazněné.
4. Zadání nesmyslu (např. `qzxwvu12345`) → text „Nebylo nalezeno žádné místo pro …".
5. Nápověda „Hledá se obec, ne ulice" už v kartě není.
6. Během hledání je tlačítko *Vyhledat souřadnice* `disabled` (v DOM atribut `disabled`).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: zaverecne overeni produkce a geocoderu"
```

---

## Self-review

### Pokrytí spec (kapitola 8)

| Bod spec | Kde v plánu |
|---|---|
| 8.1 Výchozí GPS Ústí na 8 místech | Task 1 (kroky 4–10) + kontrola krok 11 |
| 8.1 `verify_tmy*.py` neměnit | Global Constraints + krok 11 (grep) |
| 8.1 `test_fve_analysis.py:33` → Ústí | Task 1 krok 1 |
| Test defaultů (parsování `.ts`) | Task 1 krok 2 (`test_fve_defaults.py`) |
| 8.2 `apply_temperature_derate`, konstanta, před `system_loss_factor` | Task 2 kroky 3–4 |
| 8.2 test čisté funkce | Task 2 krok 1 (`test_apply_temperature_derate_formula`) |
| 8.3 sken sklon 10–70° po 5°, azimut 180 | Task 3 krok 3 |
| 8.3 propustit `winter_loss_factor` | Task 3 kroky 3–4 |
| 8.3 nikdy > 100 % | Task 3 testy (`test_production_performance_never_exceeds_100_pct`) |
| 8.4 Nominatim `search(limit=6)`, hlavičky, timeout, cache | Task 4 |
| 8.4 `get_coordinates` zrušit | Task 4 (přepis) + Task 5 (jediný volající) |
| Kontrakt 200 + `results`, 400 prázdný | Task 5 |
| 8.4 frontend `FveGeocodeResult[]`, tlačítka, nápověda, disabled | Task 6 |
| 10.2 přepsat geocode testy (200/prázdný/Ústí) | Task 1, Task 5 |
| Unit test geocode s mockem | Task 4 |
| Živé geocode testy zůstávají | Task 5 krok 1 |

### Placeholdery

Žádné `TODO`, `...` ani „implementuj později". Každý krok má konkrétní kód nebo příkaz. Jediné `...` je v ukázce parsovacího regexu (součást Python kódu), ne placeholder.

### Konzistence typů

Přesné řetězce: `geocoder.search` → `{"lat", "lon", "display_name"}`; endpoint mapuje na `{"latitude", "longitude", "display_name"}`; frontend `FveGeocodeResult` má `latitude/longitude/display_name`. `get_optimal_pv_production` nově přijímá `winter_loss_factor=None`; `load_production_data` ho předává. `apply_temperature_derate(production, cell_temp, coeff)` vrací tentýž tvar (Series/skalár). `_CACHE` je veřejně přístupný pro mock testy (`geocoder._CACHE.clear()`).

### Review Focus (rekapitulace)

1. **Shoda defaultů na osmi místech:** parity test odhalí drift; plán záměrně sjednocuje `grid_export_limit_kw` na 10.0. Ověření krokem 11 (grep) a krokem 12.
2. **Teplotní ztráta před `system_loss_factor` a v reálu i optimu:** test `temp_air=5` vs `45`; optimum volá tutéž funkci.
3. **Optimum ≤ 100 %:** sken zahrnuje 35°, `winter_loss_factor` propuštěn; test poměru.
4. **Nominatim kontrakt + hlavičky + cache:** unit test s mockem i živé testy.
5. **Frontend picker:** `FveGeocodeResult[]`, tlačítka, zvýraznění, odstraněná nápověda, disabled.

### Testy, které plán přidává / přepisuje

- Nové: `test_fve_defaults.py` (shoda defaultů + GPS Ústí), `test_pv_calculator.py` (teplotní derate, optimum), `test_geocoder.py` (Nominatim mock).
- Přepsané: `test_fve_analysis.py:33` → Ústí; `test_fve_analysis.py` + poměr ≤ 100 %; `test_fve_api.py` geocode testy → 200 + `results`.