# Procesní pipeline (Dispečink) — workflow + AI kroky pro Antelon Energy

**Datum:** 2026-09-24
**Status:** schváleno uživatelem (2026-09-24, diskuze v plan mode)
**Repo:** AntelonEnergy (fveAnalyzator) — rozšíření modulu `backend/app/reportgen/` + `frontend-web/`

## 1. Cíl

Nahradit Excelový „PROCESNÍ DISPEČINK" interním **procesním workflow** v aplikaci. Zákazka (projekt) prochází **typovou šablonou pipeline** s tvrdými přechody, paralelními větvemi, podmíněnými kroky, automatickými akcemi a **AI kroky** napojenými na existující výpočetní moduly (fveAnalyzator, NZÚ 2026, OTE, ReportGen). Součástí je ekonomika procesu (administrativní a realizační čas, sazby, marže), materiály s měrnými jednotkami a rozšířený model rolí s přepínáním.

## 2. Rozhodnutí z brainstormingu

| Téma | Volba |
|------|-------|
| Účel | Workflow + AI kroky (plné propojení) + zákaznický portál |
| Definice pipeline | Typové šablony dle typu zakázky (11 typů) |
| Vynucení postupu | Tvrdý workflow s paralelními větvemi a podmíněnými kroky; admin zásahy do flow |
| Role | Rozšířený model — uživatel může mít více rolí, role-switcher v UI |
| AI kroky | Hybridně: jednoduché výpočty automaticky, nabídka/vizualizace ručně; výstup vždy schvaluje člověk |
| Běh AI | Synchronně |
| Časová evidence | Administrativní čas (z Excelu) a realizační čas (per template) odděleně |
| Ekonomika | Náklad/marže per krok, reálný čas, materiály (ks/m/h), plán vs. skutečnost |
| 2 500 Kč poplatek | Samostatný daňový doklad (faktura) při „pokračujeme"; ve finální faktuře sleva |
| Reklamace | Samostatný typ zakázky s vlastní krátkou pipeline |
| Notifikace | V1 v aplikaci; e-mail později (e-mail = přihlašovací parametr, již existuje) |
| Výchozí data | Import 46 zakázek z Excelu včetně stavů/dat/poznámek |

## 3. Typy pipeline (11)

| Code | Název | Poznámka |
|------|-------|----------|
| `rd` | Rodinný dům | plný proces |
| `byt` | Byt | plný proces (zkrácené kroky střechy) |
| `firma` | Firma | plný proces |
| `bojler` | Bojler | zkrácený |
| `rozsireni` | Rozšíření | zkrácený |
| `wb` | Wallbox | zkrácený |
| `ostatni` | Ostatní | zkrácený |
| `reklamace` | Reklamace | krátká pipeline: přijetí → diagnostika → oprava/výměna → předání + zpráva |
| `elektroprace` | Elektro práce | samostatné elektro zakázky |
| `carport` | Instalace CarPort | zastřešení + FVE/elektro dle zakázky |
| `kontrola` | Pravidelná kontrola/revize | periodická revize |

## 4. Workflow engine

### 4.1 Stavy kroku

```
not_started → planned (Plánováno na [datum], přiřazeno [osoba]) → in_progress → done
```
- `not_started` — nelze začít, dokud nejsou splněny předchozí potřebné stavy (tvrdá brána s přesným hlášením).
- `planned` — nový stav: krok je naplánován na datum a přiřazen odpovědné osobě.
- Smluvní kroky (`state_model = contract`): `sent → signed` (s audit daty „zasláno/podepsáno").
- Speciální stavy: `skipped`, `not_applicable` (jen admin / override).
- `cancelled` — zakázka (při „Zamítnuto" nebo explicitně adminem).

### 4.2 Brány a závislosti

- Přechod kroku ověřuje `workflow_service.can_transition(step, action, user, project)`:
  role uživatele z `allowed_roles` kroku **a** splněné podmíněné předchozí kroky.
- Bez splnění → 403 s hlášením „Nelze začít — nejsou splněny předchozí potřebné stavy: [seznam]".
- Admin override (přeskočit, vrátit, upravit přiřazení, přidat/odebrat krok v instanci).

### 4.3 Paralelní větve

- Kroky ve stejné `parallel_group` sdílejí jen *gate* krok; jinak nemají vzájemné závislosti.
- Příklad (fáze po podpisu SoD): fakturace, SOP/žádost o připojení, NZÚ registrace, bezúročná půjčka běží souběžně.

### 4.4 Podmíněné kroky

- `condition_json`: podmínky na stavy předchozích kroků a na vlastnosti zakázky.
- Data z dotazníku v kroku „Technické posouzení": dotace ano/ne, bezúročná půjčka ano/ne, pozemek/skladování atd.

### 4.5 Automatické akce (hooky na `done`)

| Krok (dokončení) | Akce |
|------------------|------|
| Odsouhlasení předběžné nabídky = **pokračujeme** | **Vystavení samostatné faktury 2 500 Kč** (pol. „Posouzení realizace zakázky"). Při pod-stavu „Zamítnuto": bez faktury, zakázka → `cancelled`. |
| Podpis Smlouvy o dílo (SoD) | Otevře realizační větev; zápis „2 500 Kč bude ve finální faktuře slevou (odečtena)". |
| Žádost o připojení (SOP) | Otevře větev přetoků (ÚTP, výměna elektroměru, sdílení). |
| Elektro-montáž | Otevře větev revize (měření, revizní zpráva). |
| AI kroky | Spustí analýzu (viz §6), výsledek čeká na schválení. |

### 4.6 Notifikace

- V1: v aplikaci (centrum notifikací/badge za úkoly a přiřazení, otevření větve, čekání na zákazníka).
- E-mail až v pozdější verzi; e-mailová adresa je přihlašovací parametr (již existuje na `users.email`).

## 5. Datový model (SQLite `data/reportgen.db`)

### Nové tabulky

- `pipeline_templates(id, code, name, zakazka_type, version)` — šablona per typ zakázky.
- `pipeline_steps(id, template_id, code, name, phase, order, est_admin_minutes, est_work_minutes, admin_rate_role, work_rate_role, state_model, allowed_roles_json, condition_json, auto_hook, parallel_group)`.
  - `state_model`: `simple | contract | ai | material`
  - `est_admin_minutes` — administrativní čas (z Excelu; celkem 553 min u RD).
  - `est_work_minutes` — realizační čas (montáž, měření…) dle template.
- `project_pipeline(project_id, template_id)` — instance šablony na zakázce.
- `project_steps(id, project_id, step_id, status, plan_date, assigned_user_id, note, started_at, done_at, real_admin_minutes, real_work_minutes)`.
- `step_events(id, step_id, action, from_status, to_status, user_id, at)` — audit („Plánováno na 12.9.", „zasláno 15.9.", „podepsáno 20.9.").
- `pipeline_ai_results(id, step_id, kind, input_json, output_json, pdf_version_id, status, created_by, reviewed_by, reviewed_at)` — `status = draft | approved | rejected`.
- `materials(id, code, name, unit, price, active)` — číselník materiálů; `unit ∈ {ks, m, h, …}`.
- `project_materials(id, project_id, material_id, qty_planned, qty_actual, price_snapshot, lane, step_id)` — `lane ∈ {plan, order, issue, actual}`.
- `time_entries(id, project_id, step_id, user_id, minutes, work_date, kind, note)` — `kind ∈ {admin, work}`; výkaz odpracovaných hodin.
- `invoice_items` / fakturační záznamy: zálohová faktura, faktura 2 500 Kč, konečná faktura (+ sleva −2 500 Kč).

### Úpravy stávajících

- `users.role` → `users.roles` (JSON array nebo vazební tabulka `user_roles`); uživatel může mít více rolí. Existující seed → single-element pole.
- `projects`: + `type` (zakazka_type), `status` (`lead|active|done|cancelled`), `tech`.
- Vazba dokumentů na kroky (karta zakázky / protokoly z Podkladů — pozdější iterace; směřování v modelu je připravené přes `step_id` FK).

## 6. AI kroky

| AI krok | Spouštění | Modul | Výstup |
|---------|-----------|-------|--------|
| Návrh velikosti FVE | auto po „Technické posouzení" | energy + economic (ekonomika provozu, úspory, porovnání S&P 500) | kWp, výroba kWh, roční úspora, ROI/NPV, porovnání S&P 500 |
| Návrh kapacity baterie | auto | energy (simulace baterie) | kWh, SoC, ekonomika baterie |
| Výpočet dotační úspory | auto | NZÚ 2026 kalkulačka | dotace Kč + podmínky |
| Možnost bezúročné půjčky | auto po dotaci | nový malý modul (pravidla půjčky) | ano/ne + částka |
| Vytvoření nabídky (PDF) | ručně „Spustit AI" | ReportGen `economic` (+ `energy`) | PDF nabídka → `pdf_versions` |
| Příprava vizualizace (PDF) | ručně | ReportGen Antelon/energy + grafy | PDF vizualizace |

- Vstup: `fve_params` projektu + data z kroků (roční spotřeba, lokalita, sklon, dotace/půjčka ano/ne).
- Běh: synchronní.
- Výstup je `draft`; schválí/zamítne zodpovědná osoba (obchodník/projektant) → teprve pak krok `done`.

## 7. Ekonomika a materiály

- **Kalkulace nákladu kroku**: `est_admin_minutes × admin_rate_role` (sazba v Kč/h, číselník; default 500 Kč/h z Excelu) **+** `est_work_minutes × work_rate_role`. Marže (default 30 %) → kalkulovaný prodej.
- **Administrativní a realizační časy se nepromíchávají**.
- **Reálný čas**: `time_entries` per krok/osobu/typ → plán vs. skutečnost (zakázka i firemní přehled).
- **Materiály**: číselník (ks/m/h…); na zakázce 4 pruhy: plán → objednávka → výdej ze skladu → skutečná spotřeba; porovnání plán vs. skutečnost.
- **2 500 Kč**: položka (faktura) „Posouzení realizace zakázky" vzniká automaticky při „pokračujeme"; ve finální faktuře je **sleva −2 500 Kč** (zákazník neplatí dvakrát).
- **Výkaz hodin montérů** → exportovatelný podklad.

## 8. Role a oprávnění

| Role | Zkratka | Oblast |
|------|---------|--------|
| admin | `admin` | číselníky, šablony, zásahy do flow, uživatelé, import |
| antelon | `antelon` | vedení/plný přístup |
| obchodník | `sales` | lead, nabídky, prodej |
| projektant/kancelář | `designer` | technické posouzení, návrhy, projekt |
| skladník | `warehouse` | skladová kontrola, výdeje |
| nákupčí | `buyer` | objednávky u dodavatelů |
| admin dotací | `subsidy` | NZÚ, SFŽP |
| admin připojení (ČEZ) | `connection` | SOP, přetoky, ÚTP |
| stavební montér | `roofer` | střešní/stavební montáž |
| elektro-montér (najatý) | `electrician` | elektro-montáž, propojení, test |
| revizní technik | `inspector` | měření, revizní zpráva |
| customer | `customer` | zákaznický portál |
| anonymous | — | teaser `/p/{code}` |

- Hierarchie rozšířena: admin ⊃ antelon ⊃ ostatní interní role ⊃ customer ⊃ anonymous.
- **Uživatel může mít více rolí**; role-switcher v UI (každá role vidí jen podstatné: např. Nákupčí → co je naplánováno / ve skladu / co nakoupit).
- Per-krok `allowed_roles` — kdo krok smí plnit/zahájit.

## 9. API (`/api/v1`)

- `GET/POST/PUT /pipeline-templates`, `GET/POST/PUT /pipeline-templates/{id}/steps` (admin)
- `GET /projects/{id}/pipeline` — kroky, stavy, události, časy, materiály
- `POST /projects/{id}/steps/{sid}/transition {action, note, plan_date?}` (RBAC dle kroku)
- `POST /projects/{id}/steps/{sid}/run-ai`, `POST /projects/{id}/steps/{sid}/review-ai {approved, note?}`
- `POST /projects/{id}/time-entries`, `GET /projects/{id}/time-entries`
- `GET/POST /materials`, `POST /projects/{id}/materials {lane, ...}`, `GET /projects/{id}/materials`
- `POST /projects/{id}/invoice-items` (fakturace ZF/KF, 2 500 Kč, sleva)
- `GET /projects/{id}/my-tasks` (customer: úkoly + stav zakázky) + rozšíření `/public/p/{code}`
- `GET /admin/users`, `PUT /admin/users/{id}/roles`
- `POST /admin/import/dispecink` (XLSX → projekty + pipeline instance)

## 10. Frontend (React)

- `/dispecink` — tabule zakázek: filtry (typ, stav, odpovědná osoba), sloupcový pohled pipeline (živý „Excel").
- `/projekty/:id/pipeline` — kroky: přechody vč. „Plánováno na [datum] + osoba", AI spuštění/schválení, výkaz času, materiály, historie událostí.
- `/projekty/:id/materialy` — bilance materiálů (plán/objednávka/výdej/spotřeba + plán vs. skutečnost).
- `/admin/pipeline` — šablony, kroky, role, sazby, číselníky, import Excelu, uživatelé.
- **Role-switcher** — přepínač aktivní role v hlavičce; per-role pohled (Nákupčí, Skladník, Montér, Admin dotací…).
- Zákaznický portál: stav zakázky + úkoly (nahrát podklady, odsouhlasit nabídku, podepsat SoD/plnou moc), rozšíření `/p/:code`.

## 11. Import Excelu

- Parser XLSX: NFD/NFC robustnost názvu souboru; mapa hlavička → krok šablony.
- Buňky: datum → `done_at`/`plan_date`, „a"/„x" → `done`, poznámky → `note`, „zasláno/podepsáno" → `step_events`.
- Sloupec aktivní/neaktivní → `projects.status`; typ zakázky (RD/byt/firma/…) → volba šablony.
- 46 řádků = startovní projekty.

## 12. Milníky

- **M1** DB + šablony (11 typů, seed 57 kroků RD + varianty) + import Excelu
- **M2** workflow engine (stavy, brány, paralelní větve, podmíněné kroky, audit, admin zásahy)
- **M3** AI kroky (integrace energy/economic/NZÚ/OTE/ReportGen) + schvalování
- **M4** ekonomika + materiály + fakturace (2 500 Kč, ZF/KF, sleva) + časové výkazy
- **M5** frontend (dispečink, pipeline, materiály, admin, role-switcher, customer portál)
- **M6** testy (pytest jednotkové/integrační + Playwright E2E) + dokumentace + import/seed verifikace

## 13. Testy

- Jednotkové: workflow přechody a brány, podmíněné kroky, hooky (2 500 Kč), časová kalkulace, materiály.
- Integrační API (TestClient): create pipeline, transition, run-ai/review, time-entries, materials, import.
- E2E Playwright: login → dispečink → pipeline akce → role-switcher → customer úkoly.
- Regrese: stávající `pytest` a E2E ReportGen musí projít.

## 14. Rizika

- Velikost scope — milník po milníku, V1 neobsahuje e-mail notifikace ani dokumenty na kroky.
- Migrace role → roles (users) — řešit bez ztráty dat (single-element pole).
- NFD/NFC názvy souborů — parser pomocí glob + normalizace.
- Synchronní AI — analýzy jsou sekundy, bez fronty v V1.
- `data/reportgen.db` — CWD závislé cesty (viz stávající reportgen).