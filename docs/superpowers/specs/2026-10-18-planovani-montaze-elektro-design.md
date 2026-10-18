# Plánování montáže a elektro — návrh

> Stav: schváleno v chatu 2026-10-18 · Etapy viz sekce 2
> Související: [architektura](../../architektura.md), [procesní pipeline](../prirucka-procesni-pipeline.md)

## 1. Cíl

Pohled **přehled + kalendář** nad projekty, v němž se plánují **pracovní kroky**
montáže a elektroinstalace podle **pracovních čteta** a jejich dostupnosti.
Plán je **simulace** (nic se nezapisuje): vidíme filmy (aktivní zakázky) i
**rezervace** (leadové, které se mohou potvrdit) a **what-if** („co kdyby
dodatká četa“). Rezervace vytvářejí viditelný tlak na obchodníky k potvrzení.

## 2. Etapy

| Etapa | Obsah | Stav |
|---|---|---|
| **1 — backend** | Model `work_crews` + kalendář ČR + čistý scheduler + API + seed | tento plán |
| **2 — frontend** | Stránka `/planovani`: Gantt + kalendář + panel čteta + what-if | po etape 1 |
| **3 — integrace** (později) | Zápis potvrzeného plánu do `ProjectStep.plan_date`, notifikace u expirujících rezervací | později |

## 3. Doména

### 3.1 Pracovní kroky

Plánovatel čte existující data pipeline — **žádné nové sloupce u projektů/kroků**:

- plánují se kroky šablon s `PipelineStep.est_work_minutes > 0`;
- `PipelineStep.work_role` určuje **typ čtety** (`roofer` = montáž,
  `electrician` = elektro; později např. `inspector`);
- **návaznost** = pořadí `PipelineStep.order` v šabloně + podmínky kroků:
  pracovní krok startuje až po dokončení předchozího *pracovního* kroku
  téže zakázky. Nová stadium v budoucnu = nový krok ve šabloně → plánuje se
  automaticky.
- krok s `status` done/skipped/not_applicable/cancelled se přeskočí;
  `in_progress` se plánuje od „dnes“ (okupuje četu od dnes).
- **trvání** = `max(1, ceil(est_work_minutes / 480))` pracovních dnů
  (8h = 1 den, granularita = dny).

### 3.2 Film vs rezervace

| | podmínka |
|---|---|
| **film** | `Project.status == "active"` **nebo** krok `sod` má `status == "done"` (podepsaná SoD) |
| **rezervace** | `Project.status == "lead"` bez podepsané SoD |
| **mimo plán** | `fve_analyza` (pipeline není připojena), `cancelled`, `done`, projekty bez pipeline |

- **Expirace rezervace:** rezervace platí, dokud je projekt starý
  ≤ `PLANOVANI_RESERVATION_TTL_DAYS` (default **30**, čteno ze `settings`,
  viz níže); pak se sama uvolní (nezobrazuje se jako aktivní, UI ji
  označí „expirovaná“). Stárnutí se měří od `Project.created_at`.
- Rezervace **konkurují** o kapacitu čteta; **filmy mají absolutní
  přednost** (řadí se dříve).

### 3.3 Pracovní dny ČR

Pracovní den = pondělí–pátek **mimo státní svátky**. Svátky se **počítají**
pro libovolné roky (žádná data se nestahují, žádné externí API): pevná data
+ velikonočně závislé (Maškopust = Velikonoce−47, Velký pátek = Velikonoce−2,
Velikonoční pondělí = Velikonoce+1), Velikonoce přes computus
(`_easter_sunday`, funkční cca 1900–2099).

## 4. Datový model

Nová tabulka `work_crews` (`backend/app/reportgen/storage.py`,
`Base.metadata.create_all` ji vytvoří automaticky):

```python
class WorkCrew(Base):
    __tablename__ = "work_crews"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    work_type = Column(String(30), nullable=False)   # roofer | electrician | ...
    available_from = Column(Date, nullable=False)
    available_to = Column(Date, nullable=False)
    work_days_json = Column(Text, nullable=True)     # ["po","ut","st","ct","pa"], default všech 5
    absent_dates_json = Column(Text, nullable=True)  # ["2026-11-05", ...]
    active = Column(Boolean, nullable=False, default=True)
```

**Pracovní den čtety** = `available_from ≤ d ≤ available_to`
∩ týden `d.weekday() ∈ work_days` ∩ `d ∉ absent_dates` ∩ pracovní den ČR.

**Seed** (idempotentní, volá se z `init_db()` po `ensure_pipeline_templates`):
`Montáž` (roofer) a `Elektro` (electrician), okno 2026-10-01 → 2027-12-31,
Po–Pá.

**Nastavení:** klíč `planovani_reservation_ttl_days` v existující tabulce
`settings` (default 30, `_seed_settings` doplní).

## 5. Scheduler (čisté jádro — `backend/app/reportgen/planning.py`)

Čistá funkce, **bez DB ani FastAPI** (stejné pravidlo jako `fve_analysis.py`):

```python
@dataclass(frozen=True)
class WorkItem:
    project_id: int
    project_name: str
    step_code: str
    step_name: str
    work_type: str          # roofer | electrician | ...
    duration_days: int      # >= 1
    kind: str               # "firm" | "reserve"

@dataclass(frozen=True)
class Crew:
    name: str
    work_type: str
    available_from: date
    available_to: date
    work_days: frozenset[int]   # weekday(), 0=Po
    absent: frozenset[date]

def schedule(items: Sequence[WorkItem], crews: Sequence[Crew], today: date) -> Plan
```

**Pravidla:**

1. Nic se neplánuje do minulosti (`start ≥ today`).
2. Řazení: filmy dle (důkaz potvrzení → viz 5.1), pak rezervace dle
   `(project_id)`; uvnitř projektu pořadí `WorkItem` = pořadí kroku.
5.1. Pořadí filmů: datum podepsání SoD (`done_at` kroku `sod`), jinak
   `created_at`.
3. Krok projektu startuje **první pracovní den přiřazené čtety**, který je
   ≥ den po skončení předchozího pracovního kroku téhož projektu (nebo ≥
   `today`, pokud předchozích není).
4. Četa dělá **max. 1 krok/den**; krok s `duration_days = N` obsadí četu na
   N po sobě jdoucích pracovních dnech čtety (weekend/svaky/výjimky
   se přeskočí).
5. **Přiřazení čtety:** z čteta správného `work_type` se bere ta, která
   krok dokončí **dříve**; při shodě menší `Crew`… (deterministicky:
   menší ID / abecedně). Četa, jejíž `available_to` nedosahuje, se
   nepoužívá (krok se neprotáhí do budoucna — čeká na jinou četu; pokud
   žádná není, `start=None` → UI „bez čteta“).
6. **Výstup** `Plan`: pro každý `WorkItem` → `start, end, crew_name`
   (nebo `None`); pro každý projekt → `done_date` (end posledního kroku,
   `None` pokud nějaký krok nedostal četu); `makespan` (poslední konec).

**What-if** = stejná funkce s rozšířeným seznamem čteta (žádná persiste).

## 6. Sestavení vstupů (DB → WorkItem)

`build_plan_input(db, today)` v `planning.py` (jedina část modulu, co
potřebuje DB session):

- projekty s připojenou pipeline a `status in ("lead", "active")`;
- z jejich `ProjectStep` + `PipelineStep` vybere pracovní kroky dle 3.1;
- určí `kind` dle 3.2; rezervace starší TTL se vrátí jako
  `kind="expired"` (UI je ukáže šedě, scheduler je ignoruje);
- vrací `(items, crews, calendar_info, projects_meta)`.

## 7. API — nový `backend/app/reportgen/planning_router.py`

Registrovaný v `main.py` přes `_load()` jako ostatní routery.

| Metoda | Cesta | Právo | Výstup |
|---|---|---|---|
| GET | `/api/v1/planning/overview?from=YYYY-MM-DD&to=YYYY-MM-DD` | interní role (`get_current_user` + `is_internal_user`) | `{ today, holidays_in_range[], crews[], items[{project_id, project_name, step_code, step_name, work_type, kind, duration_days, start, end, crew_name}], projects[{id, name, kind, lead_age_days, reservation_expires, done_date, sod_date}] }` — `today` = **reálné dnešek** (plán se na něj kotví); `from`/`to` určuje jen `holidays_in_range` (zobrazovaný rozsah) |
| POST | `/api/v1/planning/simulate` | interní role | body `{ add_crews: { "roofer": 2, "electrician": 1 } }` → `{ items, projects, makespan, crews: [{name, work_type, virtual}] }` (týž formát items/projects jako overview, bez today/holidays; `crews` = základní čety s `virtual: false` + virtuální s `virtual: true`); dodatečné čety = kopie dostupnosti první aktivní čtety daného typu (název „Montáž +1“); pokud typ neexistuje, okno `today..today+180` Po–Pá; počet četa mimo `0–20` → 422 |
| GET | `/api/v1/planning/crews` | admin/antelon | seznam čteta |
| POST | `/api/v1/planning/crews` | admin/antelon | vytvořit |
| PUT | `/api/v1/planning/crews/{id}` | admin/antelon | upravit (název, typ, okno, dny, výjimky, aktivní) |

`holidays_in_range` = svaky z kalendáře v rozmezí (weekendy počítá
frontend). Chybné `from`/`to` → 422.

## 8. Frontend — stránka `/planovani` (etapa 2)

- Nová položka v menu pro interní role (vedle Dispečinku).
- **Gantt:** řádky = projekty (film nahoře, rezervace dole), pruhy = kroky;
  barva = `work_type` (montáž vs elektro); film = plná barva, rezervace =
  šrafovaná/50 %; svaky + weekendy ztmavené (z `holidays_in_range`), čára
  „dnes“. Rozsah = `max(today+90d, makespan+7d)`, takže se dooboru vidí i
  delší plány. **Zoom** Dny (40 px/den, default) / Týdny (ISO týden,
  „19.–25.10.“) / Měsíce; horní řada = meze měsíců (při zoomu Měsíce roky).
  **Skok do období:** date picker + „Jít“ + „Dnes“ (plynulé posunutí na
  sloupec daného dne). Na hrubých zóomech (šířka < 60 px) pruh bez textu,
  detail v tooltipu. **Virtuální čety ze simulace** mají pruhovaný rámeček
  a „(virtuální)“ v tooltipu. **Svátky na celý rozsah:** přehled se načte
  do `today+90d`; pokud makespan sahá dál, tichý re-fetch overview s `to` =
  konec gantu doplní jen `holidays_in_range` (guard `holidaysEnd` brání
  re-fetch loopu) → stínování i KPI „Svátky v období“ fungují po celou
  délku plánu.
- **Kalendář (měsíc):** dny s čipy kroků (projekt + krok + četa), filtry
  (četa / typ / film-rezervace).
- **Panel čteta:** seznam + editace dostupnosti (admin/antelon).
- **What-if (co-kdyby):** number inputy 0–5 **podle typu čtety** (unie
  typů z čteta i položek — Montáž / Elektro / Inspekce, neznámý typ = raw
  name) → volá `simulate`. KPI karta ukáže diff makespanu + **složení čteta**
  („3 Montáž · 2 Elektro“).
- Čisté divy/karty — **žádné nové Plotly trace** (`test_plotly_traces.py`
  zůstává green).

## 9. Testy

- `tests/reportgen/test_planning.py` — **srdce**: kalendář (pevné svaky,
  velikonoční, víkend, svaky pro následující roky = počítané, ne
  načítané), scheduler (návaznost, kapacita čtety, skip
  víkendů/sváků, okno dostupnosti, výjimky, work_days, priorita film nad
  rezervací, expirace, what-if = dřívější makespan, `None` bez čtety,
  determinismus).
- `tests/reportgen/test_planning_router.py` — struktura odpovědí, auth
  (403 pro customer, 403 pro sales u crews), simulate s dodatečnou čtou
  (včetně `crews` pole — základní `virtual: false` / virtuální
  `virtual: true`), 422 na špatné datum i záporný počet četa.
- Frontend (etapa 2): vitest komponent (Gantt renderuje z mock API,
  what-if počet volá simulate a ukáže složení čteta, virtuální pruh s
  pruhovaným rámečkem, zoom na týdny, skok do období, tichý re-fetch
  svátků při makespanu delším než 90 dní).
- `tests/test_plotly_traces.py` se nemění.

## 10. Explicitně mimo rozsah (V1)

- Zápis plánu do `plan_date` / notifikace (etapa 3).
- Částečná obsazenost dne (balení krátkých kroků do jednoho dne) —
  granularita je dny.
- Sdílení plánu se zákazníkem (portál `/p/{code}`).
- Více čteta na 1 krok (rozdělení kroku na dvě čety).
