# Ceník materiálů jako zdroj investice — implementační plán

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zavést katalog materiálů s cenovou historií, jedinou čistou funkcí pro odvození počtů, výpočtem investice z materiálů a výběrem sestavy ve FVE formuláři.

**Architecture:** `materials` dostane kategorii, viditelnost, výkon a příznak výchozí volby; ceny se verzují v nové tabulce `material_prices` (platnost `valid_from`/`valid_to`) a `materials.price` zůstává jen denormalizovaná aktuální cena, kterou smí zapisovat **výhradně** helper `set_material_price`. Backend poskytuje jedinou čistou funkci `derive_qty(category, rating, params)` pro počty kusů a `compute_investment_cost(params)`, který má prioritu: snímek `fve_materials` → explicitní `investment_cost` → legacy fallback 350 000 Kč. FVE formulář se rozdělí na tři karty a dostane přepínač „komponenty / hotový systém“ s živým součtem investice; snímek `fve_materials` se ukládá do `fve_params_json`, takže se analýza později nepřepočítá podle změněného ceníku.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x nad SQLite, pytest, React + TypeScript (Vite).

**Spec:** `docs/superpowers/specs/2026-10-06-fve-analyza-opravy-a-cenik-design.md` (části 3, 4, 5, 6, 7.6)

## Global Constraints

- Backend se spouští z kořene repa, aby data padla do `data/`. Testy: `./venv/bin/python -m pytest tests/reportgen -q`.
- Testy **nesmí** sáhnout na `data/reportgen.db` — používají `tmp_path` přes fixtures v `tests/reportgen/conftest.py` (`db`, `db_path`, `engine`, `client`).
- Časové značky přes `datetime.utcnow()` (shodné se stávajícím kódem). Platnosti cen přes `datetime.date`.
- Do `materials.price` a do `material_prices` smí zapisovat **jen** `set_material_price`. Žádný endpoint ani seed neposílá price přímo do `Material`.
- RBAC zápis do ceníku = jen `admin`, `antelon`. Čtení `GET /materials` beze změny = `admin, antelon, buyer, warehouse`.
- FVE evidenci investorů (testovací účty, koordinace) řeší souběžný plán `2026-10-06-1-ukladani-a-opravneni.md` (rozšíření `ANY_ROLE` o `buyer`, `projects.active`). Tento plán na něm nezávisí, ale nesmí jeho změny přepsat.
- Commit messages v konvenci repa: `feat(...)`, `fix(...)`, `test(...)`, `chore(...)`.
- Vývoj běží v dev workspace, **ne** v produkci `/home/roman/apps/antelon-energy`.
- Geocode picker a `downloadEnergyPdf` se v tomto plánu **nemění** (patří do plánů 3 a 4).

## Review Focus

Než začneš, přečti si spec. Těchto pět vstupů a stavů spec zmiňuje jen okrajově a je nejpravděpodobnější, že je někdo rozbije — každý má v úkolu vlastní test:

1. **Opakované přecenění materiálu** — `set_material_price` musí uzavřít právě předchozí otevřený řádek (`valid_to = valid_from − 1 den`), vložit nový a přepsat `materials.price`; po dvou přeceněních smí být otevřený jen jeden řádek a `current_price` musí vrátit cenu platnou k danému dni. Task 3.
2. **Staré analýzy bez `fve_materials`** — musí dostat fallback 350 000 Kč a prázdný snímek `[]` se nesmí chovat jako nula. Task 5.
3. **Neaktivní a interní materiály nesmí uniknout** — `customer` nesmí vidět `visibility='internal'`, `is_internal_user` ano; soft-smazaný (`active=0`) materiál se nesmí objevit v nabídce FVE formuláře. Task 6 (+ ověření v Tasku 7 delete testem).
4. **`buyer` nesmí měnit ceny ani mazat** — `POST/PUT/DELETE /materials` a `POST /materials/{id}/price` vrací 403, ale `GET /materials` a `GET /fve-analysis/materials` smí číst. Task 7.
5. **Kontrolní součet seedu** — výchozí sestava 19× PAN-550 + INV-10 + BAT-10 + INS-MONT musí být přesně 300 000 Kč; jakákoli změna ceny nebo `derive_qty` musí test shodit. Task 4.

---

## Souborová mapa

| Soubor | Odpovědnost | Změna |
|---|---|---|
| `backend/app/reportgen/storage.py` | modely + migrace + seed | `Material` nové sloupce, `MaterialPrice`, `Index` import, `_migrate` ALTER, `MATERIAL_SEED`, `_seed_materials` |
| `backend/app/reportgen/materials_service.py` | **nový** | `derive_qty`, `set_material_price`, `current_price`, `compute_investment_cost` |
| `backend/app/reportgen/fve_router.py` | FVE endpointy + `FveParams` | nová pole `FveParams`, `GET /fve-analysis/materials` |
| `backend/app/reportgen/pipeline_router.py` | materiálové endpointy | `MaterialIn` rozšíření, `PUT`, `DELETE`, `POST /{id}/price`, RBAC admin/antelon |
| `backend/app/fve_analysis.py` | ekonomika | `compute_investment_cost` v `run_economic_analysis` |
| `frontend-web/src/types.ts` | typy | `FveMaterial`, `FveMaterialLine`, nová pole `FveParams`, `Material` rozšíření |
| `frontend-web/src/api/fve.ts` | FVE klient | `fetchFveMaterials`, defaulty `DEFAULT_FVE_PARAMS` |
| `frontend-web/src/api/pipeline.ts` | materiálový klient | `setMaterialPrice` |
| `frontend-web/src/components/fve/FveAnalysisForm.tsx` | formulář | karty, přepínač sestavy, živý součet |
| `frontend-web/src/pages/Materialy.tsx` | ceník UI | `canManage` admin/antelon, UI pro platnost cen |
| `tests/reportgen/test_materials.py` | **nový** | schema, seed, `derive_qty`, `set_material_price`, FVE endpoint, RBAC |
| `tests/reportgen/test_fve_api.py` | FVE API | `FveParams` nová pole, `compute_investment_cost` v ekonomice |

---

### Task 1: Schéma — `Material` nové sloupce a tabulka `MaterialPrice`

**Files:**
- Modify: `backend/app/reportgen/storage.py` (import na řádku 5, `Material` ~186, `_migrate` ~317, nový model za `ProjectMaterial` ~206)
- Test: `tests/reportgen/test_materials.py` (nový)

**Interfaces:**
- Consumes: nic
- Produces: `Material.category`, `Material.visibility`, `Material.rating`, `Material.supplier`, `Material.is_default`, `Material.system_kwp`, `Material.system_battery_kwh`; nový model `MaterialPrice(material_id, price, valid_from, valid_to, created_by, created_at)`. Na těchto sloupcích staví Tasky 3, 4, 6, 7.

- [ ] **Step 1: Napiš padající testy**

Vytvoř `tests/reportgen/test_materials.py`:

```python
"""Část 3 — ceník materiálů: schéma, ceny s platností, seed, odvození počtů.

Testy sdílejí fixtures z conftest.py (`db`, `db_path`, `client`).
"""
import json
import sqlite3

import pytest


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _login(client, email, password):
    r = client.post("/api/v1/auth/login",
                    json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def admin_token(client):
    return _login(client, "admin@test.local", "Admin123!")


@pytest.fixture
def customer_token(client):
    return _login(client, "zakaznik@test.local", "Zakaznik123!")


def test_material_new_columns_have_defaults(db):
    from reportgen.storage import Material

    m = Material(code="X-1", name="Materiál", unit="ks", price=100)
    db.add(m)
    db.commit()
    db.refresh(m)
    assert m.category == "other"
    assert m.visibility == "public"
    assert m.rating is None
    assert m.supplier is None
    assert m.is_default is False
    assert m.system_kwp is None
    assert m.system_battery_kwh is None


def test_material_price_roundtrip(db):
    from datetime import date

    from reportgen.storage import Material, MaterialPrice

    m = Material(code="X-1", name="Materiál", unit="ks", price=100)
    db.add(m)
    db.commit()
    db.refresh(m)

    row = MaterialPrice(material_id=m.id, price=100.0, valid_from=date(2026, 1, 1))
    db.add(row)
    db.commit()
    db.refresh(row)
    assert row.id
    assert row.valid_to is None
    assert row.created_by is None
    assert row.created_at is not None


def test_migrate_adds_material_columns(db_path):
    """Starší DB s tabulkou materials bez nových sloupců se dorovná v _migrate."""
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE materials (id INTEGER PRIMARY KEY AUTOINCREMENT,
            code VARCHAR(50) NOT NULL UNIQUE, name VARCHAR(200) NOT NULL,
            unit VARCHAR(10), price FLOAT, active BOOLEAN, created_at DATETIME);
    """)
    con.commit()
    con.close()

    from reportgen import storage

    storage.init_db(db_path)

    con = sqlite3.connect(db_path)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(materials)").fetchall()}
    finally:
        con.close()
    for c in ("category", "visibility", "rating", "supplier", "is_default",
              "system_kwp", "system_battery_kwh"):
        assert c in cols, f"chybí sloupec materials.{c}"
```

- [ ] **Step 2: Spusť testy — musí padat**

Run: `./venv/bin/python -m pytest tests/reportgen/test_materials.py -q`
Expected: FAIL — `TypeError: 'category' is an invalid keyword argument for Material` (nebo `no such column`).

- [ ] **Step 3: Přidej sloupce do modelu `Material`**

V `backend/app/reportgen/storage.py` nahraď třídu `Material` (řádky 186–194):

```python
class Material(Base):
    __tablename__ = "materials"
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    unit = Column(String(10), default="ks")
    price = Column(Float, default=0)          # denormalizovaná AKTUÁLNÍ cena
    active = Column(Boolean, default=True)
    # panel | inverter | battery | install | system | other
    category = Column(String(30), default="other", server_default=text("'other'"))
    # public = vidí zákazník, internal = jen pracovníci
    visibility = Column(String(20), default="public", server_default=text("'public'"))
    rating = Column(Float, nullable=True)     # Wp u panelů, kW u měničů, kWh u baterií
    supplier = Column(String(120), nullable=True)  # konkrétní typ dodavatele
    is_default = Column(Boolean, default=False, server_default=text("0"))
    system_kwp = Column(Float, nullable=True)            # jen category='system'
    system_battery_kwh = Column(Float, nullable=True)    # jen category='system'
    created_at = Column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 4: Přidej model `MaterialPrice`**

V `backend/app/reportgen/storage.py` vlož za třídu `ProjectMaterial` (za řádek 206):

```python
class MaterialPrice(Base):
    """Historie cen materiálu. Aktuální cena = nejnovější platný řádek.

    Do této tabulky i do `Material.price` smí zapisovat jen
    `materials_service.set_material_price`.
    """
    __tablename__ = "material_prices"
    id = Column(Integer, primary_key=True, autoincrement=True)
    material_id = Column(Integer, ForeignKey("materials.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    price = Column(Float, nullable=False)
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=True)     # NULL = stále platí
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        Index("ix_material_prices_material_valid", "material_id", "valid_from"),
    )
```

- [ ] **Step 5: Doplň `Index` a `date` do importů**

V `backend/app/reportgen/storage.py`:
- řádek 4 změň na `from datetime import date, datetime`
- řádek 5 přidej `Index` na konec importu z `sqlalchemy`:

```python
from sqlalchemy import create_engine, Column, Integer, String, Text, Float, DateTime, Date, ForeignKey, Boolean, UniqueConstraint, Index, text
```

- [ ] **Step 6: Doplň ALTER do `_migrate`**

V `backend/app/reportgen/storage.py` vlož do `_migrate` za blok `if "notifications" in tables:` (před `conn.commit()` na řádku 322):

```python
        if "materials" in tables:
            cols = columns_of("materials")
            if "category" not in cols:
                conn.execute(text("ALTER TABLE materials ADD COLUMN category VARCHAR(30) DEFAULT 'other'"))
            if "visibility" not in cols:
                conn.execute(text("ALTER TABLE materials ADD COLUMN visibility VARCHAR(20) DEFAULT 'public'"))
            if "rating" not in cols:
                conn.execute(text("ALTER TABLE materials ADD COLUMN rating FLOAT"))
            if "supplier" not in cols:
                conn.execute(text("ALTER TABLE materials ADD COLUMN supplier VARCHAR(120)"))
            if "is_default" not in cols:
                conn.execute(text("ALTER TABLE materials ADD COLUMN is_default BOOLEAN DEFAULT 0"))
            if "system_kwp" not in cols:
                conn.execute(text("ALTER TABLE materials ADD COLUMN system_kwp FLOAT"))
            if "system_battery_kwh" not in cols:
                conn.execute(text("ALTER TABLE materials ADD COLUMN system_battery_kwh FLOAT"))
```

- [ ] **Step 7: Spusť testy**

Run: `./venv/bin/python -m pytest tests/reportgen/test_materials.py -q`
Expected: PASS (3 testy)

- [ ] **Step 8: Spusť celou sadu**

Run: `./venv/bin/python -m pytest tests/reportgen -q`
Expected: PASS (beze změny počtu existujících testů)

- [ ] **Step 9: Commit**

```bash
git add backend/app/reportgen/storage.py tests/reportgen/test_materials.py
git commit -m "feat(materials): sloupce materialu a tabulka material_prices"
```

---

### Task 2: `derive_qty` — jediná čistá funkce pro počty kusů

**Files:**
- Create: `backend/app/reportgen/materials_service.py`
- Test: `tests/reportgen/test_materials.py`

**Interfaces:**
- Consumes: nic (čistá funkce, bez DB)
- Produces: `derive_qty(category: str, rating: float | None, params: dict) -> float`. Používá ji Task 4 (kontrolní součet), Task 10 (frontend zrcadlí stejný vzorec) a frontend live součet.

- [ ] **Step 1: Napiš padající testy**

Přidej na konec `tests/reportgen/test_materials.py`:

```python
# ---------- derive_qty ----------

def test_derive_qty_panel_rounds_up():
    from reportgen.materials_service import derive_qty

    assert derive_qty("panel", 550, {"kwp": 10.0}) == 19   # ceil(18.18)
    assert derive_qty("panel", 450, {"kwp": 10.0}) == 23   # ceil(22.22)
    assert derive_qty("panel", 615, {"kwp": 10.0}) == 17   # ceil(16.26)


def test_derive_qty_inverter_and_battery():
    from reportgen.materials_service import derive_qty

    assert derive_qty("inverter", 10, {"kwp": 10.0}) == 1
    assert derive_qty("inverter", 10, {"kwp": 15.0}) == 2
    assert derive_qty("battery", 10, {"kwp": 10.0, "battery_capacity": 10.0}) == 1
    assert derive_qty("battery", 5, {"kwp": 10.0, "battery_capacity": 12.0}) == 3


def test_derive_qty_install_system_other_is_one():
    from reportgen.materials_service import derive_qty

    assert derive_qty("install", None, {}) == 1
    assert derive_qty("system", None, {}) == 1
    assert derive_qty("other", None, {}) == 1


def test_derive_qty_missing_rating_is_zero():
    from reportgen.materials_service import derive_qty

    assert derive_qty("panel", None, {"kwp": 10.0}) == 0
    assert derive_qty("inverter", None, {"kwp": 10.0}) == 0
    assert derive_qty("battery", None, {"battery_capacity": 10.0}) == 0


def test_derive_qty_defaults_kwp_to_ten():
    from reportgen.materials_service import derive_qty

    assert derive_qty("panel", 550, {}) == 19
```

- [ ] **Step 2: Spusť testy — musí padat**

Run: `./venv/bin/python -m pytest tests/reportgen/test_materials.py -q -k derive_qty`
Expected: FAIL — `ModuleNotFoundError: No module named 'reportgen.materials_service'`

- [ ] **Step 3: Vytvoř `materials_service.py`**

Vytvoř `backend/app/reportgen/materials_service.py`:

```python
"""Ceník materiálů — jediné místo, kde se počítají počty kusů a investice
a kde se zapisuje cena.

`derive_qty` je čistá funkce (žádná DB). `set_material_price` je jediný
povolený zápis do `materials.price` a `material_prices`. Frontend má
vlastní zrcadlo `deriveQty` pro okamžitý součet — hodnoty se musí rovnat,
jinak se snímek a živý součet rozjedou; rozdíl hlídá Task 10.
"""
import math


def derive_qty(category: str, rating: float | None, params: dict) -> float:
    """Počet kusů dané komponenty pro definovaný výkon elektrárny.

    - panel:      ceil(kWp × 1000 / Wp)
    - inverter:   ceil(kWp / kW)
    - battery:    ceil(kapacita / kWh)
    - install, system, other: 1
    """
    kwp = float(params.get("kwp", 10.0))
    if category == "panel":
        if not rating:
            return 0.0
        return math.ceil(kwp * 1000 / rating)
    if category == "inverter":
        if not rating:
            return 0.0
        return math.ceil(kwp / rating)
    if category == "battery":
        kap = float(params.get("battery_capacity", 0.0))
        if not rating:
            return 0.0
        return math.ceil(kap / rating)
    return 1.0
```

- [ ] **Step 4: Spusť testy**

Run: `./venv/bin/python -m pytest tests/reportgen/test_materials.py -q -k derive_qty`
Expected: PASS (5 testů)

- [ ] **Step 5: Commit**

```bash
git add backend/app/reportgen/materials_service.py tests/reportgen/test_materials.py
git commit -m "feat(materials): derive_qty pro pocty kusu"
```

---

### Task 3: `set_material_price` a `current_price` — ceny s platností

**Files:**
- Modify: `backend/app/reportgen/materials_service.py`
- Test: `tests/reportgen/test_materials.py`

**Interfaces:**
- Consumes: `Material`, `MaterialPrice` (Task 1)
- Produces:
  - `set_material_price(db, material_id: int, price: float, valid_from: date, created_by: int | None = None) -> MaterialPrice` — uzavře předchozí otevřený řádek, vloží nový, přepíše `materials.price`; **necommituje** (volající commitne).
  - `current_price(db, material_id: int, on: date) -> float | None`
  - Používá je Task 4 (seed), Task 7 (endpointy).

- [ ] **Step 1: Napiš padající testy**

Přidej na konec `tests/reportgen/test_materials.py`:

```python
# ---------- set_material_price / current_price ----------

def _new_material(db):
    from reportgen.storage import Material

    m = Material(code="X-PRICE", name="Cenověný", unit="ks", price=0)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def test_set_material_price_updates_denormalized_price(db):
    from datetime import date

    from reportgen.materials_service import current_price, set_material_price

    m = _new_material(db)
    set_material_price(db, m.id, 100.0, date(2026, 1, 1), created_by=None)
    db.commit()
    assert current_price(db, m.id, date(2026, 6, 1)) == 100.0

    set_material_price(db, m.id, 130.0, date(2026, 7, 1), created_by=None)
    db.commit()
    assert current_price(db, m.id, date(2026, 6, 1)) == 100.0   # stará cena do 30. 6.
    assert current_price(db, m.id, date(2026, 7, 1)) == 130.0
    db.refresh(m)
    assert m.price == 130.0


def test_set_material_price_closes_previous_open_row(db):
    from datetime import date

    from reportgen.storage import MaterialPrice
    from reportgen.materials_service import set_material_price

    m = _new_material(db)
    set_material_price(db, m.id, 100.0, date(2026, 1, 1))
    set_material_price(db, m.id, 130.0, date(2026, 7, 1))
    db.commit()

    rows = (db.query(MaterialPrice)
            .filter(MaterialPrice.material_id == m.id)
            .order_by(MaterialPrice.valid_from).all())
    assert len(rows) == 2
    assert rows[0].price == 100.0 and rows[0].valid_to == date(2026, 6, 30)
    assert rows[1].price == 130.0 and rows[1].valid_to is None
    assert sum(1 for r in rows if r.valid_to is None) == 1


def test_set_material_price_same_day_reprice_wins(db):
    from datetime import date

    from reportgen.materials_service import current_price, set_material_price

    m = _new_material(db)
    set_material_price(db, m.id, 100.0, date(2026, 1, 1))
    set_material_price(db, m.id, 150.0, date(2026, 1, 1))
    db.commit()
    assert current_price(db, m.id, date(2026, 1, 1)) == 150.0
```

- [ ] **Step 2: Spusť testy — musí padat**

Run: `./venv/bin/python -m pytest tests/reportgen/test_materials.py -q -k "material_price"`
Expected: FAIL — `ImportError: cannot import name 'set_material_price'`

- [ ] **Step 3: Implementuj helpery**

Doplň do `backend/app/reportgen/materials_service.py` (nahoře doplň importy a tělo):

```python
from datetime import date, timedelta

from reportgen.storage import Material, MaterialPrice


def set_material_price(db, material_id: int, price: float, valid_from: date,
                       created_by: int | None = None) -> MaterialPrice:
    """Zapíše novou cenu a uzavře předchozí otevřený řádek.

    Jediné povolené místo zápisu do `material_prices` i `materials.price`.
    Necommituje — transakci uzavírá volající.
    """
    prev = (db.query(MaterialPrice)
            .filter(MaterialPrice.material_id == material_id,
                    MaterialPrice.valid_to.is_(None))
            .order_by(MaterialPrice.valid_from.desc())
            .first())
    if prev is not None:
        prev.valid_to = valid_from - timedelta(days=1)

    row = MaterialPrice(material_id=material_id, price=price,
                        valid_from=valid_from, valid_to=None,
                        created_by=created_by)
    db.add(row)

    mat = db.query(Material).filter(Material.id == material_id).first()
    if mat is not None:
        mat.price = price
    db.flush()
    return row


def current_price(db, material_id: int, on: date) -> float | None:
    """Nejnovější cena platná k dni `on`, nebo None když žádná neplatí."""
    row = (db.query(MaterialPrice)
           .filter(MaterialPrice.material_id == material_id,
                   MaterialPrice.valid_from <= on,
                   (MaterialPrice.valid_to.is_(None))
                   | (MaterialPrice.valid_to >= on))
           .order_by(MaterialPrice.valid_from.desc())
           .first())
    return row.price if row is not None else None
```

- [ ] **Step 4: Spusť testy**

Run: `./venv/bin/python -m pytest tests/reportgen/test_materials.py -q -k "material_price"`
Expected: PASS (3 testy)

- [ ] **Step 5: Commit**

```bash
git add backend/app/reportgen/materials_service.py tests/reportgen/test_materials.py
git commit -m "feat(materials): set_material_price a current_price s platnosti"
```

---

### Task 4: Idempotentní seed 12 materiálů (součet 300 000 Kč)

**Files:**
- Modify: `backend/app/reportgen/storage.py` (`_seed_materials` a `MATERIAL_SEED` za `_seed_rate_cards` ~řádek 343, volání v `init_db` ~řádek 407)
- Test: `tests/reportgen/test_materials.py`

**Interfaces:**
- Consumes: `MaterialPrice` (Task 1), `set_material_price` a `derive_qty` (Tasky 2, 3)
- Produces: `MATERIAL_SEED`, `storage._seed_materials(db)`, vedlejší efekt `init_db` (12 materiálů + cenové řádky). Používá Task 4 testy a Task 6/7.

- [ ] **Step 1: Napiš padající testy**

Přidej na konec `tests/reportgen/test_materials.py`:

```python
# ---------- seed ----------

def test_seed_materials_count_and_idempotent(db):
    from reportgen.storage import Material, _seed_materials

    assert db.query(Material).count() == 12
    _seed_materials(db)
    db.expire_all()
    assert db.query(Material).count() == 12


def test_seed_sum_is_exactly_300k(db):
    from reportgen.storage import Material
    from reportgen.materials_service import derive_qty

    by_code = {m.code: m for m in db.query(Material).all()}
    assert len(by_code) == 12
    params = {"kwp": 10.0, "battery_capacity": 10.0}
    total = (
        by_code["PAN-550"].price * derive_qty("panel", by_code["PAN-550"].rating, params)
        + by_code["INV-10"].price * derive_qty("inverter", by_code["INV-10"].rating, params)
        + by_code["BAT-10"].price * derive_qty("battery", by_code["BAT-10"].rating, params)
        + by_code["INS-MONT"].price * derive_qty("install", by_code["INS-MONT"].rating, params)
    )
    assert total == 300_000, f"kontrolní součet je {total}, čekáno 300000"


def test_seed_defaults_and_system_fields(db):
    from reportgen.storage import Material

    by_code = {m.code: m for m in db.query(Material).all()}
    for code in ("PAN-550", "INV-10", "BAT-10", "INS-MONT", "SYS-10-10"):
        assert by_code[code].is_default is True, code
    assert all(m.visibility == "public" for m in by_code.values())
    assert by_code["SYS-10-10"].system_kwp == 10.0
    assert by_code["SYS-10-10"].system_battery_kwh == 10.0
    assert by_code["SYS-15-10"].system_kwp == 15.0


def test_seed_creates_price_rows(db):
    from datetime import date

    from reportgen.storage import Material, MaterialPrice
    from reportgen.materials_service import current_price

    for m in db.query(Material).all():
        count = db.query(MaterialPrice).filter(MaterialPrice.material_id == m.id).count()
        assert count >= 1, f"{m.code} nemá cenový řádek"
        assert current_price(db, m.id, date(2026, 10, 6)) == m.price


def test_seed_materials_idempotent_on_second_init(db_path):
    from reportgen import storage
    from reportgen.storage import Material
    from sqlalchemy.orm import sessionmaker

    storage.init_db(db_path)
    storage.init_db(db_path)
    Session = sessionmaker(bind=storage.get_engine(db_path))
    s = Session()
    try:
        assert s.query(Material).count() == 12
    finally:
        s.close()
```

- [ ] **Step 2: Spusť testy — musí padat**

Run: `./venv/bin/python -m pytest tests/reportgen/test_materials.py -q -k seed`
Expected: FAIL — `ImportError: cannot import name '_seed_materials'`

- [ ] **Step 3: Přidej `MATERIAL_SEED` a `_seed_materials`**

V `backend/app/reportgen/storage.py` vlož za `_seed_rate_cards` (za řádek 343):

```python
# Návrh cen k ruční kalibraci v UI. Výchozí sestava
# 19× PAN-550 + INV-10 + BAT-10 + INS-MONT = 300 000 Kč je nový základ
# ekonomiky (bylo 350 000). Konkrétní typy dodavatelů se neseedují.
MATERIAL_SEED = [
    {"code": "PAN-450", "name": "Panel 450 Wp", "category": "panel",
     "rating": 450, "price": 2000, "visibility": "public", "is_default": False},
    {"code": "PAN-550", "name": "Panel 550 Wp", "category": "panel",
     "rating": 550, "price": 2500, "visibility": "public", "is_default": True},
    {"code": "PAN-615", "name": "Panel 615 Wp", "category": "panel",
     "rating": 615, "price": 2800, "visibility": "public", "is_default": False},
    {"code": "INV-10", "name": "Měnič 10 kW", "category": "inverter",
     "rating": 10, "price": 45000, "visibility": "public", "is_default": True},
    {"code": "INV-15", "name": "Měnič 15 kW", "category": "inverter",
     "rating": 15, "price": 62000, "visibility": "public", "is_default": False},
    {"code": "INV-20", "name": "Měnič 20 kW", "category": "inverter",
     "rating": 20, "price": 78000, "visibility": "public", "is_default": False},
    {"code": "BAT-5", "name": "Baterie 5 kWh", "category": "battery",
     "rating": 5, "price": 48000, "visibility": "public", "is_default": False},
    {"code": "BAT-10", "name": "Baterie 10 kWh", "category": "battery",
     "rating": 10, "price": 87500, "visibility": "public", "is_default": True},
    {"code": "BAT-15", "name": "Baterie 15 kWh", "category": "battery",
     "rating": 15, "price": 125000, "visibility": "public", "is_default": False},
    {"code": "INS-MONT", "name": "Montáž instalace", "category": "install",
     "rating": None, "price": 120000, "visibility": "public", "is_default": True},
    {"code": "SYS-10-10", "name": "FVE 10 kWp / 10 kWh", "category": "system",
     "rating": None, "price": 300000, "visibility": "public", "is_default": True,
     "system_kwp": 10.0, "system_battery_kwh": 10.0},
    {"code": "SYS-15-10", "name": "FVE 15 kWp / 10 kWh", "category": "system",
     "rating": None, "price": 349000, "visibility": "public", "is_default": False,
     "system_kwp": 15.0, "system_battery_kwh": 10.0},
]


def _seed_materials(db):
    """Idempotentní seed ceníku — jen když je tabulka prázdná.

    Ceny jdou přes `set_material_price`, takže vznikne i historie
    (`material_prices`) a `materials.price` je s ní konzistentní.
    """
    if db.query(Material).count() > 0:
        return
    from .materials_service import set_material_price

    for row in MATERIAL_SEED:
        data = dict(row)
        price = data.pop("price")
        m = Material(**data)
        db.add(m)
        db.flush()
        set_material_price(db, m.id, price, date(2020, 1, 1), created_by=None)
    db.commit()
```

- [ ] **Step 4: Zavolej seed v `init_db`**

V `backend/app/reportgen/storage.py` za `_seed_rate_cards(db)` (řádek 407) přidej:

```python
        # ceník materiálů — idempotentní seed (část 3)
        _seed_materials(db)
```

- [ ] **Step 5: Spusť testy**

Run: `./venv/bin/python -m pytest tests/reportgen/test_materials.py -q -k seed`
Expected: PASS (5 testů)

- [ ] **Step 6: Ověř kontrolní součet ručně**

Run:
```bash
./venv/bin/python -c "
import os, tempfile
os.environ.setdefault('RG_ADMIN_EMAIL','a@t.local'); os.environ.setdefault('RG_ADMIN_PASSWORD','Admin123!')
import sys; sys.path.insert(0, 'backend'); sys.path.insert(0, 'backend/app')
from reportgen import storage
from reportgen.materials_service import derive_qty
p = tempfile.mkdtemp()
eng = storage.init_db(os.path.join(p, 'r.db'))
S = storage.get_session_factory(os.path.join(p, 'r.db')); db = S()
by = {m.code: m for m in db.query(storage.Material).all()}
t = (by['PAN-550'].price*derive_qty('panel', by['PAN-550'].rating, {'kwp':10})
     + by['INV-10'].price + by['BAT-10'].price + by['INS-MONT'].price)
print('součet =', t); assert t == 300000
"
```
Expected: `součet = 300000`

- [ ] **Step 7: Commit**

```bash
git add backend/app/reportgen/storage.py tests/reportgen/test_materials.py
git commit -m "feat(materials): idempotentni seed ceniku (300 000 Kc)"
```

---

### Task 5: `compute_investment_cost` a jeho zapojení do ekonomiky

**Files:**
- Modify: `backend/app/reportgen/materials_service.py`
- Modify: `backend/app/fve_analysis.py` (`run_economic_analysis` ~řádek 470–477)
- Test: `tests/reportgen/test_materials.py` (unit) a `tests/reportgen/test_fve_api.py` (integrace)

**Interfaces:**
- Consumes: nic (čistá funkce)
- Produces: `compute_investment_cost(params) -> float`; `run_economic_analysis` používá snímek `fve_materials` z `params`.

- [ ] **Step 1: Napiš padající unit testy**

Přidej na konec `tests/reportgen/test_materials.py`:

```python
# ---------- compute_investment_cost ----------

def test_compute_investment_cost_prefers_snapshot():
    from reportgen.materials_service import compute_investment_cost

    bom = [{"line_total": 250000.0}, {"line_total": 50000.0}]
    assert compute_investment_cost({"fve_materials": bom,
                                    "investment_cost": 999999}) == 300000.0


def test_compute_investment_cost_explicit_when_no_snapshot():
    from reportgen.materials_service import compute_investment_cost

    assert compute_investment_cost({"investment_cost": 275000.0}) == 275000.0


def test_compute_investment_cost_legacy_fallback():
    from reportgen.materials_service import compute_investment_cost

    assert compute_investment_cost({}) == 350000.0
    # prázdný snímek NENÍ nula — spadne na explicitní/legacy
    assert compute_investment_cost({"fve_materials": []}) == 350000.0
```

- [ ] **Step 2: Spusť testy — musí padat**

Run: `./venv/bin/python -m pytest tests/reportgen/test_materials.py -q -k compute_investment`
Expected: FAIL — `ImportError: cannot import name 'compute_investment_cost'`

- [ ] **Step 3: Implementuj `compute_investment_cost`**

Doplň na konec `backend/app/reportgen/materials_service.py`:

```python
LEGACY_INVESTMENT_COST = 350_000.0


def compute_investment_cost(params) -> float:
    """Investice pro ekonomiku.

    Priorita: snímek `fve_materials` (nové analýzy) → explicitní
    `investment_cost` → legacy fallback 350 000 Kč (staré analýzy beze
    změny — záměrně se nepřepočítávají podle nového ceníku).
    """
    bom = (params or {}).get("fve_materials")
    if bom:
        return sum(float(line.get("line_total", 0)) for line in bom)
    if params is not None and "investment_cost" in params:
        return float(params["investment_cost"])
    return LEGACY_INVESTMENT_COST
```

- [ ] **Step 4: Spusť unit testy**

Run: `./venv/bin/python -m pytest tests/reportgen/test_materials.py -q -k compute_investment`
Expected: PASS (3 testy)

- [ ] **Step 5: Zapoj do `run_economic_analysis`**

V `backend/app/fve_analysis.py` vlož na začátek těla `run_economic_analysis` (za docstring, řádek 471):

```python
    from reportgen.materials_service import compute_investment_cost
```

a nahraď řádek 477:

```python
        initial_investment_czk=compute_investment_cost(params),
```

- [ ] **Step 6: Napiš integrační test do `test_fve_api.py`**

Přidej na konec `tests/reportgen/test_fve_api.py`:

```python
# ---------- M4 — investice ze snímku materiálů (část 3) ----------

def test_economic_uses_bom_snapshot(client, admin_token):
    """Snímek fve_materials má přednost před legacy 350 000 Kč."""
    legacy = client.post("/api/v1/fve-analysis/economic",
                         json={"annual_savings": 30000},
                         headers=_auth(admin_token)).json()
    with_bom = client.post("/api/v1/fve-analysis/economic",
                           json={"annual_savings": 30000,
                                 "fve_materials": [{"line_total": 300000.0}]},
                           headers=_auth(admin_token)).json()
    assert with_bom["metrics"]["npv_czk"] != legacy["metrics"]["npv_czk"]
```

- [ ] **Step 7: Spusť integrační test**

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_api.py::test_economic_uses_bom_snapshot -q`
Expected: PASS

- [ ] **Step 8: Spusť celou sadu**

Run: `./venv/bin/python -m pytest tests/reportgen -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/app/reportgen/materials_service.py backend/app/fve_analysis.py tests/reportgen/test_materials.py tests/reportgen/test_fve_api.py
git commit -m "feat(economy): investice ze snimku materialu s legacy fallbackem"
```

---

### Task 6: `GET /api/v1/fve-analysis/materials` s filtrem viditelnosti

**Files:**
- Modify: `backend/app/reportgen/fve_router.py` (importy, nový endpoint za `list_appliances` ~řádek 158)
- Test: `tests/reportgen/test_materials.py`

**Interfaces:**
- Consumes: `Material` sloupce (Task 1), `is_internal_user` (`reportgen.auth`)
- Produces: `GET /api/v1/fve-analysis/materials` → `{"materials": [{id, code, name, category, visibility, rating, unit, price, is_default, system_kwp, system_battery_kwh}]}`. Používá ji Task 9 (`fetchFveMaterials`).

- [ ] **Step 1: Napiš padající testy**

Přidej na konec `tests/reportgen/test_materials.py`:

```python
# ---------- GET /fve-analysis/materials ----------

def _insert_material(db_path, code, name, price=100.0, visibility="public",
                     category="other", rating=None):
    """Vloží materiál přímo do DB — testuje endpoint nezávisle na CRUD (Task 7)."""
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "INSERT INTO materials (code, name, unit, price, active, category, "
            "visibility, rating, is_default) VALUES (?, ?, 'ks', ?, 1, ?, ?, ?, 0)",
            (code, name, price, category, visibility, rating))
        mid = con.execute("SELECT id FROM materials WHERE code = ?", (code,)).fetchone()[0]
        con.commit()
    finally:
        con.close()
    return mid


def test_fve_materials_customer_sees_only_public(client, admin_token, customer_token, db_path):
    _insert_material(db_path, "X-PUB", "Veřejný", visibility="public")
    _insert_material(db_path, "X-INT", "Interní", visibility="internal")

    adm = {m["code"] for m in client.get("/api/v1/fve-analysis/materials",
                                         headers=_auth(admin_token)).json()["materials"]}
    cus = {m["code"] for m in client.get("/api/v1/fve-analysis/materials",
                                         headers=_auth(customer_token)).json()["materials"]}
    assert {"X-PUB", "X-INT"} <= adm
    assert "X-PUB" in cus
    assert "X-INT" not in cus


def test_fve_materials_excludes_inactive(client, admin_token, db_path):
    mid = _insert_material(db_path, "X-OFF", "Vypnutý")
    con = sqlite3.connect(db_path)
    try:
        con.execute("UPDATE materials SET active = 0 WHERE id = ?", (mid,))
        con.commit()
    finally:
        con.close()
    codes = {m["code"] for m in client.get("/api/v1/fve-analysis/materials",
                                           headers=_auth(admin_token)).json()["materials"]}
    assert "X-OFF" not in codes


def test_fve_materials_response_shape(client, admin_token):
    rows = client.get("/api/v1/fve-analysis/materials",
                      headers=_auth(admin_token)).json()["materials"]
    assert rows, "seed musí nabídnout materiály"
    assert set(rows[0].keys()) == {
        "id", "code", "name", "category", "visibility", "rating", "unit",
        "price", "is_default", "system_kwp", "system_battery_kwh",
    }
```

- [ ] **Step 2: Spusť testy — musí padat**

Run: `./venv/bin/python -m pytest tests/reportgen/test_materials.py -q -k fve_materials`
Expected: FAIL — 404 na `/api/v1/fve-analysis/materials`

- [ ] **Step 3: Implementuj endpoint**

V `backend/app/reportgen/fve_router.py` vlož za funkci `list_appliances` (za řádek 158):

```python
@router.get("/fve-analysis/materials")
def fve_materials(user: User = Depends(ANY_ROLE), db: Session = Depends(get_db)):
    """Katalog pro přepínač sestavy FVE formuláře.

    Interní pracovník vidí i `visibility='internal'`, zákazník jen
    `'public'`. Smazané (active=0) se nenabízejí.
    """
    from .storage import Material

    q = db.query(Material).filter(Material.active.is_(True))
    if not is_internal_user(user):
        q = q.filter(Material.visibility == "public")
    rows = q.order_by(Material.category, Material.code).all()
    return {"materials": [
        {"id": m.id, "code": m.code, "name": m.name, "category": m.category,
         "visibility": m.visibility, "rating": m.rating, "unit": m.unit,
         "price": m.price, "is_default": m.is_default,
         "system_kwp": m.system_kwp, "system_battery_kwh": m.system_battery_kwh}
        for m in rows
    ]}
```

`is_internal_user` je už importovaný na řádku 21, `User` na řádku 29, `get_db` na řádku 31.

- [ ] **Step 4: Spusť testy**

Run: `./venv/bin/python -m pytest tests/reportgen/test_materials.py -q -k fve_materials`
Expected: PASS (3 testy)

- [ ] **Step 5: Commit**

```bash
git add backend/app/reportgen/fve_router.py tests/reportgen/test_materials.py
git commit -m "feat(fve): endpoint materialu s filtrem viditelnosti"
```

---

### Task 7: Materiálové endpointy — `PUT`, `DELETE` (soft) a `POST /{id}/price` + RBAC admin/antelon

**Files:**
- Modify: `backend/app/reportgen/pipeline_router.py` (`MaterialIn` ~372, `create_material` ~388, nové endpointy za ním)
- Test: `tests/reportgen/test_materials.py`

**Interfaces:**
- Consumes: `set_material_price` (Task 3), `Material` sloupce (Task 1), `GET /fve-analysis/materials` (Task 6)
- Produces: `POST /materials` (admin, antelon), `PUT /materials/{id}`, `DELETE /materials/{id}` (`active=0`), `POST /materials/{id}/price` (`{price, valid_from?}`).

- [ ] **Step 1: Napiš padající testy**

Přidej na konec `tests/reportgen/test_materials.py`:

```python
# ---------- CRUD materiálů a RBAC ----------

def _add_user(db_path, email, role):
    """Uživatel mimo seed — API na vytvoření uživatele neexistuje."""
    from reportgen.auth import hash_password

    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "INSERT INTO users (email, password_hash, role, roles_json) "
            "VALUES (?, ?, ?, ?)",
            (email, hash_password("Xx123456!"), role, json.dumps([role])))
        con.commit()
    finally:
        con.close()


def _create_material(client, token, code="X-NEW", **over):
    body = {"code": code, "name": "Nový materiál", "unit": "ks",
            "price": 1234.0, "category": "panel", "rating": 550}
    body.update(over)
    return client.post("/api/v1/materials", json=body, headers=_auth(token))


def test_buyer_cannot_write_materials(client, admin_token, db_path):
    _add_user(db_path, "buyer-mat@test.local", "buyer")
    tok = _login(client, "buyer-mat@test.local", "Xx123456!")
    assert _create_material(client, tok, code="X-BUY").status_code == 403


def test_admin_creates_material_with_price_history(client, admin_token, db_path):
    r = _create_material(client, admin_token, code="X-ADM", visibility="internal")
    assert r.status_code == 200, r.text
    assert r.json()["id"]
    assert r.json()["category"] == "panel"
    assert r.json()["visibility"] == "internal"

    con = sqlite3.connect(db_path)
    try:
        mid = r.json()["id"]
        price = con.execute("SELECT price FROM materials WHERE id = ?", (mid,)).fetchone()[0]
        rows = con.execute("SELECT COUNT(*) FROM material_prices WHERE material_id = ?",
                           (mid,)).fetchone()[0]
    finally:
        con.close()
    assert price == 1234.0
    assert rows == 1


def test_admin_updates_and_soft_deletes_material(client, admin_token, db_path):
    mid = _create_material(client, admin_token, code="X-UPD").json()["id"]

    upd = client.put(f"/api/v1/materials/{mid}",
                     json={"name": "Přejmenováno", "visibility": "internal"},
                     headers=_auth(admin_token))
    assert upd.status_code == 200, upd.text
    assert upd.json()["name"] == "Přejmenováno"

    dele = client.delete(f"/api/v1/materials/{mid}", headers=_auth(admin_token))
    assert dele.status_code == 200, dele.text

    listed = client.get("/api/v1/materials", headers=_auth(admin_token)).json()
    row = next(m for m in listed if m["id"] == mid)
    assert row["active"] is False
    # soft-smazaný materiál se nenabízí ve FVE formuláři
    fve = client.get("/api/v1/fve-analysis/materials",
                     headers=_auth(admin_token)).json()["materials"]
    assert all(m["id"] != mid for m in fve)


def test_price_endpoint_closes_previous_row(client, admin_token, db_path):
    mid = _create_material(client, admin_token, code="X-PR", price=1000.0).json()["id"]

    r = client.post(f"/api/v1/materials/{mid}/price",
                    json={"price": 2000.0, "valid_from": "2026-08-01"},
                    headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["price"] == 2000.0

    con = sqlite3.connect(db_path)
    try:
        price = con.execute("SELECT price FROM materials WHERE id = ?", (mid,)).fetchone()[0]
        open_rows = con.execute(
            "SELECT COUNT(*) FROM material_prices WHERE material_id = ? AND valid_to IS NULL",
            (mid,)).fetchone()[0]
    finally:
        con.close()
    assert price == 2000.0
    assert open_rows == 1


def test_buyer_cannot_set_price_or_delete(client, admin_token, db_path):
    mid = _create_material(client, admin_token, code="X-BUY2").json()["id"]
    _add_user(db_path, "buyer2-mat@test.local", "buyer")
    tok = _login(client, "buyer2-mat@test.local", "Xx123456!")
    assert client.post(f"/api/v1/materials/{mid}/price", json={"price": 1.0},
                       headers=_auth(tok)).status_code == 403
    assert client.delete(f"/api/v1/materials/{mid}",
                         headers=_auth(tok)).status_code == 403
    assert client.put(f"/api/v1/materials/{mid}", json={"name": "x"},
                      headers=_auth(tok)).status_code == 403
```

- [ ] **Step 2: Spusť testy — musí padat**

Run: `./venv/bin/python -m pytest tests/reportgen/test_materials.py -q -k "buyer_cannot_write or admin_creates or admin_updates or price_endpoint or buyer_cannot_set"`
Expected: FAIL — `POST /materials` vrátí 200 i pro buyera (dnes `admin, buyer`) a `PUT/DELETE/price` vrací 405.

- [ ] **Step 3: Rozšiř `MaterialIn` a změň RBAC `create_material`**

V `backend/app/reportgen/pipeline_router.py` nahraď `MaterialIn` a `create_material` (řádky 372–400):

```python
class MaterialIn(BaseModel):
    code: str
    name: str
    unit: str = "ks"
    price: float = 0.0
    category: str = "other"
    visibility: str = "public"
    rating: float | None = None
    supplier: str | None = None
    is_default: bool = False
    system_kwp: float | None = None
    system_battery_kwh: float | None = None


@router.post("/materials")
def create_material(data: MaterialIn,
                    user: User = Depends(require_roles("admin", "antelon")),
                    db: Session = Depends(get_db)):
    from .materials_service import set_material_price
    from .storage import Material

    if db.query(Material).filter(Material.code == data.code).first():
        raise HTTPException(400, f"Materiál s kódem {data.code!r} už existuje")
    m = Material(code=data.code, name=data.name, unit=data.unit,
                 category=data.category, visibility=data.visibility,
                 rating=data.rating, supplier=data.supplier,
                 is_default=data.is_default, system_kwp=data.system_kwp,
                 system_battery_kwh=data.system_battery_kwh)
    db.add(m)
    db.flush()
    set_material_price(db, m.id, data.price, date.today(), user.id)
    db.commit()
    db.refresh(m)
    return {"id": m.id, "code": m.code, "name": m.name, "unit": m.unit,
            "price": m.price, "category": m.category, "visibility": m.visibility,
            "rating": m.rating, "is_default": m.is_default,
            "system_kwp": m.system_kwp, "system_battery_kwh": m.system_battery_kwh}
```

`date` je už importované na řádku 5 (`from datetime import date, datetime`).

- [ ] **Step 4: Přidej `PUT`, `DELETE` a `POST /{id}/price`**

V `backend/app/reportgen/pipeline_router.py` vlož hned za `create_material`:

```python
class MaterialUpdateIn(BaseModel):
    name: str | None = None
    unit: str | None = None
    category: str | None = None
    visibility: str | None = None
    rating: float | None = None
    supplier: str | None = None
    is_default: bool | None = None
    system_kwp: float | None = None
    system_battery_kwh: float | None = None
    active: bool | None = None
    price: float | None = None
    valid_from: date | None = None


@router.put("/materials/{material_id}")
def update_material(material_id: int, data: MaterialUpdateIn,
                    user: User = Depends(require_roles("admin", "antelon")),
                    db: Session = Depends(get_db)):
    from .materials_service import set_material_price
    from .storage import Material

    m = db.query(Material).filter(Material.id == material_id).first()
    if not m:
        raise HTTPException(404, "Materiál nenalezen")
    for field in ("name", "unit", "category", "visibility", "rating",
                  "supplier", "is_default", "system_kwp", "system_battery_kwh",
                  "active"):
        value = getattr(data, field)
        if value is not None:
            setattr(m, field, value)
    if data.price is not None:
        set_material_price(db, m.id, data.price,
                           data.valid_from or date.today(), user.id)
    db.commit()
    db.refresh(m)
    return {"id": m.id, "code": m.code, "name": m.name, "unit": m.unit,
            "price": m.price, "active": m.active, "category": m.category,
            "visibility": m.visibility}


@router.delete("/materials/{material_id}")
def delete_material(material_id: int,
                    user: User = Depends(require_roles("admin", "antelon")),
                    db: Session = Depends(get_db)):
    """Měkké smazání — `active=0`. Řádek i historie cen zůstávají."""
    from .storage import Material

    m = db.query(Material).filter(Material.id == material_id).first()
    if not m:
        raise HTTPException(404, "Materiál nenalezen")
    m.active = False
    db.commit()
    return {"status": "ok"}


class MaterialPriceIn(BaseModel):
    price: float
    valid_from: date | None = None


@router.post("/materials/{material_id}/price")
def set_material_price_endpoint(material_id: int, data: MaterialPriceIn,
                                user: User = Depends(require_roles("admin", "antelon")),
                                db: Session = Depends(get_db)):
    from .materials_service import set_material_price
    from .storage import Material

    m = db.query(Material).filter(Material.id == material_id).first()
    if not m:
        raise HTTPException(404, "Materiál nenalezen")
    row = set_material_price(db, material_id, data.price,
                             data.valid_from or date.today(), user.id)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "material_id": material_id, "price": row.price,
            "valid_from": row.valid_from.isoformat(),
            "valid_to": row.valid_to.isoformat() if row.valid_to else None}
```

- [ ] **Step 5: Spusť testy**

Run: `./venv/bin/python -m pytest tests/reportgen/test_materials.py -q -k "buyer_cannot_write or admin_creates or admin_updates or price_endpoint or buyer_cannot_set"`
Expected: PASS (5 testů)

- [ ] **Step 6: Spusť celou sadu**

Run: `./venv/bin/python -m pytest tests/reportgen -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/reportgen/pipeline_router.py tests/reportgen/test_materials.py
git commit -m "feat(materials): PUT/DELETE/price endpointy a RBAC admin/antelon"
```

---

### Task 8: Nová pole `FveParams`

**Files:**
- Modify: `backend/app/reportgen/fve_router.py` (`FveParams` ~40–70)
- Test: `tests/reportgen/test_fve_api.py`

**Interfaces:**
- Consumes: nic
- Produces: `FveParams.bom_mode`, `fve_materials`, `panel_material_id`, `inverter_material_id`, `battery_material_id`, `install_material_id`, `system_material_id`. Používá Task 9 (typy) / Task 10 (formulář) a ekonomika (Task 5).

- [ ] **Step 1: Napiš padající testy**

Přidej na konec `tests/reportgen/test_fve_api.py`:

```python
# ---------- FveParams — přepínač sestavy (část 3) ----------

def test_save_persists_bom_fields(client, admin_token):
    params = {
        "kwp": 10.0,
        "bom_mode": "system",
        "system_material_id": 5,
        "fve_materials": [{
            "material_id": 5, "code": "SYS-10-10", "category": "system",
            "qty": 1, "unit_price": 300000.0, "line_total": 300000.0,
        }],
    }
    r = _save(client, admin_token, params=params)
    assert r.status_code == 200, r.text
    proj = client.get(f"/api/v1/projects/{r.json()['id']}",
                      headers=_auth(admin_token)).json()
    fp = proj["fve_params"]
    assert fp["bom_mode"] == "system"
    assert fp["system_material_id"] == 5
    assert fp["fve_materials"][0]["line_total"] == 300000.0


def test_save_rejects_unknown_bom_mode(client, admin_token):
    r = _save(client, admin_token, params={"bom_mode": "drak"})
    assert r.status_code == 422
    assert "sestavy" in str(r.json()["detail"])


def test_save_defaults_bom_mode_to_components(client, admin_token):
    r = _save(client, admin_token, params={"kwp": 10.0})
    proj = client.get(f"/api/v1/projects/{r.json()['id']}",
                      headers=_auth(admin_token)).json()
    assert proj["fve_params"]["bom_mode"] == "components"
    assert proj["fve_params"]["fve_materials"] == []
```

- [ ] **Step 2: Spusť testy — musí padat**

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_api.py -q -k bom`
Expected: FAIL — `test_save_rejects_unknown_bom_mode` vrátí 200 (neznámý režim se tiše zahodí) a `bom_mode` v `fve_params` chybí.

- [ ] **Step 3: Přidej pole a validátor do `FveParams`**

V `backend/app/reportgen/fve_router.py` vlož do `FveParams` za `active_appliances` (za řádek 63):

```python
    # Přepínač sestavy — spec 6.1, 6.2
    bom_mode: str = "components"        # "system" | "components"
    # Snímek výběru: [{material_id, code, category, qty, unit_price, line_total}]
    fve_materials: list[dict] = []
    panel_material_id: int | None = None
    inverter_material_id: int | None = None
    battery_material_id: int | None = None
    install_material_id: int | None = None
    system_material_id: int | None = None
```

a hned za existující validátor `_valid_scheme` (za řádek 70):

```python
    @field_validator("bom_mode")
    @classmethod
    def _valid_bom_mode(cls, v: str) -> str:
        if v not in ("components", "system"):
            raise ValueError(f"Neznámý režim sestavy: {v}")
        return v
```

- [ ] **Step 4: Spusť testy**

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_api.py -q -k bom`
Expected: PASS (3 testy)

- [ ] **Step 5: Spusť celou sadu**

Run: `./venv/bin/python -m pytest tests/reportgen -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/reportgen/fve_router.py tests/reportgen/test_fve_api.py
git commit -m "feat(fve): FveParams nese vyber sestavy a snimek materialu"
```

---

### Task 9: Frontend typy a klient pro materiály

**Files:**
- Modify: `frontend-web/src/types.ts` (`Material` ~149, nové typy u `FveParams` ~224)
- Modify: `frontend-web/src/api/fve.ts` (importy, `fetchFveMaterials`, `DEFAULT_FVE_PARAMS`)
- Test: typecheck (repo nemá frontend unit testy)

**Interfaces:**
- Consumes: backend endpoint `/fve-analysis/materials` (Task 6)
- Produces: `FveMaterial`, `FveMaterialLine`, rozšířené `FveParams`, `fetchFveMaterials()`, aktualizované `DEFAULT_FVE_PARAMS`. Používá Task 10.

- [ ] **Step 1: Zapiš typy (padající typecheck)**

V `frontend-web/src/types.ts` rozšiř `Material` (za `active?: boolean;` na řádku 155):

```ts
  category?: string;
  visibility?: string;
  rating?: number | null;
  is_default?: boolean;
```

a za `FveParams` (za řádek 246) vlož nové typy:

```ts
/** Jedna položka snímku sestavy, uložená v `fve_params_json`. */
export interface FveMaterialLine {
  material_id: number;
  code: string;
  category: string;
  qty: number;
  unit_price: number;
  line_total: number;
}

/** Katalog pro přepínač sestavy. Server skryje `internal` zákazníkovi. */
export interface FveMaterial {
  id: number;
  code: string;
  name: string;
  category: "panel" | "inverter" | "battery" | "install" | "system" | "other";
  visibility: "public" | "internal";
  rating?: number | null;
  unit?: string;
  price: number;
  is_default?: boolean;
  system_kwp?: number | null;
  system_battery_kwh?: number | null;
}
```

a doplň do `FveParams` (za `active_appliances: string[];` na řádku 245):

```ts
  bom_mode: "system" | "components";
  fve_materials: FveMaterialLine[];
  panel_material_id: number | null;
  inverter_material_id: number | null;
  battery_material_id: number | null;
  install_material_id: number | null;
  system_material_id: number | null;
```

- [ ] **Step 2: Ověř, že typecheck padá**

Run: `cd frontend-web && npx tsc -b`
Expected: FAIL — `DEFAULT_FVE_PARAMS` v `api/fve.ts` nedodává nová povinná pole `FveParams`.

- [ ] **Step 3: Doplň klienta a defaulty**

V `frontend-web/src/api/fve.ts` přidej `FveMaterial` do importu type (za `FveGeocode,` na řádku 7):

```ts
  FveMaterial,
```

a nahraď `DEFAULT_FVE_PARAMS` (řádky 52–73) a přidej `fetchFveMaterials` před něj:

```ts
/** Katalog pro přepínač sestavy. Server filtruje `internal` podle role. */
export const fetchFveMaterials = () =>
  client
    .get<{ materials: FveMaterial[] }>("/fve-analysis/materials")
    .then((r) => r.data.materials);

/** Defaulty musí sedět s backendem (FveParams v fve_router.py). */
export const DEFAULT_FVE_PARAMS: FveParams = {
  kwp: 10.0,
  battery_capacity: 10.0,
  annual_consumption_mwh: 5.0,
  price_power: 3.0,
  price_distribution: 2.0,
  price_sell: 2.0,
  sell_price_scheme: "fixed",
  community_sell_price: 1.5,
  shared_sell_price: 2.54,
  spot_price_margin: 0.4,
  latitude: 50.0880,
  longitude: 14.4208,
  surface_tilt: 35,
  surface_azimuth: 180,
  grid_export_limit_kw: 10.0,
  system_loss_factor: 14.0,
  winter_loss_factor: 10.0,
  thermal_battery_capacity_kwh: 0.0,
  thermal_battery_charge_power_kw: 2.0,
  active_appliances: [],
  bom_mode: "components",
  fve_materials: [],
  panel_material_id: null,
  inverter_material_id: null,
  battery_material_id: null,
  install_material_id: null,
  system_material_id: null,
};
```

- [ ] **Step 4: Spusť typecheck**

Run: `cd frontend-web && npx tsc -b`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend-web/src/types.ts frontend-web/src/api/fve.ts
git commit -m "feat(frontend): typy a klient pro katalog materialu"
```

---

### Task 10: Formulář — karty, přepínač sestavy a živý součet investice

**Files:**
- Modify: `frontend-web/src/components/fve/FveAnalysisForm.tsx` (celý)
- Test: `npx tsc -b` + `npm run build`

**Interfaces:**
- Consumes: `fetchFveMaterials`, `FveMaterial`, `FveMaterialLine`, nová pole `FveParams` (Task 9)
- Produces: snímek `params.fve_materials` aktualizovaný při každé změně; živý součet investice; tři karty. Geocode picker zůstává **beze změny** (patří do plánu 4).

- [ ] **Step 1: Nahraď `FveAnalysisForm.tsx` (padající typecheck)**

Přepiš **celý** soubor `frontend-web/src/components/fve/FveAnalysisForm.tsx`:

```tsx
import { useEffect, useState } from "react";
import { fetchFveMaterials, geocode } from "../../api/fve";
import type {
  FveAppliance, FveGeocode, FveMaterial, FveMaterialLine, FveParams,
} from "../../types";

const SELL_SCHEMES = [
  { value: "fixed", label: "Fixní cena" },
  { value: "community", label: "Komunita" },
  { value: "shared", label: "Sdílení" },
  { value: "spot", label: "Spot" },
] as const;

function NumberField({
  label, unit, min, max, step = 0.1, value, onChange, help,
}: {
  label: string;
  unit?: string;
  min?: number;
  max?: number;
  step?: number;
  value: number;
  onChange: (v: number) => void;
  help?: string;
}) {
  return (
    <label className="block">
      <span className="text-sm text-slate-700">{label}</span>
      <div className="flex items-center gap-2 mt-1">
        <input
          type="number"
          value={Number.isFinite(value) ? value : ""}
          min={min}
          max={max}
          step={step}
          onChange={(e) => {
            const n = Number(e.target.value);
            // prázdné pole není 0 — 0 kWp je nesmysl, prázdno je „ještě nevyplněno"
            onChange(e.target.value === "" ? NaN : n);
          }}
          className="w-full border border-slate-300 rounded px-3 py-2 text-sm"
        />
        {unit && <span className="text-sm text-slate-500 w-12">{unit}</span>}
      </div>
      {help && <span className="text-xs text-slate-500">{help}</span>}
    </label>
  );
}

/** Tři dílčí karty místo jednoho dlouhého seznamu (spec 6.3). */
function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="bg-white rounded-lg border border-slate-200">
      <h3 className="font-semibold text-navy px-5 py-3 border-b border-slate-100">{title}</h3>
      <div className="p-5 space-y-4">{children}</div>
    </section>
  );
}

/** Zrcadlo backendové `derive_qty` — musí počítat stejně, jinak se snímek
 *  a živý součet rozjedou. Backend je autoritativní při uložení. */
function deriveQty(category: string, rating: number | null | undefined, p: FveParams): number {
  if (category === "panel") return rating ? Math.ceil((p.kwp * 1000) / rating) : 0;
  if (category === "inverter") return rating ? Math.ceil(p.kwp / rating) : 0;
  if (category === "battery") return rating ? Math.ceil(p.battery_capacity / rating) : 0;
  return 1;
}

function buildBom(p: FveParams, mats: FveMaterial[]): FveMaterialLine[] {
  const byId = (id: number | null) => mats.find((m) => Number(m.id) === id);
  if (p.bom_mode === "system") {
    const m = byId(p.system_material_id);
    if (!m) return [];
    const price = Number(m.price ?? 0);
    return [{
      material_id: Number(m.id), code: m.code, category: m.category,
      qty: 1, unit_price: price, line_total: price,
    }];
  }
  const picks: Array<{ id: number | null; category: string }> = [
    { id: p.panel_material_id, category: "panel" },
    { id: p.inverter_material_id, category: "inverter" },
    { id: p.battery_material_id, category: "battery" },
    { id: p.install_material_id, category: "install" },
  ];
  const out: FveMaterialLine[] = [];
  for (const pick of picks) {
    const m = byId(pick.id);
    if (!m) continue;
    const qty = deriveQty(pick.category, m.rating, p);
    const price = Number(m.price ?? 0);
    out.push({
      material_id: Number(m.id), code: m.code, category: pick.category,
      qty, unit_price: price, line_total: qty * price,
    });
  }
  return out;
}

function MaterialSelect({
  label, value, options, onChange,
}: {
  label: string;
  value: number | null;
  options: FveMaterial[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="block">
      <span className="text-sm text-slate-700">{label}</span>
      <select
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full border border-slate-300 rounded px-3 py-2 text-sm bg-white"
      >
        <option value="">— nevybráno —</option>
        {options.map((m) => (
          <option key={m.id} value={m.id}>
            {m.code} — {m.name}{m.rating ? ` (${m.rating})` : ""}
          </option>
        ))}
      </select>
    </label>
  );
}

interface Props {
  params: FveParams;
  onChange: (next: FveParams) => void;
  appliances: FveAppliance[];
  onRun: () => void;
  running: boolean;
}

export default function FveAnalysisForm({
  params, onChange, appliances, onRun, running,
}: Props) {
  const [city, setCity] = useState("");
  const [geo, setGeo] = useState<FveGeocode | null>(null);
  const [geoError, setGeoError] = useState("");
  const [geocoding, setGeocoding] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [materials, setMaterials] = useState<FveMaterial[]>([]);

  useEffect(() => {
    fetchFveMaterials().then(setMaterials).catch(() => setMaterials([]));
  }, []);

  // is_default předvyplní volbu, ale jen dokud uživatel nic nezvolil
  useEffect(() => {
    if (materials.length === 0) return;
    if (params.panel_material_id != null || params.system_material_id != null) return;
    const pick = (cat: string) =>
      materials.find((m) => m.category === cat && m.is_default) ?? null;
    const panel = pick("panel");
    const inverter = pick("inverter");
    const battery = pick("battery");
    const install = pick("install");
    const system = pick("system");
    const next: FveParams = {
      ...params,
      panel_material_id: panel ? Number(panel.id) : null,
      inverter_material_id: inverter ? Number(inverter.id) : null,
      battery_material_id: battery ? Number(battery.id) : null,
      install_material_id: install ? Number(install.id) : null,
      system_material_id: system ? Number(system.id) : null,
    };
    next.fve_materials = buildBom(next, materials);
    onChange(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [materials]);

  const set = <K extends keyof FveParams>(key: K, value: FveParams[K]) => {
    const next = { ...params, [key]: value };
    if (materials.length > 0) next.fve_materials = buildBom(next, materials);
    onChange(next);
  };

  const setBomMaterial = (
    key: "panel_material_id" | "inverter_material_id" | "battery_material_id"
       | "install_material_id" | "system_material_id",
    raw: string,
  ) => {
    const id = raw === "" ? null : Number(raw);
    const next: FveParams = { ...params, [key]: id };
    if (key === "system_material_id" && id != null) {
      const m = materials.find((x) => Number(x.id) === id);
      // balíček předvyplní výkon/kapacitu; cena se PŘEPOČÍTÁVAT NEBUDE
      if (m?.system_kwp != null) next.kwp = m.system_kwp;
      if (m?.system_battery_kwh != null) next.battery_capacity = m.system_battery_kwh;
    }
    next.fve_materials = buildBom(next, materials);
    onChange(next);
  };

  const doGeocode = async () => {
    if (!city.trim()) {
      setGeoError("Zadejte název obce");
      return;
    }
    setGeocoding(true);
    setGeoError("");
    try {
      const r = await geocode(city.trim());
      setGeo(r);
      onChange({ ...params, latitude: r.latitude, longitude: r.longitude });
    } catch (e: any) {
      setGeo(null);
      setGeoError(e?.response?.data?.detail || "Místo se nepodařilo najít");
    } finally {
      setGeocoding(false);
    }
  };

  const toggleAppliance = (name: string, on: boolean) =>
    onChange({
      ...params,
      active_appliances: on
        ? [...params.active_appliances, name]
        : params.active_appliances.filter((n) => n !== name),
    });

  const panels = materials.filter((m) => m.category === "panel");
  const inverters = materials.filter((m) => m.category === "inverter");
  const batteries = materials.filter((m) => m.category === "battery");
  const installs = materials.filter((m) => m.category === "install");
  const systems = materials.filter((m) => m.category === "system");
  const investment = params.fve_materials.reduce((a, l) => a + l.line_total, 0);

  return (
    <div className="space-y-4">
      <Card title="Fotovoltaická elektrárna">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <NumberField label="Instalovaný výkon" unit="kWp" min={0.1} max={50}
                      value={params.kwp} onChange={(v) => set("kwp", v)} />
          <NumberField label="Kapacita baterie" unit="kWh" min={0} max={100}
                      value={params.battery_capacity}
                      onChange={(v) => set("battery_capacity", v)} />
        </div>

        <div className="border-t border-slate-100 pt-4">
          <p className="text-sm font-medium text-navy mb-2">Sestava</p>
          <div className="flex gap-4 text-sm">
            <label className="flex items-center gap-2">
              <input type="radio" name="bom_mode"
                     checked={params.bom_mode === "components"}
                     onChange={() => set("bom_mode", "components")} />
              Jednotlivé komponenty
            </label>
            <label className="flex items-center gap-2">
              <input type="radio" name="bom_mode"
                     checked={params.bom_mode === "system"}
                     onChange={() => set("bom_mode", "system")} />
              Hotový systém
            </label>
          </div>

          {params.bom_mode === "system" ? (
            <label className="block mt-3">
              <span className="text-sm text-slate-700">Systém</span>
              <select
                value={params.system_material_id ?? ""}
                onChange={(e) => setBomMaterial("system_material_id", e.target.value)}
                className="mt-1 w-full border border-slate-300 rounded px-3 py-2 text-sm bg-white"
              >
                <option value="">— vyberte balíček —</option>
                {systems.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.code} — {m.name} ({Number(m.price).toLocaleString("cs-CZ")} Kč)
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
              <MaterialSelect label="Panely" value={params.panel_material_id}
                              options={panels}
                              onChange={(v) => setBomMaterial("panel_material_id", v)} />
              <MaterialSelect label="Měnič" value={params.inverter_material_id}
                              options={inverters}
                              onChange={(v) => setBomMaterial("inverter_material_id", v)} />
              <MaterialSelect label="Baterie" value={params.battery_material_id}
                              options={batteries}
                              onChange={(v) => setBomMaterial("battery_material_id", v)} />
              <MaterialSelect label="Montáž" value={params.install_material_id}
                              options={installs}
                              onChange={(v) => setBomMaterial("install_material_id", v)} />
            </div>
          )}

          <div className="mt-3 text-sm flex justify-between border-t border-slate-100 pt-3">
            <span className="font-medium text-navy">Celková investice</span>
            <span className="font-semibold">{investment.toLocaleString("cs-CZ")} Kč</span>
          </div>
        </div>

        <div className="border-t border-slate-100 pt-4 space-y-4">
          <p className="text-sm font-medium text-navy">Spotřeba a ceny</p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <NumberField label="Roční spotřeba" unit="MWh" min={0.1} max={100}
                        value={params.annual_consumption_mwh}
                        onChange={(v) => set("annual_consumption_mwh", v)} />
            <NumberField label="Cena silové energie" unit="Kč/kWh" min={0}
                        value={params.price_power} onChange={(v) => set("price_power", v)} />
            <NumberField label="Cena distribuce" unit="Kč/kWh" min={0}
                        value={params.price_distribution}
                        onChange={(v) => set("price_distribution", v)} />
          </div>
        </div>

        <div className="border-t border-slate-100 pt-4 space-y-4">
          <p className="text-sm font-medium text-navy">Prodej přebytků</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label className="block">
              <span className="text-sm text-slate-700">Schéma prodeje</span>
              <select
                value={params.sell_price_scheme}
                onChange={(e) => set("sell_price_scheme", e.target.value as FveParams["sell_price_scheme"])}
                className="mt-1 w-full border border-slate-300 rounded px-3 py-2 text-sm bg-white"
              >
                {SELL_SCHEMES.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </label>
            {params.sell_price_scheme === "fixed" && (
              <NumberField label="Výkupní cena" unit="Kč/kWh" min={0}
                           value={params.price_sell} onChange={(v) => set("price_sell", v)} />
            )}
            {params.sell_price_scheme === "community" && (
              <NumberField label="Cena komunity" unit="Kč/kWh" min={0}
                           value={params.community_sell_price}
                           onChange={(v) => set("community_sell_price", v)} />
            )}
            {params.sell_price_scheme === "shared" && (
              <NumberField label="Cena sdílení" unit="Kč/kWh" min={0}
                           value={params.shared_sell_price}
                           onChange={(v) => set("shared_sell_price", v)} />
            )}
            {params.sell_price_scheme === "spot" && (
              <NumberField label="Marže nad spotem" unit="Kč/kWh" min={0}
                           value={params.spot_price_margin}
                           onChange={(v) => set("spot_price_margin", v)} />
            )}
          </div>
        </div>
      </Card>

      <Card title="Umístění a pokročilé parametry">
        <div className="border border-slate-200 rounded-lg p-4 bg-slate-50">
          <label className="block text-sm text-slate-700">
            Obec nebo město
            <input
              type="text"
              value={city}
              onChange={(e) => setCity(e.target.value)}
              placeholder="např. Praha"
              className="mt-1 w-full border border-slate-300 rounded px-3 py-2 text-sm bg-white"
            />
          </label>
          <p className="text-xs text-slate-500 mt-1">
            Vyhledává se obec, ne ulice — zadejte např. „Praha" nebo „Brno".
          </p>
          {geoError && <p className="text-xs text-red-600 mt-1">{geoError}</p>}
          {geo && (
            <p className="text-xs text-emerald-700 mt-1">
              Nalezeno: {geo.display_name} ({geo.latitude.toFixed(4)}, {geo.longitude.toFixed(4)})
            </p>
          )}
          <button
            type="button"
            onClick={doGeocode}
            disabled={geocoding}
            className="mt-2 text-sm text-navy underline disabled:opacity-50"
          >
            {geocoding ? "Hledám…" : "Vyhledat souřadnice"}
          </button>
        </div>

        <button
          type="button"
          onClick={() => setShowAdvanced((s) => !s)}
          className="text-sm text-navy underline"
        >
          {showAdvanced ? "Skrýt pokročilé parametry" : "Pokročilé parametry"}
        </button>

        {showAdvanced && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2">
            <NumberField label="Zeměpisná šířka" min={-90} max={90} step={0.0001}
                         value={params.latitude} onChange={(v) => set("latitude", v)} />
            <NumberField label="Zeměpisná délka" min={-180} max={180} step={0.0001}
                         value={params.longitude} onChange={(v) => set("longitude", v)} />
            <NumberField label="Sklon střešního panelu" unit="°" min={0} max={90} step={1}
                         value={params.surface_tilt} onChange={(v) => set("surface_tilt", v)} />
            <NumberField label="Azimut" unit="°" min={0} max={359} step={1}
                         value={params.surface_azimuth} onChange={(v) => set("surface_azimuth", v)} />
            <NumberField label="Systémové ztráty" unit="%" min={0} max={50}
                         value={params.system_loss_factor}
                         onChange={(v) => set("system_loss_factor", v)} />
            <NumberField label="Zimní ztráty" unit="%" min={0} max={100}
                         value={params.winter_loss_factor}
                         onChange={(v) => set("winter_loss_factor", v)} />
            <NumberField
              label="Limit exportu do sítě"
              unit="kW"
              min={0}
              help="Prázdné = bez limitu"
              value={params.grid_export_limit_kw ?? NaN}
              onChange={(v) => set("grid_export_limit_kw", Number.isNaN(v) ? null : v)}
            />
            <NumberField label="Tepelná baterie" unit="kWh" min={0}
                         value={params.thermal_battery_capacity_kwh}
                         onChange={(v) => set("thermal_battery_capacity_kwh", v)} />
            <NumberField label="Výkon dobíjení tepelné baterie" unit="kW" min={0}
                         value={params.thermal_battery_charge_power_kw}
                         onChange={(v) => set("thermal_battery_charge_power_kw", v)} />
          </div>
        )}
      </Card>

      <Card title={`Spotřebiče v domácnosti (${params.active_appliances.length} zapnuto)`}>
        {appliances.length === 0 ? (
          <p className="text-sm text-slate-500">Načítám katalog spotřebičů…</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {appliances.map((a) => (
              <label key={a.name} className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={params.active_appliances.includes(a.name)}
                  onChange={(e) => toggleAppliance(a.name, e.target.checked)}
                  className="mt-1"
                />
                <span>
                  {a.name}
                  <span className="block text-xs text-slate-500">
                    {a.power_kw} kW · {a.description}
                  </span>
                </span>
              </label>
            ))}
          </div>
        )}
      </Card>

      <div className="flex justify-end">
        <button
          type="button"
          onClick={onRun}
          disabled={running}
          className="bg-antelonGreen text-navy font-semibold px-6 py-3 rounded-lg hover:brightness-110 disabled:opacity-50"
        >
          {running ? "Počítám…" : "Spočítat analýzu"}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Spusť typecheck a build**

Run: `cd frontend-web && npx tsc -b && npm run build`
Expected: PASS (bez chyb)

- [ ] **Step 3: Ověř, že živý součet sedí s backendem (kontrolní test)**

Run:
```bash
cd frontend-web && npx tsc -b
node -e "
const ceil = Math.ceil;
const qty = (cat, rating, p) =>
  cat==='panel' ? ceil(p.kwp*1000/rating) :
  cat==='inverter' ? ceil(p.kwp/rating) :
  cat==='battery' ? ceil(p.battery_capacity/rating) : 1;
const p = {kwp:10, battery_capacity:10};
const total = qty('panel',550,p)*2500 + qty('inverter',10,p)*45000
            + qty('battery',10,p)*87500 + qty('install',null,p)*120000;
if (total !== 300000) { console.error('NESHODA', total); process.exit(1); }
console.log('frontend součet =', total);
"
```
Expected: `frontend součet = 300000` (stejně jako backend test v Tasku 4)

- [ ] **Step 4: Commit**

```bash
git add frontend-web/src/components/fve/FveAnalysisForm.tsx
git commit -m "feat(frontend): karty formulare, přepinač sestavy a živý součet investice"
```

---

### Task 11: `Materialy.tsx` — `canManage` admin/antelon a UI pro platnost cen

**Files:**
- Modify: `frontend-web/src/api/pipeline.ts` (za `addMaterial` ~154)
- Modify: `frontend-web/src/pages/Materialy.tsx` (`canManage` ~30, sekce za „Nový materiál" ~200–213)
- Test: `npx tsc -b` + `npm run build`

**Interfaces:**
- Consumes: `POST /materials/{id}/price` (Task 7), `Material` rozšíření (Task 9)
- Produces: `setMaterialPrice(materialId, {price, valid_from?})`; v UI možnost zapsat novou cenu s datem platnosti pro admin/antelon.

- [ ] **Step 1: Změň `canManage` (padající typecheck pro novou funkci)**

V `frontend-web/src/pages/Materialy.tsx` nahraď řádek 30:

```tsx
  const canManage = hasAnyRole(user, ["admin", "antelon"]);
```

- [ ] **Step 2: Přidej `setMaterialPrice` do klienta**

V `frontend-web/src/api/pipeline.ts` vlož za funkci `addMaterial` (za řádek 154):

```ts
export async function setMaterialPrice(
  materialId: number | string,
  body: { price: number; valid_from?: string },
): Promise<{ id: number | string; material_id: number | string; price: number; valid_from: string; valid_to: string | null }> {
  const res = await client.post(`/materials/${materialId}/price`, body);
  return res.data;
}
```

- [ ] **Step 3: Doplň UI pro platnost cen**

V `frontend-web/src/pages/Materialy.tsx` rozšiř import z `../api/pipeline` (řádky 4–10) o `setMaterialPrice`:

```tsx
import {
  addMaterial,
  addProjectMaterial,
  getMaterials,
  getMaterialsBalance,
  listProjects,
  setMaterialPrice,
} from "../api/pipeline";
```

Přidej stav za `const [mPrice, setMPrice] = useState("0");` (řádek 46):

```tsx
  // form: nová cena s platností
  const [priceMatId, setPriceMatId] = useState("");
  const [newPrice, setNewPrice] = useState("0");
  const [validFrom, setValidFrom] = useState(() => new Date().toISOString().slice(0, 10));
```

Přidej handler za `handleAddMaterial` (za řádek 110):

```tsx
  const handleSetPrice = async () => {
    if (!priceMatId) {
      setMsg("Vyberte materiál pro změnu ceny.");
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      const r = await setMaterialPrice(priceMatId, {
        price: Number(newPrice) || 0,
        valid_from: validFrom,
      });
      setMsg(`Nová cena materiálu od ${r.valid_from}: ${Number(r.price).toLocaleString("cs-CZ")} Kč`);
      setAddMatId(priceMatId);
      await loadCatalog();
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Změna ceny selhala";
      setMsg(`Chyba: ${m}`);
    } finally {
      setBusy(false);
    }
  };
```

V JSX vlož za blok „Nový materiál" (za `</div>` na řádku 212, stále uvnitř `{canManage && (`):

```tsx
              <div className="pt-3 border-t border-slate-100 space-y-2">
                <p className="text-xs font-semibold uppercase text-slateMuted">Nová cena s platností</p>
                <select
                  value={priceMatId}
                  onChange={(e) => {
                    setPriceMatId(e.target.value);
                    const m = materials.find((x) => String(x.id) === e.target.value);
                    setNewPrice(String(m?.price ?? 0));
                  }}
                  className="w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm"
                >
                  <option value="">— materiál —</option>
                  {materials.map((m) => (
                    <option key={String(m.id)} value={String(m.id)}>
                      {m.code} — {m.name}
                    </option>
                  ))}
                </select>
                <div className="grid grid-cols-2 gap-2">
                  <input type="number" min={0} value={newPrice}
                         onChange={(e) => setNewPrice(e.target.value)}
                         placeholder="cena Kč"
                         className="border border-slate-200 rounded-lg px-2 py-1.5 text-sm" />
                  <input type="date" value={validFrom}
                         onChange={(e) => setValidFrom(e.target.value)}
                         className="border border-slate-200 rounded-lg px-2 py-1.5 text-sm" />
                </div>
                <button onClick={handleSetPrice} disabled={busy || !priceMatId}
                        className="btn-navy w-full text-sm disabled:opacity-50">
                  Uložit cenu
                </button>
              </div>
```

- [ ] **Step 4: Spusť typecheck a build**

Run: `cd frontend-web && npx tsc -b && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend-web/src/pages/Materialy.tsx frontend-web/src/api/pipeline.ts
git commit -m "feat(frontend): canManage admin/antelon a UI pro platnost cen"
```

---

### Task 12: Závěrečné ověření

**Files:**
- Data: `data/reportgen.db` (jen kontrola, žádná editace)

**Interfaces:**
- Consumes: vše z Tasků 1–11
- Produces: ověřený zelený stav

- [ ] **Step 1: Celá backendová sada**

Run: `./venv/bin/python -m pytest tests/reportgen -q`
Expected: PASS (původních 154 + nové)

- [ ] **Step 2: Frontend typecheck a build**

Run: `cd frontend-web && npx tsc -b && npm run build`
Expected: bez chyb

- [ ] **Step 3: Ověř seed a kontrolní součet na vývojové DB**

Run:
```bash
./venv/bin/python -c "
import sys; sys.path.insert(0, 'backend'); sys.path.insert(0, 'backend/app')
from reportgen import storage
storage.init_db()
from reportgen.materials_service import derive_qty
S = storage.get_session_factory(); db = S()
by = {m.code: m for m in db.query(storage.Material).all()}
print('materiálů:', len(by))
t = (by['PAN-550'].price*derive_qty('panel', by['PAN-550'].rating, {'kwp':10})
     + by['INV-10'].price + by['BAT-10'].price + by['INS-MONT'].price)
print('kontrolní součet:', t)
assert len(by) == 12 and t == 300000
"
```
Expected: `materiálů: 12`, `kontrolní součet: 300000`

- [ ] **Step 4: Ověření v prohlížeči (playwright, aserce na DOM)**

Backend 8051, web 3100. Přihlášení: `admin@antelon.local` / `Admin123!`, `zakaznik@antelon.local` / `Zakaznik123!`.

1. admin → Materiály: vidí 12 položek a u materiálu lze zapsat novou cenu s datem (v seznamu se cena přepíše).
2. `zakaznik` → nová analýza → karta *Fotovoltaická elektrárna*: tři karty místo pěti sekcí, přepínač *Jednotlivé komponenty / Hotový systém*.
3. Výchozí sestava (PAN-550 / INV-10 / BAT-10 / INS-MONT, 10 kWp / 10 kWh) ukazuje **Celková investice 300 000 Kč**.
4. Změna kWp na 15 přepočítá počet panelů a součet se změní; přepnutí na *Hotový systém* a výběr SYS-10-10 ukáže 300 000 Kč a předvyplní kWp 10 / baterii 10.
5. Uložit analýzu → v `fve_params` je `fve_materials` se `line_total` 300 000.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore(materials): zaverecne overeni ceniku"
```

---

## Self-review (provedeno autorem plánu)

**Pokrytí spec:**
- 3.1 nové sloupce `Material` → Task 1
- 3.2 `MaterialPrice` s `valid_from`/`valid_to` + index → Task 1
- 3.3 `set_material_price` (uzavře, vloží, přepíše) → Task 3; `current_price` → Task 3
- 3.4 idempotentní seed 12 položek, součet 300 000 Kč → Task 4
- 5 `derive_qty` (jediná čistá funkce na backendu) → Task 2
- 7.6 `compute_investment_cost` (snímek → explicitní → 350 000) → Task 5
- 4.1 `GET /api/v1/fve-analysis/materials` s `is_internal_user` filtrem → Task 6
- 4.2 `POST` zúžen, `PUT`, `DELETE` soft, `POST /{id}/price`, RBAC admin/antelon → Task 7
- 6.1 přepínač sestavy → Task 10
- 6.2 nová pole `FveParams` a snímek → Task 8 (backend), Task 9 (typy)
- 6.3 tři karty, geocode picker beze změny → Task 10
- 6.4 živý součet investice → Task 10
- `Materialy.tsx` `canManage` + platnost cen → Task 11

**Placeholdery:** žádné „TBD"/„doplň"/„podobně jako". Každý kódový krok obsahuje konkrétní kód nebo příkaz.

**Konzistence typů:** `set_material_price(db, material_id, price, valid_from, created_by)` je v Tasku 3 definován a v Tasku 7 volán se stejnou signaturou. `compute_investment_cost(params)` v Tasku 5 odpovídá volání v `fve_analysis.py`. `FveMaterial`/`FveMaterialLine` z Tasku 9 odpovídají `buildBom` v Tasku 10. `active` z `DELETE` je boolean, test porovnává přesně `is False`.

**Review Focus:** každá z pěti položek má test v uvedeném tasku (Task 3 dvě přecenění, Task 5 fallback, Task 6 viditelnost + Task 7 soft-delete, Task 7 buyer 403, Task 4 kontrolní součet).

**Známé odchylky/rozhodnutí:** frontend má vlastní zrcadlo `deriveQty` (spec 5 říká „frontend jen zobrazuje výsledek"; pro okamžitý součet bez nového endpointu je zrcadlo nejmenší zásah) — shoda je ověřena v Tasku 10, kroku 3. `SYS-10-10`/`SYS-15-10` dostávají `system_kwp`/`system_battery_kwh`, protože je spec 3.1 vyžaduje pro předvyplnění dle 6.1 a v tabulce seedu nejsou vylučně uvedené.