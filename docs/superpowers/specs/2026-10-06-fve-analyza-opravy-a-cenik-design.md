# FVE analýza — opravy 6 bodů + ceník materiálů jako zdroj investice

**Datum:** 2026-10-06
**Status:** schváleno uživatelem (2026-10-06, šest částí po jedné)
**Repo:** AntelonEnergy (fveAnalyzator) — `backend/` + `frontend-web/`
**Navazuje na:** `docs/superpowers/specs/2026-10-01-fve-analysis-design.md`

## 1. Cíl

Uživatel převzal hotovou FVE analýzu a nahlásil šest problémů. Tento dokument
definuje opravu všech šesti a s tím související přechod na **ceník materiálů
jako jediný zdroj investice**.

| # | Problém | Řešení |
|---|---------|--------|
| 1 | Uložení na kartě „Kontakt a uložení" padá (obě tlačítka) | úklid sirotků + `projects.active` místo tvrdého mazání |
| 2 | PDF nemá grafy ekonomiky, sekci ekonomiky a přílohy | Chrome do Dockerfile + sekce Ekonomika + Přílohy A–D |
| 3 | Ceny komponent jsou zahalené, mění se v čase | katalog Materiály + platnost cen dle data + snímek do `fve_params` |
| 4 | Produkce vypadá moc vysoká, default GPS není Ústí | teplotní ztráta + reálné optimum + Ústí nad Labem |
| 5 | Geocoding nenajde adresy, plete stejné názvy | Nominatim + výběr z více výsledků tlačítkem |
| 6 | Karta „Parametry" je jeden dlouhý seznam | pět dílčích karet |

## 2. Rozhodnutí z brainstormingu

| Téma | Volba |
|------|-------|
| Zdroj investice | **Výhradně materiály** — Σ cena × počet, včetně montáže a hotvých systémů |
| Persistence výběru | **Snímek** `fve_materials` v `fve_params_json` (nevolá se ceník zpětně) |
| kwHp a kapacita baterie | Zůstávají ruční vstup; **balíček je jen předvyplní**, cena je cena balíčku |
| Nový základ | **10 kWp + 10 kWh = 300 000 Kč** (bylo 350 000) |
| Staré analýzy | **Beze změny** — fallback 350 000 Kč, žádné zpětné úpravy |
| Seed cen | Asistent navrhne čísla laděná na 300 000, uživatel je opraví v Materialy před nasazením. **Konkrétní typy dodavatelů se neseedují** — vytváří pracovníci |
| RBAC zápis do ceníku | `POST/PUT /materials`, `POST /materials/{id}/price` = **jen `admin`, `antelon`** — `buyer` nesmí měnit ceny |
| RBAC čtení ceníku | `GET /materials` beze změny = `admin, antelon, buyer, warehouse` |
| RBAC FVE endpointů | `ANY_ROLE` rozšířit o **`buyer`** („Buyer si muze ulozit vypocet") |
| RBAC převod na zakázku | `require_roles("admin", "antelon", "sales")` — odpovídá `pipeline_seed.ALLOWED_LEAD` |
| Odvozování počtů | Backend, jediná čistá funkce `derive_qty(category, rating, params)` |
| Geocoder | **Nominatim (OSM)** místo Open-Meteo, výsledky jako tlačítka k výběru |
| Default GPS | **Ústí nad Labem (50.6607, 14.03227)** |
| Budoucí mazání projektů | **Deaktivace `projects.active = 0`**, ne tvrdé mazání |
| `PRAGMA foreign_keys` | **Odloženo** — vynucení by vyžadovalo mazat docházkové a fakturační řádky |

## 3. Část 1 — Data a schéma

### 3.1 `materials` — nové sloupce

Stávající `Material` má jen `code,name,unit,price,active,created_at`. Tabulka
je **prázdná (0 řádků)**, takže seed je bezpečný.

| Sloupec | Typ | Default | Význam |
|---------|-----|---------|--------|
| `category` | `String(30)` | `'other'` | `panel` \| `inverter` \| `battery` \| `install` \| `system` \| `other` |
| `visibility` | `String(20)` | `'public'` | `public` = vidí zákazník, `internal` = jen pracovníci |
| `rating` | `Float` | `NULL` | výkon: Wp u panelů, kW u měničů, kWh u baterií |
| `supplier` | `String(120)` | `NULL` | konkrétní typ dodavatele, `NULL` = základní/generický |
| `is_default` | `Boolean` | `False` | předvyplněná volba ve formuláři |
| `system_kwp` | `Float` | `NULL` | jen `category='system'`: předvyplní `kwp` |
| `system_battery_kwh` | `Float` | `NULL` | jen `category='system'`: předvyplní `battery_capacity` |

Sloupce se přidávají přes `ALTER TABLE` v `_migrate` (vzor: `type`, `status`) +
deklarace v modelu pro `create_all` na čerstvé DB. Pořadí v `init_db` je
`_migrate(eng)` → `Base.metadata.create_all(eng)`, takže obě cesty se kryjí.

### 3.2 `material_prices` — platnost cen dle datumu

```
id            INTEGER PK
material_id   INTEGER FK -> materials.id  ON DELETE CASCADE
price         FLOAT    NOT NULL
valid_from    DATE     NOT NULL
valid_to      DATE     NULL        -- NULL = stále platí
created_by    INTEGER  FK -> users.id  ON DELETE SET NULL
created_at    DATETIME
```

Index na `(material_id, valid_from)`.

Cena se vybírá jako nejnovější řádek, kde `valid_from <= dnes` a
(`valid_to IS NULL` nebo `valid_to >= dnes`).

### 3.3 `Material.price` zůstává

Zůstává jako denormalizovaná „aktuální" cena, udržovaná **jedinou** helper
funkcí `set_material_price(db, material_id, price, valid_from, created_by)`:

1. uzavře předchozí otevřený řádek (`valid_to = valid_from - 1 den`)
2. vloží nový řádek
3. přepíše `materials.price`

Žádný jiný kód nesmí psát do `materials.price` ani do `material_prices`.
Existující `POST /materials` (který nastavuje `price` při vytvoření) půjde
přes stejnou helper funkci.

### 3.4 Seed — idempotentní, jen když je tabulka prázdní

Vzor: `storage._seed_rate_cards()`. Podmínka = `db.query(Material).count() == 0`.

| Code | Název | Cat | Rating | Cena (Kč) |
|------|-------|-----|--------|-----------|
| `PAN-450` | Panel 450 Wp | panel | 450 | 2 000 |
| `PAN-550` | Panel 550 Wp | panel | 550 | 2 500 |
| `PAN-615` | Panel 615 Wp | panel | 615 | 2 800 |
| `INV-10` | Měnič 10 kW | inverter | 10 | 45 000 |
| `INV-15` | Měnič 15 kW | inverter | 15 | 62 000 |
| `INV-20` | Měnič 20 kW | inverter | 20 | 78 000 |
| `BAT-5` | Baterie 5 kWh | battery | 5 | 48 000 |
| `BAT-10` | Baterie 10 kWh | battery | 10 | 87 500 |
| `BAT-15` | Baterie 15 kWh | battery | 15 | 125 000 |
| `INS-MONT` | Montáž instalace | install | — | 120 000 |
| `SYS-10-10` | FVE 10 kWp / 10 kWh | system | — | 300 000 |
| `SYS-15-10` | FVE 15 kWp / 10 kWh | system | — | 349 000 |

`visibility='public'` u všech, `is_default=True` u `PAN-550`, `INV-10`,
`BAT-10`, `INS-MONT`, `SYS-10-10`.

**Kontrolní součet musí být přesně 300 000 Kč:**
`19 × 2 500 + 45 000 + 87 500 + 120 000 = 47 500 + 45 000 + 87 500 + 120 000 = 300 000`

`19 ks` je `ceil(10 kWp × 1000 / 550) = ceil(18.18) = 19` — viz `derive_qty`.

Ceny jsou **návrh k opravě uživatelem v Materialy před nasazením**. Konkrétní
typy dodavatelů („Solar Sofar HYD 10KTL") se neseedují, vytváří pracovníci.

## 4. Část 2 — API a viditelnost

### 4.1 Nový endpoint pro FVE formulář

`GET /api/v1/fve-analysis/materials` → `require_roles("admin", "antelon", "sales", "customer", "buyer", "warehouse")`
(přesný výčet dle `ANY_ROLE` rozšířeného o `buyer` — viz 4.3)

Odpověď:

```json
{ "materials": [ { "id", "code", "name", "category", "visibility",
                   "rating", "unit", "price", "is_default",
                   "system_kwp", "system_battery_kwh" } ] }
```

**Filtruje se podle `is_internal_user`** (`any(r != "customer" for r in roles)`):

- interní uživatel → všechny řádky včetně `visibility='internal'`
- `customer` → **jen `visibility='public'`**

### 4.2 Stávající endpointy materiálů

| Endpoint | Role | Změna |
|----------|------|-------|
| `GET /materials` | `admin, antelon, buyer, warehouse` | beze změny |
| `POST /materials` | `admin, antelon` | **bylo `admin, buyer` → zúžit** |
| `PUT /materials/{id}` | `admin, antelon` | **nový** (dnes chybí) |
| `DELETE /materials/{id}` | `admin, antelon` | **nový** — soft, `active=0` |
| `POST /materials/{id}/price` | `admin, antelon` | **nový** — volá `set_material_price` |

`Materialy.tsx`: `canManage = hasAnyRole(user, ["admin", "antelon"])`
(dnes `["admin", "buyer"]`).

### 4.3 Rozšíření `ANY_ROLE`

`fve_router.py:37` — dnes `require_roles("admin", "antelon", "customer")`.
**Přidat `"buyer"`,** aby si obchodník mohl uložit výpočet.

### 4.4 `convert-to-order`

`fve_router.py:268` — dnes `if is_internal_user(user)`, přestože docstring
tvrdí „Pouze admin/antelon — je to obchodní rozhodnutí". Přepnout na:

```python
require_roles("admin", "antelon", "sales")
```

Role `sales` existuje (`storage.ROLES`), má sazebník (500 Kč/h) a
`pipeline_seed.ALLOWED_LEAD = ["admin", "antelon", "sales"]` — převod na
zakázku je stejné rozhodnutí jako přiřazení leada.

Tlačítko *Vytvořit zakázku a pokračovat* se na kartě Kontakt zobrazuje jen pro
tyhle tři role. `buyer` může uložit rozpracovanou analýzu, ale nepřevést ji.

## 5. Odvozování počtů — `derive_qty`

Jediná čistá funkce, **na backendu** (frontend jen zobrazuje výsledek):

```python
def derive_qty(category: str, rating: float | None, params: dict) -> float:
    """Počet kusů dané komponenty pro definovaný výkon elektrárny."""
    kwp = float(params.get("kwp", 10.0))
    if category == "panel":
        if not rating: return 0.0
        return math.ceil(kwp * 1000 / rating)
    if category == "inverter":
        if not rating: return 0.0
        return math.ceil(kwp / rating)
    if category == "battery":
        kap = float(params.get("battery_capacity", 0.0))
        if not rating: return 0.0
        return math.ceil(kap / rating)
    if category in ("install", "system"):
        return 1.0
    return 1.0
```

- `panel`: `ceil(kWp × 1000 / Wp)`
- `inverter`: `ceil(kWp / kW)`
- `battery`: `ceil(kapacita / kWh)`
- `install`, `system`, `other`: `1`

## 6. Část 3 — Formulář FVE

### 6.1 Přepínač sestavy

Nové pole `FveParams`:

```python
bom_mode: str = "components"   # "system" | "components"
```

- **`system`** — vybere se jedna položka `category='system'`; cena = cena
  balíčku; `kwp` a `battery_capacity` se předvyplní z `system_kwp` /
  `system_battery_kwh` (uživatel je může dál měnit, **cena se nepřepočítá**)
- **`components`** — vyberou se jednotlivé komponenty, ceny se vynásobí
  počty z `derive_qty` a sečtou

### 6.2 Nová pole `FveParams`

```python
bom_mode: str = "components"
fve_materials: list[dict] = []     # [{material_id, code, category, qty, unit_price, line_total}]
panel_material_id: int | None = None
inverter_material_id: int | None = None
battery_material_id: int | None = None
install_material_id: int | None = None
system_material_id: int | None = None
```

Snímek `fve_materials` se ukládá do `fve_params_json` při uložení analýzy —
později se ceník nevytahuje zpětně, takže se analýza nepromění, když pracovník
změní cenu.

### 6.3 Karty

Stávajících pět sekcí `FveAnalysisForm.tsx` (řádky 106, 116, 129, 165, 239)
se **nemění obsahově**, jen se rozdělí na dílčí karty:

1. **Fotovoltaická elektrárna + Spotřeba a ceny + Prodej přebytků**
2. **Umístění a pokročilé parametry**
3. **Spotřebiče v domácnosti**

Karta *Umístění* dostává výběr geocodingu (viz část 5).

### 6.4 Živý součet

V kartě s komponentami se zobrazuje **Celková investice** — Σ
`line_total` přepočítaná při každé změně `kwp` / `battery_capacity` / výběru
komponenty.

## 7. Část 4 — Ekonomika a PDF

### 7.1 Chrome pro kaleido (kořenová příčina chybějících grafů)

Kontejner je **Debian 13 (trixie)** — kvůli přechodu na 64bitový `time_t` se
jinak jmenují balíčky (`libasound2t64`, `libatk1.0-0t64`, `libcups2t64`).
Všech 18 názvů níže ověřeno přes `apt-cache show` na trixie.

Ověřený stav kontejneru: 8 z 9 knihoven pro headless Chrome **chybí**
(chybí `libnss3`, `libatk-bridge`, `libgbm`, `libasound`, `libxkbcommon`,
`libXcomposite`, `libdrm`, `libcups`; `libpango` je). `ca-certificates`
je, `HOME=/root`.

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    <stávající závislosti WeasyPrint> \
    libnss3 libnspr4 libatk1.0-0t64 libatk-bridge2.0-0t64 libatspi2.0-0t64 \
    libcups2t64 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2t64 libx11-6 libxcb1 libxext6 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt
RUN plotly_get_chrome -y
```

- `fonts-liberation` je záměrně — bez písma vykreslí Chrome do grafů místo
  popisků os prázdné čtverce.
- `plotly_get_chrome` **musí být po `pip install`**, protože CLI pochází z kaleido.
- Image naroste z 1,16 GB o zhruba 250–300 MB.

### 7.2 Viditelnost chyb

`reporting.py:60` loguje `print(f"...: {e}")` — a když `str(e)` začíná dvěma
novými řádky, vypadá to v logu jako prázdná hláška (přesně to zmátlo
vyšetřování). Přepsat na `logging` s `type(e).__name__` na třech místech:
pět grafů, investiční graf, výjimka z `energy_pdf`.

### 7.3 Payload PDF

`downloadEnergyPdf(energy, economic)` → `POST /fve-analysis/report/energy`:

```json
{ "energy": {...}, "economic": {...} | null }
```

`ReportGenerator.generate_energy_report(data, economic=None)` — druhý parametr
explicitně, nekecáme klíč do vstupního slovníku. Chybějící `economic` = sekce
se vynechá (chování jako dnes).

### 7.4 Složení investice

`run_economic_analysis` navíc vrátí:

- `investment_cost` — vypočtená investice
- `investment_breakdown` — pole `fve_materials` z parametrů

PDF z toho sestaví tabulku *Komponenta · Výkon · Počet · Cena/ks · Celkem* s
řádkem CELKEM. BOM se tedy neposílá zvlášť — nese ho ekonomická odpověď.

### 7.5 Pořadí šablony `energy_report.html`

**Hlavní část:**

1. Souhrnné výsledky
2. Vstupní parametry
3. Měsíční statistika výroby a spotřeby (graf)
4. Energetická bilance (+4 grafy)
5. Měsíční bilance
6. Doporučené strategie a scénáře
7. **Nově: Ekonomická analýza** — souhrnné metriky + graf investice + tabulka
   složení investice

**Přílohy** na vlastní stránce (`break-before: page`, WeasyPrint podporuje):

- **Příloha A** — Detail Spotřebičů (ročně)
- **Příloha B** — Měsíční bilance spotřebičů (kWh)
- **Příloha C** — Detail nastavení spotřebičů
- **Příloha D** — Ekonomický plán po jednotlivých letech

Tabulka D vychází z `economic.raw_data`, 6 sloupců, aby se vešly na A4:

`Year` · `PV_Cumulative_CashFlow` · `PV_Reinvest_Net_Result` ·
`PV_Cumulative_DCF` · `SP500_Total_Value` · `SP500_Net_Result`

### 7.6 `compute_investment_cost`

```python
def compute_investment_cost(params) -> float:
    bom = params.get("fve_materials")
    if bom:                                    # nové analýzy — snímek
        return sum(float(l.get("line_total", 0)) for l in bom)
    if "investment_cost" in params:            # explicitní zadání
        return float(params["investment_cost"])
    return 350_000.0                           # legacy — staré analýzy beze změny
```

Nahradí `float(_p("investment_cost", 350000.0))` v `run_economic_analysis:477`.

### 7.7 Frontend

- `FveAnalysisResults` dostane **`params` jako prop** (z `FveAnalysis.tsx` i
  `ProjectFveAnalysis.tsx`)
- `loadEconomic` pošle `{...params, annual_savings: result.financial_balance.annual_savings_czk}`
- `downloadPdf` nejdřív zajistí, že ekonomika existuje (spočítá ji, když
  chybí), teprve pak exportuje
- Na kartě Výsledky přibude metrika **Investice**

### 7.8 Refactor kvůli testovatelnosti

`generate_energy_report` rozdělit na `_build_context(data, economic)` a
samotné vykreslení — context se pak testuje bez WeasyPrint i bez kaleida.

## 8. Část 5 — Výpočet produkce a geocoder

### 8.1 Výchozí GPS → Ústí nad Labem (50.6607, 14.03227)

Osm míst v runtime kódu, mění se všechna:

| Soubor | Míno |
|--------|------|
| `backend/app/fve_analysis.py:55-56` | `_DEFAULTS` |
| `backend/app/reportgen/fve_router.py:54-55` | `FveParams` |
| `frontend-web/src/api/fve.ts:63-64` | `DEFAULT_FVE_PARAMS` |
| `backend/app/reporting.py:80-81` | fallback šablony |
| `backend/app/reportgen/fve_wrap.py:24-25` | fallback čtení parametrů |
| `backend/app/data_loader.py:45` | signatura `load_production_data` |
| `backend/main.py:197` | spot-profitabilita |
| `backend/app/reportgen/fve_wrap.py:140` | spot-profitabilita |

`verify_tmy*.py` — vývojové skripty, **neměnit**.
`tests/reportgen/test_fve_analysis.py:33` assertuje `(50.0880, 14.4208)` →
přepsat na Ústí. Ostatní testy jsou jen relativní, změna je nerozbije.

### 8.2 Teplotní ztráta (bod 4a)

`pv_calculator.py:143` počítá `cell_temp` přes `pvlib.temperature.faiman` a
hoď ho. Ověřit na čistou testovatelnou funkci:

```python
TEMP_COEFF_PER_C = -0.004     # −0.4 %/°C pro Pmax, typické pro mono PERC

def apply_temperature_derate(production, cell_temp, coeff=TEMP_COEFF_PER_C):
    return production * (1 + coeff * (cell_temp - 25.0))
```

Aplikuje se na DC výkon **před** násobením `system_loss_factor`. Není to
parametr v UI — konstanta v modulu.

**Riziko dvojitého započtení:** pokud 14% `system_loss_factor` už teplotu
obsahuje, je to dvojité započtení. Proto se po zapojení **změří skutečná roční
produkce pro Ústí a porovná s PVGIS SARAH3** pro tytéž souřadnice a sklon.
Odhad dopadu −4 až −6 %, tedy z 1125 na ~1070 kWh/kWp.

### 8.3 Referenční optimum (bod 4b)

`get_optimal_pv_production` bere `surface_tilt=latitude` (50°) a
`winter_loss_factor=None` → `production_performance_pct = 101,9 %`, což je
nesmysl. Oprava:

1. prohledat sklon 10–70° po 5° při azimutu 180°, vzít maximum
   (azimut v ČR optimalizovat netřeba, jižní je optimální)
2. propustit `winter_loss_factor`, aby se lišila **jen** orientace

Výsledek nikdy nepřekročí 100 %. Cena: 13 výpočtů nad týmž načteným
počasím, bez HTTP, ~0,3 s.

### 8.4 Geocoder → Nominatim (bod 5)

`backend/app/geocoder.py` přepsat na:

```python
def search(address: str, limit: int = 6) -> list[dict]:
    """Více výsledků z Nominatim (OSM). Vrací [] když nic není."""
```

- `GET https://nominatim.openstreetmap.org/search`
- parametry: `q`, `format=jsonv2`, `limit`, `addressdetails=1`
- hlavičky: **`User-Agent: antelon-energy/1.0`** (povinný podle politiky OSM),
  `Accept-Language: cs`
- `timeout=10`, `raise_for_status()`
- malá paměťová mezipaměť (opakované hledání se neopakuje)
- `get_coordinates` **zrušit** — jediný volající je `fve_router.py:136-144`

Ověřeno: Nominatim funguje z kontejneru, „Varvažov 210 Telnice" → 1 přesná
shoda, „Telnice" → 2 výsledky rozlišené krajem.

**Kontrakt endpointu** `POST /fve-analysis/geocode`:

- **200 + `{"results": [...]}`** — prázdný seznam = nenalezeno
- **400** — prázdný vstup (zůstává)

Důvod změny z 404: s Nominatim se „Vodičkova 5" **najde**, takže 404 jako
„nenalezeno" přestává dávat smysl.

**Frontend** (`FveGeocode` → `FveGeocodeResult[]`) — v kartě *Umístění*:

- po hledání výpis tlačítek, každé = `display_name` (plná hierarchie
  „Telnice, okres Brno-venkov, Jihomoravský kraj, Česko") + souřadnice
- klik nastaví lat/lon a zvýrazní vybranou variantu
- prázdný výsledek → „Nebylo nalezeno žádné místo pro „…""
- **odstranit** nápovědu „Hledá se obec, ne ulice" — s Nominatim to není pravda
- tlačítko je disabled po dobu `geocoding` (ochrana proti < 1 req/s)

## 9. Část 6 — Oprava ukládání (bod 1)

### 9.1 Kořenová příčina

`PRAGMA foreign_keys` **není v backendu nastavený ani jednou** → SQLite default
`OFF` → `ON DELETE CASCADE`, který model deklaruje na `project_users`, nikdy
nevyplní.

Stav živé `data/reportgen.db`:

- `project_users` — 4 sirotci `(37,7)`, `(38,8)`, `(39,9)`, `(40,10)`
- `project_steps` — 32 sirotků (16 pro projekt 37, 16 pro 38)
- `projects` MAX(id)=36, `users` MAX(id)=6 → další INSERT do `project_users`
  je **přesně `(37,7)`** → `UNIQUE constraint failed` na `project_users`
- `uq_project_step` by zablokoval i kroky, protože id 37 a 38 se opět použijí
- `PRAGMA foreign_key_check` hlásí všech 36 porušení (4 + 32)

Obojí tlačítka na kartě Kontakt prochází přes `save_analysis`, proto padají obě.

### 9.2 Úklid stávajících sirotků

**Ti se deaktivovat nedají** — rodičovský řádek neexistuje, není ke komu
přiřadit `active = 0`. Je to řádek odkazující do prázdna, datově mrtvý.

V `_migrate`, stejně idempotentní a stejně chráněné existencí tabulek jako
ostatní větve: projít `PRAGMA foreign_key_check` a smazat hlášené řádky podle
`rowid`, seskupené podle tabulky. Zachytí oba směry `project_users` i cokoli
jiného bez hardcodovaného seznamu tabulek.

**Před nasazením jednoruční záloha:**
`cp data/reportgen.db data/reportgen.db.bak-2026-10-06`
V kódu zálohu nedělat — `_migrate` běží každý start.

### 9.3 Budoucí mazání → deaktivace

Nový sloupec `projects.active` (`Boolean`, default `True`):

- `type` a `status` se v `_migrate` přidávají přes `ALTER TABLE` — vzor existuje
- čerstvá DB dostane sloupec z `create_all`, existující z `_migrate`
- název odpovídá `Material.active`, `RateCard.active`, `PipelineTemplate.active`

`DELETE /projects/{id}` nastaví `active = 0` místo `db.delete(p)`.

Proč deaktivace a ne tvrdé mazání:

1. `DELETE` by vymazal `invoice_items`, `time_entries`, `pdf_versions` — tedy
   **fakturační a docházkové záznamy**. Dnes to s vypnutým FK stejně
   nesmaže, jen odstraní řádek v `projects` a nechá sirotky.
2. **ID se nikdy neuvolní** → ke kolizi `(37,7)` nemůže dojít znovu.
3. Odpadá zapínání `PRAGMA foreign_keys` i osmitabulková kaskáda.

**Místa, kde se musí filtrovat `active = 1`:**

- `GET /projects` — obě větve výpisu (`router.py:161`, `:164-166`)
- `_ensure_project_access` → **404**, čímž se jedním řádkem zablokuje ~15
  endpointů podle `id`
- lookup podle `share_code` (`router.py:364`, `:377`) — `_ensure_project_access`
  **nepoužívají**, jinak by veřejný odkaz na smazaný projekt dál fungoval
- `convert_to_order` (`fve_router.py:271`)

### 9.4 `remove_step` zůstává tvrdé mazání

Důvod: `uq_project_step` na dvojici `(project_id, step_id)`. Kdyby se krok jen
deaktivoval, opětovné `add_step` by spadlo na unique constraint.

Přidat ale `UPDATE project_materials SET step_id = NULL` — ať se kvůli smazání
kroku neztratí záznamy materiálů.

### 9.5 `PRAGMA foreign_keys` — ODLOŽENO

Děti `project_steps` jsou v modelu i v živé DB `NO ACTION` a sloupce jako
`time_entries.step_id` **nejsou nulovatelné**, takže vynucení FK by znamenalo
**mazat docházkové a fakturační řádky**, jen aby to prošlo.

`remove_step` je jediná zbývající mazací cesta. Zbylé vzácné sirotky zachytí
sweep při dalším startu. Zapínání FK = samostatný follow-up až po udělání
nulovatelných sloupců.

## 10. Testy

### 10.1 Nové

| Test | Co ověřuje |
|------|-----------|
| `test_report_pdf.py` — kontext | „Ekonomická analýza" a Přílohy A–D jsou v contextu, když `economic` je; nejsou, když není |
| `test_report_pdf.py` — grafy | všech 6 grafů se do contextu dostane (mock na `pio.to_image`) |
| `test_report_pdf.py` — odolnost | když `to_image` spadne, PDF se stejně vygeneruje |
| `compute_investment_cost` | 300 000 (default seed) / 350 000 (legacy) / explicitní |
| `derive_qty` | panel 19 ks, měnič 1 ks, baterie 1 ks, instalace 1 ks |
| `set_material_price` | uzavře starý řádek, vloží nový, přepíše `materials.price` |
| defaulty shoda | `DEFAULT_FVE_PARAMS` (parsované z `.ts`) == `_DEFAULTS` == `FveParams` |
| `apply_temperature_derate` | při `cell_temp > 25` je výsledek nižší |
| optimum | syntetické počasí přes `weather_data`, optimum ≥ libovolný sklon |
| geocode kontrakt | 200 + `results`, 400 pro prázdný vstup |
| geocode unit (mock) | `User-Agent` hlavička, `limit=6`, parsování dvou výsledků |
| RBAC materiály | `buyer` nesmí `POST /materials`; `customer` nevidí `internal` |
| RBAC FVE | `buyer` smí uložit analýzu |
| RBAC převod | `sales` smí, `buyer` a `customer` ne |
| **sirotci** | uměle vložený sirotek → `init_db` → sweep → prázdné |
| **delete projekt** | `foreign_key_check` prázdný, `project_users`/`project_steps` prázdné |
| **ulož → smaž → ulož** | druhé uložení projde (přímý test bodu 1) |
| **deaktivace** | smazaný projekt není v seznamu, `share_code` vrací 404 |

### 10.2 Přepisovat

- `test_geocode_finds_city` → `r.json()["results"]` neprázdné
- `test_geocode_explains_itself_when_not_found` → dnes čeká 404 pro
  „Vodičkova 5"; s Nominatim to bude 200 s výsledky → použít nesmyslný
  řetězec a čekat prázdný seznam
- `test_fve_analysis.py:33` → výchozí souřadnice Ústí

### 10.3 Omezení

- Testy běží na hostu (`./venv/bin/python -m pytest`), kde **Chrome není** →
  `pio.to_image` se v testech mockuje. WeasyPrint 67.0 na hostu je.
- Živé geocode testy zůstávají živé (osvědčený vzor v repu).

## 11. Závěrečné ověření

1. `./venv/bin/python -m pytest` — 154 testů musí zůstat zelených + nové
2. `cd frontend-web && npx tsc -b && npm run build`
   (nestačí — build nechytá render chyby)
3. `docker compose build backend` → ověřit Chrome a `pio.to_image`
4. Browser přes playwright, aserce na DOM a text PDF, **ne na screenshoty**:
   - `zakaznik` → nová analýza → uložit rozpracovanou (200, projekt v seznamu)
   - `admin` → Vytvořit zakázku (a ověřit, že `buyer` tlačítko nevidí)
   - výsledky → export PDF → text obsahuje „Ekonomická analýza",
     „Příloha A", „Příloha D" a víc obrázků než dnes
   - geocoder „Varvažov 210 Telnice" → ≥1 výsledek; „Telnice" → ≥2 výsledky;
     klik na variantu → lat/lon se nastaví
   - nový formulář ukazuje Ústí (50.6607, 14.03227)
   - změřená produkce proti PVGIS SARAH3
5. Materiály: seed vytvořený, kontrolní součet přesně 300 000 Kč

## 12. Soubory

### Backend — vytvořit
- `backend/app/reportgen/materials_service.py` — `derive_qty`, `set_material_price`, `compute_investment_cost`
- `tests/reportgen/test_report_pdf.py`

### Backend — upravit
- `backend/app/reportgen/storage.py` — sloupce `Material`, `MaterialPrice`, `Project.active`, `_migrate` (ALTER + sweep), seed materiálů
- `backend/app/reportgen/fve_router.py` — `FveParams`, `ANY_ROLE` + buyer, geocode endpoint, `convert-to-order`, `compute_investment_cost`
- `backend/app/reportgen/pipeline_router.py` — endpointy materiálů, RBAC, `remove_step`
- `backend/app/reportgen/router.py` — `delete_project` deaktivace, filtry `active`, `share_code` lookupy
- `backend/app/reporting.py` — `_build_context`, logování chyb, sekce Ekonomika + Přílohy
- `backend/app/fve_analysis.py` — `_DEFAULTS` Ústí, `compute_investment_cost`
- `backend/app/pv_calculator.py` — `apply_temperature_derate`, optimum sken
- `backend/app/geocoder.py` — přepis na Nominatim
- `backend/app/data_loader.py` — defaulty Ústí, propuštění `winter_loss_factor` do optimum
- `backend/templates/energy_report.html` — pořadí + Ekonomika + Přílohy A–D
- `Dockerfile` — Chrome + knihovny

### Frontend
- `frontend-web/src/api/fve.ts` — `DEFAULT_FVE_PARAMS`, `downloadEnergyPdf(energy, economic)`, `geocode`
- `frontend-web/src/types.ts` — `FveGeocodeResult`, `FveParams` nová pole
- `frontend-web/src/components/fve/FveAnalysisForm.tsx` — karty, přepínač sestavy, geocode picker
- `frontend-web/src/components/fve/FveAnalysisResults.tsx` — `params` prop, investice, export
- `frontend-web/src/components/fve/ContactStep.tsx` — tlačítko podle rolí
- `frontend-web/src/pages/FveAnalysis.tsx`, `ProjectFveAnalysis.tsx` — předání `params`
- `frontend-web/src/pages/Materialy.tsx` — `canManage` admin/antelon, platnost cen

### Data
- `data/reportgen.db` — záloha před nasazením + čištění sirotků
