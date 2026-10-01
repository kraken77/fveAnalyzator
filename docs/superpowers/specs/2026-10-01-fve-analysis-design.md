# FVE analýza (fveAnalysis) — samostatný nástroj + první krok projektu

**Datum:** 2026-10-01
**Status:** schváleno uživatelem (2026-10-01, diskuze v plan mode)
**Repo:** AntelonEnergy (fveAnalyzator) — nové moduly v `backend/app/reportgen/` + `frontend-web/`
**Zdroj:** přenos funkcionality ze `frontend-streamlit/pages/1_Energetická_analýza.py` (642 ř.) a `2_Ekonomická_analýza.py` (436 ř.) — **tyto soubory dnes neexistují, viz změnu níže**

> ### Změna 2026-10-01 (po schválení tohoto designu)
>
> Legacy Streamlit frontend byl **odstraněn** — rozhodnutím uživatele
> („chceme vše v jednom"). Zmizely:
>
> - kontejner `frontend-streamlit` v `docker-compose.yml` (a `streamlit`
>   v `requirements.txt`),
> - endpointy `/analysis/{energy,economic,geocoding}` a
>   `/report/{energy,economic}` v `backend/main.py` — včetně pydantic
>   modelů `EnergyAnalysisInput` a `EconomicAnalysisInput`,
> - adresáře `frontend-streamlit/` a `settings/` (prázdné, netracknuté).
>
> Výpočet se **nepřesouval podruhé** — zůstává v `app/fve_analysis.py`.
> Odstranění si vyžádalo jednu věc navíc, kterou tento design neřešil:
> `main.run_energy_analysis` a `main.run_economic_analysis` se volaly i
> jako plain Python funkce z `app/reportgen/ai_service.py` a
> `app/reportgen/router.py`. Oba moduly teď volají přímo
> `app.fve_analysis`, čímž zmizel i kruhový import
> `main → reportgen.router → main`.
>
> `/ote/*` zůstalo odložené (chybějí skripty). Aktuální stav systému je
> v [docs/architektura.md](../../architektura.md).

## 1. Cíl

Přenést energetickou a ekonomickou analýzu FVE ze Streamlitu do React aplikace jako **první krok procesu zakázky**. Uživatel zadá parametry FVE, dostane bilanci a ekonomiku, a výsledek se uloží jako **rozpracovaná analýza**, kterou lze jedním krokem převést na zakázku v pipeline. Analýza musí fungovat i zcela samostatně, bez existujícího projektu.

## 2. Rozhodnutí z brainstormingu

| Téma | Volba |
|------|-------|
| Uspořádání | **C** — samostatná i jako součást projektu, jedna UI komponenta |
| Uložení samostatné analýzy | **B** — jako „rozpracovaná analýza" v DB |
| Kdo má přístup | **admin, antelon i zákazník** (rozšíření dnešního RBAC) |
| Kontakt | povinný: jméno + e-mail + telefon, vyžadován při uložení analýzy |
| Vazba na uživatele | **A** — při uložení se user dohledá podle e-mailu, jinak se vytvoří |
| První kolo scope | parametry + bilance + grafy + PDF + převod na zakázku. **Bez** XLSX, **bez** OTE analýzy, **bez** save/load do JSON |

## 3. Datový model

### 3.1 Rozpracovaná analýza = projekt se stavem `fve_analyza`

**Nová tabulka není potřeba.** Projekt už má oba potřebné kontejnery a `status` s hodnotami. Rozpracovaná analýza je projekt ve stavu `fve_analyza`.

```
projects
  ├─ name               "Novákovi — FVE 12 kWp"     (z názvu/adresy)
  ├─ status             "fve_analyza"               (5. hodnota, nová)
  ├─ owner_id           4                           (kdo analýzu spustil)
  ├─ customer_id        NULL → naplní se při uložení (viz 3.3)
  ├─ customer_name      "Jiří Novák"
  ├─ customer_email     "novak@example.cz"          (nový sloupec)
  ├─ customer_phone     "+420 777 123 456"          (nový sloupec)
  ├─ type               "ostani"                    (výchozí, při převodu změní)
  ├─ fve_params_json    {kwp, battery_capacity, active_appliances, latitude, ...}  viz 6.2
  └─ antelon_params_json {}
```

`status` nově nabývá `fve_analyza` vedle dnešních `lead|active|done|cancelled`.

### 3.2 Proč nový sloupec, ne `users`

`PRAGMA table_info(projects)` potvrzuje, že `projects` dnes nemá telefon ani e-mail — jen `customer_name`. `users` má `email`, ale **nemá telefon**.

Kontakt patří k **zakázce**, ne k uživateli: jeden zákazník může mít více zakázek s různými kontakty (různá manželka, firma). Proto `customer_email` + `customer_phone` na `projects`, nikoli na `users`.

Zákazník přitom nemusí být vůbec vytvořený jako user, aby se mohl dozval.

### 3.3 Naplnění `customer_id` (rozhodnutí A)

Při uložení rozpracované analýzy:

1. Dohledat `User` podle `customer_email` (case-insensitive)
2. Nenalezen → vytvořit s rolí `customer` a náhodným heslem (reset přes flow obnovy hesla, mimo scope)
3. Nastavit `project.owner_id` i `project.customer_id` na tohoto usera

Tím se prázdné `customer_id` opraví postupně a `/p/{share_code}` pro zákazníka začne fungovat bez ručního přidělování.

Dnešní stav: u všech 36 existujících projektů je `customer_id = NULL`. Tato oprava se jich netýká, jde jen o nové záznamy.

### 3.4 Migrace

Nové sloupce se doplní existující tabulce `projects`. Aplikace běží z `./data` bind mountu, `reportgen.db` je produkční data — migrace musí být **aditivní** (pouze `ADD COLUMN`), žádné přepisování tabulky. Před migrací záloha do `data/backups/`, stejně jako to dělá `deploy.sh`.

## 4. Převod na zakázku

`POST /api/v1/projects/{id}/convert-to-order`

```
fve_analyza  →  lead
```

- zkopíruje `fve_params` do `antelon_params` (kwp, battery kWh, soc)
- připojí pipeline z šablony podle `type`
- nechá `customer_id`, kontakt a všechny výsledky analýzy beze změny
- idempotentní — už převedený projekt vrací 409

Tím se `fve_params` stane vstupem do definice zakázky, jak je popsáno v zadání.

**Propojení s pipeline:** šablona `rd` má 57 kroků, včetně těchto dvou, které analýza fakticky nahrazuje:

```
3: první indikativní nabídka dle telefonátu
6: Zjištění roční spotřeby          ← dodává ho fve_params
```

Po převodu se tyto kroky označí jako `done` s poznámkou odkazující na zdrojovou analýzu, aby je nebylo nutné dělat znovu. Implementace přes `state_model` a `ProjectStep.status` — bez zásahu do šablon.

## 5. API

Vše v `/api/v1/*` s JWT, existující `require_roles`. **Staré endpointy `/analysis/*` se nepřenášejí** — legacy Streamlit si je ponechá.

| Endpoint | Role | Co dělá |
|---|---|---|
| `POST /fve-analysis/run` | admin, antelon, customer | parametry → výsledky (bilance, grafy, ekonomika) |
| `POST /fve-analysis/geocode` | admin, antelon, customer | adresa → lat/lon |
| `POST /fve-analysis` | admin, antelon, customer | uloží rozpracovanou analýzu (validace kontaktu, dohledání usera) |
| `PUT /projects/{id}/fve-params` | admin, antelon, customer (owner) | přepočítá parametry existující analýzy |
| `POST /projects/{id}/convert-to-order` | admin, antelon | `fve_analyza` → `lead` + pipeline |

### 5.1 Reuse existující logiky — žádná duplicita matematiky

Kód analýzy **už existuje** a je sdílený. `backend/app/reportgen/fve_wrap.py` volá přesně to, co volá Streamlit:

```python
run_fve_energy(params)
  → data_loader.load_consumption_data / load_production_data
  → analyzer.calculate_energy_balance
  → analyzer.calculate_financials
  → appliance_manager.ApplianceManager
  → visualizer.plot_*
```

Nové endpointy tedy **jen zpřístupňují** tuto funkci přes API s auth. Nepíše se žádná nová fyzika ani ekonomie. Ekonomika v PDF už dnes jezdí (generátor `/projects/{id}/generate` ji volá) — to je důkaz, že cesta funguje.

`analyze_spot_profitability` a vizualizace pro OTE se v tomto kole nepropojují (viz 8).

## 6. UI

### 6.1 Dvě routy, jedna komponenta

| Route | Zdroj parametrů | Dostupné akce |
|---|---|---|
| `/fve-analysis` | defaulty, prázdná | uložit jako rozpracovanou analýzu, vytvořit zakázku |
| `/projects/{id}/fve-analysis` | `project.fve_params` | přepočítat, převést na zakázku, export PDF |

Obě používají **stejné komponenty** — `FveAnalysisForm` (parametry) a `FveAnalysisResults` (výstup). Liší se jen props. Žádná duplicita kódu.

### 6.2 Tříkrokový flow

```
[1] Parametry   →  [2] Výsledky  →  [3] Kontakt a uložení
```

Parametry se přenesou ze Streamlitu (`DEFAULT_SETTINGS`, 20 číselných polí):

- **FVE:** kWp, kapacita baterie kWh
- **Spotřeba a ceny:** roční spotřeba MWh, cena silové, cena distribuce
- **Prodej přebytků:** schéma (fixní / komunita / sdílení), výkupní cena
- **Pokročilé** (rozbalovací): zeměpisná šířka/délka (+ geokódování adresy), sklon panelů, azimut, systémové ztráty, zimní ztráty, limit exportu do sítě, tepelná baterie
- **Spotřebiče:** checkboxy ze `ApplianceManager` — dnes jich je 17, načítají se z API, ne hardcoded

### 6.3 Výstupy

Ze Streamlitu: roční bilance, parametry výroby, energetická bilance kWh, finanční bilance Kč, celkové shrnutí, 2 Plotly grafy, PDF.

Ekonomická stránka: investiční srovnání, NPV/ROI, 3+ grafy, PDF.

Grafy jako Plotly v Reactu (v repozitáři už je použitý ve fveAnalyzatoru, kompatibilní zdroj dat — JSON, ne obrázky).

### 6.4 Krok 3 — kontakt

```
Jméno a příjmení *      [____________]
E-mail *                [____________]
Telefon *               [+420 ________]
Poznámka               [____________]
[ Uložit jako rozpracovanou analýzu ]
[ Vytvořit zakázku a pokračovat ]   → převede na lead a otevře pipeline
```

Validace: e-mail regex, telefon min. 9 číslic. **Obě povinná v každé roli** — bez kontaktu nemá smysl analýzu v pipeline zpracovat.

### 6.5 Nabídka v menu

`fveAnalysis` v hlavní nabídce pro `admin` a `antelon`. Pro `customer` jako položka v jeho menu (dnes má jen „Moje projekty").

## 7. RBAC

Dnes `_ensure_project_access` vrací 403 pro `customer` na vše, kde není v `project_users`. Rozšíření:

- `can_access_project` zůstává beze změny — bezpečnostní pravidlo **zákazník vidí jen vlastní** platí dál
- vlastní analýzu (`owner_id == user.id`) zákazník vidí a může přepočítat
- `/api/v1/projects` pro `customer` zobrazí i jeho rozpracované analýzy
- převod na zakázku: zákazník **ne**, admin/antelon ano (obchodní rozhodnutí)

Vytvoření a uložení analýzy smí zákazník — to je ta nová schopnost.

## 8. Co se v tomto kole NEdělá (YAGNI)

| Vynecháno | Proč |
|---|---|
| **Analýza OTE** (110 ř. ve Streamlitu) | vyžaduje `data/spot_market.db`, která v repu chybí; navíc `download_ote_data.sh` a `process_ote_data.py` neexistují, takže `POST /ote/update` dnes spadne na `FileNotFoundError` |
| XLSX export (6 listů) | už existuje v `/projects/{id}/generate` |
| Ukládání/načítání nastavení do JSON | nahrazeno tím, že analýza je uložený projekt |
| Denní stahování OTE dat | navazuje na předchozí bod; skripty uživatel najde později |
| Migrace legacy Streamlit na `/api/v1/*` | mimo scope, legacy běží dál |
| Obnovení hesla nově vytvořenému zákazníkovi | náhodná hesla, reset mimo scope |

## 9. Testování

**Backend** — pytest, existující `tests/`:
- `run` vrací konzistentní strukturu pro výchozí parametry
- `run` respektuje `grid_export_limit_kw`, schéma prodeje, baterii
- uložení bez e-mailu/telefonu → 422 s konkrétním hlášením
- uložení s validním kontaktem vytvoří usera, pokud neexistuje; podruhé ho najde
- `convert-to-order` převede stav a připojí pipeline; druhý pokus → 409
- `customer` dostane 403 na cizí analýzu, 200 na vlastní
- zákazník **nemůže** převést na zakázku

**Frontend** — Playwright, existující `tests/test_e2e.py`:
- přihlášení jako zákazník, `/fve-analysis` se zobrazí v menu
- tříkrokový flow dojde do kroku 3, validace zablokuje prázdný e-mail
- uložení vrátí URL rozpracované analýzy, v `/projects` je vidět
- převod na zakázku otevře pipeline s běžícími kroky
- žádná console chyba, žádný selhaný request

**Ruční ověření:** analýza běží na `localhost:3001` i `https://fve.etikos.cz`, obě role admin i zákazník.

## 10. Rizika

| Riziko | Řešení |
|---|---|
| Analýza na 15+ let dat může trvat desítky sekund | dlouhý výpočet → loading stav, timeout na 120 s |
| `reportgen.db` je produkční data | aditivní migrace, záloha do `data/backups/` |
| Nový stav `fve_analyza` může rozbít filtry Dispečinku | filtry explicitně zobrazují známé stavy; `fve_analyza` se v tabulce zakázek schová |
| Duplicitní uživatelé při psaní e-mailu | dohledávání case-insensitive, existující user se použije |
| Výpočet běží v synchronním FastAPI requestu | akceptováno pro V1 (odpovídá dnešnímu `/generate`), horizontální škálování není požadavkem |
