# Report — varianty pro zákazníka/firmu, výběr oddílů, vysvětlivky, úplné vstupní parametry

**Datum:** 2026-10-09
**Status:** návrh (čeká na review uživatele)
**Repo:** AntelonEnergy (fveAnalyzator) — `backend/` + `frontend-web/`
**Navazuje na:** `docs/superpowers/specs/2026-10-06-fve-analyza-opravy-a-cenik-design.md`,
Plány 1–4 (`docs/superpowers/plans/2026-10-06-*.md`)

## 1. Cíl

PDF „Energetická a ekonomická analýza" dnes generuje jednu pevnou podobu. Potřebujeme:

1. **Dvě varianty** — *zákaznická* a *firemní* — lišící se hlavně sekcí „Složení investice"
   (zákazník = agregát, firma = rozpis komponent).
2. **Výběr oddílů** — zaměstnanec před exportem zaškrtne, které oddíly do PDF půjdou,
   a **určí jejich pořadí**; pevný základ je vždy.
3. **Vysvětlující text** — úvod „Jak číst report", popisky u tabulek/grafů, slovníček pojmů;
   v obou variantách.
4. **Úplné vstupní parametry** — v PDF musí být uvedeny všechny smysluplné vstupy
   (cena silové energie, distribuce, výkup, schéma prodeje, sklon, …), ne jen výkon a lokalita.

## 2. Rozhodnutí z brainstormingu

| Téma | Volba |
|------|-------|
| Volba varianty | **Role určuje, jaká tlačítka vidí**; firma (admin/antelon/sales) = dvě tlačítka, zákazník (customer/buyer) = jedno |
| Zákaznické „Složení investice" | **Jedna souhrnná řádka + CELKEM** (např. „FVE 10 kWp + baterie 10 kWh včetně instalace") |
| Firemní „Složení investice" | **Plný rozpis komponent** jako dnes (PAN-550, INV-10, BAT-10, INS-MONT… + CELKEM) |
| Rozsah pickeru | **Obě varianty**; volba se ukládá zvlášť pro zákaznickou a zvlášť pro firemní |
| Pevný základ (neodebratelné) | **Souhrnné výsledky, Ekonomická analýza, Složení investice** |
| Volitelné oddíly | Vstupní parametry, Energetická bilance, Měsíční statistika (graf), Grafy, Měsíční bilance, Doporučení, Investice vs S&P500, Přílohy A–D |
| Řazení | **Základ i volitelné lze přesouvat** (↑/↓); základ nelze vypnout |
| Rám dokumentu | Úvod „Jak číst report" je vždy na začátku, slovníček vždy na konci |
| Forma pickeru | **Modální okno**: seznam oddílů, zaškrtávátka, šipky ↑/↓, „Vygenerovat PDF" |
| Ukládání volby | **K analýze do DB** (`fve_params_json` → `pdf_sections`); bez změny schématu |
| Bez projektu | Fallback `localStorage` (veřejný náhled před uložením) |
| Vstupní parametry | **Všechny smysluplné vstupy** s jednotkami a lidskými názvy; skryjí se jen interní ID/přepínače |
| Vysvětlivky | Úvod + popisky (1–3 věty) u každé sekce + slovníček; statický český text, stejný v obou variantách |
| Legacy cesty | `generate_energy_report` default = **dnešní plný report** (beze změny chování) |
| Ochrana dat | Zákazník **nikdy** nedostane interní rozpis — server variantu vynutí podle role |

## 3. Architektura

### 3.1 Registr oddílů (jeden zdroj pravdy)

Nový modul `backend/app/reportgen/report_sections.py`:

```
Section = { id: str, label: str, description: str, base: bool, needs_economic: bool }
SECTIONS: tuple[Section]   # kanonické pořadí = default
BASE_IDS = ("summary", "economic_metrics", "investment_composition")
FRAME_INTRO = "intro"          # vždy první
FRAME_GLOSSARY = "glossary"    # vždy poslední

def resolve_sections(requested: list[str] | None) -> list[str]:
    """Sanitizace: ignoruj neznámé id, vynuť BASE_IDS, zachovej pořadí klienta,
    případná chybějící base id vlož v kanonickém pořadí."""

def sections_metadata() -> list[dict]:
    """Pro frontend: id, label, description, base (v kanonickém pořadí)."""
```

Kanonické pořadí a typy:

| id | label | base | needs_economic |
|----|-------|------|----------------|
| `intro` | Jak číst tento report | rám (vždy 1.) | ne |
| `summary` | Souhrnné výsledky | **ano** | ne |
| `input_params` | Vstupní parametry | ne (default ON) | ne |
| `energy_balance` | Energetická bilance | ne | ne |
| `monthly_stats` | Měsíční statistika výroby a spotřeby | ne | ne |
| `energy_charts` | Grafy (využití výroby a úspory) | ne | ne |
| `monthly_summary` | Měsíční bilance | ne | ne |
| `recommendations` | Doporučené strategie a scénáře | ne | ne |
| `economic_metrics` | Ekonomická analýza | **ano** | **ano** |
| `investment_chart` | Investice vs S&P500 | ne | **ano** |
| `investment_composition` | Složení investice | **ano** | **ano** |
| `appendix_a` | Příloha A — Detail spotřebičů (ročně) | ne | ne |
| `appendix_b` | Příloha B — Měsíční bilance spotřebičů | ne | ne |
| `appendix_c` | Příloha C — Detail nastavení spotřebičů | ne | ne |
| `appendix_d` | Příloha D — Ekonomický plán po letech | ne | **ano** |
| `glossary` | Slovníček pojmů | rám (vždy poslední) | ne |

`needs_economic` oddíly se při `economic is None` vynechají (robustnost + legacy).

### 3.2 Šablona — partialy

`backend/templates/energy_report.html` se zúží na obal:

```
{% extends "base.html" %}
... header (titulek + označení varianty) ...
{% for s in sections %}{% include "energy_sections/" + s + ".html" %}{% endfor %}
```

Nový adresář `backend/templates/energy_sections/` s jedním partialem na oddíl
(`intro.html`, `summary.html`, `input_params.html`, `energy_balance.html`,
`monthly_stats.html`, `energy_charts.html`, `monthly_summary.html`,
`recommendations.html`, `economic_metrics.html`, `investment_chart.html`,
`investment_composition.html`, `appendix_a.html`…`appendix_d.html`, `glossary.html`).

Obsah se přenese z dnešní `energy_report.html` (řádky 8–338) beze změny dat;
jen `investment_composition.html` má dvě větve podle `variant`.

### 3.3 Reporting

`backend/app/reporting.py`:

```
def generate_energy_report(self, data, economic=None,
                           variant="company", sections=None, params=None):
```

- `variant in ("customer", "company")`; default `company` (legacy = plný rozpis).
- `sections is None` → kanonické pořadí všech oddílů, jejichž data existují
  (tj. dnešní chování, včetně vynechání ekonomiky, když `economic is None`).
- `params` → nová položka kontextu `input_params_rows` (viz §5).
- Kontext dále: `variant`, `variant_label` („nabídka pro zákazníka" / „interní"),
  `sections` (seřazené id pro include).
- `investment_composition`: firemní = stávající `investment_breakdown`; zákaznická =
  `investment_summary_text` + `investment_cost_czk`.

## 4. API

### 4.1 Metadata oddílů

`GET /api/v1/fve-analysis/report/sections` (auth `ANY_ROLE`) →
`{"sections": [{"id","label","description","base"}]}` v kanonickém pořadí.
Frontend staví modal z tohoto seznamu (žádná duplikace labelů v TS).

### 4.2 Generování PDF

`POST /api/v1/fve-analysis/report/energy` — payload rozšířen:

```
{
  "energy": {...},
  "economic": {...} | null,
  "params": {...},                       # vstupy pro tabulku Vstupní parametry
  "variant": "customer" | "company",
  "sections": ["intro","summary",...]    # seřazené id zapnutých oddílů
}
```

Server:

1. **Vynutí variantu podle role:** uživatel bez firemní role (`admin`/`antelon`/`sales`)
   vždy dostane `variant="customer"`, i kdyby poslal `company`.
2. `sections = resolve_sections(payload.sections)` — ignoruje neznámé, vynutí základ.
3. Zavolá `generate_energy_report(energy, economic, variant, sections, params)`.

### 4.3 Legacy cesty

`ai_service.py:221` a `router.py:534` volají `generate_energy_report(data)` bez
varianty/sekcí → default plný report jako dnes. Žádná změna.

## 5. Vstupní parametry v PDF

`reporting._build_input_params(params)` vytvoří seřazené řádky `{label, value}` z živých
vstupů (sloučených s backendovými defaulty). Zobrazí se jen smysluplné vstupy:

| Label | Zdroj | Formát |
|-------|-------|--------|
| Instalovaný výkon | `kwp` | `{n} kWp` |
| Kapacita baterie | `battery_capacity` | `{n} kWh` |
| Roční spotřeba | `annual_consumption_mwh` | `{n} MWh` |
| Lokalita (lat/lon) | `latitude`/`longitude` | `{lat}, {lon}` |
| Cena silové energie | `price_power` | `{n} Kč/kWh` |
| Cena distribuce | `price_distribution` | `{n} Kč/kWh` |
| Schéma prodeje | `sell_price_scheme` | Fixní / Komunita / Sdílení / Spot |
| Výkupní cena | dle schématu:* | `{n} Kč/kWh` |
| Sklon střechy | `surface_tilt` | `{n}°` |
| Azimut | `surface_azimuth` | `{n}°` |
| Limit exportu | `grid_export_limit_kw` | `{n} kW` / „bez limitu" |
| Systémové ztráty | `system_loss_factor` | `{n} %` |
| Zimní ztráty | `winter_loss_factor` | `{n} %` |
| Tepelná baterie | `thermal_battery_capacity_kwh` | `{n} kWh` |
| Dobíjení tepelné baterie | `thermal_battery_charge_power_kw` | `{n} kW` |
| Aktivní spotřebiče | `active_appliances` | seznam (jen když neprázdný) |

\* `fixed`→`price_sell`, `community`→`community_sell_price`, `shared`→`shared_sell_price`,
`spot`→`spot_price_margin` (marže nad spotem).

Vynechá se: `bom_mode`, `*_material_id`, `fve_materials` (technické/interní).

## 6. Vysvětlivky

Statický český text v šabloně (ne AI). Dvě úrovně:

- **`intro.html`** — odstavec „Jak číst tento report": co dokument obsahuje, jak je členěn,
  na co se dívat.
- **Popisky u sekcí** — 1–3 věty pod nadpisem (co tabulka/graf ukazuje, jak ho číst).
- **`glossary.html`** — pojmy: vlastní spotřeba, přetok/export, roční úspora, návratnost,
  diskontovaná návratnost, NPV, reinvestice, S&P500 benchmark.

Obsah navrhne asistent, uživatel doladí při review.

## 7. Frontend

### 7.1 Typy a klient

- `types.ts`: `FveParams` rozšířeno o `pdf_sections?: { customer?: string[]; company?: string[] }`;
  nový `ReportSectionMeta`.
- `api/fve.ts`:
  - `fetchReportSections()` → `GET /fve-analysis/report/sections`.
  - `downloadEnergyPdf(energy, economic, params, variant, sections)`.

### 7.2 UI

- `FveAnalysisResults.tsx` — podle role (`useAuth`/`hasAnyRole`):
  - firma: dvě tlačítka „PDF pro zákazníka" / „PDF pro firmu";
  - zákazník: jedno tlačítko „Stáhnout PDF" (zákaznická varianta, uložená volba, bez modalu).
- Nový `PdfSectionsModal.tsx` — seznam oddílů z metadat; základ zaškrtnutý a zamčený;
  volitelné přepínatelné; u všech šipky ↑/↓ pro pořadí; dole „Vygenerovat PDF".
- Perzistence: komponenta dostane `onSaveSections?(variant, ids)`.
  - V projektu (`ProjectFveAnalysis.tsx`) → sloučí `pdf_sections` do `params` a uloží
    přes stávající `PUT /projects/{id}/params`.
  - Mimo projekt → `localStorage` (`fve_pdf_sections`).

## 8. Bezpečnost a chybové stavy

- **Role:** server vynutí variantu; zákazník nemůže získat interní rozpis ani odesláním
  `variant="company"`. Základ oddílů vynucen vždy.
- **Chybějící ekonomika:** `needs_economic` oddíly se vynechají; UI ekonomiku dopočítá před
  exportem (stávající chování `downloadPdf`).
- **Neznámé id v `sections`:** ignorováno (žádný 500).
- **Prázdný/poškozený `params`:** fallback na defaulty; tabulka vstupů se vykreslí z defaultů.
- **Generování PDF:** stávající `try/except` → 500 s českou hláškou (beze změny).

## 9. Testy (TDD)

**Backend (`tests/reportgen/`):**
- `resolve_sections`: vynucení základu, ignorování neznámých, zachování pořadí.
- metadata endpoint: obsahuje `intro`…`glossary`, `base` příznaky.
- `_build_input_params`: správné labely/hodnoty, výběr ceny dle schématu, vynechání
  interních polí.
- render seznamu oddílů: zadané oddíly přítomné, ostatní nepřítomné (subset i reorder).
- zákaznická vs firemní `investment_composition` (agregát vs rozpis).
- endpoint: `customer` role se serverovým vynucením varianty; chybějící base se doplní.
- **regrese:** `generate_energy_report(data, economic)` bez varianty/sekcí == dnešní výstup.

**Frontend:**
- `tsc -b` + `npm run build` (jako dnes).
- E2E (Playwright): firma vygeneruje obě varianty; zákaznická nemá rozpis komponent a má
  agregát; vypnutý oddíl v PDF chybí; uložená volba se po reloadu předvyplní.

## 10. Dotčené soubory

**Backend:** `reportgen/report_sections.py` (nový), `reportgen/fve_router.py`,
`reporting.py`, `templates/energy_report.html` (obal), `templates/energy_sections/*.html` (nové),
`templates/base.html` (jen pokud potřeba).

**Frontend:** `types.ts`, `api/fve.ts`, `components/fve/FveAnalysisResults.tsx`,
`components/fve/PdfSectionsModal.tsx` (nový), `pages/ProjectFveAnalysis.tsx`,
`pages/FveAnalysis.tsx` (fallback).

## 11. Mimo rozsah

- Změna podoby firemního rozpadu investice (jen se přenáší jako dnes).
- Nové varianty (jazyk, jiné publikum).
- Editace vysvětlujících textů v UI (texty jsou statické v šabloně).
- Změna ekonomického modelu či ceníku.
