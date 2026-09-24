# Procesní dispečink — uživatelská příručka (procesní pipeline)

> Verze: 2026-09-24 · Modul M1–M6 · Zdroje: [design](2026-09-24-procesni-pipeline-design.md), [plán](2026-09-24-procesni-pipeline.md), [image-spec]()
>
> Tato příručka popisuje používání **procesního dispečinku** v aplikaci Antelon Energy (React frontend `frontend-web` + FastAPI backend `/api/v1`). Pokrývá role, denní práci obchodníka, montéra, nákupčího, skladníka, administrátora i pohled zákazníka.

---

## 1. Co to je

Procesní dispečink vede každou zakázku od prvního telefonátu až po servis. Zakázka má **pipeline** — posloupnost kroků ve fázích:

**Lead → Příprava (nabídky) → Smlouva (SoD) → Realizace (montáž, revize, předání) → Servis & správa**

Kroky mají stavy: `not_started` → `planned` → `in_progress` → `done` (u smluv: `sent` → `signed`; lze i `skipped` / `cancelled` / `not_applicable`). Přechody řídí **brány** (krok nejde začít, dokud neskončí předchozí) a **podmínky** (např. kroky dotace/půjčky se zobrazí jen pokud se týkají zákazníka).

Přehled obrazovek:

| Stránka | Cesta | Kdo |
|---|---|---|
| Tabule zakázek | `/dispecink` | všechny interní role |
| Pipeline detail | `/projects/{id}/pipeline` | všechny role + zákazník (svůj projekt) |
| Materiály | `/materialy`, `/projects/{id}/materialy` | admin, antelon, nákupčí, skladník |
| Administrace pipeline | `/admin/pipeline` | admin |
| Customer portál | `/p/{kód}` (sdílecí odkaz) | zákazník/veřejnost |

---

## 2. Přihlášení a role

Přihlášení na `/login`. Účet si může vytvořit kdokoli (`/register`), role mu přiřadí **admin** (`Administrace → Uživatelé a role`).

Role v systému:

| Role | Typická náplň | Přístup k dispečinku |
|---|---|---|
| `admin` | vše + správa | vše |
| `antelon` | jednatel/kancelář | vše + projekty |
| `sales` | obchodník | tabule, pipeline, AI schválení |
| `designer` | projektant | tabule, pipeline (návrh FVE) |
| `buyer` | nákupčí | tabule, materiály (číselník + plán/objednávky) |
| `warehouse` | skladník | dispečink + materiály (výdej/skutečnost) |
| `subsidy` | dotace (NZÚ) | tabule, AI dotace |
| `connection` | připojení (distributor) | tabule, AI žádost o připojení |
| `electrician` / `roofer` / `inspector` | montér, pokrývač, revizní technik | tabule, pipeline, časové výkazy, montážní kroky |
| `customer` | zákazník | jen své projekty (přes sdílecí odkaz / po připojení) |

**Viditelnost zakázek:** všechny **interní role** (cokoli jiného než `customer`) vidí v dispečinku **všechny zakázky** společnosti — otevření detailu pipeline není omezeno projektovou vazbou. Zákazník (`customer`) vidí a otevírá **jen své** projekty (kde je vlastníkem nebo je propojen přes sdílecí odkaz); cizí zakázky dostanou 403. Samotné **akce** na krocích zůstávají omezené rolí daného kroku (`allowed_roles`) — např. montážní krok může zahájit/dokončit jen `electrician`, obchodní krok zase `sales`.

**Multi-role a přepínač rolí:** uživatel může mít více rolí najednou. V hlavičce je přepínač **„Role:"** — vyberte roli, ve které právě pracujete (mení se podle ní i nabídka a oprávnění akcí).

> Příklad: montér, který občas zastupuje skladníka, má role `electrician` + `warehouse`; přepnutím na `warehouse` uvidí menu Materiály s výdeji.

---

## 3. Den obchodníka (sales) / dispečera

### 3.1 Tabule zakázek (`/dispecink`)

- Přehled všech zakázek: ID, název, zákazník, typ, stav, **proužek pipeline** (čtverečky kroků s barvou stavu) a podíl hotových kroků.
- **Filtry**: hledání textu, typ zakázky, stav zakázky a **odpovědná osoba** (zakázky, kde má daný uživatel krok v plánu/práci).
- Klik na název/zakázku → `Pipeline detail`.
- Legenda barev pod tabulkou: `done`=zelená, `in_progress`=žlutá, `planned`=modrá, `not_started`=bílá, `cancelled`/`skipped`=šedá.

### 3.2 Pipeline detail (`/projects/{id}/pipeline`)

Kroky jsou seskupené do fází. U každého kroku:

- **Stavový štítek**, kód, plánované datum, odpovědná osoba, odhad minut (admin/práce), vykázaný čas, poznámka.
- **Akční tlačítka** podle toho, co je možné. Typický postup u nové zakázky:
  1. `Plánovat` → datum + odpovědná osoba (+ `Uložit plán`).
  2. `Začít` → krok běží (`in_progress`).
  3. `Dokončit` → krok hotový, zpravidla se odemkne/přidá další krok.
- **Smluvní kroky** (SoD, plná moc): `Odeslat` (zákazník dostane notifikaci „čeká na zákazníka“) → `Podepsat`.
- Krok lze `Přeskočit` nebo `Zrušit` (jen admin/antelon).

Karty **Historie** zobrazují kompletní log událostí kroků.

### 3.3 Finanční efekty (automatika)

- **Technické posouzení = 2 500 Kč**: když zákazník řekne „jdeme do toho“ (krok `odsouhlaseni_predbezne` → `Dokončit` = „Odeslání nabídky“), systém **vytvoří fakturační položku 2 500 Kč**. Při „Zamítnuto“ se žádná faktura nevytvoří a zakázka se označí `cancelled`.
- **Sleva −2 500 Kč**: při podpisu SoD (`sod` → `Podepsat`) systém přidá položku `final_discount` = −2 500 Kč. Kontrolní součet posouzení + sleva = 0 Kč.
- **Zálohová a finální faktura**: přidává se ručně v záložce **Fakturace** (`Přidat položku`), vystavuje admin (tlačítko `Vystavit` vygeneruje číslo `inv-{projekt}-{pořadí}`).

### 3.4 AI kroky (dotace, půjčka, návrh FVE…)

Kroky označené šablonou „AI“ se počítají automaticky nebo ručně:

- **Automaticky** (`ai_chain`): po dokončení `tech_posouzeni` se spustí řetězec (návrh FVE → baterie → dotace → půjčka). Pokud jeden běh spadne, krok zůstane `in_progress` a zobrazí se událost `ai_chain_error` — **nepokračujte manuálně, dokud schválíte/zamítnete výsledky**.
- **Ručně**: u AI kroku s tlačítkem `▶ Spustit AI (kód)`.
- **Schválení**: výstup se zobrazí v boxu kroku jako `draft` → `Schválit` (použije se dál) nebo `Zamítnout` (zadá se důvod). Schvaluje admin/antelon/sales; ne každý má na to právo.

### 3.5 Notifikace

Zvonek 🔔 v hlavičce shrnuje: plánování kroku konkrétní osobě, „čeká na zákazníka“ (odeslání nabídky/SoD), chyby AI řetězce. Klikem „Přečteno“ se označí vše jako přečtené.

---

## 4. Montér / revizní technik (electrician, roofer, inspector)

- **Časové výkazy** (`Pipeline detail → Časové výkazy`): vyberete krok (nebo „volný čas“ — jen admin/antelon), zadáte minuty, **typ**:
  - `admin` — kancelářská práce,
  - `práce (montér)` — fyzická montáž/revize,
  datum a poznámku → `Zapsat čas`.
- Čas se promítá do skutečných minut kroku i do **ekonomiky** (sazba dle role).
- **Výkaz montérů (admin)**: `POST /admin/reports/monteri-csv?from&to` nebo odkaz „stáhnout CSV“ v záložce Časové výkazy — CSV s uživatelem, kroky, minutami, projektem a typem.

---

## 5. Nákupčí / skladník (buyer, warehouse) — materiály

Stránky: globální číselník `/materialy` + matice projektu `/projects/{id}/materialy`.

1. **Číselník** (admin/buyer): kód, název, jednotka, cena. Tlačítko „Přidat do číselníku“.
2. **Bilance projektu** (vyberte projekt): tabulka materiál × 4 pruhy:
   - **Plán** — kolik se má spotřebovat,
   - **Objednávka** (buyer), **Výdej** (warehouse), **Skutečnost** — co reálně bylo použito.
   - Cena se uloží jako **snapshot** při prvním přiřazení (změna ceníku nemění historické projekty).
3. **Přiřadit materiál**: vyber materiál, množství, pruh → `Přidat`.
4. Součtový řádek „Celkem Kč“ = plán × cena snapshotu.

---

## 6. Ekonomika (`Pipeline detail → Ekonomika`)

- Zobrazení **plán vs skutečnost** po složkách **admin** a **práce zvlášť** (nikdy se nesčítají do jednoho sloupce).
- Sazby z číselníku **RateCard** (`Administrace → Sazby`): kancelářské role 500 Kč/h (výchozí), montáž 450–550 Kč/h.
- **Marže** z číselníku `settings` (klíč `margin`, výchozí **30 %**).
- `Doporučená cena` = plán × (1 + marže); `Podle skutečnosti` = skutečný náklad × (1 + marže).

> Interpretace: pokud `Doporučená cena` < součet faktur, projekt je v plusu nad plánovanou marži a naopak. Smluvní sleva −2 500 Kč je už ve Fakturaci.

---

## 7. Admin (`/admin/pipeline`)

Záložky:

1. **Import** — nahrání `PROCESNÍ DISPEČINK.xlsx` (idempotentní: duplicitní zakázky se přeskočí). Po importu se objeví zakázky na tabuli včetně stavů, dat a poznámek z Excelu.
2. **Šablony** — seznam 11 šablon (`rd`, `byt`, `firma`, `obec`, `bojler`, `rozsireni`, `wb`, `ostatni`, `reklamace`, `elektroprace`, `carport`, `kontrola`…). U každého kroku lze editovat **název** a **odhady minut (admin/práce)** — uloží se po opuštění pole (onBlur). Změny ovlivní jen **nově připojované** projekty.
3. **Uživatelé a role** — přiřazení více rolí uživatelům (klikací čip role).
4. **Sazby (RateCard)** — Kč/hod pro admin i práci; zaškrtnutí aktivní/neaktivní.

### Připojení šablony k projektu

Projekt, který nemá pipeline (např. nově ručně vytvořený), připojíte přes API nebo plánovaný UI v budoucnu:
`POST /api/v1/projects/{id}/pipeline/attach { "template_code": "ostatni" }`.

### Admin zásahy do kroku (v havarijních situacích)

Přes `POST /api/v1/projects/{id}/steps/{step_id}/admin`: `skip` / `revert` (vrácení do předchozího stavu) / `cancel` / `add_step` (přidání kroku ze šablony) / `remove_step`.

---

## 8. Zákazník (customer portál)

1. Dostanete **sdílecí odkaz** `/p/{kód}` (kód je na kartě projektu).
2. Bez přihlášení: **teaser** — vybrané sekce zprávy rozostřené, PDF s vodoznakem.
3. Po přihlášení/registraci → „**Připojit se k projektu**“ → plný náhled + **Procesní stav zakázky**:
   - barevné tečky u každého kroku (zelená=hotovo, žlutá=probíhá, modrá=naplánováno, šedá=nezahájeno),
   - kroky **„čeká na vás“** (sběr podkladů, odsouhlasení nabídky, podpis SoD) jsou zvýrazněné.
4. Akce neprovádíte sami — krok „odeslal“ Vám obchodník, Vy mu podklady dodáte a kontaktujete ho; **smlouvy/plné moci podepisujete přes obchodníka** (elektronický podpis je mimo V1).

---

## 9. API (pro pokročilé / integrace)

Základ: `http://<host>:8051/api/v1`, auth `Authorization: Bearer <token>` (`POST /auth/login`).

| Oblast | Endpointy |
|---|---|
| Import | `POST /admin/import/dispecink` |
| Šablony | `GET /admin/pipeline-templates`, `GET/PUT …/{id}/steps[/{step_id}]` |
| Pipeline | `GET /projects/{id}/pipeline`, `POST …/steps/{sid}/transition`, `POST …/steps/{sid}/admin` |
| AI | `POST …/steps/{sid}/run-ai`, `POST …/steps/{sid}/review-ai`, `GET …/steps/{sid}/ai-results` |
| Časy | `POST/GET /projects/{id}/time-entries`, `GET …/time-entries/summary`, `GET /admin/reports/monteri-csv?from&to` |
| Materiály | `GET/POST /materials`, `GET/POST /projects/{id}/materials`, `GET …/materials/balance` |
| Fakturace | `GET/POST /projects/{id}/invoice-items`, `POST …/{item_id}/status` |
| Ekonomika | `GET /projects/{id}/economy` |
| Ostatní | `GET/PUT /admin/rate-cards…`, `GET /admin/users`, `PUT /admin/users/{id}/roles`, `GET/POST /notifications…` |

---

## 10. Nasazení a data

- Migrace produkční DB proběhne automaticky při startu backendu (`init_db` → `_migrate` + `create_all`) — **nedestruktivní** (ALTER + backfill). Nové tabulky: `settings`, `pipeline_templates`, `pipeline_steps`, `project_pipelines`, `project_steps`, `step_events`, `pipeline_ai_results`, `rate_cards`, `time_entries`, `materials`, `project_materials`, `invoice_items`, `notifications`.
- Nasazení: `./deploy.sh` na serveru (záloha `data/reportgen.db` → `git pull --ff-only` → `docker compose up -d --build` → healthcheck).
- Po nasazení **importujte aktuální dispečink** přes `Administrace → Import` (idempotentní).

---

## 11. FAQ / tipy

- **„Krok nejde začít“** — nesplněná brána/předchozí krok. Dořešte předchozí krok (nebo admin `skip`/`revert`).
- **AI výstup se nenačetl** — krok zůstal `in_progress` a je událost `ai_chain_error`: opravte vstup (parametry projektu) a spusťte AI ručně.
- **Faktura 2 500 Kč chybí** — zkontrolujte, že byl krok `odsouhlaseni_predbezne` skutečně dokončen („pokračujeme“), ne „Zamítnuto“ (pak je zakázka `cancelled` a faktura správně není).
- **Materiál změnil cenu** — historické projekty drží snapshot ceny; nový projekt vezme aktuální ceník.
- **Marže** — mění se v číselníku `settings` (klíč `margin`), výchozí 0.30.
- **Chybí role v přepínači** — uživatel má jen jednu roli, nebo mu admin nepřiřadil další.