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

    Výchozí účty (seed při prvním startu, hesla lze změnit v `.env`):

    | Role | E-mail | Heslo | Práva |
    |------|--------|-------|-------|
    | `admin` | `admin@antelon.local` | `Admin123!` | vše + správa uživatelů/spotřebičů |
    | `antelon` | `antelon@antelon.local` | `Antelon123!` | všechny projekty, nahrávání fotek, čistý PDF |
    | `customer` | `zakaznik@antelon.local` | `Zakaznik123!` | jen přiřazené projekty (přes QR/odkaz), čistý PDF |
    | `anonymous` | — | — | teaser `/p/{code}` + PDF s vodoznakem |

    Nastavitelné přes `.env`: `RG_ADMIN_*`, `RG_ANTELON_*`, `RG_CUSTOMER_*`, `RG_JWT_SECRET`, `RG_PUBLIC_URL` (viz `.env.example`). Další uživatelé přes registraci na webu nebo `admin` → `PUT /admin/users/{id}`.

    Přihlašovací jména jsou zdokumentována zde a v `.env.example`.

### 1b. ReportGen — generátor PDF reportů (nový modul)

Nový modul `backend/app/reportgen` + `frontend-web`:

- **Šablona Antelon** (Pentagon v2, 16:9): z CSV Shelly datalogeru (`Fáze A/B/C`, `Celkem`, `Time, V` / `Čas, Wh`, BOM, `0`=chybí). Podporuje 1 i více CSV (více měsíců se sloučí), denní + volitelně hodinový/15min profil. Přímá editace textů a vypínání sekcí, fotogalerie, QR sdílení.
- **Šablony fveAnalyzator**: wrap existujících Energy/Economic/OTE reportů (WeasyPrint).
- **Role**: `admin` (správa uživatelů/spotřebičů), `antelon` (všechny projekty, čistý PDF), `customer` (jen přiřazené projekty, čistý PDF), `anonymous` (teaser náhled `/p/{code}`, PDF s vodoznakem). Blur pro `teaser`/`internal` sekce.
- API: `/api/v1/*` — auth, projekty, upload, data preview, generate, pdf download, share/QR, public preview, OTE, admin.

Viz `docs/superpowers/specs/2026-08-28-reportgen-design.md`.

### 1c. Procesní pipeline (Dispečink)

End-to-end procesní dispečink zakázek (lead → příprava/smlouva → realizace → servis) v modulech `backend/app/reportgen` (pipeline, AI, ekonomika, materiály, fakturace) + `frontend-web` (stránka **Dispečink**).

- **Typy zakázek a šablony**: 11 šablon (`rd`, `byt`, `firma`, `obec`, `bojler`, `rozsireni`, `ostatni`, …) se seedují při startu; admin je vidí a edituje kroky v `Administrace → Šablony`.
- **Import dispečinku**: `Administrace → Import` nahraje `PROCESNÍ DISPEČINK.xlsx` (idempotentně, duplicity se přeskočí). Alternativně `POST /api/v1/admin/import/dispecink`.
- **Tabule zakázek**: `/dispecink` — filtry (typ, stav, text), proužek pipeline u každé zakázky, klikaní do detailu.
- **Pipeline detail**: `/projects/{id}/pipeline` — kroky ve fázích, plánování (datum, odpovědná osoba), přechody (začít/dokončit/odeslat/podepsat/přeskočit/zrušit), brány a podmínky (např. dotace NZÚ, půjčka), paralelní větve; historie událostí.
- **AI kroky**: návrh FVE, baterie, dotace NZÚ (C.3), půjčka, podrobná nabídka — generují se automaticky (`ai_chain`) nebo ručně; výstup musí admin/antelon schválit nebo zamítnout.
- **Finanční efekty**: 2 500 Kč za technické posouzení (faktura při „pokračujeme“, žádná při „Zamítnuto“ → zakázka `cancelled`), sleva −2 500 Kč při podpisu SoD, zálohová/finální faktura.
- **Časové výkazy a montéři**: `Pipeline detail → Časové výkazy` (minuty admin/práce na krok), souhrn, výkaz montérů CSV (`/admin/reports/monteri-csv`).
- **Ekonomika**: náklad admin/work dle sazebníku RateCard (kancelář 500 Kč/h, montáž 450–550 Kč/h), marže z číselníku `settings` (default 30 %) — `Pipeline detail → Ekonomika`. Admin a práce se nikdy nesčítají.
- **Materiály**: číselník (`/materialy`, správa admin/nákupčí) + matice plán/objednávka/výdej/skutečnost po projektu s cenovým snapshotem.
- **Fakturace**: položky dokladů v projektu, vystavení (čísla `inv-{projekt}-{seq}`), stav `issued → paid`.
- **Role a role-switcher**: uživatel může mít více rolí (`/auth/me` vrací `roles`); přepínač rolí v hlavičce. Role: `admin`, `antelon`, `sales`, `designer`, `buyer`, `warehouse`, `subsidy`, `connection`, `electrician`, `roofer`, `inspector`, `customer`.
- **Customer portál**: zákazník přes sdílecí odkaz (`/p/{code}`) vidí stav pipeline a kroky „čeká na vás“ (sběr podkladů, odsouhlasení nabídky, podpis SoD); akce řídí obchodník.
- **Notifikace**: zvonkohra v hlavičce (plánování kroku, čekání na zákazníka, AI chyby).

Viz `docs/superpowers/specs/2026-09-24-procesni-pipeline-design.md` (design) a `docs/superpowers/plans/2026-09-24-procesni-pipeline.md` (plán M1–M6).

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

### 3. Nasazení na server (produkce)

Aplikace běží na serveru **drakisa** (192.168.119.167) jako Docker Compose projekt `antelon-energy` v adresáři `/home/roman/apps/antelon-energy`. Veřejně dostupná na **https://fve.etikos.cz** (web na portu 3001 — port 3000 obsazuje Grafana), backend API na 8051.

**Flow nasazení:**

1. Lokálně: commit + `git push origin main`.
2. Na serveru: `cd /home/roman/apps/antelon-energy && ./deploy.sh`
3. `deploy.sh` automaticky:
   - zálohuje produkční `data/reportgen.db` do `data/backups/`,
   - stáhne nejnovější kód (`git pull --ff-only`),
   - znovupostaví a restartuje kontejnery (`docker compose up -d --build`),
   - ověří health backendu a webu.

**Důležité:**

- Produkční data (`reportgen.db`, `data/projects/`, `spot_market.db`) žijí pouze na disku serveru — **nejsou v gitu** a nesmí se přepsat lokální vývojovou verzí.
- Citlivé hodnoty (hesla, `RG_JWT_SECRET`, `RG_PUBLIC_URL=https://fve.etikos.cz`) jsou v `.env` na serveru; v gitu je jen `.env.example`.
- Legacy Streamlit frontend na serveru neběží (Exited) — aktivní klient je `frontend-web` (React).

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
