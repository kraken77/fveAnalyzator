# Report — varianty, výběr oddílů, vysvětlivky, úplné vstupní parametry — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rozšířit PDF FVE analýzy o dvě varianty (zákazník/firma), konfigurovatelný výběr a pořadí oddílů, vysvětlující text a úplný přehled vstupních parametrů.

**Architecture:** Registr oddílů (`report_sections.py`) je jediný zdroj pravdy. `ReportGenerator` skládá kontext a šablona `energy_report.html` se změní na obal, který v cyklu includuje partialy z `templates/energy_sections/`. Endpoint `report/energy` přijme `variant`/`sections`/`params`, vynutí variantu dle role a sanitizuje seznam oddílů. Frontend přidá modální výběr oddílů a dvě tlačítka dle role, volbu ukládá do `fve_params_json`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Jinja2, WeasyPrint, Plotly/kaleido; React + TypeScript + Vite; pytest; Playwright.

**Spec:** `docs/superpowers/specs/2026-10-09-report-varianty-a-vyber-oddilu-design.md`

## Global Constraints

- Bez změny DB schématu — volba se ukládá do existujícího `fve_params_json`.
- `generate_energy_report(data, economic=None, variant="company", sections=None, params=None)` — default se musí rovnat dnešnímu plnému reportu (legacy volající `ai_service.py:221`, `router.py:534` beze změny).
- Legacy cesty (bez varianty/sekcí) nesmí změnit výstup ani spadnout.
- Zákazník (role bez `admin`/`antelon`/`sales`) nikdy nedostane `variant="company"` — server variantu vynutí.
- Pevný základ (neodebratelné): `summary`, `economic_metrics`, `investment_composition`.
- Rám: `intro` vždy první, `glossary` vždy poslední.
- Oddíly s `needs_economic=True` se vynechají, když `economic is None` (žádný 500).
- Neznámé id v `sections` se ignorují, ne 500.
- Vstupní parametry: všechny smysluplné vstupy s jednotkami; vynechat `bom_mode`, `*_material_id`, `fve_materials`.
- Testy: `./venv/bin/python -m pytest tests/reportgen -q`; frontend gate `cd frontend-web && npx tsc -b && npm run build`.
- Necommitovat `data/reportgen.db.bak-*`, `data/*.db`, cache.

## Review Focus

- Oddíl s `needs_economic=True` požadovaný, ale `economic is None` → vynechá se, PDF se vygeneruje (nesmí 500).
- `sections` obsahuje neznámé id nebo chybí base id → sanitizace, žádný 500.
- Zákaznická role pošle `variant="company"` → server přepíše na `customer` (žádný interní rozpis).
- Prázdný/poškozený `params` → tabulka vstupů z backendových defaultů, nesmí spadnout.
- Base oddíl uvedený uprostřed/na konci klientem → zůstane ve svém (klientem daném) pořadí, ale je přítomen.
- Reorder ve frontendu s vypnutým oddílem → výstup obsahuje jen zapnuté, ve zvoleném pořadí.

---

### Task 1: Registr oddílů

**Files:**
- Create: `backend/app/reportgen/report_sections.py`
- Test: `tests/reportgen/test_report_sections.py`

**Interfaces:**
- Consumes: —
- Produces:
  - `Section` dataclass: `id: str, label: str, description: str, base: bool, needs_economic: bool, frame: str | None`
  - `SECTIONS: tuple[Section, ...]` (kanonické pořadí)
  - `BASE_IDS: tuple[str, ...]`, `FRAME_FIRST: tuple[str, ...]`, `FRAME_LAST: tuple[str, ...]`, `ALL_IDS: tuple[str, ...]`
  - `resolve_sections(requested: list[str] | None, *, has_economic: bool = True) -> list[str]`
  - `sections_metadata() -> list[dict]` (`id,label,description,base`)

- [ ] **Step 1: Write the failing test**

Create `tests/reportgen/test_report_sections.py`:

```python
"""Registr oddílů reportu — pořadí, základ, rám, filtr ekonomiky."""
from reportgen.report_sections import (
    ALL_IDS, BASE_IDS, FRAME_FIRST, FRAME_LAST, SECTIONS,
    resolve_sections, sections_metadata,
)


def test_canonical_order_ids_unique():
    ids = [s.id for s in SECTIONS]
    assert len(ids) == len(set(ids))
    assert ALL_IDS[0] == "intro"
    assert ALL_IDS[-1] == "glossary"


def test_default_returns_canonical_order():
    assert resolve_sections(None) == list(ALL_IDS)


def test_resolve_ignores_unknown_ids():
    assert resolve_sections(["summary", "neexistuje", "glossary"]) == [
        "intro", "summary", "glossary",
    ]


def test_resolve_forces_base_when_missing():
    out = resolve_sections(["glossary"])
    for b in BASE_IDS:
        assert b in out
    assert out[0] == "intro"
    assert out[-1] == "glossary"


def test_resolve_keeps_client_order_for_optional():
    out = resolve_sections(
        ["intro", "summary", "recommendations", "input_params",
         "economic_metrics", "investment_composition", "glossary"]
    )
    i = {name: pos for pos, name in enumerate(out)}
    assert i["recommendations"] < i["input_params"]


def test_resolve_drops_economic_sections_without_economic():
    out = resolve_sections(None, has_economic=False)
    assert "economic_metrics" not in out
    assert "investment_composition" not in out
    assert "appendix_d" not in out
    assert "summary" in out


def test_resolve_forces_frame_positions():
    out = resolve_sections(["summary", "glossary", "intro", "economic_metrics",
                            "investment_composition"])
    assert out[0] == "intro"
    assert out[-1] == "glossary"
    assert out.index("intro") == 0
    assert out.index("glossary") == len(out) - 1


def test_metadata_flags_base():
    by_id = {m["id"]: m for m in sections_metadata()}
    assert by_id["summary"]["base"] is True
    assert by_id["appendix_a"]["base"] is False
    assert by_id["summary"]["label"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/reportgen/test_report_sections.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'reportgen.report_sections'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/reportgen/report_sections.py`:

```python
"""Registr oddílů PDF reportu — jediný zdroj pravdy pro skládání dokumentu.

Kanonické pořadí `SECTIONS` je default. `resolve_sections` sanitizuje
požadavek klienta: ignoruje neznámé id, vždy přidá pevný základ a rám
(intro na začátek, slovník na konec) a zachová pořadí zbytku.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    id: str
    label: str
    description: str
    base: bool = False
    needs_economic: bool = False
    frame: str | None = None  # "first" | "last" | None


SECTIONS: tuple[Section, ...] = (
    Section("intro", "Jak číst tento report",
            "Úvod vysvětlující, co dokument obsahuje a jak ho číst.", frame="first"),
    Section("summary", "Souhrnné výsledky",
            "Hlavní čísla analýzy: roční úspora, vlastní spotřeba, export.", base=True),
    Section("input_params", "Vstupní parametry",
            "Přehled všech vstupů, ze kterých se počítalo."),
    Section("energy_balance", "Energetická bilance",
            "Roční tok energie a peněz mezi domácností a sítí."),
    Section("monthly_stats", "Měsíční statistika výroby a spotřeby",
            "Graf měsíční výroby a spotřeby."),
    Section("energy_charts", "Grafy (využití výroby a úspory)",
            "Kam se vyrobená energie a úspory rozdělily."),
    Section("monthly_summary", "Měsíční bilance",
            "Tabulka měsíčních toků energie a úspor."),
    Section("recommendations", "Doporučené strategie a scénáře",
            "Doporučení pro provoz a nastavení."),
    Section("economic_metrics", "Ekonomická analýza",
            "Návratnost, NPV a výnosy investice.", base=True, needs_economic=True),
    Section("investment_chart", "Investice vs S&P500",
            "Srovnání výnosu FVE a pasivního investování.", needs_economic=True),
    Section("investment_composition", "Složení investice",
            "Z čeho se investice skládá a kolik stojí.", base=True, needs_economic=True),
    Section("appendix_a", "Příloha A — Detail spotřebičů (ročně)",
            "Roční bilance po jednotlivých spotřebičích."),
    Section("appendix_b", "Příloha B — Měsíční bilance spotřebičů (kWh)",
            "Měsíční bilance po spotřebičích."),
    Section("appendix_c", "Příloha C — Detail nastavení spotřebičů",
            "Jak jsou spotřebiče nastavené."),
    Section("appendix_d", "Příloha D — Ekonomický plán po jednotlivých letech",
            "Roční ekonomický plán investice.", needs_economic=True),
    Section("glossary", "Slovníček pojmů",
            "Vysvětlení použitých pojmů.", frame="last"),
)

_BY_ID = {s.id: s for s in SECTIONS}
BASE_IDS: tuple[str, ...] = tuple(s.id for s in SECTIONS if s.base)
FRAME_FIRST: tuple[str, ...] = tuple(s.id for s in SECTIONS if s.frame == "first")
FRAME_LAST: tuple[str, ...] = tuple(s.id for s in SECTIONS if s.frame == "last")
ALL_IDS: tuple[str, ...] = tuple(s.id for s in SECTIONS)


def resolve_sections(requested: list[str] | None, *, has_economic: bool = True) -> list[str]:
    """Vrátí seřazený seznam id k vykreslení (sanitizovaný)."""
    if requested is None:
        ids = list(ALL_IDS)
    else:
        ids = [i for i in requested if i in _BY_ID]
        for s in SECTIONS:  # doplň chybějící pevný základ
            if s.base and s.id not in ids:
                ids.append(s.id)

    if not has_economic:
        ids = [i for i in ids if not _BY_ID[i].needs_economic]

    # rám: first odstranit a dát na začátek, last na konec
    ids = [i for i in ids if _BY_ID[i].frame != "first"]
    ids = [i for i in ids if _BY_ID[i].frame != "last"]
    ids = list(FRAME_FIRST) + ids + list(FRAME_LAST)

    seen: set[str] = set()
    out: list[str] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def sections_metadata() -> list[dict]:
    return [
        {"id": s.id, "label": s.label, "description": s.description, "base": s.base}
        for s in SECTIONS
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/reportgen/test_report_sections.py -q`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/reportgen/report_sections.py tests/reportgen/test_report_sections.py
git commit -m "feat(report): registr oddilu (zaklad, ram, filtr ekonomiky)"
```

---

### Task 2: Stavitel řádků vstupních parametrů

**Files:**
- Modify: `backend/app/reporting.py` (přidat metodu do `ReportGenerator`)
- Test: `tests/reportgen/test_report_pdf.py` (přidat testy na konec)

**Interfaces:**
- Consumes: `resolve_sections` z Tasku 1 (zatím nevyužito).
- Produces: `ReportGenerator._build_input_params(params: dict | None) -> list[dict]` (řádky `{"label","value"}`).

- [ ] **Step 1: Write the failing test**

Přidej na konec `tests/reportgen/test_report_pdf.py`:

```python
def test_input_params_rows_cover_all_meaningful_inputs():
    params = {
        "kwp": 10.0, "battery_capacity": 10.0, "annual_consumption_mwh": 5.0,
        "latitude": 50.6607, "longitude": 14.03227,
        "price_power": 3.0, "price_distribution": 2.0,
        "sell_price_scheme": "shared", "price_sell": 2.0,
        "shared_sell_price": 2.54, "spot_price_margin": 0.4,
        "surface_tilt": 35, "surface_azimuth": 180,
        "grid_export_limit_kw": 10.0, "system_loss_factor": 14.0,
        "winter_loss_factor": 10.0, "thermal_battery_capacity_kwh": 0.0,
        "thermal_battery_charge_power_kw": 2.0, "active_appliances": ["Bazén"],
        "bom_mode": "components", "panel_material_id": 1,
    }
    rows = ReportGenerator()._build_input_params(params)
    labels = {r["label"]: r["value"] for r in rows}
    assert "Cena silové energie" in labels
    assert "Cena distribuce" in labels
    assert labels["Schéma prodeje"] == "Sdílení"
    assert "Sdílení" in labels["Výkupní cena (sdílení)"]
    assert "2.54" in labels["Výkupní cena (sdílení)"]
    assert labels["Sklon střechy"] == "35°"
    assert labels["Limit exportu do sítě"] == "10.0 kW"
    assert labels["Aktivní spotřebiče"] == "Bazén"
    # interní/technické se neuvádí
    assert "bom_mode" not in " ".join(labels)
    assert all("material_id" not in lbl for lbl in labels)


def test_input_params_empty_params_use_backend_defaults():
    rows = ReportGenerator()._build_input_params(None)
    labels = {r["label"]: r["value"] for r in rows}
    assert labels["Instalovaný výkon"] == "10.0 kWp"
    assert labels["Výkupní cena"] == "2.00 Kč/kWh"  # default scheme=fixed, price_sell=2.0


def test_input_params_null_export_limit_means_no_limit():
    rows = ReportGenerator()._build_input_params({"grid_export_limit_kw": None})
    labels = {r["label"]: r["value"] for r in rows}
    assert labels["Limit exportu do sítě"] == "bez limitu"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/reportgen/test_report_pdf.py -q -k input_params`
Expected: FAIL with `AttributeError: 'ReportGenerator' object has no attribute '_build_input_params'`

- [ ] **Step 3: Write minimal implementation**

Do `backend/app/reporting.py` přidej konstantu a metodu do třídy `ReportGenerator` (např. za `_format_number`):

```python
    SCHEME_LABELS = {
        "fixed": "Fixní cena",
        "community": "Komunita",
        "shared": "Sdílení",
        "spot": "Spot",
    }
    SCHEME_PRICE = {
        "fixed": ("price_sell", "Výkupní cena"),
        "community": ("community_sell_price", "Výkupní cena (komunita)"),
        "shared": ("shared_sell_price", "Výkupní cena (sdílení)"),
        "spot": ("spot_price_margin", "Marže nad spotem"),
    }

    def _build_input_params(self, params):
        """Řádky tabulky Vstupní parametry — jen smysluplné vstupy."""
        p = dict(params or {})
        defaults = {
            "kwp": 10.0, "battery_capacity": 10.0, "annual_consumption_mwh": 5.0,
            "latitude": 50.6607, "longitude": 14.03227,
            "price_power": 3.0, "price_distribution": 2.0,
            "sell_price_scheme": "fixed", "price_sell": 2.0,
            "community_sell_price": 1.5, "shared_sell_price": 2.54,
            "spot_price_margin": 0.4, "surface_tilt": 35, "surface_azimuth": 180,
            "system_loss_factor": 14.0, "winter_loss_factor": 10.0,
            "thermal_battery_capacity_kwh": 0.0,
            "thermal_battery_charge_power_kw": 2.0,
        }

        def val(key):
            v = p.get(key, defaults.get(key))
            return defaults.get(key) if v is None else v

        rows = []

        def add(label, value):
            if value not in (None, ""):
                rows.append({"label": label, "value": value})

        add("Instalovaný výkon", f"{self._format_number(val('kwp'), 1)} kWp")
        add("Kapacita baterie", f"{self._format_number(val('battery_capacity'), 1)} kWh")
        add("Roční spotřeba", f"{self._format_number(val('annual_consumption_mwh'), 1)} MWh")
        add("Lokalita (lat/lon)",
            f"{self._format_number(val('latitude'), 5)}, "
            f"{self._format_number(val('longitude'), 5)}")
        add("Cena silové energie", f"{self._format_number(val('price_power'), 2)} Kč/kWh")
        add("Cena distribuce", f"{self._format_number(val('price_distribution'), 2)} Kč/kWh")

        scheme = p.get("sell_price_scheme") or defaults["sell_price_scheme"]
        add("Schéma prodeje", self.SCHEME_LABELS.get(scheme, scheme))
        price_key, price_label = self.SCHEME_PRICE.get(scheme, self.SCHEME_PRICE["fixed"])
        add(price_label, f"{self._format_number(val(price_key), 2)} Kč/kWh")

        add("Sklon střechy", f"{self._format_number(val('surface_tilt'), 0)}°")
        add("Azimut", f"{self._format_number(val('surface_azimuth'), 0)}°")

        limit = p.get("grid_export_limit_kw")
        add("Limit exportu do sítě",
            "bez limitu" if limit is None else f"{self._format_number(limit, 1)} kW")

        add("Systémové ztráty", f"{self._format_number(val('system_loss_factor'), 0)} %")
        add("Zimní ztráty", f"{self._format_number(val('winter_loss_factor'), 0)} %")
        add("Tepelná baterie",
            f"{self._format_number(val('thermal_battery_capacity_kwh'), 1)} kWh")
        add("Dobíjení tepelné baterie",
            f"{self._format_number(val('thermal_battery_charge_power_kw'), 1)} kW")

        apps = p.get("active_appliances") or []
        if apps:
            add("Aktivní spotřebiče", ", ".join(apps))
        return rows
```

Pozn.: `_format_number` formátuje s tisíci a nahrazuje `,` za mezeru; pro hodnoty < 1000 vrací např. `10.0`. Test proto očekává `"10.0 kWp"`, `"2.00 Kč/kWh"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/reportgen/test_report_pdf.py -q -k input_params`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/reporting.py tests/reportgen/test_report_pdf.py
git commit -m "feat(report): stavitel radku vstupnich parametru pro PDF"
```

---

### Task 3: Kontext — varianta, oddíly, souhrn investice

**Files:**
- Modify: `backend/app/reporting.py` (`_build_context`, `generate_energy_report`)
- Test: `tests/reportgen/test_report_pdf.py`

**Interfaces:**
- Consumes: `resolve_sections` (Task 1), `_build_input_params` (Task 2).
- Produces:
  - `_build_context(data, economic=None, variant="company", sections=None, params=None) -> dict`
  - nové klíče kontextu: `variant: str`, `variant_label: str`, `sections: list[str]`, `input_params_rows: list[dict]`, `investment_summary_text: str`
  - `generate_energy_report(data, economic=None, variant="company", sections=None, params=None) -> bytes`

- [ ] **Step 1: Write the failing test**

Přidej na konec `tests/reportgen/test_report_pdf.py` (import `resolve` netřeba):

```python
def test_context_default_sections_full_report():
    ctx = ReportGenerator()._build_context(_energy_data(), _economic())
    assert ctx["variant"] == "company"
    assert ctx["variant_label"] == "interní"
    # ekonomika přítomna -> ekonomické oddíly zůstávají
    assert "economic_metrics" in ctx["sections"]
    assert "investment_composition" in ctx["sections"]
    assert ctx["sections"][0] == "intro"
    assert ctx["sections"][-1] == "glossary"


def test_context_customer_variant_summary_and_label():
    ctx = ReportGenerator()._build_context(
        _energy_data(), _economic(), variant="customer")
    assert ctx["variant_label"] == "nabídka pro zákazníka"
    assert "FVE 10.0 kWp" in ctx["investment_summary_text"]
    assert "10.0 kWh" in ctx["investment_summary_text"]
    # detailní rozpis zůstává v kontextu (šablona ho pro zákazníka nepoužije)
    assert ctx["investment_breakdown"][0]["name"] == "Panel 550 Wp"


def test_context_subset_and_order():
    ctx = ReportGenerator()._build_context(
        _energy_data(), _economic(),
        sections=["intro", "summary", "recommendations",
                  "economic_metrics", "investment_composition", "glossary"])
    assert ctx["sections"] == ["intro", "summary", "recommendations",
                               "economic_metrics", "investment_composition", "glossary"]


def test_context_drops_economic_sections_without_economic():
    ctx = ReportGenerator()._build_context(_energy_data(), None, sections=None)
    assert "economic_metrics" not in ctx["sections"]
    assert "investment_composition" not in ctx["sections"]
    assert ctx["sections"][0] == "intro"


def test_context_input_params_rows_present():
    ctx = ReportGenerator()._build_context(
        _energy_data(), _economic(), params={"price_power": 4.5, "sell_price_scheme": "fixed"})
    labels = {r["label"]: r["value"] for r in ctx["input_params_rows"]}
    assert labels["Cena silové energie"] == "4.50 Kč/kWh"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/reportgen/test_report_pdf.py -q -k context`
Expected: FAIL with `KeyError: 'variant'`

- [ ] **Step 3: Write minimal implementation**

V `backend/app/reporting.py` nahraď hlavičku importu a rozšiř `_build_context` + `generate_energy_report`.

Import na začátek (za ostatní importy):

```python
from .reportgen.report_sections import resolve_sections
```

Změň signaturu a vlož nové klíče (do `context = {...}` přidej na konec objektu,
resp. po vytvoření `context`):

```python
    def _build_context(self, data, economic=None, variant="company",
                       sections=None, params=None):
```

Za definicí `context = { ... }` (před zpracováním `appliance_metrics`) vlož:

```python
        has_economic = economic is not None
        context["variant"] = variant
        context["variant_label"] = (
            "nabídka pro zákazníka" if variant == "customer" else "interní")
        context["sections"] = resolve_sections(sections, has_economic=has_economic)
        context["input_params_rows"] = self._build_input_params(params)
        context["investment_summary_text"] = (
            f"FVE {self._format_number(data.get('kwp', 0.0), 1)} kWp + "
            f"baterie {self._format_number(data.get('battery_capacity', 0.0), 1)} kWh "
            f"včetně instalace a montáže"
        )
```

Změň `generate_energy_report`:

```python
    def generate_energy_report(self, data, economic=None, variant="company",
                               sections=None, params=None):
        """Generuje PDF energetické (+ ekonomické) analýzy.

        `economic` je volitelný — bez něj se ekonomické oddíly vynechají.
        `variant`/`sections`/`params` mají defaulty = dnešní plný report
        (legacy volající beze změny).
        """
        context = self._build_context(data, economic, variant, sections, params)
        template = self.env.get_template("energy_report.html")
        html_content = template.render(context)
        pdf_bytes = HTML(string=html_content).write_pdf()
        return pdf_bytes
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/reportgen/test_report_pdf.py -q -k context`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/reporting.py tests/reportgen/test_report_pdf.py
git commit -m "feat(report): kontext varianty, oddilu a souhrnu investice"
```

---

### Task 4: Rozdělení šablony na partialy + obal

**Files:**
- Create: `backend/templates/energy_sections/` (16 partialů)
- Modify: `backend/templates/energy_report.html` (obal)
- Test: `tests/reportgen/test_report_pdf.py`

**Interfaces:**
- Consumes: `ctx["sections"]`, `ctx` klíče z Tasku 3 a stávající klíče.
- Produces: šablona `energy_report.html` skládající partialy podle `sections`.

- [ ] **Step 1: Write the failing test**

Přidej na konec `tests/reportgen/test_report_pdf.py`:

```python
def test_render_respects_sections_subset_and_order():
    html = _render(_energy_data(), _economic(), sections=[
        "intro", "summary", "recommendations",
        "economic_metrics", "investment_composition", "glossary"])
    assert "Doporučené strategie" in html
    # vynechaný oddíl v PDF není
    assert "Měsíční Bilance" not in html
    assert "Příloha A" not in html
    # pořadí: Doporučení před Ekonomickou analýzou
    assert html.index("Doporučené strategie") < html.index("Ekonomická analýza")


def test_render_reorder_moves_section():
    html = _render(_energy_data(), _economic(), sections=[
        "intro", "summary", "energy_balance", "monthly_stats",
        "economic_metrics", "investment_composition", "glossary"])
    assert html.index("Energetická Bilance") < html.index("Měsíční Statistika")
```

Rozšiř helper `_render` o `sections`:

```python
def _render(data, economic=None, sections=None, variant="company", params=None):
    """Postaví kontext a vyrenderuje šablonu — bez WeasyPrint."""
    gen = ReportGenerator()
    with patch("app.reporting.pio.to_image", return_value=b"PNG"):
        ctx = gen._build_context(data, economic, variant, sections, params)
    return gen.env.get_template("energy_report.html").render(ctx)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/reportgen/test_report_pdf.py -q -k "respects_sections or reorder"`
Expected: FAIL (vynechané oddíly jsou stále v HTML — šablona je monolit)

- [ ] **Step 3: Write minimal implementation**

Přesuň obsah dnešní `energy_report.html` (řádky 8–338) do partialů a šablonu
zúž na obal. **Obsah sekcí přenes 1:1** (řádky uprav jen na úroveň nadpisů
`<h2>`/`<h3>` a zachovej CSS třídy).

Vytvoř tyto soubory (obsah = příslušný blok z dnešní šablony):

| Soubor | Obsah z dnešní šablony |
|--------|------------------------|
| `intro.html` | (nové — Task 5; pro Task 4 stačí prázdný `{# intro #}`) |
| `summary.html` | řádky 8–23 (summary-box) |
| `input_params.html` | řádky 25–33 (dnešní Vstupní Parametry; Task 5 nahradí za `input_params_rows`) |
| `energy_balance.html` | řádky 43–75 (tabulka Energetická bilance) |
| `monthly_stats.html` | řádky 35–41 (graf měsíční statistiky) |
| `energy_charts.html` | řádky 77–117 (čtyři grafy) |
| `monthly_summary.html` | řádky 119–148 (Měsíční Bilance) |
| `recommendations.html` | řádky 150–161 |
| `economic_metrics.html` | řádky 163–180 (nadpis Ekonomická analýza + tabulka metrik) |
| `investment_chart.html` | řádky 182–187 (graf Investice vs S&P500) |
| `investment_composition.html` | řádky 189–215 (Složení investice; Task 6 přidá variantu) |
| `appendix_a.html` … `appendix_d.html` | řádky 217–248, 250–283, 285–308, 310–337 |
| `glossary.html` | (nové — Task 5; pro Task 4 stačí `{# glossary #}`) |

Nová `backend/templates/energy_report.html`:

```html
{% extends "base.html" %}

{% block title %}Energetický Report{% endblock %}
{% block report_title %}Energetická a ekonomická analýza{% endblock %}

{% block content %}
<p style="text-align: center; color: #7f8c8d; font-size: 10pt;">
    Verze: {{ variant_label }}
</p>

{% for s in sections %}
{% include "energy_sections/" ~ s ~ ".html" %}
{% endfor %}
{% endblock %}
```

Pozn.: `intro` obsahuje vlastní nadpis `<h2>`, proto v něm `break-before` není;
přílohy si `break-before: page` nesou dál ze svého partialu (test
`test_appendix_headings_break_to_new_page` musí dál projít).

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/reportgen/test_report_pdf.py -q`
Expected: PASS (včetně všech stávajících regresních testů)

- [ ] **Step 5: Commit**

```bash
git add backend/templates/energy_report.html backend/templates/energy_sections/
git commit -m "refactor(report): rozdelit sablonu na partialy a obal skladajici dle oddilu"
```

---

### Task 5: Vysvětlivky (úvod, popisky, slovníček)

**Files:**
- Modify: `backend/templates/energy_sections/*.html` (popisky `{% if %}` nejsou potřeba — statický text)
- Modify: `backend/templates/energy_sections/intro.html`
- Modify: `backend/templates/energy_sections/glossary.html`
- Modify: `backend/templates/energy_sections/input_params.html` (použít `input_params_rows`)
- Test: `tests/reportgen/test_report_pdf.py`

**Interfaces:**
- Consumes: `ctx["input_params_rows"]`, `ctx["variant_label"]`.
- Produces: statické české vysvětlivky v partialech.

- [ ] **Step 1: Write the failing test**

Přidej na konec `tests/reportgen/test_report_pdf.py`:

```python
def test_render_has_intro_captions_and_glossary():
    html = _render(_energy_data(), _economic(), params={"price_power": 3.0})
    assert "Jak číst tento report" in html or "Jak číst" in html
    assert "Slovníček pojmů" in html
    assert "NPV" in html           # slovníček
    assert "Cena silové energie" in html  # tabulka vstupů


def test_input_params_section_uses_rows_not_hardcoded():
    html = _render(_energy_data(), _economic(), params={"price_power": 7.77})
    assert "7.77 Kč/kWh" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/reportgen/test_report_pdf.py -q -k "intro_captions or uses_rows"`
Expected: FAIL (`7.77 Kč/kWh` se nevykreslí, slovníček chybí)

- [ ] **Step 3: Write minimal implementation**

`backend/templates/energy_sections/intro.html`:

```html
<h2>Jak číst tento report</h2>
<p>
  Dokument shrnuje návrh fotovoltaického systému: kolik vyrobí, kolik ušetří
  a za jak dlouho se investice vrátí. Je členěn od souhrnu k detailu — nejdřív
  hlavní čísla, pak energetická a ekonomická bilance, grafy a nakonec přílohy
  s rozpisem po spotřebičích a letech. Každá tabulka a graf má pod sebou krátké
  vysvětlení. Použité pojmy najdete ve slovníčku na konci.
</p>
```

`backend/templates/energy_sections/input_params.html`:

```html
<h2>Vstupní parametry</h2>
<p class="section-caption" style="color:#7f8c8d; font-size:9pt;">
  Hodnoty, ze kterých se analýza počítala.
</p>
<table>
    <tr><th>Parametr</th><th class="text-right">Hodnota</th></tr>
    {% for row in input_params_rows %}
    <tr><td>{{ row.label }}</td><td class="text-right">{{ row.value }}</td></tr>
    {% endfor %}
</table>
```

`backend/templates/energy_sections/glossary.html`:

```html
<h2 style="break-before: page;">Slovníček pojmů</h2>
<dl style="font-size: 0.9em;">
  <dt><strong>Vlastní spotřeba</strong></dt>
  <dd>Část vyrobené energie, kterou spotřebujeme přímo v budově, místo nákupu ze sítě.</dd>
  <dt><strong>Přetok / export do sítě</strong></dt>
  <dd>Přebytek výroby předaný do distribuční sítě, obvykle za výkupní cenu.</dd>
  <dt><strong>Roční úspora</strong></dt>
  <dd>Kolik korun ušetříme za rok díky vlastní spotřebě a prodeji přebytků.</dd>
  <dt><strong>Návratnost</strong></dt>
  <dd>Počet let, než kumulovaná úspora vyrovná vstupní investici.</dd>
  <dt><strong>Diskontovaná návratnost</strong></dt>
  <dd>Návratnost s ohledem na časovou hodnotu peněz (budoucí úspory mají nižší hodnotu).</dd>
  <dt><strong>NPV (čistá současná hodnota)</strong></dt>
  <dd>Součet budoucích peněžních toků přepočtených na dnešní hodnotu mínus investice. Kladná = výhodná.</dd>
  <dt><strong>Reinvestice</strong></dt>
  <dd>Varianta, kdy se roční úspory dále investují.</dd>
  <dt><strong>Benchmark S&amp;P500</strong></dt>
  <dd>Srovnání: co by ze stejné investice vzniklo při pasivním investování do akciového indexu.</dd>
</dl>
```

Do ostatních partialů přidej pod nadpis krátký popisek `<p class="section-caption">` (1–3 věty) — obsah dle popisů v registru (např. u `energy_balance`: „Roční tok energie a peněz mezi domácností a sítí. Záporná čísla u importu znamenají náklad, u exportu příjem.").

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/reportgen/test_report_pdf.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/templates/energy_sections/
git commit -m "feat(report): uvod, popisky sekci a slovnicek pojmu"
```

---

### Task 6: Varianta „Složení investice" (zákazník vs firma)

**Files:**
- Modify: `backend/templates/energy_sections/investment_composition.html`
- Test: `tests/reportgen/test_report_pdf.py`

**Interfaces:**
- Consumes: `ctx["variant"]`, `ctx["investment_summary_text"]`, `ctx["investment_cost_czk"]`, `ctx["investment_breakdown"]`.
- Produces: dvě větve renderu.

- [ ] **Step 1: Write the failing test**

Přidej na konec `tests/reportgen/test_report_pdf.py`:

```python
def test_customer_variant_shows_aggregate_not_breakdown():
    html = _render(_energy_data(), _economic(), variant="customer")
    assert "FVE 10.0 kWp + baterie 10.0 kWh" in html
    assert "300 000 Kč" in html
    assert "Panel 550 Wp" not in html   # žádný rozpis komponent
    assert "Cena/ks" not in html


def test_company_variant_shows_breakdown():
    html = _render(_energy_data(), _economic(), variant="company")
    assert "Panel 550 Wp" in html
    assert "Cena/ks" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/reportgen/test_report_pdf.py -q -k "customer_variant or company_variant"`
Expected: FAIL (zákaznická verze stále obsahuje rozpis)

- [ ] **Step 3: Write minimal implementation**

`backend/templates/energy_sections/investment_composition.html`:

```html
<h3>Složení investice</h3>
{% if variant == "customer" %}
<p style="font-size: 0.95em;">{{ investment_summary_text }}</p>
<table style="font-size: 0.9em;">
    <thead>
        <tr><th>Položka</th><th class="text-right">Celkem</th></tr>
    </thead>
    <tbody>
        <tr class="highlight">
            <td><strong>CELKEM</strong></td>
            <td class="text-right"><strong>{{ investment_cost_czk }}</strong></td>
        </tr>
    </tbody>
</table>
{% else %}
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
{% endif %}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/reportgen/test_report_pdf.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/templates/energy_sections/investment_composition.html
git commit -m "feat(report): zakaznicka varianta slozeni investice (agregat)"
```

---

### Task 7: API — metadata oddílů + varianta/oddíly/params v report/energy

**Files:**
- Modify: `backend/app/reportgen/fve_router.py`
- Modify: `tests/reportgen/test_fve_api.py`
- Modify: `README.md`, `docs/architektura.md` (zmínka o variantách a endpointu oddílů)

**Interfaces:**
- Consumes: `sections_metadata`, `resolve_sections` (Task 1); `generate_energy_report` (Task 3).
- Produces:
  - `GET /api/v1/fve-analysis/report/sections` → `{"sections":[{"id","label","description","base"}]}`
  - `POST /api/v1/fve-analysis/report/energy` payload: `{energy, economic, params, variant, sections}`.

- [ ] **Step 1: Write the failing test**

Přidej do `tests/reportgen/test_fve_api.py`:

```python
def test_report_sections_metadata(client, admin_token):
    r = client.get("/api/v1/fve-analysis/report/sections", headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    ids = [s["id"] for s in r.json()["sections"]]
    assert ids[0] == "intro" and ids[-1] == "glossary"
    assert any(s["id"] == "summary" and s["base"] for s in r.json()["sections"])


def test_energy_pdf_admin_company_variant_has_breakdown(client, admin_token):
    result = client.post("/api/v1/fve-analysis/run", json={"kwp": 10.0},
                         headers=_auth(admin_token)).json()
    r = client.post("/api/v1/fve-analysis/report/energy",
                    json={"energy": result, "economic": None,
                          "variant": "company", "sections": None},
                    headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"


def test_energy_pdf_customer_cannot_get_company_variant(client, customer_token):
    """Zákazník pošle variant=company → server přepíše na customer (bez rozpadu)."""
    from unittest.mock import patch
    result = client.post("/api/v1/fve-analysis/run", json={"kwp": 8.0},
                         headers=_auth(customer_token)).json()
    seen = {}

    def fake(self, data, economic=None, variant="company", sections=None, params=None):
        seen["variant"] = variant
        return b"%PDF-1.4 fake"

    with patch("app.reporting.ReportGenerator.generate_energy_report", fake):
        r = client.post("/api/v1/fve-analysis/report/energy",
                        json={"energy": result, "economic": None,
                              "variant": "company"},
                        headers=_auth(customer_token))
    assert r.status_code == 200, r.text
    assert seen["variant"] == "customer"


def test_energy_pdf_unknown_section_ids_ignored(client, admin_token):
    result = client.post("/api/v1/fve-analysis/run", json={"kwp": 10.0},
                         headers=_auth(admin_token)).json()
    r = client.post("/api/v1/fve-analysis/report/energy",
                    json={"energy": result, "economic": None,
                          "sections": ["summary", "nesmysl", "glossary"]},
                    headers=_auth(admin_token))
    assert r.status_code == 200, r.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_api.py -q -k "report_sections_metadata or company_variant or cannot_get_company or unknown_section"`
Expected: FAIL (`404 Not Found` u `/report/sections`; varianta se ignoruje)

- [ ] **Step 3: Write minimal implementation**

V `backend/app/reportgen/fve_router.py` přidej import nahoru (mezi ostatní `from app...`):

```python
from app.reportgen import report_sections as rs
```

(nebo `from . import report_sections as rs` — soubor je v `reportgen/`.)

Nahraď endpoint `energy_pdf` a přidej metadata endpoint:

```python
@router.get("/fve-analysis/report/sections")
def report_sections_metadata(user: User = Depends(ANY_ROLE)):
    """Metadata oddílů PDF pro modální výběr (label, base)."""
    return {"sections": rs.sections_metadata()}


COMPANY_ROLES = {"admin", "antelon", "sales"}


def _is_company(user: User) -> bool:
    return any(user.has_role(r) for r in COMPANY_ROLES)


@router.post("/fve-analysis/report/energy")
def energy_pdf(payload: dict, user: User = Depends(ANY_ROLE)):
    """PDF energetické i ekonomické analýzy.

    Payload: {"energy", "economic"|null, "params"|null,
              "variant": "customer"|"company", "sections": [id, ...]}.
    Variantu vynutí role (zákazník vždy customer); seznam oddílů se
    sanitizuje (neznámé id ignorováno, pevný základ vždy přítomen).
    """
    from app.reporting import ReportGenerator

    payload = payload or {}
    energy = payload.get("energy")
    economic = payload.get("economic")
    if not energy or "energy_balance_kwh" not in energy:
        raise HTTPException(400, "Chybí výsledek analýzy")

    variant = payload.get("variant") or "company"
    if not _is_company(user):
        variant = "customer"
    sections = rs.resolve_sections(payload.get("sections"),
                                   has_economic=economic is not None)
    try:
        pdf_bytes = ReportGenerator().generate_energy_report(
            energy, economic, variant=variant, sections=sections,
            params=payload.get("params"))
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

Ověř, že `require_roles`/`ANY_ROLE` a `User.has_role` jsou v souboru dostupné
(jsou — viz `ANY_ROLE` řádek 42).

Do `README.md` a `docs/architektura.md` doplň jednu větu: report má varianty
`customer`/`company`, seznam oddílů je v `GET /fve-analysis/report/sections`
a volba se ukládá do `fve_params.pdf_sections`.

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_api.py -q -k "report or energy_pdf"`
Expected: PASS (nové i stávající PDF testy)

- [ ] **Step 5: Run celý reportgen balík**

Run: `./venv/bin/python -m pytest tests/reportgen -q`
Expected: PASS (bez regresí)

- [ ] **Step 6: Commit**

```bash
git add backend/app/reportgen/fve_router.py tests/reportgen/test_fve_api.py README.md docs/architektura.md
git commit -m "feat(report): API varianty/oddilu + metadata oddilu + vynuceni role"
```

---

### Task 8: Frontend — typy, klient, modální výběr oddílů

**Files:**
- Modify: `frontend-web/src/types.ts`
- Modify: `frontend-web/src/api/fve.ts`
- Create: `frontend-web/src/components/fve/PdfSectionsModal.tsx`

**Interfaces:**
- Consumes: `GET /fve-analysis/report/sections`.
- Produces:
  - typy `PdfVariant`, `PdfSectionsConfig`, `ReportSectionMeta`; `FveParams.pdf_sections?`
  - `fetchReportSections(): Promise<ReportSectionMeta[]>`
  - `downloadEnergyPdf(energy, economic, params, variant, sections: string[] | null)`
  - komponenta `PdfSectionsModal`

- [ ] **Step 1: Napiš typy a klient (bez testu — ověřeno buildem)**

Do `frontend-web/src/types.ts` přidej:

```ts
export type PdfVariant = "customer" | "company";
export interface PdfSectionsConfig {
  customer?: string[];
  company?: string[];
}
export interface ReportSectionMeta {
  id: string;
  label: string;
  description: string;
  base: boolean;
}
```

Do `FveParams` (uvnitř interface) přidej:

```ts
  pdf_sections?: PdfSectionsConfig;
```

Do `frontend-web/src/api/fve.ts` nahraď `downloadEnergyPdf` a přidej `fetchReportSections`:

```ts
export const fetchReportSections = () =>
  client
    .get<{ sections: import("../types").ReportSectionMeta[] }>(
      "/fve-analysis/report/sections",
    )
    .then((r) => r.data.sections);

export const downloadEnergyPdf = (
  energy: FveAnalysisResult,
  economic: FveEconomicResult | null,
  params: Partial<FveParams>,
  variant: import("../types").PdfVariant,
  sections: string[] | null,
) =>
  client.post(
    "/fve-analysis/report/energy",
    { energy, economic, params, variant, sections },
    { responseType: "blob" },
  );
```

- [ ] **Step 2: Vytvoř modální komponentu**

Create `frontend-web/src/components/fve/PdfSectionsModal.tsx`:

```tsx
import { useEffect, useState } from "react";
import { fetchReportSections } from "../../api/fve";
import type { PdfVariant, ReportSectionMeta } from "../../types";

interface Props {
  variant: PdfVariant;
  initial?: string[];
  onClose: () => void;
  onGenerate: (orderedIds: string[]) => void;
}

export default function PdfSectionsModal({ variant, initial, onClose, onGenerate }: Props) {
  const [metas, setMetas] = useState<ReportSectionMeta[]>([]);
  const [order, setOrder] = useState<string[]>([]);
  const [enabled, setEnabled] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetchReportSections()
      .then((ms) => {
        setMetas(ms);
        const ids = ms.map((m) => m.id);
        const selected = initial && initial.length ? initial.filter((i) => ids.includes(i)) : ids;
        setEnabled(new Set(selected));
        setOrder([...selected, ...ids.filter((i) => !selected.includes(i))]);
      })
      .catch(() => setMetas([]));
  }, [initial]);

  const move = (idx: number, dir: -1 | 1) => {
    const j = idx + dir;
    if (j < 0 || j >= order.length) return;
    const next = [...order];
    [next[idx], next[j]] = [next[j], next[idx]];
    setOrder(next);
  };

  const toggle = (id: string, base: boolean) => {
    if (base) return;
    setEnabled((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };

  const label = variant === "customer" ? "PDF pro zákazníka" : "PDF pro firmu";

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[85vh] overflow-y-auto p-5">
        <h3 className="text-lg font-semibold text-navy mb-1">{label} — oddíly</h3>
        <p className="text-sm text-slate-500 mb-4">
          Pevný základ je vždy součástí. Volitelné oddíly zapněte a šipkami upravte pořadí.
        </p>
        <ul className="space-y-1">
          {order.map((id, idx) => {
            const meta = metas.find((m) => m.id === id);
            if (!meta) return null;
            const on = meta.base || enabled.has(id);
            return (
              <li key={id} className="flex items-center gap-3 border-b border-slate-100 py-2">
                <input type="checkbox" checked={on} disabled={meta.base}
                       onChange={() => toggle(id, meta.base)} className="h-4 w-4" />
                <div className="flex-1">
                  <div className="text-sm text-slate-800">{meta.label}
                    {meta.base && <span className="text-xs text-slate-400 ml-2">(pevný základ)</span>}
                  </div>
                  <div className="text-xs text-slate-500">{meta.description}</div>
                </div>
                <div className="flex gap-1">
                  <button type="button" onClick={() => move(idx, -1)} disabled={idx === 0}
                          className="px-2 py-1 border rounded disabled:opacity-30">↑</button>
                  <button type="button" onClick={() => move(idx, 1)} disabled={idx === order.length - 1}
                          className="px-2 py-1 border rounded disabled:opacity-30">↓</button>
                </div>
              </li>
            );
          })}
        </ul>
        <div className="flex justify-end gap-3 mt-5">
          <button type="button" onClick={onClose}
                  className="px-4 py-2 text-sm border rounded-lg">Zrušit</button>
          <button type="button" onClick={() => onGenerate(order.filter((i) => enabled.has(i)))}
                  className="px-4 py-2 text-sm bg-antelonGreen text-navy font-semibold rounded-lg">
            Vygenerovat PDF
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Ověř build**

Run: `cd frontend-web && npx tsc -b && npm run build`
Expected: exit 0

- [ ] **Step 4: Commit**

```bash
git add frontend-web/src/types.ts frontend-web/src/api/fve.ts frontend-web/src/components/fve/PdfSectionsModal.tsx
git commit -m "feat(fve-web): typy, klient a modal pro vyber oddilu PDF"
```

---

### Task 9: Frontend — tlačítka dle role + perzistence volby

**Files:**
- Modify: `frontend-web/src/components/fve/FveAnalysisResults.tsx`
- Modify: `frontend-web/src/pages/ProjectFveAnalysis.tsx`
- Modify: `frontend-web/src/pages/FveAnalysis.tsx` (jen předání `params` už je; nic dalšího není potřeba)

**Interfaces:**
- Consumes: `downloadEnergyPdf`, `fetchReportSections`, `PdfSectionsModal` (Task 8); `useAuth`, `hasAnyRole`.
- Produces: tlačítka dle role, uložení `pdf_sections` (projekt → DB, jinak localStorage).

- [ ] **Step 1: Uprav `FveAnalysisResults.tsx`**

Nahraď importy a signaturu komponenty a `downloadPdf`:

```tsx
import PlotlyChart from "./PlotlyChart";
import PdfSectionsModal from "./PdfSectionsModal";
import { downloadEnergyPdf, runEconomic } from "../../api/fve";
import { useState } from "react";
import { hasAnyRole, useAuth } from "../../context/AuthContext";
import type {
  FveAnalysisResult, FveEconomicResult, FveParams,
  PdfSectionsConfig, PdfVariant,
} from "../../types";

const LS_KEY = "fve_pdf_sections";

function loadLsSections(): PdfSectionsConfig {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || "{}"); } catch { return {}; }
}
```

Uvnitř komponenty (za `const [error, setError] = useState("")`):

```tsx
  const { user } = useAuth();
  const isCompany = hasAnyRole(user, ["admin", "antelon", "sales"]);
  const [modalVariant, setModalVariant] = useState<PdfVariant | null>(null);
```

Nahraď `downloadPdf` (přejmenuj na `runDownload` s parametry varianty a sekcí):

```tsx
  const runDownload = async (variant: PdfVariant, sections: string[] | null) => {
    setPdfLoading(true);
    setError("");
    try {
      let econ = economic;
      if (!econ) {
        econ = await runEconomic({
          ...params,
          annual_savings: result.financial_balance.annual_savings_czk,
        });
        setEconomic(econ);
      }
      const res = await downloadEnergyPdf(result, econ, params, variant, sections);
      const url = window.URL.createObjectURL(
        new Blob([res.data], { type: "application/pdf" }),
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = variant === "customer"
        ? "Energeticka_analyza_zakaznik.pdf" : "Energeticka_analyza_firma.pdf";
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(e?.response?.data?.detail || "PDF se nepodařilo stáhnout");
    } finally {
      setPdfLoading(false);
    }
  };

  const savedSections = params.pdf_sections ?? loadLsSections();
  const sectionsFor = (v: PdfVariant) => savedSections[v] ?? null;

  const persistAndGenerate = async (variant: PdfVariant, ids: string[]) => {
    const next: PdfSectionsConfig = { ...savedSections, [variant]: ids };
    setModalVariant(null);
    if (onSaveSections) {
      await onSaveSections(next);
    } else {
      localStorage.setItem(LS_KEY, JSON.stringify(next));
    }
    await runDownload(variant, ids);
  };
```

Změň signaturu komponenty na příjem `onSaveSections`:

```tsx
export default function FveAnalysisResults(
  { result, params, onSaveSections }: {
    result: FveAnalysisResult;
    params: Partial<FveParams>;
    onSaveSections?: (cfg: PdfSectionsConfig) => void | Promise<void>;
  },
) {
```

Nahraď spodní blok s tlačítkem:

```tsx
      <div className="flex justify-end gap-3 border-t border-slate-200 pt-4">
        {isCompany ? (
          <>
            <button
              type="button"
              onClick={() => setModalVariant("customer")}
              disabled={pdfLoading}
              className="border border-navy text-navy px-5 py-2.5 rounded-lg hover:bg-slate-50 disabled:opacity-50"
            >
              PDF pro zákazníka
            </button>
            <button
              type="button"
              onClick={() => setModalVariant("company")}
              disabled={pdfLoading}
              className="bg-antelonGreen text-navy font-semibold px-5 py-2.5 rounded-lg hover:brightness-110 disabled:opacity-50"
            >
              PDF pro firmu
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={() => runDownload("customer", sectionsFor("customer"))}
            disabled={pdfLoading}
            className="border border-navy text-navy px-5 py-2.5 rounded-lg hover:bg-slate-50 disabled:opacity-50"
          >
            {pdfLoading ? "Generuji…" : "Stáhnout PDF"}
          </button>
        )}
      </div>

      {modalVariant && (
        <PdfSectionsModal
          variant={modalVariant}
          initial={sectionsFor(modalVariant) ?? undefined}
          onClose={() => setModalVariant(null)}
          onGenerate={(ids) => persistAndGenerate(modalVariant, ids)}
        />
      )}
```

- [ ] **Step 2: Uprav `ProjectFveAnalysis.tsx` — perzistence do DB**

Přidej import typu a handler (za `convert`):

```tsx
import type { FveAnalysisResult, FveAppliance, FveParams, PdfSectionsConfig } from "../types";
```

(uprav existující `import type` řádek o `PdfSectionsConfig`.)

```tsx
  const saveSections = async (cfg: PdfSectionsConfig) => {
    const next = { ...params, pdf_sections: cfg };
    setParams(next);
    await client.put(`/projects/${project!.id}/params`, { fve_params: next });
  };
```

Předání do výsledků:

```tsx
      {tab === "results" && result && (
        <FveAnalysisResults result={result} params={params} onSaveSections={saveSections} />
      )}
```

- [ ] **Step 3: Ověř build**

Run: `cd frontend-web && npx tsc -b && npm run build`
Expected: exit 0

- [ ] **Step 4: Commit**

```bash
git add frontend-web/src/components/fve/FveAnalysisResults.tsx frontend-web/src/pages/ProjectFveAnalysis.tsx
git commit -m "feat(fve-web): tlacitka PDF dle role a ulozeni vyberu oddilu"
```

---

### Task 10: E2E ověření obou variant (Playwright)

**Files:**
- Create: `/tmp/opencode/pw_report_variants.py` (throwaway skript, necommitovat)
- Test: běh proti aktuálnímu preview

**Interfaces:**
- Consumes: hotový frontend + backend na 3103/8051.
- Produces: potvrzení, že zákaznická verze nemá rozpis a firemní ano.

- [ ] **Step 1: Napiš Playwright skript**

`/tmp/opencode/pw_report_variants.py`:

```python
import asyncio
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:3103"
EMAIL = "admin@antelon.local"
PWD = "Admin123!"

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page()
        await pg.goto(f"{BASE}/login")
        await pg.fill('input[type="email"]', EMAIL)
        await pg.fill('input[type="password"]', PWD)
        await pg.click('button[type="submit"]')
        await pg.wait_for_url("**/projects")
        # ... otevřít FVE analýzu, spustit, přejít na Výsledky,
        # kliknout "PDF pro zákazníka", v modalu "Vygenerovat PDF",
        # zachytit download a ověřit, že obsahuje agregát a ne rozpis.
        print("OK")
        await b.close()

asyncio.run(main())
```

(Skript dotáhni podle aktuálních selektorů; jde o throwaway ověření,
necommitovat.)

- [ ] **Step 2: Spusť a ověř**

Run: `./venv/bin/python /tmp/opencode/pw_report_variants.py`
Expected: stažení `Energeticka_analyza_zakaznik.pdf` (obsahuje agregát, bez „Cena/ks")
i `Energeticka_analyza_firma.pdf` (obsahuje rozpis); vypnutý oddíl v PDF chybí.

- [ ] **Step 3: Zkontroluj, že nic necommitneš navíc**

Run: `git status --short`
Expected: jen zamýšlené změny; žádné `data/*.bak-*` ani throwaway skripty.

---

## Self-Review

- **Coverage:** varianty (T6/T7/T9), výběr+pořadí (T1/T4/T8/T9), perzistence (T9), rám/vysvětlivky (T5), úplné vstupy (T2/T5), API+role (T7), E2E (T10). Spec §5 schéma prodeje → `SCHEME_PRICE` v T2. Spec §8 bezpečnost → T7 (`_is_company`, `resolve_sections`).
- **Placeholders:** žádné „TBD/TODO"; throwaway skript v T10 je záměrně skeleton s poznámkou (ověřovací krok, ne produkční kód).
- **Type consistency:** `resolve_sections(requested, *, has_economic)`, `sections_metadata()`, `_build_input_params(params)`, `_build_context(data, economic, variant, sections, params)`, `generate_energy_report(data, economic, variant, sections, params)` — používané konzistentně napříč T1–T7; TS `PdfVariant/PdfSectionsConfig/ReportSectionMeta` a `downloadEnergyPdf(..., variant, sections)` konzistentní T8–T9.
- **Review Focus:** každý bod má test — economic-missing (T3/T4), unknown id (T1/T7), role override (T7), prázdné params (T2), base pořadí (T1), reorder s vypnutým (T1/T8).
