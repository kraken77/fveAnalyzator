# Implementační plán — Procesní pipeline (Dispečink) pro Antelon Energy

**Datum:** 2026-09-24
**Zdrojový design:** `docs/superpowers/specs/2026-09-24-procesni-pipeline-design.md` (schváleno)
**Status:** k realizaci — přípraven pro implementaci na stroji drakisa

---

## 0. Kontext a prostředí (čti první)

Tento plán provede implementaci **procesního dispečinku** — typového workflow pro zakázky s tvrdými přechody, paralelními větvemi, podmíněnými kroky, automatickými akcemi, AI kroky, ekonomikou, materiály a rozšířenými rolemi. Celý scope je rozdělen na milníky **M1–M6**; každý milník končí spustitelným, otestovaným stavem a vlastním commitem.

### Kde se implementuje
- **Vývoj běží na serveru drakisa** v izolovaném dev workspace (např. `/home/roman/dev/antelon-energy`), **NE** v produkci `/home/roman/apps/antelon-energy`.
- Produkce (`/home/roman/apps/antelon-energy`, data `reportgen.db`, `data/projects/`, `spot_market.db`) se **nesmí dotknout**. Veškeré testy a běhy jen v dev workspace s vlastní dev databází `data/reportgen.db`.
- Nasazení do produkce až po review přes `./deploy.sh` v produkčním adresáři (skript už je v repu).

### Technické prostředí drakisa
| Nástroj | Verze | Dopad |
|---|---|---|
| python | 3.11.14 | menší rozdíl oproti lokálu (3.12); žádné breaking change předpokládáme — ověřit při instalaci deps |
| node | **v12.22.9** | hostí node je starý → **frontend se buildí jen přes Docker** (multi-stage `node:20`) nebo přes CI; lokální `npm run build` na hostu **ne** |
| docker | 29.2.1 | k dispozici; build `docker compose` |

### Jak spustit backend lokálně na drakisa (dev)
```bash
cd /home/roman/dev/antelon-energy
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
# DB cesty jsou CWD-dependentní (backend/app/reportgen/storage.py: DB_PATH -> <repo>/data/reportgen.db)
# -> backend MUSÍ startovat z kořene repa, aby data padala do dev data/
./venv/bin/uvicorn backend.main:app --reload --port 8052   # dev port (produkce má 8051)
```
- Dev DB `data/reportgen.db` vytvoří `init_db()` automaticky.
- Frontend se testuje buildem a E2E; dev režim frontendu: `npm install` + `npm run dev` (vyžaduje Node 20 — na drakisa přes `docker run node:20` nebo vynechat a testovat přes build + E2E).

### Testy
- Nové testy: `tests/reportgen/` (pytest, unittest.mock pro AI moduly). Do `tests/reportgen/conftest.py` přidat `sys.path` pro `backend/app` (stávající `tests/conftest.py` je Playwright-only — nedotýkej se ho).
- Spouštění: `cd /home/roman/dev/antelon-energy && ./venv/bin/python -m pytest tests/reportgen -q`
  - (některé starší testy v `tests/test_e2e.py` vyžadují Playwright/Chromium — přeskočí se, pokud nemají deps; na to nespoléhat)
- Každý úkol = **TDD**: nejdřív (červený) test, pak implementace, pak zelená + commit.

### Konvence
- DB přístup přes `get_db`/`Session` z `backend/app/reportgen/storage.py`.
- Router: rozšiřovat `backend/app/reportgen/router.py` (prefix `/api/v1`) nebo přidat samostatné routry (`pipeline.py`, `ai.py`, `economy.py`) include-nuté v `router.py`. **Preferuj nové soubory** — router.py už má 680 řádků.
- Datum/čas: `datetime.utcnow()` (shodné se stávajícím kódem).
- JSON sloupce = SQLAlchemy `Text` + `json.dumps/loads` (stávající vzor).
- Commit messages konvence viz stávající repo (`feat(...)`, `fix(...)`, `test(...)`).

---

## Souborová mapa

| Soubor | Účel | M |
|---|---|---|
| `backend/app/reportgen/storage.py` | modely + migrace (rozšířit) | M1 |
| `backend/app/reportgen/pipeline_seed.py` | **nový** — definice 11 šablon a ~57 kroků + seed do DB | M1 |
| `backend/app/reportgen/import_dispecink.py` | **nový** — parser XLSX + import 46 zakázek | M1 |
| `backend/app/reportgen/pipeline.py` | **nový** — workflow engine (stavy, brány, hooky, admin zásahy) | M2 |
| `backend/app/reportgen/ai_service.py` | **nový** — AI kroky (fve, baterie, dotace, půjčka, nabídka, vizualizace) | M3 |
| `backend/app/reportgen/subsidy.py` | **nový** — zjednodušený NZÚ 2026 modul (port pravidel z `nz2026-calculator`) | M3 |
| `backend/app/reportgen/loan_rules.py` | **nový** — pravidla bezúročné půjčky (ano/ne + částka) | M3 |
| `backend/app/reportgen/economy.py` | **nový** — kalkulace nákladu/marže, časové výkazy, materiály, fakturace | M4 |
| `backend/app/reportgen/pipeline_router.py` | **nový** — API endpointy pipeline (workflow+AI+ekonomika) | M2–M4 |
| `backend/app/reportgen/auth.py` | rozšířit: `has_role`, multi-role helpery, registrované role | M2 |
| `backend/main.py` | bez strukturních změn (AI moduly se importují z reportgen) | — |
| `frontend-web/src/api/*` | klienti API pro pipeline | M5 |
| `frontend-web/src/pages/Dispecink.tsx` | tabule zakázek | M5 |
| `frontend-web/src/pages/PipelineDetail.tsx` | detail pipeline projektu | M5 |
| `frontend-web/src/pages/Materialy.tsx` | bilance materiálů | M5 |
| `frontend-web/src/pages/AdminPipeline.tsx` | admin: šablony/kroky/role/sazby/číselníky/import | M5 |
| `frontend-web/src/components/RoleSwitcher.tsx` | přepínač rolí | M5 |
| `frontend-web/src/App.tsx`, `Layout.tsx`, `AuthContext.tsx`, `ProtectedRoute.tsx` | routy + role-switcher + customer portál | M5 |
| `tests/reportgen/conftest.py` | **nový** — path setup + fixture in-memory DB | M1 |
| `tests/reportgen/test_models.py` | migrace + modely | M1 |
| `tests/reportgen/test_import.py` | import XLSX | M1 |
| `tests/reportgen/test_workflow.py` | stavy, brány, paralelní větve, podmínky, hooky, admin zásahy | M2 |
| `tests/reportgen/test_ai.py` | AI kroky + schvalování | M3 |
| `tests/reportgen/test_economy.py` | kalkulace, materiály, fakturace, výkazy | M4 |
| `tests/test_dispecink_e2e.py` | E2E Playwright (login → dispečink → akce) | M5–M6 |
| `docs/superpowers/plans/...` | tento plán | — |
| `README.md` | dokumentace (sekce Dispečink) | M6 |

---

# M1 — DB, migrace, šablony, import

## M1.1 Modely a migrace (`storage.py`)

### Úkol M1.1.1 — Rozšířit `User` o multi-role
- Přidat sloupec `roles_json = Column(Text, nullable=True)` (JSON pole rolí). Sloupec `role` (primární role) **zůstává** kvůli zpětné kompatibilitě stávajících endpointů; nový kód používá `roles`.
- Přidat na `User`:
  ```python
  @property
  def roles(self) -> list:
      try:
          return json.loads(self.roles_json) if self.roles_json else [self.role]
      except Exception:
          return [self.role]

  def has_role(self, role: str) -> bool:
      return role in self.roles

  def set_roles(self, roles: list):
      if not roles:
          roles = ["customer"]
      self.roles_json = json.dumps(list(dict.fromkeys(roles)))
      self.role = roles[0]  # primární role pro zpětnou kompatibilitu
  ```
- Nové role (číselník) — konstanty v `storage.py`:
  `ROLES = ["admin", "antelon", "sales", "designer", "warehouse", "buyer", "subsidy", "connection", "roofer", "electrician", "inspector", "customer"]`

### Úkol M1.1.2 — Rozšířit `Project`
- Přidat sloupce: `type = Column(String(30), nullable=False, default="ostatni")`, `status = Column(String(20), nullable=False, default="lead")`, `tech = Column(String(255), nullable=True)`.
- `status` číselník: `lead | active | done | cancelled`.

### Úkol M1.1.3 — Nové tabulky (přidat modely do `storage.py`)
```python
class PipelineTemplate(Base):
    __tablename__ = "pipeline_templates"
    id, code(String(30) unique), name(String(100)), zakazka_type(String(30)),
    version(Integer default 1), active(Boolean default True), created_at

class PipelineStep(Base):
    __tablename__ = "pipeline_steps"
    id, template_id(FK pipeline_templates.id, ondelete CASCADE),
    code(String(50)), name(String(200)), phase(String(50)),
    order(Integer), est_admin_minutes(Integer default 0), est_work_minutes(Integer default 0),
    admin_rate_role(String(30) default "sales"), work_rate_role(String(30) default "electrician"),
    state_model(String(20) default "simple"),        # simple | contract | ai | material
    allowed_roles_json(Text), condition_json(Text, nullable), auto_hook(String(50), nullable),
    parallel_group(String(50), nullable)

class ProjectPipeline(Base):
    __tablename__ = "project_pipeline"
    id, project_id(FK unique), template_id(FK), created_at

class ProjectStep(Base):
    __tablename__ = "project_steps"
    id, project_id(FK index), step_id(FK pipeline_steps.id),
    status(String(20) default "not_started"),        # not_started|planned|in_progress|done|skipped|not_applicable|cancelled
    plan_date(DateTime nullable), assigned_user_id(FK users.id nullable),
    note(Text nullable), started_at, done_at(DateTime nullable),
    real_admin_minutes(Integer default 0), real_work_minutes(Integer default 0)
    UniqueConstraint(project_id, step_id)

class StepEvent(Base):
    __tablename__ = "step_events"
    id, project_id(FK index), step_id(FK project_steps.id), action(String(50)),
    from_status(String(20), nullable), to_status(String(20), nullable),
    user_id(FK), at(DateTime default utcnow), note(Text nullable)

class PipelineAiResult(Base):
    __tablename__ = "pipeline_ai_results"
    id, project_id(FK index), step_id(FK project_steps.id), kind(String(50)),
    input_json(Text), output_json(Text), pdf_version_id(FK pdf_versions.id nullable),
    status(String(20) default "draft"),              # draft|approved|rejected
    created_by(FK users.id), reviewed_by(FK nullable), reviewed_at(nullable), created_at

class Material(Base):
    __tablename__ = "materials"
    id, code(String(50) unique), name(String(200)), unit(String(10) default "ks"),
    price(Float default 0), active(Boolean default True), created_at

class ProjectMaterial(Base):
    __tablename__ = "project_materials"
    id, project_id(FK index), material_id(FK materials.id), price_snapshot(Float),
    qty_planned(Float default 0), qty_actual(Float default 0),
    lane(String(20) default "plan"),                 # plan|order|issue|actual
    step_id(FK project_steps.id nullable), created_at

class TimeEntry(Base):
    __tablename__ = "time_entries"
    id, project_id(FK index), step_id(FK project_steps.id nullable),
    user_id(FK), minutes(Integer), work_date(Date), kind(String(10) default "admin"),  # admin|work
    note(Text nullable), created_at

class RateCard(Base):
    __tablename__ = "rate_cards"
    id, role(String(30)), kind(String(10) default "admin"),   # admin|work
    rate_czk_h(Float default 500), active(Boolean default True)

class InvoiceItem(Base):
    __tablename__ = "invoice_items"
    id, project_id(FK index), step_id(FK project_steps.id nullable),
    doc_type(String(30)),                                 # posouzeni|zaloha|final|final_discount
    doc_number(String(30) nullable), description(String(255)),
    amount_czk(Float), status(String(20) default "draft"), created_at

class Notification(Base):
    __tablename__ = "notifications"
    id, user_id(FK users.id), project_id(FK nullable), text(String(500)),
    read(Boolean default False), created_at
```
- `created_at` všude `default=datetime.utcnow`.

### Úkol M1.1.4 — Migrace existující produkční DB (bez ztráty dat)
Implementovat `_migrate(engine)` volané na začátku `init_db()` (před `create_all`):
- `PRAGMA table_info(users)`/`table_info(projects)` → chybějící sloupce přidat přes `ALTER TABLE` (SQLite: `ALTER TABLE users ADD COLUMN roles_json TEXT`; `projects` přidat `type/status/tech`).
- Backfill: `UPDATE users SET roles_json = '["' || role || '"]' WHERE roles_json IS NULL`; nastavit `projects.type='ostatni'`, `projects.status='lead'` pro NULL/chybějící.
- Nové tabulky vytvoří stávající `Base.metadata.create_all`.
- **Test (M1.1.4)**: vytvořit starou DB s `users(role)`, bez nových sloupců → `init_db` na ní → sloupce/tabulky existují, data zachována, roles_json = `["role"]`.

### Úkol M1.1.5 — Seed sazeb a prázdných číselníků
- V `init_db()` po migraci: pokud `RateCard` prázdná, seednout `admin/500` pro role `sales, designer, buyer, subsidy, connection, warehouse` a `work/...` defaulty (roofers 450, electrician 500, inspector 550, sales 500 — **placeholder, kalibruje se**).

## M1.2 Šablony pipeline (`pipeline_seed.py`)

### Úkol M1.2.1 — Definice šablon (statická data ve formátu: list of dicts)
- 11 typů: `rd, byt, firma, bojler, rozsireni, wb, ostatni, reklamace, elektroprace, carport, kontrola`.
- **Plné šablony `rd`/`byt`/`firma`** — kroky (kód, název z Excelu, fáze, `est_admin` z Excelu, AI/contract/condition/hook, `est_work` = pracovní default pro montážní kroky; admin časy **z Excelu řádek „čas (min)“**, totál 553 min):

| code | name (Excel) | phase | admin(min) | work(min) | pozn. |
|---|---|---|---|---|---|
| `lead_zaevidovani` | Zaevidování poptávky - LEAD, OP | lead | 1 | 0 | |
| `lead_telefon` | První telefonát (do 24h) | lead | 20 | 0 | |
| `nabidka_indikativni` | První indikativní nabídka dle telefonátu | lead | 10 | 0 | |
| `odsouhlaseni_predbezne` | Odsouhlasení předběžné nabídky - pokračujeme | lead | 0 | 0 | **hook `invoice_2500`**; sub-výsledek „Zamítnuto" → zrušení |
| `overeni_vlastnictvi` | Ověření vlastnictví | priprava | 5 | 0 | |
| `rocni_spotreba` | Zjištění roční spotřeby | priprava | 5 | 0 | |
| `stop_pamatkari` | Prověření stop-stavů (Památkáři, CHKO) | priprava | 5 | 0 | podmínka `stop_stavy="ano"` |
| `stop_strecha` | Prověření stop-stavů (Střecha) | priprava | 5 | 0 | |
| `stop_azbest` | Prověření stop-stavů (Azbest) | priprava | 5 | 0 | |
| `sber_podkladu` | Sběr podkladů od zákazníka | priprava | 5 | 0 | |
| `tech_posouzeni` | Technické posouzení na dálku | priprava | 10 | 0 | sbírá dotace/půjčka/stop-stavy → podmínky |
| `navrh_fve` | Návrh velikosti FVE | priprava | 10 | 0 | **AI** (`fve_size`, auto) |
| `kapacita_baterie` | Návrh kapacity baterie | priprava | 0 | 0 | **AI** (`battery`, auto) |
| `dotacni_uspora` | Výpočet dotační úspory | priprava | 5 | 0 | **AI** (`subsidy`, auto) |
| `moznost_pujcky` | Možnost bezúročné půjčky | priprava | 20 | 0 | **AI** (`loan`, auto) |
| `nabidka_podrobna` | Vytvoření podrobnější nabídky | priprava | 10 | 0 | **AI** (`offer_pdf`, ručně) |
| `vizualizace` | Příprava vizualizace | priprava | 0 | 0 | **AI** (`visualization_pdf`, ručně) |
| `odeslani_nabidky` | Odeslání nabídky | priprava | 10 | 0 | |
| `followup_1` | První follow-up (po 3 dnech) | sledovani | 10 | 0 | |
| `konzultace_navratnost` | Konzultace návratnosti | sledovani | 5 | 0 | |
| `konzultace_znacky` | Konzultace značek komponentů | sledovani | 5 | 0 | |
| `planovani_prohlidky` | Plánování osobní prohlídky | sledovani | 5 | 0 | |
| `osobni_schuzka` | Osobní schůzka na místě | sledovani | 120 | 0 | |
| `statika_strechy` | Kontrola statiky střechy | priprava | 5 | 0 | |
| `trasovani_kabelaze` | Trasování kabeláže | priprava | 10 | 0 | |
| `jistice_rozvadec` | Kontrola jističů a rozvaděče | priprava | 10 | 0 | |
| `teplota_technologie` | Prověření teploty pro technologii | priprava | 5 | 0 | |
| `revize_nabidky` | Revize a úprava nabídky | priprava | 10 | 0 | |
| `finalni_rozpocet` | Finální schválení rozpočtu | priprava | 10 | 0 | |
| `sod` | Podpis Smlouvy o dílo (SoD) | smlouva | 10 | 0 | **contract**; sub-stavy zasláno/podepsáno; hook `sod_signed` |
| `plna_moc` | Podpis plná moc pro Distributora (ČEZ, PRE) | smlouva | 10 | 0 | **contract** |
| `zalohova_faktura` | Vystavení zálohové faktury | finance | 5 | 0 | **paralelní g. `smlouva_after`** |
| `kontrola_zalohy` | Kontrola připsání zálohy | finance | 5 | 0 | **g. `smlouva_after`** |
| `sop` | Žádost o připojení (Smlouva) SOP | pripojeni | 20 | 0 | **contract**; **g. `smlouva_after`**; hook `sop_signed` |
| `sledovani_vykonu` | Sledování schválení rezervovaného výkonu | pripojeni | 20 | 0 | **g. `smlouva_after`** |
| `registrace_nzu` | Podání registrace do NZÚ | dotace | 20 | 0 | **g. `smlouva_after`**; podmínka `dotace="ano"` |
| `administrace_pujcky` | Administrace bezúročné půjčky | dotace | 5 | 0 | **g. `smlouva_after`**; podmínka `pujcka="ano"` |
| `priprava_projektu` | Příprava projektu | realizace | 30 | 0 | |
| `skladova_kontrola` | Skladová kontrola materiálu | realizace | 20 | 0 | role skladník |
| `objednani_dodavatele` | Objednání u dodavatelů | realizace | 30 | 0 | role nákupčí |
| `planovani_montaze` | Plánování termínu montáže střecha | realizace | 5 | 0 | |
| `stavba_montaz` | Stavební a střešní montáž | realizace | 0 | 480 | role roofer; **work** |
| `elektro_montaz` | Elektro-montáž komponentů | realizace | 2 | 360 | role electrician; hook `elektro_done` |
| `propojeni_test` | Propojení a ostrovní test | realizace | 0 | 120 | role electrician |
| `predani_zauceni` | Předání a zaškolení | predani | 0 | 90 | |
| `monitorovaci_app` | Instalace monitorovací aplikace | predani | 0 | 30 | |
| `mereni_revize` | Měření a revize systému | revize | 0 | 60 | role inspector; **g. `revize_after`** |
| `podklady_revize` | Zaslání podkladů pro revizní zprávu | revize | 0 | 0 | role inspector; **g. `revize_after`** |
| `revizni_zprava` | Vystavení Výchozí revizní zprávy | revize | 5 | 0 | role inspector; **g. `revize_after`** |
| `utp` | Žádost o umožnění ÚTP | pretoky | 10 | 0 | role connection; **g. `pretoky_after`**; podmínka `pretoky="ano"` |
| `vymena_elektromeru` | Výměna elektroměru | pretoky | 0 | 0 | role connection; **g. `pretoky_after`** |
| `prevzeti_odchylky` | Získání odběratele na přetoky (převzetí odpovědnosti za odchylku) | pretoky | 0 | 0 | role connection; **g. `pretoky_after`** |
| `kontrola_prevodni_smlouvy` | Kontrola smlouvy na přetoky | pretoky | 5 | 0 | role connection; **g. `pretoky_after`** |
| `povoleni_pretoku` | Povolení přetoků na střídači | pretoky | 5 | 0 | role connection; **g. `pretoky_after`** |
| `sdileni_komunita` | Nastavení sdílení v komunitě | pretoky | 5 | 0 | **contract** (zasláno/vyřízeno); **g. `pretoky_after`** |
| `konecna_faktura` | Vystavení konečné faktury | final | 10 | 0 | poslední krok |
| `dolozeni_sfzp` | Doložení realizace na SFŽP | dotace | 10 | 0 | podmínka `dotace="ano"` |

- `allowed_roles` per krok dle fáze (V1):
  - lead/priprava/smlouva/finance/konecna_faktura → `["sales","admin","antelon"]`
  - `tech_posouzeni`, `navrh*`, `kapacita*`, `dotacni*`, `vizualizace`, statika/trasování/jističe/teplota → `["designer","sales","admin","antelon"]` (schválení AI: obchodník nebo projektant)
  - `sop`,`sledovani_vykonu`, pretoky → `["connection","admin","antelon"]`
  - `registrace_nzu`,`dolozeni_sfzp`,`administrace_pujcky` → `["subsidy","admin","antelon"]`
  - `skladova_kontrola` → `["warehouse","admin","antelon"]`; `objednani_dodavatele` → `["buyer","admin","antelon"]`
  - `stavba_montaz` → `["roofer","admin","antelon"]`; `elektro_montaz`,`propojeni_test` → `["electrician","admin","antelon"]`
  - revize → `["inspector","admin","antelon"]`
  - `predani_zauceni`,`monitorovaci_app` → `["sales","roofer","admin","antelon"]`
- **Varianty**:
  - `byt` = stejný seznam; kroky `statika_strechy`, `stop_strecha`, `planovani_montaze`/`stavba_montaz` dostanou `condition_json` s poznámkou (V1: nechat, jen nastavit `note`); jednoduše opakuj plnou šablonu (změna = data, ne kód).
  - `firma` = kopie plné šablony.
  - **Krátké** `bojler`, `rozsireni`, `wb`, `ostatni`:
    `lead_zaevidovani(1)` → `lead_telefon(20)` → `nabidka_indikativni(10)` → `odsouhlaseni_predbezne(0, hook)` → `sber_podkladu(5)` → `tech_posouzeni(10)` → `nabidka_podrobna(10, AI offer_pdf)` → `odeslani_nabidky(10)` → `sod(10, contract)` → `zalohova_faktura(5)` → `kontrola_zalohy(5)` → `objednani_dodavatele(30)` → `planovani_montaze(5)` → `montaz(0, work per typ)` → `predani_zauceni(0,90)` → `konecna_faktura(10)`
  - `reklamace`: `rekl_prijeti(15)` → `rekl_diagnostika(45)` → `rekl_oprava(0, work 240)` → `rekl_predani(15)` (konec = zpráva)
  - `elektroprace`: `lead_zaevidovani(5)` → `tech_posouzeni(15)` → `nabidka_podrobna(10, AI)` → `sod(10, contract)` → `elektro_montaz(0,work)` → `mereni_revize(0,work)` → `revizni_zprava(5)` → `predani_zauceni(0,30)` → `konecna_faktura(10)`
  - `carport`: `lead_zaevidovani(5)` → `tech_posouzeni(15)` → `nabidka_podrobna(10, AI)` → `sod(10, contract)` → `priprava_pozemku(0)` → `montaz_streseni(0,work 480)` → `elektro_montaz(0,work 240)` → `revizni_zprava(5)` → `predani_zauceni(0,30)` → `konecna_faktura(10)`
  - `kontrola` (revize): `knt_planovani(15)` → `knt_provedeni(0,work 90)` → `knt_zavady(30)` → `knt_predani(15)` → `konecna_faktura(10)`

### Úkol M1.2.2 — Seed funkce
- `ensure_pipeline_templates(db)` — upsert dle `template.code`; kroky upsert dle `(template_id, code)` — **idempotentní** (neznmožovat při opakovaném běhu).
- Volá se z `init_db()` po migraci.
- `condition_json` formát (V1): `{"project_param_in": {"fve_params.dotace": ["ano"]}}` a/nebo `{"requires_step": ["<code ne_potrebne>"]}` — vyhodnocovač v M2.

### Úkol M1.2.3 — `attach_template(db, project, template_code)`
- Vytvoří `ProjectPipeline` + instanci `ProjectStep` pro každý krok šablony (status `not_started`, `assigned_user_id=None`).

## M1.3 Import Excelu (`import_dispecink.py`)

Zdroj: `Podklady/Procesy/PROCESNÍ DISPEČINK.xlsx` (list `Přehled`, 46 řádků dat; list `reklamace` prázdný). Parsovat **pandas + openpyxl** (pandas je závislost backendu).

### Realná struktura listu „Přehled" (0-indexované řádky)
- řádek **1**: značky osob/AI per sloupec (informativní), řádek **3**: „čas (min)" = `est_admin` per sloupec
- řádek **4**: hlavička — sloupec 3 „Příjmení", 4 „jméno", 5 „aktivní neaktivní", sloupce 6–68 = názvy kroků (víz M1.2.1)
- řádek **5**: sub-stavy smluv (stále v hlavičce): 36 „zasláno"/37 „podepsáno" (SoD), 38/39 (plná moc), 42/43 (SOP), 65 „zasláno"/66 „vyřízeno" (sdílení v komunitě); sloupec 20 „zadáno"/21 „hotovo" (Možnost půjčky = AI výstup)
- řádek **6+**: jeden projekt na řádek; buňka = `a`/`x`/datum (`1.8.26`) / text poznámky

### Pravidla mapování buňky → krok (funkce `_map_value(s: str)`):
- datum `d.m.yy` → krok `done` (`done_at` = datum) + `StepEvent(„done")`; pokud krok má sub-stavy (contract): text v buňce „zasláno"/„podepsáno" → odpovídající událost.
- `a` (resp. `x`) → krok `done` („aktivní"/hotovo), ke kroku přidat `note="a"` není třeba — stačí `done`.
- buňka s textem → `note`.
- Sloupec 5 „aktivní neaktivní": `aktivní` → `Project.status="active"`, `neaktivní` → `Project.status="cancelled"`.
- Typ zakázky → sloupec 2 „typ" v datech (RD/byt/firma/bojler/rozšíření/WB/ostatní) → vyber šablonu (`map_zakazka_type()`). Pozor: typové hodnoty v Excelu znormalizuj (lower, bez diakritiky: `rd`, `byt`, `firma`, `bojler`, `rozsireni`, `wb`, `ostatni`).
- Jméno projektu: `"{příjmení} {jméno}"` (např. „Vopršálek"); `customer_name` = totéž.
- `tech` ← sloupec technologie.
- **Idempotence**: pokud `Project` se stejným `share_code`-opakování nechceme — klíč: znovuspuštění importu **nereimportuje** řádky, které se shodují jménem (`name`), jen je přeskočí a vrátí count.

### Úkol M1.3.1 — `parse_dispecink_xlsx(path) -> list[dict]`
- čte sešit, vrátí normalizované řádky (dict) připravené na zápis.

### Úkol M1.3.2 — `import_dispecink(path, db) -> {"imported": n, "skipped": m}`
- vytvoří/aktualizuje projekty, připojí šablonu dle typu, nastaví `project_steps`/`step_events`/`note`, `status`, `tech`.
- Pokud typ chybí v datech → default `ostatni`.

### Úkol M1.3.3 — Endpoint `POST /api/v1/admin/import/dispecink`
- `UploadFile` (xlsx, max 10 MB) → uloží do `data/imports/` (vytvořit) → `import_dispecink()` → vrátí `{"imported": n, "skipped": m, "projects": [...]}`.
- **Role:** `require_roles("admin")`.

### NFD/NFC názvy souborů
- CSV/XLSX upload přes `UploadFile` nemá NFD problém (pandas čte stream). Kdyby cesta, použít `unicodedata.normalize("NFC", name)` pro klíče mapování.

## M1.4 Testy M1 (`tests/reportgen/`)
- `conftest.py`: `sys.path.insert(0, <repo>/backend/app)` + fixture `client` (TestClient nad hlavní `app` s dočasnou DB přes `init_db(tmp_path/...)/get_session_factory`) — **vzor**: stávající `get_session_factory(db_path)`, `init_db(db_path)`. TestClient vždy s `RG_*` env defaults.
- `test_models.py`:
  - migrace staré DB beze ztrát (roles_json backfill, projects přidané sloupce),
  - `set_roles`/`has_role`,
  - seed šablon → 11 template, kroky rd ≥ 55 (kontrola počtu), idempotence seedu (2× init → stejný počet),
  - `attach_template` → instance kroků.
- `test_import.py`: fixture zkopíruje `Podklady/Procesy/PROCESNÍ DISPEČINK.xlsx` do tmp; import; `imported == 46`; ukázkový projekt má správný typ, status, `done_at`, kroky; 2. běh → `skipped == 46`; neaktivní řádek → `cancelled`.

## M1 verifikace
```bash
./venv/bin/python -m pytest tests/reportgen/test_models.py tests/reportgen/test_import.py -q
```
Po spuštění backendu: `GET /admin/users`, `POST /admin/import/dispecink` (upload výše zmíněného xlsx) → 46 projektů. Zmeň projektům `status` a zkontroluj `projects` list.
**Commit:** `feat(dispecink): M1 - modely, migrace, 11 sablon, import dispecink xlsx`

---

# M2 — Workflow engine

## M2.1 Základ přechodů (`pipeline.py`)

### Úkol M2.1.1 — Stavy a akce
Stavový model (per `state_model` stepu):
```
simple:   not_started → planned → in_progress → done
          (akce: plan, begin, complete)
contract: not_started → sent → signed            (akce: plan, sent, sign; "sent" vyžaduje zaslání,
          nepovinný krok planned)
ai:       not_started → in_progress(draft čeká) → done  (complete = schválení výstupu, M3)
```
- Speciální (jen admin): `skip` → `skipped` (krok ze stavu vyřazen), `revert` → `not_started|planned` (vrátí), `reassign` (změní `assigned_user_id`), `cancel` → `cancelled`.
- `can_transition(db, project_step, action, user, project) -> (ok: bool, blockers: list[str], error_msg: str|None)`
  - Ověří: (1) krok je z instance patřící projektu, (2) akce je pro stav přípustná, (3) role uživatele ∩ `allowed_roles`, (4) **brána**: všechny *povinné předchozí* kroky mají požadovaný status (viz M2.2).
- `transition(db, project, project_step, action, user, note=None, plan_date=None, assigned_user_id=None) -> project_step`
  - Zapíše `StepEvent`, aktualizuje `status`, `plan_date`, `assigned_user_id`, `started_at`/`done_at`, `project.updated_at`.
  - Po úspěšném `complete`/`sign` zavolá hooky (M2.4).
  - Vrací `HTTPException(403, "Nelze začít — nejsou splněny předchozí potřebné stavy: ...")` při selhání brány; `403` při špatné roli.

### Povinné "předchozí kroky" — výpočet hran
- Vychází se z `pipeline_steps.order` + `parallel_group`:
  - kroky **bez** `parallel_group`: předchůdce = poslední krok s menším `order` (bez group).
  - kroky **s** `parallel_group`: gate = krok v group s nejmenším `order` — ostatní z group se k sobě nevážou; group považována za splněnou, když **všechny kroky group** jsou `done|skipped|not_applicable`; následující krok (po group) má bránu = celá group.
- `condition_json` kroku: pokud obsahuje `requires_step: [codes]` → tyto kroky v instanci taky splněné.
- Funkce `_blockers(db, project_step, ordered_steps, statuses) -> list[str]` vrací názvy nesplněných kroků pro hlášení.

### Úkol M2.1.2 — `get_pipeline_view(db, project_id) -> dict`
Slouží i M1/M5: vrátí `{project, template, steps: [{id, code, name, phase, order, status, plan_date, assigned_user_id, note, real_admin_minutes, real_work_minutes, est_admin_minutes, est_work_minutes, ai: {status, kind}, can: [...], allowed_roles}], events: [...], groups}`.

## M2.2 Brány, paralelní větve, podmínky (testy napřed)
- Implementace: viz M2.1.1 „Povinné předchozí kroky".
- Podmíněné kroky: `_condition_met(db, step, project) -> bool`:
  - `project_param_in`: čte `project.fve_params_json`/`antelon_params_json` (tečka = cesta) a kontroluje výskyt hodnoty; nenalezeno → false.
  - `requires_step`: kontroluje splnění kroku.
  - Nenastavená podmínka → met.
  - Podmíněné kroky **skryje** v `get_pipeline_view` (`hidden: true`) a vynechá z brány, pokud podmínka není splněna.
- Admin může kdykoli `skip`/`revert`/`reassign` (bez ohledu na bránu).

## M2.3 Notifikace (V1)
- Na `plan` s `assigned_user_id`: notifikace přiřazenému „Krok [název] naplánován na [datum]".
- Na otevření větve (hook) a na stav „čeká na zákazníka": notifikace `antelon` (+ `customer` pokud je propojený).
- `GET /notifications`, `POST /notifications/{id}/read` — vlastní notifikace (role dle `user_id`).

## M2.4 Automatické akce (hooky) — implementace v `pipeline.py`
Debug — hooky se zavolají z `transition()` po `complete|sign`:
1. `invoice_2500` (dokončení **odsouhlaseni_predbezne**):
   - default: vytvoř `InvoiceItem(doc_type="posouzeni", description="Posouzení realizace zakázky", amount_czk=2500, status="draft", step_id=...)` + notifikace „vystavena faktura 2 500 Kč".
   - pokud `note` kroku začíná „Zamítnuto" (case-insensitive) **nebo** předáno pole `result="zamitnuto"`: **žádná faktura**, `project.status="cancelled"`, notifikace.
2. `sod_signed` (podpis SoD — akce `sign`): vytvoř `InvoiceItem(doc_type="final_discount", description="Sleva - Posouzení realizace zakázky (2 500 Kč)", amount_czk=-2500)`; notifikace „Otevřena realizační větev".
3. `sop_signed` (podpis SOP): notifikace „Otevřena větev přetoků" (kroky `utp`..`sdileni_komunita` se stávají aktivními pro brány).
4. `elektro_done`: notifikace „Otevřena větev revize".
- Hooky jsou **idempotentní** (2 500 faktura/sleva jen jednou — kontrola existujícího `InvoiceItem` se stejným `doc_type`+`step_id`).

## M2.5 API (`pipeline_router.py`, mount v `router.py` → `router.include_router(pipeline_router)`)
- `GET /pipeline-templates` (admin) — seznam šablon.
- `GET /pipeline-templates/{id}/steps` (admin) — kroky.
- `POST /projects/{id}/pipeline/attach {template_code}` (admin/antelon) — připojí šablonu.
- `GET /projects/{id}/pipeline` — `get_pipeline_view`.
- `POST /projects/{id}/steps/{sid}/transition {action, note?, plan_date?, assigned_user_id?}` (RBAC per krok; `assign` jen admin/antelon).
- `POST /projects/{id}/steps/{sid}/admin {action: skip|revert|reassign|add_step|remove_step, ...}` (admin).
- `GET /notifications`, `POST /notifications/{id}/read`.

## M2.6 Testy (`tests/reportgen/test_workflow.py`)
- simple přechody + události + plánování (plan→begin→complete).
- brána: zamítnutí bez splnění předchozího (403 + zpráva), povolení po splnění.
- paralelní group: kroky ve větvi na sobě nezávisí; gate = celá group.
- podmíněný krok: `fve_params.dotace="ano"` → registrace NZÚ aktivní; kontrola `hidden`.
- hook `invoice_2500`: po done default → InvoiceItem 2 500; s „Zamítnuto" → žádný, project cancelled.
- `sod_signed` → final_discount −2 500 (idempotentní).
- admin skip/revert/reassign; non-admin nesmí.
- notifikace při plan.
- `get_pipeline_view` shape.

**Commit:** `feat(dispecink): M2 - workflow engine, brane, paralelni vetve, hooky, notifikace`

---

# M3 — AI kroky

## M3.1 Pravidla a porty (`subsidy.py`, `loan_rules.py`)
- `subsidy.py` — port **NZÚ 2026, oblast C.3 (FVE + baterie)** z `nz2026-calculator/index.html`:
  - sazby: **25 000 Kč/kWp**, **15 000 Kč/kWh baterie**, **max 400 000 Kč** (dílčí opatření RD); komplexní: základ 5 kWp × 25 000 + 40 000 Kč za každý další kWp (kód v index.html: `base: 25000, extraKwp: 40000, perKwh: 15000`).
  - `compute_subsidy(kwp, battery_kwh, mode="dilci") -> dict{castka, limit, podminky: [...]}`
  - Jednotkové testy: 10 kWp + 10 kWh → očekávaná částka (per vzorec), cap na 400 000.
- `loan_rules.py`:
  - `evaluate_loan(project_params, subsidy_result) -> dict{eligible: bool, amount_czk, reason}`
  - Pravidla V1: bezúročná půjčka = NZÚ úvěr; `eligible` pokud dotace ano a zákazník souhlas; `amount` = min(dotace, 750 000).

## M3.2 `ai_service.py` — běh AI kroku
- `run_ai(db, project, project_step, user, trigger="auto"|"manual") -> PipelineAiResult`
  - Mapuje `pipeline_step.code` → `kind`:
    - `navrh_fve` → `fve_size`: postav `EnergyAnalysisInput` z `project.fve_params` (+ defaults dle spec), zavolej `run_energy_analysis` a `run_economic_analysis` (přes `backend/main.py`, jak to dělá `router.generate_pdf`). Výstup JSON: `{kwp, vyroba_kwh, vlastni_spotreba_kwh, rocni_uspora_czk, investice_czk, npv, roi_years, sp500_srovnani: {...}}`.
    - `kapacita_baterie` → `battery`: simulovat 2–3 varianty `battery_capacity` (např. 5/10/15 kWh) přes `run_energy_analysis`, vybrat dle samospotřeby + ekonomiky; výstup `{doporuceno_kwh, samospotreba_pct, vyuziti, ...}`.
    - `dotacni_uspora` → `subsidy`: `subsidy.compute_subsidy(kwp, battery)` → `{castka_czk, sazby, max}`.
    - `moznost_pujcky` → `loan`: `loan_rules.evaluate_loan(...)` → `{eligible, amount, reason}`.
    - `nabidka_podrobna` → `offer_pdf`: vygenerovat PDF (energetický+ekonomický report, reuse `router.generate_pdf` logiky; uložit `PdfVersion`, `pdf_version_id`), výstup `{pdf_version_id, url?}`. **Spouštění: `trigger="manual"`**.
    - `vizualizace` → `visualization_pdf`: PDF vizualizace (graf + fotky), **manual**.
  - Výstup vždy `status="draft"`; `input_json` = json vstup (z projekčního stavu), `output_json` = výsledek.
- Po `run_ai` **ukončí** krok v `in_progress` (auto: hook na `complete` předcházejícího kroku v M2 — tj. `complete` kroku `tech_posouzeni` spustí `run_ai` pro `navrh_fve`, pak `kapacita_baterie`, `dotacni_uspora`, `moznost_pujcky` — sekvenčně; výsledky čekají na schválení; samotné **AI kroky zůstávají `in_progress`, dokud člověk neschválí** (M3.3)).
- `review_ai(db, ai_result_id, approved: bool, user, note=None)`:
  - `approved=True` → `status="approved"`, `reviewed_by/reviewed_at`, a **jeho** `ProjectStep.status="done"` + `StepEvent("done", note="Schválen výstup AI")`.
  - `approved=False` → `status="rejected"`, krok zůstane `in_progress`, `note` = důvod; uživatel může spustit `run_ai` znovu.
- Ošetřit selhání modulu: `run_ai` vyhodí `HTTPException(500, "AI krok selhal: ...")`, krok zůstane `in_progress`.

## M3.3 API
- `POST /projects/{id}/steps/{sid}/run-ai {trigger?}` — ruční spuštění (hlavně `offer_pdf`/`vizualizace`; auto kroky povoleny taky).
- `POST /projects/{id}/steps/{sid}/review-ai {result_id, approved, note?}`.
- `GET /projects/{id}/steps/{sid}/ai-results` — draft/výsledky (vč. výstupu JSON).

## M3.4 Testy (`tests/reportgen/test_ai.py`)
- `subsidy.compute_subsidy` vzorce a cap.
- mock `backend.main.run_energy_analysis`/`run_economic_analysis` (unittest.mock) → `fve_size` výstup tvaru; draft; approve → step done + event; reject → zůstane in_progress.
- baterie výběr varianty; půjčka pravidla; `offer_pdf` vytvoří PdfVersion a `pdf_version_id` (mock PDF generace).
- selhání modulu → 500 a stav beze změny.

**Commit:** `feat(dispecink): M3 - AI kroky (fve, baterie, dotace, pujcka, nabidka) + schvalovani`

---

# M4 — Ekonomika, materiály, fakturace, čas

## M4.1 Kalkulace (`economy.py`)
- `calc_step_cost(step, rate_cards) -> dict{admin_minutes, admin_cost, work_minutes, work_cost, total_cost, sell_recommended}`
  - sazba z `rate_cards` dle `admin_rate_role/work_rate_role`; marže default **30 %** (`sell = cost * (1 + margin)`), margin z číselníku `settings` (nová tabulka `settings(key TEXT, value TEXT)`; seed `margin=0.30`).
- `project_economy(db, project_id) -> dict{plan, actual, margin, sell}` — součet přes kroky (plán = est_*, skutečnost = real_* z `time_entries`).
- Rozlišení `kind=admin|work` — **nikdy se nesčítají do jednoho sloupce**.

## M4.2 Časové výkazy
- `POST /projects/{id}/time-entries {step_id?, minutes, work_date, kind, note?}` (RBAC: uživatel zapisuje na kroky, kde má roli; admin/antelon kdekoli).
- `GET /projects/{id}/time-entries` + souhrn `GET /projects/{id}/time-entries/summary {by_user, by_step, by_type}`.
- **Výkaz montérů**: `GET /admin/reports/monteri-csv?from&to` → CSV (uživatel, kroky, minuty, projekt, typ) — export přes `Response(media_type="text/csv")`.
- Po zápisu: příslušný `ProjectStep.real_admin_minutes/real_work_minutes` inkrementuje.

## M4.3 Materiály
- `GET/POST /materials` (admin) — řídí číselník `Material`.
- `GET/POST /projects/{id}/materials {material_id, qty, lane, step_id?, price_snapshot?}` — pole: `plan|order|issue|actual`.
  - `price_snapshot` se nastaví z `Material.price`, pokud není uveden.
- `GET /projects/{id}/materials/balance` — per materiál: plán vs objednáno vs vydáno vs skutečné + rozdíly.

## M4.4 Fakturace
- `GET/POST /projects/{id}/invoice-items` — seznam/přidání (doc_type: `posouzeni|zaloha|final|final_discount`).
- `POST /projects/{id}/invoice-items/{id}/status {status}` — draft→issued; vystavit = vygenerovat `doc_number` (FV formát: `inv-{project_id}-{seq}`).
- `EFEKT 2 500 Kč`: automaticky přes hooky M2 (posouzení při „pokračujeme"; sleva −2 500 při podpisu SoD). Kontrolní součet: pokud existuje `posouzeni`+`final_discount` → zákazník platí 2 500 jen jednou.

## M4.5 Testy (`tests/reportgen/test_economy.py`)
- `calc_step_cost` s rate_cards a marží; plán vs reálný čas se odděluje.
- time_entries: zápis inkrementuje real_*, summary by_user/by_type, CSV export má hlavičku.
- materiály: lane balance, price_snapshot, plán vs skutečnost.
- fakturace: hooky vytvoří posouzeni 2 500 + final_discount −2 500; kontrolní součet; doc_number po vystavení.

**Commit:** `feat(dispecink): M4 - ekonomika, casove vykazy, materialy, fakturace 2500/sleva`

---

# M5 — Frontend (React + Vite, `frontend-web`)

## M5.1 API klient (rozšířit `src/api/`)
- do `src/api/client.ts` přidat typované funkce/fetch promisery: `getPipeline`, `transitionStep`, `runAI`, `reviewAI`, `getTimeEntries`, `addTimeEntry`, `getMaterials`, `addMaterial`, `getInvoiceItems`, `getTemplates`, `importDispecink(file)`, `getNotifications`, `readNotification`.
- `src/types.ts` — rozhraní `PipelineStep`, `TemplateStep`, `Material`, `TimeEntry`, `InvoiceItem`, `AiResult`, `Notification` (korespondují s API).

## M5.2 Role-switcher (`components/RoleSwitcher.tsx` + `AuthContext`)
- `User.roles: string[]`, `activeRole` v AuthContextu (persist do localStorage).
- `Layout.tsx` hlavička: dropdown přepínač rolí (viditelné jen když `roles.length > 1`).
- Per-role viditelnost v menu: Nákupčí (`buyer`) → jen dispečink + materiály + objednávky; Skladník (`warehouse`) → sklad; Montér → montážní úkoly; atd. (mapa rola → cesty).

## M5.3 Stránky (routy v `App.tsx`)
- `/dispecink` (ProtectedLayout) — **Dispecink.tsx**: tabule zakázek; filtry (typ, stav, osoba); sloupcový pohled pipeline (kroky jako sloupce, status jako barevná buňka); kliknutí na projekt → detail; tlačítko import XLSX (admin) + nahrání souboru.
- `/projects/:id/pipeline` — **PipelineDetail.tsx**: kroky (fáze), stavy, plánování (`plan_date` + `assigned_user_id`), přechody, AI spuštění + schválení (draft box), historie `StepEvent`, notifikace; **montér výkaz** (sekce časů).
- `/projects/:id/materialy` — **Materialy.tsx**: matice materiál × laně (plán/objednávka/výdej/skutečnost).
- `/admin/pipeline` — **AdminPipeline.tsx**: šablony/kroky (editace seed kroků přes `PUT /pipeline-templates/{id}/steps`), role, sazby (RateCard), číselníky (materiály), import, uživatelé a jejich role (`GET/PUT /admin/users`, rozšířit na multi-roles).
- **Customer portál** (rozšířit `PublicPreview.tsx` / nová sekce `/p/:code`): pokud je uživatel propojen s projektem, vidí stav pipeline + **úkoly**: nahrát podklady, odsouhlasit nabídku, podepsat SoD/plnou moc (ukazatel stavu; akce ovládá obchodník — customer dostane „čeká na zákazníka"/„hotovo").

## M5.4 Routing & Auth úpravy
- `App.tsx`: přidat nové routy; `Admin` → i `AdminPipeline`. 
- `ProtectedRoute`/`Layout` — aktivní role + případná omezení (adminOnly → `roles.includes("admin")`, zpětně kompatibilní s `role`).
- API odpovědi `/auth/me` + `/auth/login|register` vrátí `roles` pole (backend úprava v M2/M5: přidat `roles=user.roles`).

## M5.5 Ověření frontendu
- Build: `cd frontend-web && npm ci && npm run build` (na drakisa přes `docker run --rm -v $PWD:/app -w /app node:20 sh -c "npm ci && npm run build"`).
- E2E: `tests/test_dispecink_e2e.py` (pytest-playwright, `browser_type_launch_args` ze `tests/conftest.py`):
  - login (dev seed) → `/dispecink` → filtr + otevření projektu → pipeline: dokončí `lead_telefon` (brána `lead_zaevidovani` done) → AI krok navrh_fve → schválení → notifikace; role-switcher (dvě role jednoho uživatele); customer úkol.

**Commit:** `feat(dispecink): M5 - frontend dispecink, pipeline detail, materialy, admin, role-switcher, portal`

---

# M6 — Testy E2E, dokumentace, verifikace importu, regrese

## M6.1 Regrese
```bash
./venv/bin/python -m pytest tests/reportgen tests/test_api_geocoding.py -q   # bez Playwrightu
# Playwright E2E (pokud dostupný):
./venv/bin/python -m pytest tests/test_dispecink_e2e.py -q
```

## M6.2 Verifikace importu v produkci-mód (dev DB)
1. Zapnout backend z kořene repa (dev workspace).
2. `POST /admin/import/dispecink` s `Podklady/Procesy/PROCESNÍ DISPEČINK.xlsx`.
3. Zkontrolovat přes `GET /projects` + `GET /projects/{id}/pipeline`: 46 projektů, stavy/datumy, `step_events`, datové kroky.
4. Automatizovaný sanity test `tests/reportgen/test_import.py` pokrývá stejné scénáře — slouží jako doklad.

## M6.3 Dokumentace
- `README.md`: sekce **„Procesní pipeline (Dispečink)"** — typy zakázek, role, jak použít (import, plánování, AI, ekonomika, materiály), odkazy na spec a plán.
- `docs/superpowers/specs/2026-09-24-procesni-pipeline-design.md` — nechat jako design; plán odkazuje.
- Případné `docs/superpowers/plans/...` zůstává.

## M6.4 Packaging pro nasazení
- Ověřit `deploy.sh` (již v repu) funguje: záloha DB, pull, `docker compose up -d --build`, healthcheck.
- Ujistit se, že nové tabulky přijdou do produktivní DB **migrací v init_db** (žádný destruktivní reset).
- Seznam nových migračních přírůstků pro produkci je v M1 (bezpečné ALTER/backfill).

## M6.5 Akceptační zhodnocení (checklist)
- [ ] 11 šablon se seeduje, admin je vidí a kroky upraví
- [ ] Import 46 zakázek z Excelu (stav, data, poznámky, typ)
- [ ] Workflow: plánování, přechody, brány, paralelní větve, podmínky (dotace/půjčka), admin zásahy
- [ ] 2 500 Kč: faktura při „pokračujeme", žádná při „Zamítnuto" (+ zakázka cancelled), sleva −2 500 u SoD, fakturace ZF/KF
- [ ] AI kroky: draft → schválení/zamítnutí; PDF nabídka/vizualizace
- [ ] Ekonomika: náklad/marže, admin vs work čas, plán vs skutečnost, výkaz montérů CSV
- [ ] Materiály: číselník + 4 pruhy + plán vs skutečnost
- [ ] Role: multi-roles, role-switcher, per-role pohled
- [ ] Customer portál: stav + úkoly
- [ ] Produkční DB zálohovatelná a migrace beze ztrát (M1.1.4 test)

**Commit:** `docs(dispecink): M6 - E2E, dokumentace, verifikace importu`

---

## Nasazení do produkce (po dokončení M1–M6, po review)
```bash
# NA SERVERU drakisa, produkční adresář:
cd /home/roman/apps/antelon-energy
git pull --ff-only
docker system prune -af          # disk je ~98 % plný — uvolnit před buildem
./deploy.sh                      # záloha DB → build → restart → healthcheck
```
- Migrace proběhne při startu backendu (`init_db` → `_migrate`).
- Po nasazení: import produkčního XLSX přes admin UI (idempotentní).

## Rizika a otevřené otázky (na vědomí, blokují = zeptat se uživatele)
1. **Škrty V1**: dokumenty navázané na kroky (karta zakázky/protokoly) a e-mail notifikace jsou mimo V1.
2. **Montážní časy** (est_work_minutes) a sazby montérů jsou placeholder — kalibrovat s uživatelem po M1.
3. **Návrh velikosti FVE**: automatický výpočet bude iterovat parametry — vyžaduje volání `run_energy_analysis` (PVGIS) — sekundy; synchronně OK, ale pozor na price path `data/spot_market.db` pro spot režim.
4. `users.role` zůstává jako primární role (backward compat) — nový kód používá `roles`.
5. Import: typové hodnoty v Excelu se nemusejí přesně shodovat s číselníkem — mapování default `ostatni`.