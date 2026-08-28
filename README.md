# fveAnalyzator

## Popis / Description

Tento nástroj poskytuje hloubkovou analýzu proveditelnosti realizace fotovoltaické elektrárny (FVE) pro zákazníky Antelon Energy s.r.o. (dříve Rabiav) a zahrnuje:

1. **FVE Analyzer** — deep analysis of PV system feasibility (ROI, NPV, energy flow, ekonomické porovnání).
2. **NZÚ 2026 Calculator** — standalone kalkulačku dotací programu "Nová zelená úsporám" (viz [nz2026-calculator/](nz2026-calculator/README.md)).
3. **ReportGen** — generátor PDF reportů (Antelon Pentagon 16:9 + fveAnalyzator Energy/Economic/OTE).

This project provides a comprehensive toolkit for analyzing PV power plant feasibility and green subsidy calculations.

## Klíčové Funkce

- **Analýza toků energie**: Detailní bilance spotřeby, výroby, využití baterie a interakce se sítí.
- **Ekonomická analýza**:
  - Výpočet návratnosti (ROI), Čisté současné hodnoty (NPV).
  - Porovnání s alternativními investicemi (S&P 500) a scénářem bez FVE (pouze platby za energie).
- **Realistické modelování FVE**:
  - Využívá data **PVGIS TMY (Typical Meteorological Year)** pro konkrétní lokalitu. Křivky výroby tak odpovídají reálným historickým podmínkám (včetně zatažených dní a sezónních výkyvů), nikoliv jen teoretickému ideálu.
  - Konfigurovatelné ztráty systému a zimní penalty.
- **Pokročilá simulace spotřebičů**:
  - **Iterativní Net Surplus**: Spotřebiče jsou spínány sekvenčně na základě čistého dostupného přebytku.
  - **Chytré nabíjení EV**: Podpora strategií (Týdně, Denně, Víkendy) s definovanými kapacitami baterií (např. Jaecoo ~18kWh, Enyaq ~60-80kWh).
  - **Realistický "Fallback"**: Spotřebiče jako pračka a sušička se automaticky spustí ze sítě ve večerních hodinách, pokud nebyla během dne dostatečná výroba FVE.
- **Ukládání nastavení**: Možnost uložit aktuální parametry analýzy do JSON souborů pro pozdější použití.
- **Hloubková vizualizace**:
  - **Sunburst grafy**: Interaktivní hierarchický rozpad energie a úspor (Celkem -> Vlastní spotřeba -> Spotřebič).
  - **Treemaps**: Vizualizace podílníků na odběru ze sítě.
  - **Vylepšené UI/UX**: Responzivní tabulky, indikátory načítání (spinners) pro dlouhé operace.
- **Reporting a Exporty**:
  - **PDF**: Generování komplexních PDF reportů (Energetický, Ekonomický, OTE).
  - **Excel (XLSX)**: Detailní exporty všech tabulek a vstupních parametrů pro další analýzu.

## Použité Technologie

- **Jazyk**: Python 3.12+
- **Frontend**: Streamlit + React (Vite TS, Tailwind)
- **Backend API**: FastAPI
- **Zpracování dat**: Pandas, NumPy, pvlib
- **Vizualizace**: Plotly, Kaleido, Matplotlib
- **Reporting**: WeasyPrint, Jinja2
- **Kontejnerizace**: Docker, Nginx

## Instalace a Spuštění

### 1. Docker (Doporučeno)

Nejjednodušší způsob pro spuštění celé aplikace.

1. **Zkontrolujte volné porty** (aktuální compose používá 3000, 8051, 8550 — 8050 je obsazený jiným projektem):

    ```bash
    ss -tln | grep -E "3000|8051|8550"
    ```

2. **Sestavte a spusťte kontejnery:**

    ```bash
    docker compose up --build -d
    ```

3. **Otevřete aplikaci:**
    - ReportGen Web (React): [http://localhost:3000](http://localhost:3000)
    - Backend API (FastAPI): [http://localhost:8051/docs](http://localhost:8051/docs)
    - Frontend (Streamlit, legacy): [http://localhost:8550](http://localhost:8550)

    Výchozí admin: `admin@antelon.local` / `Admin123!` (nastavitelné přes `.env`: `RG_ADMIN_EMAIL`, `RG_ADMIN_PASSWORD`, `RG_JWT_SECRET`, `RG_PUBLIC_URL`).

### 1b. ReportGen — generátor PDF reportů (nový modul)

Nový modul `backend/app/reportgen` + `frontend-web`:

- **Šablona Antelon** (Pentagon v2, 16:9): z CSV Shelly datalogeru (`Fáze A/B/C`, `Celkem`, `Time, V` / `Čas, Wh`, BOM, `0`=chybí). Podporuje 1 i více CSV (více měsíců se sloučí), denní + volitelně hodinový/15min profil. Přímá editace textů a vypínání sekcí, fotogalerie, QR sdílení.
- **Šablony fveAnalyzator**: wrap existujících Energy/Economic/OTE reportů (WeasyPrint).
- **Role**: `admin` (správa uživatelů/spotřebičů), `antelon` (všechny projekty, čistý PDF), `customer` (jen přiřazené projekty, čistý PDF), `anonymous` (teaser náhled `/p/{code}`, PDF s vodoznakem). Blur pro `teaser`/`internal` sekce.
- API: `/api/v1/*` — auth, projekty, upload, data preview, generate, pdf download, share/QR, public preview, OTE, admin.

Viz `docs/superpowers/specs/2026-08-28-reportgen-design.md`.

### 2. Lokální Vývoj

1. **Vytvořte virtuální prostředí:**

    ```bash
    python3 -m venv venv
    source venv/bin/activate  # Windows: venv\Scripts\activate
    ```

2. **Nainstalujte závislosti:**

    ```bash
    pip install -r requirements.txt
    ```

3. **Spusťte Frontend:**

    ```bash
    streamlit run frontend-streamlit/app.py
    ```

    *(Poznámka: Pro plnou funkčnost musí běžet i backend, např. přes `uvicorn backend.main:app --reload`)*

## Integrace Dat (Spotové ceny OTE)

Projekt obsahuje sadu skriptů pro správu dat z OTE-CR. Pro uživatele je připraven jediný sjednocující skript.

1. **Aktualizace dat**:

    ```bash
    python3 run_ote_update.py
    ```

    Tento skript automaticky:
    - Stáhne chybějící data pro roky **2019 až 2026**.
    - Podporuje "chytrou" inkrementální aktualizaci (stahuje/zpracovává jen nové dny).
    - Aktualizuje lokální SQLite databázi `data/spot_market.db`.

    *Poznámka: Pro starší roky (2019-2022) může skript upozornit na chybějící kurzovní lístky CNB pokud nejsou staženy, v tom případě použije bezpečný fallback kurz.*

## Testování

Projekt obsahuje E2E testy využívající framework **Playwright**.

### 1. Instalace prohlížečů

Při prvním spuštění je nutné nainstalovat prohlížeče (Chromium):

```bash
# Vstup do venv
source venv/bin/activate

# Instalace
playwright install chromium
```

### 2. Spuštění testů

Testy předpokládají běžící aplikaci na `http://localhost:8550`.

```bash
# Spuštění testů
pytest tests/test_e2e.py
```

## Architektura (Komunikační Matice)

```mermaid
graph TD
    User((Uživatel))
    Streamlit[Streamlit Aplikace]
    FastAPI[FastAPI Backend]
    Analyzer[Modul Analýzy]
    DataLoader[Načítání Dat]
    PVCalculator[Solární Výpočty (pvlib)]
    Visualizer[Vizualizace]
    Reporter[Generování PDF]
    Data[(Datové Zdroje - OTE, PVGIS)]

    User -->|Ovládá| Streamlit
    Streamlit -->|REST API| FastAPI
    FastAPI -->|Počítá| Analyzer
    FastAPI -->|Čerpá data| DataLoader
    FastAPI -->|Vykresluje| Visualizer
    FastAPI -->|Tvoří report| Reporter
    
    DataLoader -->|API| PVCalculator
    DataLoader -->|SQL/CSV| Data
    
    Analyzer -->|Simulace| DataLoader
    Visualizer -->|Data| Analyzer
    Reporter -->|Grafy| Visualizer
```
