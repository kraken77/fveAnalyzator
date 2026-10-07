# PDF a ekonomika FVE analýzy — implementační plán

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Doplnit do PDF energetické analýzy sekci **Ekonomická analýza**, **Přílohy A–D**, investiční graf a tabulku složení investice; zajistit, že PDF funguje i v kontejneru bez Chrome (doinstalovat Chrome pro kaleido), a protáhnout investici z ceníku materiálů (`compute_investment_cost`) až do frontendu.

**Architecture:** `reporting.py` se rozdělí na `_build_context(data, economic=None)` (čisté sestavení Jinja kontextu, včetně grafů přes `plotly.io.to_image`) a `generate_energy_report(data, economic=None)` (jen `template.render` + `HTML(...).write_pdf()`). Endpoint `/fve-analysis/report/energy` přijme `{"energy": ..., "economic": ...}`. `run_economic_analysis` nově vrátí `investment_cost` (z `compute_investment_cost`, plán 2) a `investment_breakdown` (snímek `fve_materials`). Šablona se přerovná a přílohy se vysází na vlastní stránky přes `break-before: page`. Frontend dopočítá ekonomiku před exportem a předá `params` do výsledků.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, Plotly 6.5.0 + kaleido (headless Chrome), WeasyPrint 67.0, pytest; React + TypeScript (Vite).

**Spec:** `docs/superpowers/specs/2026-10-06-fve-analyza-opravy-a-cenik-design.md` (kapitola 7, body 7.1–7.8; testy v 10.1)

## Global Constraints

- **Závislost na plánu 2:** Tento plán **používá** `backend/app/reportgen/materials_service.py::compute_investment_cost(params)` a snímek `fve_materials` v `params`. Pokud plán `docs/superpowers/plans/2026-10-06-2-cenik-materialu.md` ještě není hotový, **aplikuj nejdřív jeho** — jinak Task 2 spadne na `ImportError`.
- Backend se spouští z kořene repa, aby data padla do `data/`. Testy: `./venv/bin/python -m pytest tests/reportgen -q`.
- Host venv **má** WeasyPrint 67.0 a plotly 6.5.0, ale **nemá Chrome** → v testech se `plotly.io.to_image` **mockuje** (`unittest.mock.patch`). Produkční cesta Chrome mít bude díky Tasku 1.
- Šablona používá `break-before: page` (WeasyPrint 67 ho podporuje); `base.html` už má i starý `.page-break`.
- `compute_investment_cost` je jediný zdroj investice — fallback 350 000 Kč pro staré analýzy bez `fve_materials`.
- Commit messages v konvenci repa: `feat(...)`, `fix(...)`, `test(...)`, `chore(...)`.
- Vývoj běží v dev workspace, **ne** v produkci `/home/roman/apps/antelon-energy`.

## Review Focus

Než začneš, přečti si spec. Těchto pět stavů spec zmiňuje jen okrajově a je nejpravděpodobnější, že je někdo rozbije — každý má v úkolu vlastní test:

1. **Graf selže (chybí Chrome / kaleido spadne)** — `to_image` vyhodí výjimku, přesto se PDF musí vygenerovat a chyba musí být v logu s `type(e).__name__` (ne prázdná hláška, jak to dělal `print` s `str(e)` začínajícím dvěma `\n`). Task 3 + Task 5.
2. **Ekonomika chybí** — volající `router.py:518` a `ai_service.py:221` volají `generate_energy_report(result)` bez ekonomiky; PDF musí projít a sekci Ekonomika i přílohy A–D vynechat. Task 4.
3. **Všech 6 grafů** (5 z `data["plots"]` + investiční z `economic["plot"]`) se musí dostat do kontextu. Task 3 (mock `to_image`).
4. **Návratnost je `int` nebo `"> 20"`** (string) — `_format_number` na stringu spadne; šablona proto `payback` vypisuje bez číselného formátování. Task 3/Task 4.
5. **Snímek `fve_materials` nemá `name`/`rating`** (jsou volitelné) — tabulka složení investice se nesmí zhroutit; chybějící hodnota se zobrazí jako `-`. Task 3.

Zvlášť: **druhé stažení PDF po vyplnění ekonomiky** (Task 6) nesmí počítat ekonomiku dvakrát ani exportovat prázdnou sekci.

---

## Souborová mapa

| Soubor | Odpovědnost | Změna |
|---|---|---|
| `Dockerfile` | build image | 18 knihoven pro headless Chrome + `plotly_get_chrome -y` |
| `backend/app/fve_analysis.py` | ekonomický výpočet | `run_economic_analysis` vrací `investment_cost` + `investment_breakdown` |
| `backend/app/reporting.py` | kontext + PDF | `_build_context(data, economic)`, ekonomika, přílohy, logování grafů |
| `backend/templates/energy_report.html` | layout reportu | přerovnání, sekce Ekonomika, Přílohy A–D |
| `backend/app/reportgen/fve_router.py` | endpoint PDF | payload `{"energy","economic"}`, logování výjimky |
| `frontend-web/src/api/fve.ts` | API klient | `downloadEnergyPdf(energy, economic)` |
| `frontend-web/src/types.ts` | typy | `FveMaterialLine`, `FveEconomicResult.investment_*` |
| `frontend-web/src/components/fve/FveAnalysisResults.tsx` | výsledky | `params` prop, dopočet ekonomiky před PDF, metrika Investice |
| `frontend-web/src/pages/FveAnalysis.tsx` | stránka | předá `params` výsledkům |
| `frontend-web/src/pages/ProjectFveAnalysis.tsx` | stránka | předá `params` výsledkům |
| `tests/reportgen/test_report_pdf.py` | **nový** | kontext, ekonomika, grafy, odolnost, logování |
| `tests/reportgen/test_fve_analysis.py` | ekonomika | návratové pole investice |
| `tests/reportgen/test_fve_api.py` | endpoint PDF | nový payload v existujících testech |

---

### Task 1: Chrome pro kaleido v Dockerfile (7.1)

**Files:**
- Modify: `Dockerfile:9-17` (apt vrstva), `Dockerfile:20` (pip → přidat `plotly_get_chrome`)

**Interfaces:**
- Produces: image s headless Chrome; `plotly.io.to_image(fig)` funguje i v kontejneru. Nic pro ostatní tasky.

- [ ] **Step 1: Ověř, že Chrome v image chybí (padající kontrola)**

Run: `grep -q "plotly_get_chrome" Dockerfile; echo $?`
Expected: `1` (nenalezeno)

- [ ] **Step 2: Doplň systémové knihovny pro Chrome**

V `Dockerfile` nahraď vrstvu `RUN apt-get update && apt-get install -y \ ...` (řádky 9–17) celým blokem. 18 názvů je ověřeno pro Debian 13 (trixie) — kvůli 64bitovému `time_t` mají `libasound2`, `libatk1.0-0`, `libatk-bridge2.0-0`, `libatspi2.0-0` a `libcups2` příponu `t64`:

```dockerfile
# Install system dependencies required for WeasyPrint and headless Chrome
# (kaleido → plotly.io.to_image). Kontejner je Debian 13 (trixie), proto
# t64 varianty knihoven (64bit time_t): libasound2t64, libatk1.0-0t64,
# libatk-bridge2.0-0t64, libatspi2.0-0t64, libcups2t64.
# fonts-liberation je záměrně — bez písma kreslí Chrome místo popisků os
# prázdné čtverce.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    libnss3 libnspr4 libatk1.0-0t64 libatk-bridge2.0-0t64 libatspi2.0-0t64 \
    libcups2t64 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2t64 libx11-6 libxcb1 libxext6 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 3: Nainstaluj Chrome jako součást pip vrstvy**

`plotly_get_chrome` pochází z `kaleido` (je v `requirements.txt`), takže **musí** být až po `pip install`. Nahraď řádek 20:

```dockerfile
# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Headless Chrome pro kaleido — MUSÍ být po pip install (CLI pochází z kaleido).
RUN plotly_get_chrome -y
```

- [ ] **Step 4: Build image**

Run: `docker compose build backend`
Expected: build projde, v logu je stažení Chrome. Image naroste cca o 250–300 MB.

- [ ] **Step 5: Ověř Chrome v běžícím kontejneru**

Run:
```bash
docker compose run --rm --no-deps backend python -c "
import plotly.graph_objects as go, plotly.io as pio
fig = go.Figure(go.Bar(x=['a','b'], y=[1,2]))
png = pio.to_image(fig, format='png')
print('PNG bytes:', len(png), png[:4])
"
```
Expected: `PNG bytes: <čtyřciferné+> b'\x89PNG'`

- [ ] **Step 6: Commit**

```bash
git add Dockerfile
git commit -m "chore(docker): chrome pro kaleido + knihovny pro headless plotly (7.1)"
```

---

### Task 2: `run_economic_analysis` vrací investici ze ceníku (7.4)

**Files:**
- Modify: `backend/app/fve_analysis.py:470-515` (`run_economic_analysis`)
- Test: `tests/reportgen/test_fve_analysis.py` (přidat na konec)

**Interfaces:**
- Consumes: `reportgen.materials_service.compute_investment_cost(params) -> float` (plán 2); snímek `params["fve_materials"]: list[dict]` (plán 2)
- Produces: `run_economic_analysis(params) -> dict`, který nově obsahuje klíče:
  - `investment_cost: float`
  - `investment_breakdown: list[dict]` (řádky `fve_materials`; prázdný seznam, když snímek chybí)

- [ ] **Step 1: Napiš padající testy**

Přidej na konec `tests/reportgen/test_fve_analysis.py`:

```python
def test_economic_analysis_returns_investment_from_materials():
    """Investice se počítá ze snímku fve_materials, ne z tvrdých 350 000."""
    materials = [
        {"material_id": 1, "code": "PAN-550", "category": "panel",
         "rating": 550, "qty": 19, "unit_price": 2500.0, "line_total": 47500.0},
        {"material_id": 2, "code": "INV-10", "category": "inverter",
         "rating": 10, "qty": 1, "unit_price": 45000.0, "line_total": 45000.0},
    ]
    r = run_economic_analysis({
        "annual_savings": 25000.0, "fve_materials": materials, "years": 20,
    })
    assert r["investment_cost"] == 92500.0
    assert r["investment_breakdown"] == materials


def test_economic_analysis_legacy_investment_fallback():
    """Bez snímku (staré analýzy, explicitní zadání) platí fallback 350 000.

    Staré analýzy se záměrně nepřepočítávají — chování jako dřív.
    """
    r = run_economic_analysis({"annual_savings": 30000, "years": 20})
    assert r["investment_cost"] == 350000.0
    assert r["investment_breakdown"] == []
```

- [ ] **Step 2: Spusť testy — musí padat**

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_analysis.py -q -k "investment"`
Expected: FAIL — `KeyError: 'investment_cost'`

- [ ] **Step 3: Načti investici z materiálů**

V `backend/app/fve_analysis.py` nahraď začátek `run_economic_analysis` (řádky 470–483) takto — `_mod("reportgen.materials_service")` je stejný vzor, jakým modul načítá `app.analyzer`:

```python
def run_economic_analysis(params: Dict[str, Any]) -> Dict[str, Any]:
    """Analýza návratnosti investice (FVE vs S&P500 vs reinvestace).

    Investice pochází výhradně ze snímku `fve_materials` (plán 2:
    `compute_investment_cost`). Staré analýzy bez snímku mají fallback
    350 000 Kč — záměrně se nepřepočítávají.
    """

    def _p(name: str, default):
        return params[name] if name in params else default

    investment_cost = _mod("reportgen.materials_service").compute_investment_cost(params)
    investment_breakdown = list(params.get("fve_materials") or [])

    df = _mod("analyzer").calculate_investment_comparison(
        initial_investment_czk=investment_cost,
        annual_savings_czk=float(_p("annual_savings", 30000)),
        years=int(_p("years", 20)),
        sp500_return_pct=float(_p("sp500_return", 8)),
        inflation_pct=float(_p("inflation", 3)),
        discount_rate_pct=float(_p("discount_rate", 8)),
    )
```

- [ ] **Step 4: Vrať nová pole**

V `backend/app/fve_analysis.py` v návratovém dictu `run_economic_analysis` (řádky 502–515) přidej dva klíče mezi `"metrics"` a `"plot"`:

```python
    return {
        "metrics": {
            "payback_years": (int(payback_years) if pd.notna(payback_years)
                              else f"> {years}"),
            "discounted_payback_years": (int(dpp) if pd.notna(dpp)
                                        else f"> {years}"),
            "npv_czk": npv,
            "final_pv_gain_czk": final_pv_gain,
            "final_pv_reinvest_gain_czk": final_pv_reinvest_gain,
            "final_sp500_net_czk": final_sp500_net,
        },
        "investment_cost": investment_cost,
        "investment_breakdown": investment_breakdown,
        "plot": plot,
        "raw_data": df.to_dict(orient="records"),
    }
```

- [ ] **Step 4b: Rozšiř test ekonomického endpointu o nový klíč**

V `tests/reportgen/test_fve_api.py` najdi `test_economic_endpoint` (řádek 128) a za stávající `set(...)` assertion přidej:

```python
    body = r.json()
    assert body["investment_cost"] == 350000.0  # bez fve_materials = legacy
    assert body["investment_breakdown"] == []
```

- [ ] **Step 5: Spusť testy**

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_analysis.py tests/reportgen/test_fve_api.py -q -k "investment or economic"`
Expected: PASS

- [ ] **Step 6: Celá sada**

Run: `./venv/bin/python -m pytest tests/reportgen -q`
Expected: PASS. Kdyby nějaký test volal `run_economic_analysis` s `investment_cost` v parametrech a očekával 350 000, uprav ho na explicitní hodnotu (funguje dál — `compute_investment_cost` čte `investment_cost` jako druhou prioritu).

- [ ] **Step 7: Commit**

```bash
git add backend/app/fve_analysis.py tests/reportgen/test_fve_analysis.py tests/reportgen/test_fve_api.py
git commit -m "feat(fve): investice z ceniku materialu v ekonomicke analyze (7.4)"
```

---

### Task 3: Refaktor `generate_energy_report` na `_build_context` (7.8)

**Files:**
- Modify: `backend/app/reporting.py:30-197` (`generate_energy_report`)
- Test: `tests/reportgen/test_report_pdf.py` (nový)

**Interfaces:**
- Consumes: `data: dict` (výsledek `run_energy_analysis`), `economic: dict | None` (výsledek `run_economic_analysis`)
- Produces:
  - `ReportGenerator._build_context(self, data, economic=None) -> dict` — kompletní Jinja kontext včetně klíčů `chart_monthly_stats`, `chart_energy_treemap`, `chart_savings_treemap`, `chart_energy_pie`, `chart_savings_pie`, `chart_investment`, `economic`, `investment_cost_czk`, `econ_payback`, `econ_dpp`, `econ_npv`, `econ_final_pv_gain`, `econ_final_pv_reinvest_gain`, `econ_final_sp500_net`, `investment_breakdown`, `economic_year_rows`, `appliance_metrics`, `appliance_definitions`, `appliance_monthly_summary`, `monthly_summary`, `recommendations`
  - `ReportGenerator.generate_energy_report(self, data, economic=None) -> bytes`

- [ ] **Step 1: Napiš padající testy**

Vytvoř `tests/reportgen/test_report_pdf.py`:

```python
"""reporting.py — kontext PDF bez Chrome a bez WeasyPrint.

Host venv nemá Chrome, takže `plotly.io.to_image` (kaleido) se mockuje.
Pracuje se rovnou s Jinja kontextem / renderem šablony — WeasyPrint se
použije jen v testu odolnosti na konci souboru.
"""
import logging
import sys
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "backend") not in sys.path:
    sys.path.insert(0, str(REPO / "backend"))

from app.reporting import ReportGenerator  # noqa: E402


def _energy_data():
    return {
        "kwp": 10.0,
        "battery_capacity": 10.0,
        "annual_consumption_mwh": 5.0,
        "latitude": 50.6607,
        "longitude": 14.03227,
        "financial_balance": {
            "annual_savings_czk": 25000.0,
            "cost_without_pv_czk": 35000.0,
            "cost_with_pv_czk": 10000.0,
        },
        "energy_balance_kwh": {
            "total_consumption": 5000.0,
            "grid_import": 3000.0,
            "grid_export": 2000.0,
            "self_consumption": 2000.0,
        },
        "economic_balance_czk": {
            "cost_total_consumption": 35000.0,
            "cost_import": 21000.0,
            "revenue_export": 5000.0,
            "savings_self_consumption": 10000.0,
        },
        "plots": {key: "{}" for key in (
            "monthly_stats", "energy_treemap", "savings_treemap",
            "energy_pie", "savings_pie")},
        "recommendations": ["**Zvažte baterii**"],
        "appliance_metrics": {},
        "appliance_monthly_summary": [],
        "monthly_summary": [],
        "raw_data": [],
    }


def _economic():
    """Tvar odpovědi run_economic_analysis (Task 2) — včetně investice."""
    return {
        "metrics": {
            "payback_years": 8,
            "discounted_payback_years": 11,
            "npv_czk": 100000.0,
            "final_pv_gain_czk": 200000.0,
            "final_pv_reinvest_gain_czk": 250000.0,
            "final_sp500_net_czk": 150000.0,
        },
        "investment_cost": 300000.0,
        "investment_breakdown": [
            {"material_id": 1, "code": "PAN-550", "name": "Panel 550 Wp",
             "category": "panel", "rating": 550, "qty": 19,
             "unit_price": 2500.0, "line_total": 47500.0},
        ],
        "plot": "{}",
        "raw_data": [
            {"Year": 0, "PV_Cumulative_CashFlow": -300000.0,
             "PV_Reinvest_Net_Result": -300000.0, "PV_Cumulative_DCF": -300000.0,
             "SP500_Total_Value": 300000.0, "SP500_Net_Result": 0.0},
            {"Year": 1, "PV_Cumulative_CashFlow": -275000.0,
             "PV_Reinvest_Net_Result": -275000.0, "PV_Cumulative_DCF": -274000.0,
             "SP500_Total_Value": 324000.0, "SP500_Net_Result": 24000.0},
        ],
    }


def test_context_without_economic_has_no_economic_keys():
    """Bez ekonomiky se sekce i přílohy vynechají (chování jako dřív)."""
    ctx = ReportGenerator()._build_context(_energy_data())
    assert ctx["economic"] is None
    assert ctx["investment_cost_czk"] == "-"
    assert ctx["economic_year_rows"] == []
    assert ctx["investment_breakdown"] == []


def test_context_includes_investment_and_years():
    ctx = ReportGenerator()._build_context(_energy_data(), _economic())
    assert ctx["economic"] is not None
    assert ctx["investment_cost_czk"] == "300 000 Kč"
    assert ctx["econ_payback"] == 8
    assert ctx["investment_breakdown"][0]["name"] == "Panel 550 Wp"
    assert ctx["investment_breakdown"][0]["line_total"] == "47 500 Kč"
    assert len(ctx["economic_year_rows"]) == 2
    assert ctx["economic_year_rows"][1]["pv_cumulative_dcf"] != "-"


def test_all_six_charts_reach_context():
    """5 grafů z data["plots"] + investiční z economic["plot"]."""
    with patch("app.reporting.pio.to_image", return_value=b"PNG"):
        ctx = ReportGenerator()._build_context(_energy_data(), _economic())
    for key in ("chart_monthly_stats", "chart_energy_treemap",
                "chart_savings_treemap", "chart_energy_pie",
                "chart_savings_pie", "chart_investment"):
        assert ctx[key], f"graf {key} se do kontextu nedostal"


def test_breakdown_tolerates_missing_name_and_rating():
    """Snímek nemusí mít name/rating — tabulka se nesmí zhroutit."""
    eco = _economic()
    eco["investment_breakdown"] = [
        {"code": "INS-MONT", "category": "install", "qty": 1,
         "unit_price": 120000.0, "line_total": 120000.0},
    ]
    ctx = ReportGenerator()._build_context(_energy_data(), eco)
    row = ctx["investment_breakdown"][0]
    assert row["name"] == "INS-MONT"  # fallback na code
    assert row["rating"] == "-"
    assert row["qty"] == "1"


def test_report_survives_chart_failure():
    """Když to_image spadne, PDF se stejně vygeneruje (bez grafů)."""
    with patch("app.reporting.pio.to_image",
               side_effect=RuntimeError("no chrome")):
        pdf = ReportGenerator().generate_energy_report(_energy_data())
    assert pdf[:4] == b"%PDF"
```

- [ ] **Step 2: Spusť testy — musí padat**

Run: `./venv/bin/python -m pytest tests/reportgen/test_report_pdf.py -q`
Expected: FAIL — `AttributeError: 'ReportGenerator' object has no attribute '_build_context'`

- [ ] **Step 3: Extrahuj `_build_context` a ztenči `generate_energy_report`**

V `backend/app/reporting.py` nahraď celé tělo `generate_energy_report` (řádky 30–197) dvěma metodami. Ponech pro tuto chvíli `print` (Task 5 je nahradí `logging`). Odstraň duplikované `plots_json`/`charts_b64` a mrtvý blok s `investment_table` (dnešní řádky 172–193), který už šablona nepoužívá:

```python
    def _build_context(self, data, economic=None):
        """Postaví Jinja kontext pro energy_report.html.

        Oddělené od vykreslení (WeasyPrint), aby šel kontext testovat
        bez Chrome/kaleida — `plotly.io.to_image` se v testech mockuje.
        `economic` je volitelný; bez něj se ekonomická sekce i přílohy
        A–D vynechají (chování jako dřív).
        """
        plots_json = data.get("plots", {})
        charts_b64 = {}

        plot_mapping = {
            "monthly_stats": "monthly_stats",
            "energy_treemap": "energy_treemap",
            "savings_treemap": "savings_treemap",
            "energy_pie": "energy_pie",
            "savings_pie": "savings_pie",
        }
        for key, plot_id in plot_mapping.items():
            if plot_id in plots_json:
                try:
                    fig = pio.from_json(plots_json[plot_id])
                    fig.update_layout(template="plotly_white",
                                      width=800, height=450)
                    img_bytes = pio.to_image(fig, format="png")
                    charts_b64[key] = base64.b64encode(img_bytes).decode("utf-8")
                except Exception as e:
                    print(f"Error generating plot {key}: {e}")

        if economic and economic.get("plot"):
            try:
                fig = pio.from_json(economic["plot"])
                fig.update_layout(template="plotly_white", width=800, height=450)
                img_bytes = pio.to_image(fig, format="png")
                charts_b64["investment"] = base64.b64encode(img_bytes).decode("utf-8")
            except Exception as e:
                print(f"Error generating investment plot: {e}")

        context = {
            "generation_date": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "kwp": data.get("kwp", 0.0),
            "battery_capacity": data.get("battery_capacity", 0.0),
            "annual_consumption": data.get("annual_consumption_mwh", 0.0),
            "latitude": data.get("latitude", 50.6607),
            "longitude": data.get("longitude", 14.03227),

            "annual_savings_czk": self._format_czk(
                data.get("financial_balance", {}).get("annual_savings_czk")),
            "roi_years": self._format_number(
                data.get("investment_metrics", {}).get("roi_years"), 1),
            "self_consumption_kwh": self._format_kwh(
                data.get("energy_balance_kwh", {}).get("self_consumption")),
            "export_kwh": self._format_kwh(
                data.get("energy_balance_kwh", {}).get("grid_export")),

            "balance": {
                "total_consumption_kwh": self._format_kwh(
                    data.get("energy_balance_kwh", {}).get("total_consumption")),
                "total_cost_czk": self._format_czk(
                    data.get("economic_balance_czk", {}).get("cost_total_consumption")),
                "grid_import_kwh": self._format_kwh(
                    data.get("energy_balance_kwh", {}).get("grid_import")),
                "import_cost_czk": self._format_czk(
                    data.get("economic_balance_czk", {}).get("cost_import")),
                "grid_export_kwh": self._format_kwh(
                    data.get("energy_balance_kwh", {}).get("grid_export")),
                "export_revenue_czk": self._format_czk(
                    data.get("economic_balance_czk", {}).get("revenue_export")),
                "self_consumption_kwh": self._format_kwh(
                    data.get("energy_balance_kwh", {}).get("self_consumption")),
                "savings_self_ozk": self._format_czk(
                    data.get("economic_balance_czk", {}).get("savings_self_consumption")),
            },

            "appliance_metrics": [],
            "inflation_energy": data.get("investment_context", {}).get(
                "energy_inflation_rate", 2.0),
            "degradation": data.get("investment_context", {}).get(
                "panel_degradation_rate", 0.5),

            "chart_monthly_stats": charts_b64.get("monthly_stats"),
            "chart_energy_treemap": charts_b64.get("energy_treemap"),
            "chart_savings_treemap": charts_b64.get("savings_treemap"),
            "chart_energy_pie": charts_b64.get("energy_pie"),
            "chart_savings_pie": charts_b64.get("savings_pie"),
            "chart_investment": charts_b64.get("investment"),
            "recommendations": data.get("recommendations", []),
            "monthly_summary": data.get("monthly_summary", []),
            "appliance_monthly_summary": data.get("appliance_monthly_summary", []),
        }

        # Process Appliance Metrics
        if "appliance_metrics" in data:
            for name, metrics in data["appliance_metrics"].items():
                total = metrics.get("total_kWh", 0)
                fve = metrics.get("fve_kWh", 0)
                grid = metrics.get("grid_kWh", 0)
                grid_cost = metrics.get("grid_cost_czk", 0)
                hours = metrics.get("operating_hours", 0)
                coverage = (fve / total * 100) if total > 0 else 0
                profile = self.appliance_manager.get_appliance_profile(name)
                description = profile.get("description", "") if profile else ""

                context["appliance_metrics"].append({
                    "name": name,
                    "description": description,
                    "total_kwh": self._format_kwh(total),
                    "fve_kwh": self._format_kwh(fve),
                    "grid_kwh": self._format_kwh(grid),
                    "grid_cost_czk": self._format_czk(grid_cost),
                    "operating_hours": hours,
                    "coverage_pct": self._format_number(coverage, 1),
                    "savings_czk": self._format_czk(metrics.get("savings_czk")),
                })

        # Appliance Definitions / Configuration Details
        appliance_definitions = []
        if "appliance_metrics" in data:
            active_apps = [k for k in data["appliance_metrics"].keys()
                           if k not in ["Základní chod", "CELKEM"]]
            for app in sorted(active_apps):
                profile = self.appliance_manager.get_appliance_profile(app)
                if profile:
                    logic_desc = profile.get("description", "")
                    if profile.get("seasonal", False):
                        logic_desc += f" (Sezónní: {profile.get('seasonal_months', [])})"
                    if profile.get("type") == "EV":
                        logic_desc += (f" | Strategie: {profile.get('charging_strategy', 'weekly')}"
                                       f" | Nabití: {profile.get('charge_kwh', 0)} kWh")
                    elif "daily_hours" in profile:
                        logic_desc += f" | Provoz: {profile['daily_hours']} h/den"

                    appliance_definitions.append({
                        "name": app,
                        "power": f"{profile.get('power_kW', 0)} kW",
                        "type": profile.get("type", "Standard"),
                        "description": logic_desc,
                    })
        context["appliance_definitions"] = appliance_definitions

        # Ekonomická část (nepovinná)
        econ = economic or {}
        metrics = econ.get("metrics", {})
        context["economic"] = economic
        context["investment_cost_czk"] = self._format_czk(econ.get("investment_cost"))
        context["econ_payback"] = metrics.get("payback_years")
        context["econ_dpp"] = metrics.get("discounted_payback_years")
        context["econ_npv"] = self._format_czk(metrics.get("npv_czk"))
        context["econ_final_pv_gain"] = self._format_czk(metrics.get("final_pv_gain_czk"))
        context["econ_final_pv_reinvest_gain"] = self._format_czk(
            metrics.get("final_pv_reinvest_gain_czk"))
        context["econ_final_sp500_net"] = self._format_czk(
            metrics.get("final_sp500_net_czk"))
        context["investment_breakdown"] = [
            {
                "name": row.get("name") or row.get("code") or "-",
                "rating": (self._format_number(row.get("rating"), 0)
                           if row.get("rating") is not None else "-"),
                "qty": (self._format_number(row.get("qty"), 0)
                        if row.get("qty") is not None else "-"),
                "unit_price": self._format_czk(row.get("unit_price")),
                "line_total": self._format_czk(row.get("line_total")),
            }
            for row in (econ.get("investment_breakdown") or [])
        ]
        context["economic_year_rows"] = [
            {
                "year": row.get("Year"),
                "pv_cumulative_cashflow": self._format_czk(
                    row.get("PV_Cumulative_CashFlow")),
                "pv_reinvest_net_result": self._format_czk(
                    row.get("PV_Reinvest_Net_Result")),
                "pv_cumulative_dcf": self._format_czk(row.get("PV_Cumulative_DCF")),
                "sp500_total_value": self._format_czk(row.get("SP500_Total_Value")),
                "sp500_net_result": self._format_czk(row.get("SP500_Net_Result")),
            }
            for row in (econ.get("raw_data") or [])
        ]
        return context

    def generate_energy_report(self, data, economic=None):
        """Generuje PDF energetické (+ ekonomické) analýzy.

        `economic` je volitelný — bez něj se vynechá sekce Ekonomická
        analýza i Přílohy A–D (chování jako dřív).
        """
        context = self._build_context(data, economic)
        template = self.env.get_template("energy_report.html")
        html_content = template.render(context)
        pdf_bytes = HTML(string=html_content).write_pdf()
        return pdf_bytes
```

- [ ] **Step 4: Spusť testy**

Run: `./venv/bin/python -m pytest tests/reportgen/test_report_pdf.py -q`
Expected: PASS (5 testů)

- [ ] **Step 5: Regresní testy reportů**

Run: `./venv/bin/python -m pytest tests/reportgen -q`
Expected: PASS. Pokud `test_ai.py` mockuje `generate_energy_report`, signatura s defaultním `economic=None` ho nerozbije.

- [ ] **Step 6: Commit**

```bash
git add backend/app/reporting.py tests/reportgen/test_report_pdf.py
git commit -m "refactor(reporting): _build_context oddeleny od vykresleni (7.8)"
```

---

### Task 4: Šablona — pořadí, Ekonomická analýza, Přílohy A–D (7.5)

**Files:**
- Modify: `backend/templates/energy_report.html` (celý soubor)
- Test: `tests/reportgen/test_report_pdf.py` (přidat)

**Interfaces:**
- Consumes: kontext z Tasku 3 (`economic`, `investment_cost_czk`, `chart_investment`, `investment_breakdown`, `economic_year_rows`)
- Produces: HTML/PDF s texty „Ekonomická analýza", „Příloha A"–„Příloha D".

- [ ] **Step 1: Napiš padající testy**

Přidej na konec `tests/reportgen/test_report_pdf.py`:

```python
def _render(data, economic=None):
    """Postaví kontext a vyrenderuje šablonu — bez WeasyPrint."""
    gen = ReportGenerator()
    with patch("app.reporting.pio.to_image", return_value=b"PNG"):
        ctx = gen._build_context(data, economic)
    return gen.env.get_template("energy_report.html").render(ctx)


def test_template_has_economic_section_and_appendices_when_economic():
    html = _render(_energy_data(), _economic())
    for text in ("Ekonomická analýza", "Příloha A", "Příloha B",
                 "Příloha C", "Příloha D", "Ekonomický plán",
                 "Složení investice", "300 000 Kč", "Panel 550 Wp"):
        assert text in html, f"v PDF chybí: {text}"


def test_template_omits_economic_section_without_economic():
    html = _render(_energy_data(), None)
    for text in ("Ekonomická analýza", "Příloha A", "Příloha B",
                 "Příloha C", "Příloha D"):
        assert text not in html, f"bez ekonomiky nemá být v PDF: {text}"


def test_appendix_headings_break_to_new_page():
    """Přílohy musí začínat na vlastní stránce (WeasyPrint break-before)."""
    html = _render(_energy_data(), _economic())
    assert html.count("break-before: page") >= 4
```

- [ ] **Step 2: Spusť testy — musí padat**

Run: `./venv/bin/python -m pytest tests/reportgen/test_report_pdf.py -q -k "template or appendix"`
Expected: FAIL — `Ekonomická analýza` v HTML není.

- [ ] **Step 3: Nahraď šablonu**

Přepiš celý `backend/templates/energy_report.html`. Hlavní část v pořadí: Souhrnné výsledky → Vstupní parametry → Měsíční graf → Energetická bilance (+4 grafy) → Měsíční bilance → Doporučení → **Ekonomická analýza**. Pak **Přílohy A–D** v blocích `{% if economic %}`, každá s `break-before: page`:

```html
{% extends "base.html" %}

{% block title %}Energetický Report{% endblock %}
{% block report_title %}Energetická a Ekonomická Analýza{% endblock %}

{% block content %}

<!-- 1. Summary Section -->
<div class="summary-box">
    <h2>Souhrnné Výsledky</h2>
    <div class="metric">
        <span class="metric-label">Roční úspora</span>
        <span class="metric-value">{{ annual_savings_czk }}</span>
    </div>
    <div class="metric">
        <span class="metric-label">Vlastní spotřeba FVE</span>
        <span class="metric-value">{{ self_consumption_kwh }} kWh</span>
    </div>
    <div class="metric">
        <span class="metric-label">Export do sítě</span>
        <span class="metric-value">{{ export_kwh }} kWh</span>
    </div>
</div>

<!-- 2. Parameters Section -->
<h2>Vstupní Parametry</h2>
<table>
    <tr><th>Parametr</th><th>Hodnota</th></tr>
    <tr><td>Výkon FVE</td><td>{{ kwp }} kWp</td></tr>
    <tr><td>Kapacita Baterie</td><td>{{ battery_capacity }} kWh</td></tr>
    <tr><td>Roční Spotřeba</td><td>{{ annual_consumption }} MWh</td></tr>
    <tr><td>Lokalita (Lat/Lon)</td><td>{{ latitude }} / {{ longitude }}</td></tr>
</table>

<!-- 3. Monthly Stats Chart -->
{% if chart_monthly_stats %}
<div class="chart-container">
    <h3>Měsíční Statistika Výroby a Spotřeby</h3>
    <img src="data:image/png;base64,{{ chart_monthly_stats }}" class="chart-img">
</div>
{% endif %}

<!-- 4. Energy Balance Section -->
<h2>Energetická Bilance</h2>
<table>
    <thead>
        <tr>
            <th>Položka</th>
            <th class="text-right">Energie (kWh)</th>
            <th class="text-right">Cena (Kč)</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>Celková spotřeba</td>
            <td class="text-right">{{ balance.total_consumption_kwh }}</td>
            <td class="text-right">{{ balance.total_cost_czk }}</td>
        </tr>
        <tr>
            <td>Nákup ze sítě</td>
            <td class="text-right">{{ balance.grid_import_kwh }}</td>
            <td class="text-right">{{ balance.import_cost_czk }}</td>
        </tr>
        <tr>
            <td>Export do sítě</td>
            <td class="text-right">{{ balance.grid_export_kwh }}</td>
            <td class="text-right">{{ balance.export_revenue_czk }}</td>
        </tr>
        <tr class="highlight">
            <td><strong>Úspora z vlastní spotřeby</strong></td>
            <td class="text-right"><strong>{{ balance.self_consumption_kwh }}</strong></td>
            <td class="text-right"><strong>{{ balance.savings_self_ozk }}</strong></td>
        </tr>
    </tbody>
</table>

<div style="display: table; width: 100%; margin-top: 20px;">
    <div style="display: table-row;">
        <div style="display: table-cell; width: 50%; padding-right: 10px;">
            <h3 style="text-align: center;">Využití Výroby (Treemap)</h3>
            {% if chart_energy_treemap %}
            <div class="chart-container">
                <img src="data:image/png;base64,{{ chart_energy_treemap }}" class="chart-img">
            </div>
            {% endif %}
        </div>
        <div style="display: table-cell; width: 50%; padding-left: 10px;">
            <h3 style="text-align: center;">Využití Výroby (Podíl)</h3>
            {% if chart_energy_pie %}
            <div class="chart-container">
                <img src="data:image/png;base64,{{ chart_energy_pie }}" class="chart-img">
            </div>
            {% endif %}
        </div>
    </div>
</div>

<div style="display: table; width: 100%; margin-top: 20px;">
    <div style="display: table-row;">
        <div style="display: table-cell; width: 50%; padding-right: 10px;">
            <h3 style="text-align: center;">Využití Výroby — Úspory (Treemap)</h3>
            {% if chart_savings_treemap %}
            <div class="chart-container">
                <img src="data:image/png;base64,{{ chart_savings_treemap }}" class="chart-img">
            </div>
            {% endif %}
        </div>
        <div style="display: table-cell; width: 50%; padding-left: 10px;">
            <h3 style="text-align: center;">Úspory (Podíl)</h3>
            {% if chart_savings_pie %}
            <div class="chart-container">
                <img src="data:image/png;base64,{{ chart_savings_pie }}" class="chart-img">
            </div>
            {% endif %}
        </div>
    </div>
</div>

<!-- 5. Monthly Summary -->
{% if monthly_summary %}
<h2>Měsíční Bilance</h2>
<table style="font-size: 0.85em;">
    <thead>
        <tr>
            <th>Měsíc</th>
            <th class="text-right">Výroba (kWh)</th>
            <th class="text-right">Spotřeba (kWh)</th>
            <th class="text-right">Vlastní Spotř. (kWh)</th>
            <th class="text-right">Export (kWh)</th>
            <th class="text-right">Import (kWh)</th>
            <th class="text-right">Úspora (Kč)</th>
        </tr>
    </thead>
    <tbody>
        {% for row in monthly_summary %}
        <tr>
            <td>{{ row.month }}</td>
            <td class="text-right">{{ row.production_kwh|round(1) }}</td>
            <td class="text-right">{{ row.consumption_kwh|round(1) }}</td>
            <td class="text-right">{{ row.self_consumption_kwh|round(1) }}</td>
            <td class="text-right">{{ row.export_kwh|round(1) }}</td>
            <td class="text-right">{{ row.import_kwh|round(1) }}</td>
            <td class="text-right">{{ row.savings_czk|round(0) }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endif %}

<!-- 6. Recommendations Section -->
{% if recommendations %}
<div style="page-break-before: always;"></div>
<h2>Doporučené strategie a scénáře</h2>
<div class="recommendations">
    {% for rec in recommendations %}
    <div style="margin-bottom: 15px; padding: 10px; background-color: #f9f9f9; border-left: 4px solid #2ecc71;">
        {{ rec|replace('**', '<strong>')|replace('**', '</strong>')|safe }}
    </div>
    {% endfor %}
</div>
{% endif %}

<!-- 7. Ekonomická analýza -->
{% if economic %}
<div style="break-before: page;"></div>
<h2>Ekonomická analýza</h2>
<table>
    <thead>
        <tr><th>Metrika</th><th class="text-right">Hodnota</th></tr>
    </thead>
    <tbody>
        <tr><td>Investice</td><td class="text-right">{{ investment_cost_czk }}</td></tr>
        <tr><td>Návratnost</td><td class="text-right">{{ econ_payback }} let</td></tr>
        <tr><td>Diskontovaná návratnost</td><td class="text-right">{{ econ_dpp }} let</td></tr>
        <tr><td>Čistá současná hodnota (NPV)</td><td class="text-right">{{ econ_npv }}</td></tr>
        <tr><td>Výnos FVE</td><td class="text-right">{{ econ_final_pv_gain }}</td></tr>
        <tr><td>Výnos FVE s reinvesticí</td><td class="text-right">{{ econ_final_pv_reinvest_gain }}</td></tr>
        <tr><td>Výnos S&amp;P500 (netto)</td><td class="text-right">{{ econ_final_sp500_net }}</td></tr>
    </tbody>
</table>

{% if chart_investment %}
<div class="chart-container">
    <h3>Investice vs S&amp;P500</h3>
    <img src="data:image/png;base64,{{ chart_investment }}" class="chart-img">
</div>
{% endif %}

<h3>Složení investice</h3>
<table style="font-size: 0.85em;">
    <thead>
        <tr>
            <th>Komponenta</th>
            <th class="text-right">Výkon</th>
            <th class="text-right">Počet</th>
            <th class="text-right">Cena/ks</th>
            <th class="text-right">Celkem</th>
        </tr>
    </thead>
    <tbody>
        {% for row in investment_breakdown %}
        <tr>
            <td>{{ row.name }}</td>
            <td class="text-right">{{ row.rating }}</td>
            <td class="text-right">{{ row.qty }}</td>
            <td class="text-right">{{ row.unit_price }}</td>
            <td class="text-right">{{ row.line_total }}</td>
        </tr>
        {% endfor %}
        <tr class="highlight">
            <td colspan="4"><strong>CELKEM</strong></td>
            <td class="text-right"><strong>{{ investment_cost_czk }}</strong></td>
        </tr>
    </tbody>
</table>

<!-- Příloha A -->
<h2 style="break-before: page;">Příloha A — Detail Spotřebičů (ročně)</h2>
{% if appliance_metrics %}
<table style="font-size: 0.75em;">
    <thead>
        <tr>
            <th>Spotřebič</th>
            <th class="text-right">Úspora (Kč)</th>
            <th class="text-right">Cena ze sítě (Kč)</th>
            <th class="text-right">Z FVE (kWh)</th>
            <th class="text-right">Ze sítě (kWh)</th>
            <th class="text-right">Celkem (kWh)</th>
            <th class="text-right">Pokrytí (%)</th>
            <th class="text-right">Provoz (h/r)</th>
        </tr>
    </thead>
    <tbody>
        {% for app in appliance_metrics %}
        <tr {% if app.name=='CELKEM' %}style="background-color: #e9ecef; font-weight: bold;" {% elif app.name=='Základní chod' %}style="background-color: #f1f1f1;" {% endif %}>
            <td><strong>{{ app.name }}</strong><br /><small>{{ app.description if app.description else '' }}</small></td>
            <td class="text-right">{{ app.savings_czk }}</td>
            <td class="text-right">{{ app.grid_cost_czk }}</td>
            <td class="text-right">{{ app.fve_kwh }}</td>
            <td class="text-right">{{ app.grid_kwh }}</td>
            <td class="text-right">{{ app.total_kwh }}</td>
            <td class="text-right">{{ app.coverage_pct }}%</td>
            <td class="text-right">{{ app.operating_hours }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endif %}

<!-- Příloha B -->
<h2 style="break-before: page;">Příloha B — Měsíční bilance spotřebičů (kWh)</h2>
{% if appliance_monthly_summary %}
<table style="font-size: 0.7em;">
    <thead>
        <tr>
            <th>Měsíc</th>
            <th>Spotřebič</th>
            <th class="text-right">Úspora (Kč)</th>
            <th class="text-right">Cena ze sítě (Kč)</th>
            <th class="text-right">Z FVE (kWh)</th>
            <th class="text-right">Ze sítě (kWh)</th>
            <th class="text-right">Celkem (kWh)</th>
            <th class="text-right">Pokrytí (%)</th>
            <th class="text-right">Provoz (h/m)</th>
        </tr>
    </thead>
    <tbody>
        {% for row in appliance_monthly_summary %}
        <tr {% if row.appliance=='CELKEM' %}style="background-color: #e9ecef; font-weight: bold;" {% elif row.appliance=='Základní chod' %}style="background-color: #f9f9f9;" {% endif %}>
            <td>{{ row.month }}</td>
            <td><strong>{{ row.appliance }}</strong></td>
            <td class="text-right">{{ row.savings_czk|round(1) }}</td>
            <td class="text-right">{{ row.grid_cost_czk|round(1) }}</td>
            <td class="text-right">{{ row.fve_kWh|round(1) }}</td>
            <td class="text-right">{{ row.grid_kWh|round(1) }}</td>
            <td class="text-right">{{ row.total_kWh|round(1) }}</td>
            <td class="text-right">{{ row.coverage_pct|round(1) }}%</td>
            <td class="text-right">{{ row.operating_hours }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endif %}

<!-- Příloha C -->
<h2 style="break-before: page;">Příloha C — Detail nastavení spotřebičů</h2>
{% if appliance_definitions %}
<table style="font-size: 0.8em;">
    <thead>
        <tr>
            <th>Spotřebič</th>
            <th class="text-right">Příkon</th>
            <th>Typ</th>
            <th>Logika / Popis</th>
        </tr>
    </thead>
    <tbody>
        {% for app in appliance_definitions %}
        <tr>
            <td><strong>{{ app.name }}</strong></td>
            <td class="text-right">{{ app.power }}</td>
            <td>{{ app.type }}</td>
            <td>{{ app.description }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endif %}

<!-- Příloha D -->
<h2 style="break-before: page;">Příloha D — Ekonomický plán po jednotlivých letech</h2>
{% if economic_year_rows %}
<table style="font-size: 0.75em;">
    <thead>
        <tr>
            <th>Rok</th>
            <th class="text-right">Kumul. cash flow (Kč)</th>
            <th class="text-right">Reinvestice (Kč)</th>
            <th class="text-right">Diskont. kumul. CF (Kč)</th>
            <th class="text-right">S&amp;P500 hodnota (Kč)</th>
            <th class="text-right">S&amp;P500 netto (Kč)</th>
        </tr>
    </thead>
    <tbody>
        {% for row in economic_year_rows %}
        <tr>
            <td>{{ row.year }}</td>
            <td class="text-right">{{ row.pv_cumulative_cashflow }}</td>
            <td class="text-right">{{ row.pv_reinvest_net_result }}</td>
            <td class="text-right">{{ row.pv_cumulative_dcf }}</td>
            <td class="text-right">{{ row.sp500_total_value }}</td>
            <td class="text-right">{{ row.sp500_net_result }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endif %}
{% endif %}

{% endblock %}
```

- [ ] **Step 4: Spusť testy šablony**

Run: `./venv/bin/python -m pytest tests/reportgen/test_report_pdf.py -q`
Expected: PASS (8 testů)

- [ ] **Step 5: Celá sada**

Run: `./venv/bin/python -m pytest tests/reportgen -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/templates/energy_report.html tests/reportgen/test_report_pdf.py
git commit -m "feat(report): ekonomicka sekce a prilohy A-D v sablone (7.5)"
```

---

### Task 5: Payload `{"energy","economic"}` a logování chyb (7.3, 7.2)

**Files:**
- Modify: `backend/app/reportgen/fve_router.py:169-187` (endpoint), import `logging`
- Modify: `backend/app/reporting.py` (dva `print` v `_build_context` → `logger.error`)
- Modify: `tests/reportgen/test_fve_api.py:388-416` (nový payload v existujících testech)
- Test: `tests/reportgen/test_report_pdf.py` (přidat), `tests/reportgen/test_fve_api.py` (přidat)

**Interfaces:**
- Consumes: `ReportGenerator.generate_energy_report(data, economic=None)` (Task 3)
- Produces: endpoint `/fve-analysis/report/energy` přijímá `{"energy": {...}, "economic": {...} | null}`; loguje `type(e).__name__` na třech místech (2× `reporting.py`, 1× `fve_router.py`).

- [ ] **Step 1: Napiš padající testy logování**

Přidej na konec `tests/reportgen/test_report_pdf.py`:

```python
def test_chart_failure_is_logged_with_type(caplog):
    """Chyba grafu musí být v logu s typem výjimky, ne prázdná hláška.

    Před opravou se logovalo přes `print(f"...: {e}")`, a když `str(e)`
    začínalo dvěma `\\n`, v logu zůstala prázdná hláška.
    """
    with patch("app.reporting.pio.to_image",
               side_effect=RuntimeError("no chrome")):
        with caplog.at_level(logging.ERROR):
            ReportGenerator().generate_energy_report(_energy_data())
    assert "RuntimeError" in caplog.text
```

- [ ] **Step 2: Spusť test — musí padat**

Run: `./venv/bin/python -m pytest tests/reportgen/test_report_pdf.py::test_chart_failure_is_logged_with_type -q`
Expected: FAIL — `RuntimeError` v `caplog.text` není (loguje se přes `print`).

- [ ] **Step 3: Zapni logger v `reporting.py`**

V `backend/app/reporting.py` za `import os` (řádek 1) přidej:

```python
import logging

logger = logging.getLogger(__name__)
```

- [ ] **Step 4: Nahraď oba `print` v `_build_context` za `logger.error`**

První (pět grafů):
```python
                except Exception as e:
                    logger.error("Graf '%s' se nevykreslil: %s",
                                 key, type(e).__name__, exc_info=True)
```

Druhý (investiční graf):
```python
            except Exception as e:
                logger.error("Investiční graf se nevykreslil: %s",
                             type(e).__name__, exc_info=True)
```

- [ ] **Step 5: Spusť test logování**

Run: `./venv/bin/python -m pytest tests/reportgen/test_report_pdf.py -q`
Expected: PASS

- [ ] **Step 6: Napiš padající testy endpointu**

V `tests/reportgen/test_fve_api.py` uprav `test_energy_pdf_returns_pdf` (řádek 393) a `test_energy_pdf_customer_allowed` (řádek 413) na nový payload:

```python
    r = client.post("/api/v1/fve-analysis/report/energy",
                    json={"energy": result, "economic": None},
                    headers=_auth(admin_token))
```

a na konec souboru přidej:

```python
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
```

- [ ] **Step 7: Spusť endpoint testy — musí padat**

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_api.py -q -k "energy_pdf"`
Expected: FAIL — starý payload a 500 hláška bez typu.

- [ ] **Step 8: Přepiš endpoint v `fve_router.py`**

V `backend/app/reportgen/fve_router.py` za `import json` (řádek 8) přidej:

```python
import logging
```

a za `router = APIRouter(...)` (řádek 34):

```python
logger = logging.getLogger(__name__)
```

Nahraď celý endpoint (řádky 169–187):

```python
@router.post("/fve-analysis/report/energy")
def energy_pdf(payload: dict, user: User = Depends(ANY_ROLE)):
    """PDF energetické i ekonomické analýzy.

    Payload: {"energy": {...}, "economic": {...} | null}. Ekonomika je
    volitelná — když chybí, PDF sekci Ekonomická analýza i Přílohy A–D
    vynechá. Legacy /report/energy je bez /api/v1 a bez auth.
    """
    from app.reporting import ReportGenerator

    energy = (payload or {}).get("energy")
    economic = (payload or {}).get("economic")
    if not energy or "energy_balance_kwh" not in energy:
        raise HTTPException(400, "Chybí výsledek analýzy")
    try:
        pdf_bytes = ReportGenerator().generate_energy_report(energy, economic)
    except Exception as e:
        logger.exception("Generování PDF selhalo: %s", type(e).__name__)
        raise HTTPException(
            500, f"PDF se nepodařilo vygenerovat: {type(e).__name__}")
    fname = f"fve_energy_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"',
                 "X-Filename": fname},
    )
```

- [ ] **Step 9: Spusť testy**

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_api.py tests/reportgen/test_report_pdf.py -q`
Expected: PASS (`test_energy_pdf_handles_broken_payload` posílá `{}` → 400, pořád projde)

- [ ] **Step 10: Celá sada**

Run: `./venv/bin/python -m pytest tests/reportgen -q`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
git add backend/app/reportgen/fve_router.py backend/app/reporting.py tests/reportgen/test_fve_api.py tests/reportgen/test_report_pdf.py
git commit -m "feat(report): payload energy+economic a logovani chyb s typem (7.2, 7.3)"
```

---

### Task 6: Frontend — `params`, dopočet ekonomiky před PDF, metrika Investice (7.7)

**Files:**
- Modify: `frontend-web/src/api/fve.ts:48-49`
- Modify: `frontend-web/src/types.ts:309-320` (`FveEconomicResult`)
- Modify: `frontend-web/src/components/fve/FveAnalysisResults.tsx`
- Modify: `frontend-web/src/pages/FveAnalysis.tsx:148`
- Modify: `frontend-web/src/pages/ProjectFveAnalysis.tsx:148`

**Interfaces:**
- Consumes: `FveParams.fve_materials` (plán 2, volitelné v `Partial<FveParams>`), backend `investment_cost`
- Produces: `downloadEnergyPdf(energy: FveAnalysisResult, economic: FveEconomicResult | null)`

- [ ] **Step 1: Doplň typy**

V `frontend-web/src/types.ts` před `export interface FveEconomicResult` přidej:

```ts
export interface FveMaterialLine {
  material_id?: number;
  code?: string;
  name?: string;
  category?: string;
  rating?: number | null;
  unit?: string;
  qty?: number;
  unit_price?: number;
  line_total?: number;
}
```

a do `FveEconomicResult` za `metrics` (před `plot`):

```ts
  investment_cost: number;
  investment_breakdown: FveMaterialLine[];
```

- [ ] **Step 2: Přepiš API volání**

V `frontend-web/src/api/fve.ts` nahraď `downloadEnergyPdf` (řádky 47–49):

```ts
/** PDF jako blob — ne JSON, takže responseType: "blob".
 *  Ekonomika je volitelná; když chybí, PDF ji vynechá (chování jako dřív). */
export const downloadEnergyPdf = (
  energy: FveAnalysisResult,
  economic: FveEconomicResult | null,
) =>
  client.post(
    "/fve-analysis/report/energy",
    { energy, economic },
    { responseType: "blob" },
  );
```

- [ ] **Step 3: Přidej `params` prop do výsledků**

V `frontend-web/src/components/fve/FveAnalysisResults.tsx` uprav import typů (řádek 4) a signaturu (řádek 21):

```tsx
import type { FveAnalysisResult, FveEconomicResult, FveParams } from "../../types";
```

```tsx
export default function FveAnalysisResults(
  { result, params }: { result: FveAnalysisResult; params: Partial<FveParams> },
) {
```

- [ ] **Step 4: Pošli `params` v `loadEconomic`**

Nahraď tělo `loadEconomic` (řádky 27–39). Snímek `fve_materials` i zbytek parametrů jdou do ekonomiky; `annual_savings` má přednost z výsledku energie:

```tsx
  const loadEconomic = async () => {
    setEconLoading(true);
    setError("");
    try {
      setEconomic(await runEconomic({
        ...params,
        annual_savings: result.financial_balance.annual_savings_czk,
      }));
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Ekonomickou analýzu se nepodařilo spočítat");
    } finally {
      setEconLoading(false);
    }
  };
```

- [ ] **Step 5: Dopočítej ekonomiku v `downloadPdf`**

Nahraď tělo `downloadPdf` (řádky 41–59):

```tsx
  const downloadPdf = async () => {
    setPdfLoading(true);
    setError("");
    try {
      // PDF má mít ekonomickou sekci — když ještě není spočítaná, dodělej ji.
      let econ = economic;
      if (!econ) {
        econ = await runEconomic({
          ...params,
          annual_savings: result.financial_balance.annual_savings_czk,
        });
        setEconomic(econ);
      }
      const res = await downloadEnergyPdf(result, econ);
      const url = window.URL.createObjectURL(
        new Blob([res.data], { type: "application/pdf" }),
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = "Energeticka_analyza.pdf";
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(e?.response?.data?.detail || "PDF se nepodařilo stáhnout");
    } finally {
      setPdfLoading(false);
    }
  };
```

- [ ] **Step 6: Přidej metriku Investice**

V sekci ekonomiky (za řádek 157, `grid grid-cols-2 lg:grid-cols-3`) přidej jako první metriku:

```tsx
              <Metric label="Investice" value={economic.investment_cost} unit="Kč" />
```

- [ ] **Step 7: Před MVC `params` z obou stránek**

V `frontend-web/src/pages/FveAnalysis.tsx` (řádek 148) nahraď:

```tsx
      {tab === "results" && result && <FveAnalysisResults result={result} params={params} />}
```

V `frontend-web/src/pages/ProjectFveAnalysis.tsx` (řádek 148) nahraď:

```tsx
      {tab === "results" && result && <FveAnalysisResults result={result} params={params} />}
```

- [ ] **Step 8: Typecheck**

Run: `cd frontend-web && npx tsc -b`
Expected: bez chyb. Kdyby `params` na `FveAnalysisResult` neměl `fve_materials`, `Partial<FveParams>` to toleruje; typ se doplní v plánu 2.

- [ ] **Step 9: Commit**

```bash
git add frontend-web/src/api/fve.ts frontend-web/src/types.ts \
  frontend-web/src/components/fve/FveAnalysisResults.tsx \
  frontend-web/src/pages/FveAnalysis.tsx frontend-web/src/pages/ProjectFveAnalysis.tsx
git commit -m "feat(frontend): parametry do vysledku, investice a ekonomika v PDF (7.7)"
```

---

### Task 7: Závěrečné ověření

**Files:**
- Žádné změny kódu (pokud ověření neodhalí chybu).

**Interfaces:**
- Consumes: vše z Tasků 1–6
- Produces: ověřený stav pro nasazení.

- [ ] **Step 1: Celá backendová sada**

Run: `./venv/bin/python -m pytest tests/reportgen -q`
Expected: PASS (původní sada + nové testy z `test_report_pdf.py`)

- [ ] **Step 2: Frontend build**

Run: `cd frontend-web && npx tsc -b && npm run build`
Expected: bez chyb

- [ ] **Step 3: Docker image s Chrome**

Run: `docker compose build backend && docker compose up -d backend`
Expected: build projde, backend naběhne

- [ ] **Step 4: Ověření PDF v prohlížeči (playwright, aserce na DOM/text, ne screenshoty)**

Backend 8051, web 3100. Přihlášení `admin@antelon.local` / `Admin123!`.

1. Spustit FVE analýzu → karta Výsledky → **Spočítat návratnost investice** → objeví se metrika **Investice**.
2. **Stáhnout PDF** → stáhnout soubor → extrahovat text a ověřit, že obsahuje `Ekonomická analýza`, `Příloha A`, `Příloha D`, `Složení investice` a `CELKEM`.
3. **Stáhnout PDF bez předchozího dopočtu ekonomiky** (nová analýza, hned export) → PDF se stáhne a ekonomická sekce v něm je (frontend ekonomiku dopočítá sám).
4. Ověřit, že PDF má víc obrázků než dřív (6 grafů, když je ekonomika).
5. Bez ekonomiky (např. interní `router.py` generátor) → PDF se vygeneruje a sekce Ekonomika v něm není.

Pro extrakci textu PDF použij `PyPDF2` (je v `requirements.txt`):

```bash
python - <<'PY'
from PyPDF2 import PdfReader
r = PdfReader("stazene.pdf")
text = "\n".join(p.extract_text() or "" for p in r.pages)
for needle in ("Ekonomická analýza", "Příloha A", "Příloha D", "Složení investice"):
    assert needle in text, f"chybí: {needle}"
print("OK", len(r.pages), "stran")
PY
```

- [ ] **Step 5: Commit (jen pokud Step 1–4 vyžadovaly opravu)**

```bash
git add -A
git commit -m "chore(report): zaverecne overeni PDF a ekonomiky"
```

---

## Self-review

**Krytí spec (7.1–7.8):**
- 7.1 → Task 1 (18 knihoven + `plotly_get_chrome -y`).
- 7.2 → Task 5 (3 místa: 5 grafů + investiční graf v `reporting.py`, výjimka `energy_pdf` v `fve_router.py`), `type(e).__name__`.
- 7.3 → Task 5 (payload `{"energy","economic"}`, `generate_energy_report(data, economic=None)` z Tasku 3).
- 7.4 → Task 2 (`investment_cost` + `investment_breakdown`, `compute_investment_cost`).
- 7.5 → Task 4 (pořadí, sekce Ekonomika, Přílohy A–D, `break-before: page`, Příloha D se 6 sloupci z `economic.raw_data`).
- 7.6 → pouze **použití** `compute_investment_cost` (Task 2); implementace je plán 2.
- 7.7 → Task 6 (`params` prop z obou stránek, `loadEconomic`, `downloadPdf` dopočítá, metrika Investice).
- 7.8 → Task 3 (`_build_context` + `generate_energy_report`).
- Nový test `tests/reportgen/test_report_pdf.py` → Task 3–5 (kontext, ekonomika, 6 grafů, odolnost, logování).

**Placeholder scan:** žádné „TBD"/„TODO"/„similar to"; všechny kroky mají konkrétní kód nebo příkaz.

**Konsistence typů:** `_build_context(data, economic=None)` a `generate_energy_report(data, economic=None)` sedí mezi Tasky 3/4/5; kontextové klíče `chart_investment`, `investment_cost_czk`, `investment_breakdown`, `economic_year_rows` používané v Tasku 4 odpovídají tomu, co plní Task 3; `run_economic_analysis` v Tasku 2 vrací `investment_cost`/`investment_breakdown`, které čte Task 3 i Task 6 (`FveEconomicResult.investment_cost`). Sloupce Přílohy D (`PV_Cumulative_CashFlow`, `PV_Reinvest_Net_Result`, `PV_Cumulative_DCF`, `SP500_Total_Value`, `SP500_Net_Result`) odpovídají `analyzer.calculate_investment_comparison` (analyzer.py:329–338).

**Review Focus (5 řádků + testy):**
1. Selhání grafu → `test_report_survives_chart_failure` (Task 3) + `test_chart_failure_is_logged_with_type` + `test_energy_pdf_logs_exception_type` (Task 5).
2. Ekonomika chybí → `test_context_without_economic_has_no_economic_keys` + `test_template_omits_economic_section_without_economic` (Task 3/4).
3. Všech 6 grafů → `test_all_six_charts_reach_context` (Task 3).
- 4. Payback `int`/`"> 20"` → test kontextu `econ_payback == 8` (Task 3) + šablona vypisuje bez `_format_number`.
- 5. Chybějící `name`/`rating` ve snímku → `test_breakdown_tolerates_missing_name_and_rating` (Task 3).
- Navíc: dopočet ekonomiky před PDF → Task 6, krok 5 (a ověření Task 7, krok 4.3).