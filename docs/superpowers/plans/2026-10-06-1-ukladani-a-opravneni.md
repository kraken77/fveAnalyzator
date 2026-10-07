# Ukládání FVE analýzy a oprávnění — implementační plán

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Opravit pád ukládání FVE analýzy (bod 1) tím, že se uklidí stávající sirotčí řádky a projekty se přestanou tvrdě mazat, a narovnat oprávnění u ukládání a převodu na zakázku.

**Architecture:** Kořenová příčina je, že `PRAGMA foreign_keys` je v SQLite defaultně `OFF` a backend ho nikde nezapíná, takže `ON DELETE CASCADE` na `project_users` nikdy nevyplní. `delete_project` proto nechával řádky odkazující do prázdna; ty zablokovaly `save_analysis` na `UNIQUE (project_id, user_id)`. Řešení: (1) v `_migrate` genericky smazat řádky, které `PRAGMA foreign_key_check` označí za porušené, (2) zavést `projects.active` a v `DELETE /projects/{id}` deaktivovat místo mazání, (3) filtrovat `active` na všech čtecích cestách.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x nad SQLite, pytest, React + TypeScript (Vite).

**Spec:** `docs/superpowers/specs/2026-10-06-fve-analyza-opravy-a-cenik-design.md` (části 6, 4.3, 4.4)

## Global Constraints

- Backend se spouští z kořene repa, aby data padla do `data/`. Testy: `./venv/bin/python -m pytest tests/reportgen -q`.
- Testy **nesmí** sáhnout na `data/reportgen.db` — používají `tmp_path` přes fixtures v `tests/reportgen/conftest.py`.
- `PRAGMA foreign_keys` se v tomto plánu **nezapíná**. Vynucení FK by vyžadovalo mazat docházkové a fakturační řádky (`time_entries.step_id`, `invoice_items.step_id` nejsou nulovatelné) — přesně to, co nechceme. Odloženo jako follow-up.
- `datetime.utcnow()` pro časové značky (shodné se stávajícím kódem).
- Commit messages v konvenci repa: `fix(...)`, `feat(...)`, `test(...)`, `chore(...)`.
- Vývoj běží v dev workspace, **ne** v produkci `/home/roman/apps/antelon-energy`.

## Review Focus

Než začneš, přečti si spec. Těchto pět vstupů a stavů spec zmiňuje jen okrajově a je nejpravděpodobnější, že je někdo rozbije — každý má v úkolu vlastní test:

1. **Druhé uložení analýzy po smazání** — přesně scénář bodu 1; musí projít, protože ID se už neuvolní. Task 1 + Task 2.
2. **Veřejný odkaz `share_code` na smazaný projekt** — `_ensure_project_access` ho nehlídá, takže bez vlastního filtru by odkaz dál fungoval. Task 4.
3. **Prázdná databáze při prvním startu** — `_migrate` běží **před** `create_all`, takže sweep musí být bezpečný, když tabulky ještě neexistují. Task 1.
4. **Více porušených FK v jedné tabulce i ve více tabulkách** — sweep musí smazat všechny, ne jen první. Task 1.
5. **Uživatel bez role na převod** (`buyer`, `customer`) — musí dostat 403, ale `buyer` smí uložit rozpracovanou analýzu. Task 5.

---

## Souborová mapa

| Soubor | Odpovědnost | Změna |
|---|---|---|
| `backend/app/reportgen/storage.py` | modely + migrace | `bindparam` import, sweep v `_migrate`, `Project.active`, `detach_step_materials` |
| `backend/app/reportgen/router.py` | projekty, veřejné odkazy | `delete_project` deaktivace, filtry `active` |
| `backend/app/reportgen/fve_router.py` | FVE endpointy | `ANY_ROLE` + buyer, `convert_to_order` role + filtr |
| `backend/app/reportgen/pipeline_router.py` | kroky pipeline | `remove_step` uvolní `project_materials.step_id` |
| `frontend-web/src/components/fve/ContactStep.tsx` | tlačítka uložení | tlačítko zakázky jen pro admin/antelon/sales |
| `tests/reportgen/test_project_lifecycle.py` | **nový** | sweep, deaktivace, filtry, remove_step |
| `tests/reportgen/test_fve_api.py` | RBAC ukládání | buyer smí uložit, sales smí převést |

---

### Task 1: Úklid sirotčích řádků v `_migrate`

**Files:**
- Modify: `backend/app/reportgen/storage.py` (import na řádku 6, `_migrate` — vložit před `conn.commit()` na řádku 322)
- Test: `tests/reportgen/test_project_lifecycle.py` (nový)

**Interfaces:**
- Consumes: `reportgen.storage.init_db(db_path)`
- Produces: sweep jako vedlejší efekt `init_db` — nic pro ostatní úkoly.

- [ ] **Step 1: Napiš padající test**

Vytvoř `tests/reportgen/test_project_lifecycle.py`:

```python
"""Bod 1 — ukládání analýzy padalo na sirotcích v project_users.

SQLite má `PRAGMA foreign_keys` defaultně OFF, takže `ON DELETE CASCADE`
na `project_users` nikdy nevyplní a `delete_project` nechával řádky
odkazující do prázdna. Ty pak blokovaly `save_analysis` na
`UNIQUE (project_id, user_id)`.
"""
import json
import sqlite3

import pytest

from reportgen import storage as st


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


def _orphan_counts(db_path):
    """Vrátí {tabulka: počet} pro řádky s neexistujícím rodičem."""
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        con.close()
    counts = {}
    for row in rows:            # (table, rowid, parent, fkid)
        counts[row[0]] = counts.get(row[0], 0) + 1
    return counts


def test_migrate_sweeps_orphans(db_path):
    """Sirotci v project_users i project_steps zmizí při dalším init_db."""
    st.init_db(db_path)

    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO project_users (project_id, user_id) VALUES (9001, 9001)")
    con.execute("INSERT INTO project_users (project_id, user_id) VALUES (9002, 9002)")
    con.execute("INSERT INTO project_steps (project_id, step_id, status) "
                "VALUES (9003, 9003, 'not_started')")
    con.commit()
    con.close()

    assert _orphan_counts(db_path) == {"project_users": 2, "project_steps": 1}

    # další start aplikace
    st.init_db(db_path)

    assert _orphan_counts(db_path) == {}


def test_migrate_does_not_touch_valid_rows(client, admin_token, db_path):
    """Sweep nesmí smazat nic, co má rodiče."""
    st.init_db(db_path)
    r = client.post("/api/v1/fve-analysis", json={
        "params": {"kwp": 10.0},
        "contact": {"name": "Platný", "email": "platny@example.cz",
                    "phone": "+420777123456"},
    }, headers=_auth(admin_token))
    assert r.status_code == 200, r.text

    before = _orphan_counts(db_path)
    st.init_db(db_path)
    after = _orphan_counts(db_path)

    con = sqlite3.connect(db_path)
    left = con.execute("SELECT COUNT(*) FROM project_users").fetchone()[0]
    con.close()
    assert left >= 1
    assert before == after == {}


def test_init_db_on_fresh_path_does_not_crash(tmp_path):
    """Sweep nesmí spadnout na DB, kde ještě žádné tabulky nejsou.

    `_migrate` běží PŘED `create_all`, takže na prvním startu je seznam
    tabulek prázdný.
    """
    fresh = str(tmp_path / "fresh" / "reportgen.db")
    st.init_db(db_path=fresh)
    con = sqlite3.connect(fresh)
    try:
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        con.close()
```

- [ ] **Step 2: Spusť testy — musí padat**

Run: `./venv/bin/python -m pytest tests/reportgen/test_project_lifecycle.py -q`
Expected: `test_migrate_sweeps_orphans` FAIL — `assert {'project_users': 2, 'project_steps': 1} == {}`. Ostatní dva PASS.

- [ ] **Step 3: Doplň `bindparam` do importu**

V `backend/app/reportgen/storage.py` řádek 6 — přidej `bindparam` na konec importu z `sqlalchemy`:

```python
from sqlalchemy import create_engine, Column, Integer, String, Text, Float, DateTime, Date, ForeignKey, Boolean, UniqueConstraint, text, bindparam
```

- [ ] **Step 4: Implementuj sweep**

V `backend/app/reportgen/storage.py` vlož do `_migrate` **před** `conn.commit()` (za blok `if "notifications" in tables:`, na stejnou úroveň odsazení):

```python
        # --- Úklid sirotků -------------------------------------------------
        # SQLite má `PRAGMA foreign_keys` defaultně OFF (backend ho nikde
        # nezapíná), takže `ON DELETE CASCADE` na project_users nikdy nevyplní
        # a `delete_project` nechával řádky odkazující do prázdna. Ty pak
        # blokovaly save_analysis na UNIQUE (project_id, user_id):
        # projects MAX(id)=36 a users MAX(id)=6 -> další INSERT byl přesně
        # sirotek (37, 7). Mažeme VÝHRADNĚ to, co foreign_key_check označí
        # za porušené — nic jiného.
        orphan_rows = conn.execute(text("PRAGMA foreign_key_check")).fetchall()
        if orphan_rows:
            by_table: dict = {}
            for row in orphan_rows:        # (table, rowid, parent, fkid)
                by_table.setdefault(row[0], set()).add(row[1])
            for table, rowids in by_table.items():
                # název tabulky pochází z DB, ne od uživatele — stejně ověř
                if not table.isidentifier():
                    continue
                stmt = text(
                    f"DELETE FROM {table} WHERE rowid IN :rowids"
                ).bindparams(bindparam("rowids", expanding=True))
                conn.execute(stmt, {"rowids": sorted(rowids)})
```

- [ ] **Step 5: Spusť testy**

Run: `./venv/bin/python -m pytest tests/reportgen/test_project_lifecycle.py -q`
Expected: PASS (3 testy)

- [ ] **Step 6: Spusť celou sadu**

Run: `./venv/bin/python -m pytest tests/reportgen -q`
Expected: PASS, 154 původních + 3 nové

- [ ] **Step 7: Commit**

```bash
git add backend/app/reportgen/storage.py tests/reportgen/test_project_lifecycle.py
git commit -m "fix(reportgen): sweep opustenych radku pri init_db (bod 1)"
```

---

### Task 2: Uložení analýzy projde i po smazání předchozí (přímý test bodu 1)

**Files:**
- Test: `tests/reportgen/test_fve_api.py` (přidat na konec)

**Interfaces:**
- Consumes: sweep z Tasku 1
- Produces: regresní test, který drží bod 1 zavřený.

- [ ] **Step 1: Napiš test**

Přidej na konec `tests/reportgen/test_fve_api.py`:

```python
def test_save_after_delete_reuses_ids_without_collision(client, admin_token):
    """Bod 1: uložit -> smazat -> uložit znovu musí projít.

    Před opravou: smazání nechalo sirotky v project_users, další projekt
    dostal stejné id jako smazaný a další zákazník stejné user_id ->
    UNIQUE constraint failed: project_users.project_id, project_users.user_id.
    """
    first = _save(client, admin_token, contact={
        "name": "První", "email": "prvni@example.cz", "phone": "+420777111222"})
    assert first.status_code == 200, first.text
    pid = first.json()["id"]

    r = client.delete(f"/api/v1/projects/{pid}", headers=_auth(admin_token))
    assert r.status_code == 200, r.text

    second = _save(client, admin_token, contact={
        "name": "Druhý", "email": "druhy@example.cz", "phone": "+420777333444"})
    assert second.status_code == 200, second.text
    assert second.json()["id"] != pid
```

- [ ] **Step 2: Spusť test**

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_api.py::test_save_after_delete_reuses_ids_without_collision -q`
Expected: PASS po Tasku 1. Pokud FAILuje na UNIQUE, Task 1 není správně nasazený.

- [ ] **Step 3: Commit**

```bash
git add tests/reportgen/test_fve_api.py
git commit -m "test(fve): regresni test ulozeni po smazani (bod 1)"
```

---

### Task 3: `projects.active` — deaktivace místo tvrdého mazání

**Files:**
- Modify: `backend/app/reportgen/storage.py` (`Project`, ~řádek 67, a `_migrate` blok `if "projects" in tables`)
- Modify: `backend/app/reportgen/router.py:224-231` (`delete_project`)
- Test: `tests/reportgen/test_project_lifecycle.py`

**Interfaces:**
- Consumes: `init_db` z Tasku 1
- Produces: `Project.active: bool` — Tasky 4 a 5 na něm filtrují.

- [ ] **Step 1: Napiš padající test**

Přidej do `tests/reportgen/test_project_lifecycle.py`:

```python
def test_delete_project_deactivates(client, admin_token, db_path):
    """DELETE nesmí projekt smazat — jen deaktivovat.

    Tvrdé mazání by zničilo invoice_items, time_entries a pdf_versions
    (fakturační a docházkové záznamy) a navíc uvolnilo ID, které by znovu
    kolidovalo v project_users.
    """
    r = client.post("/api/v1/fve-analysis", json={
        "params": {"kwp": 10.0},
        "contact": {"name": "Smaž Mě", "email": "smaz@example.cz",
                    "phone": "+420777111222"},
    }, headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    r = client.delete(f"/api/v1/projects/{pid}", headers=_auth(admin_token))
    assert r.status_code == 200, r.text

    con = sqlite3.connect(db_path)
    try:
        row = con.execute("SELECT active FROM projects WHERE id = ?",
                          (pid,)).fetchone()
    finally:
        con.close()
    assert row is not None, "řádek projektu musí zůstat v DB"
    assert row[0] == 0
```

- [ ] **Step 2: Spusť test, ověř že padá**

Run: `./venv/bin/python -m pytest tests/reportgen/test_project_lifecycle.py::test_delete_project_deactivates -q`
Expected: FAIL — `no such column: active` (nebo `row is None`, protože projekt zmizel)

- [ ] **Step 3: Přidej sloupec do modelu**

V `backend/app/reportgen/storage.py` v třídě `Project` za `updated_at`:

```python
    active = Column(Boolean, nullable=False, default=True, server_default=text("1"))
```

- [ ] **Step 4: Přidej ALTER do `_migrate`**

Do bloku `if "projects" in tables:` za `customer_phone`, **před** backfill `type`/`status`:

```python
            if "active" not in cols:
                # NOT NULL + konstantní default je v SQLite povolený ADD COLUMN
                conn.execute(text(
                    "ALTER TABLE projects ADD COLUMN active BOOLEAN NOT NULL DEFAULT 1"))
```

- [ ] **Step 4b: Doplň `active` do `_project_to_dict`**

V `backend/app/reportgen/router.py` v `_project_to_dict` přidej za `"status": p.status,`:

```python
        "active": p.active,
```

- [ ] **Step 5: Deaktivuj v `delete_project`**

V `backend/app/reportgen/router.py` nahraď tělo funkce (řádky 224–232):

```python
@router.delete("/projects/{project_id}")
def delete_project(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Měkké smazání: active=0. Projekt zmizí ze seznamů, ale zůstane v DB.

    Tvrdé mazání by smazalo fakturační a docházkové záznamy (invoice_items,
    time_entries, pdf_versions). Navíc by uvolnilo ID projektu a další INSERT
    do project_users by narazil na UNIQUE (project_id, user_id).
    """
    p = _ensure_project_access(project_id, user, db)
    if not (user.has_role("admin") or user.has_role("antelon")):
        raise HTTPException(403, "Jen Antelon může mazat")
    p.active = False
    p.updated_at = datetime.utcnow()
    db.commit()
    return {"status": "ok"}
```

- [ ] **Step 6: Spusť testy**

Run: `./venv/bin/python -m pytest tests/reportgen/test_project_lifecycle.py -q`
Expected: PASS (4 testy)

- [ ] **Step 7: Spusť celou sadu**

Run: `./venv/bin/python -m pytest tests/reportgen -q`
Expected: PASS. **Pozor:** kdyby některý existující test mazání projektu očekával zmizení řádku z DB, přepiš ho na `active == False` — ne naopak.

- [ ] **Step 8: Commit**

```bash
git add backend/app/reportgen/storage.py backend/app/reportgen/router.py tests/reportgen/test_project_lifecycle.py
git commit -m "feat(projects): mekke smazani pres projects.active"
```

---

### Task 4: Filtr `active` v seznamu a v přístupu k projektu

**Files:**
- Modify: `backend/app/reportgen/router.py` (`_ensure_project_access` ~řádek 88, `list_projects` ~řádky 158–172)
- Test: `tests/reportgen/test_project_lifecycle.py`

**Interfaces:**
- Consumes: `Project.active` z Tasku 3
- Produces: `_ensure_project_access` vrací 404 pro `active=0` — jedním místem se zablokuje ~15 endpointů.

- [ ] **Step 1: Napiš padající testy**

Přidej do `tests/reportgen/test_project_lifecycle.py`:

```python
def _saved_project(client, token, email="seznam@example.cz", name="Test"):
    r = client.post("/api/v1/fve-analysis", json={
        "params": {"kwp": 10.0},
        "contact": {"name": name, "email": email, "phone": "+420777123456"},
    }, headers=_auth(token))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_deactivated_project_disappears_from_list(client, admin_token):
    pid = _saved_project(client, admin_token)
    listed = client.get("/api/v1/projects", headers=_auth(admin_token)).json()
    assert any(p["id"] == pid for p in listed)

    client.delete(f"/api/v1/projects/{pid}", headers=_auth(admin_token))

    listed = client.get("/api/v1/projects", headers=_auth(admin_token)).json()
    assert all(p["id"] != pid for p in listed)


def test_deactivated_project_detail_is_404(client, admin_token):
    pid = _saved_project(client, admin_token, email="detail@example.cz")
    client.delete(f"/api/v1/projects/{pid}", headers=_auth(admin_token))

    r = client.get(f"/api/v1/projects/{pid}", headers=_auth(admin_token))
    assert r.status_code == 404, r.text


def test_deactivated_project_hidden_from_customer(client, admin_token, customer_token):
    """Zákazník vidí svůj projekt přes project_users — i tam musí filtr platit."""
    pid = _saved_project(client, admin_token, email="zakaznik@test.local",
                         name="Zákazníkův")
    assert any(p["id"] == pid for p in
               client.get("/api/v1/projects", headers=_auth(customer_token)).json())

    client.delete(f"/api/v1/projects/{pid}", headers=_auth(admin_token))

    assert all(p["id"] != pid for p in
               client.get("/api/v1/projects", headers=_auth(customer_token)).json())
```

`customer_token` v `test_project_lifecycle.py` **není** — přidej fixture vedle `admin_token`:

```python
@pytest.fixture
def customer_token(client):
    return _login(client, "zakaznik@test.local", "Zakaznik123!")
```

- [ ] **Step 2: Spusť testy, ověř že padají**

Run: `./venv/bin/python -m pytest tests/reportgen/test_project_lifecycle.py -q -k "deactivated"`
Expected: FAIL — smazaný projekt se pořád vrací v seznamu i na detailu.

- [ ] **Step 3: Filtruj v `_ensure_project_access`**

V `backend/app/reportgen/router.py` (řádek 88):

```python
def _ensure_project_access(project_id: int, user, db: Session):
    p = db.query(Project).filter(Project.id == project_id,
                                 Project.active.is_(True)).first()
    if not p:
        raise HTTPException(404, "Projekt nenalezen")
```

- [ ] **Step 4: Filtruj v `list_projects`**

Nahraď tělo funkce (řádky 158–172):

```python
@router.get("/projects")
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if is_principal(user) or is_internal_user(user):
        projects = (db.query(Project)
                    .filter(Project.active.is_(True))
                    .order_by(Project.updated_at.desc()).all())
    else:
        # customer: owned + shared
        owned = db.query(Project).filter(Project.owner_id == user.id,
                                         Project.active.is_(True)).all()
        shared_ids = [r.project_id for r in db.query(ProjectUser).filter(ProjectUser.user_id == user.id).all()]
        shared = (db.query(Project)
                  .filter(Project.id.in_(shared_ids), Project.active.is_(True)).all()
                  if shared_ids else [])
        seen = set()
        projects = []
        for p in owned + shared:
            if p.id not in seen:
                projects.append(p)
                seen.add(p.id)
        projects.sort(key=lambda x: x.updated_at or datetime.min, reverse=True)
    return [_project_to_dict(p) for p in projects]
```

- [ ] **Step 5: Spusť testy**

Run: `./venv/bin/python -m pytest tests/reportgen/test_project_lifecycle.py -q`
Expected: PASS (7 testů)

- [ ] **Step 6: Spusť celou sadu**

Run: `./venv/bin/python -m pytest tests/reportgen -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/reportgen/router.py tests/reportgen/test_project_lifecycle.py
git commit -m "fix(projects): filtr active v seznamu a v _ensure_project_access"
```

---

### Task 5: Filtr `active` u veřejných odkazů a převodu na zakázku

**Files:**
- Modify: `backend/app/reportgen/router.py` (`public_join` ~řádek 364, `public_preview` ~řádek 377)
- Modify: `backend/app/reportgen/fve_router.py` (`convert_to_order` ~řádek 271)
- Test: `tests/reportgen/test_project_lifecycle.py`

**Interfaces:**
- Consumes: `Project.active`, `_ensure_project_access` z Tasku 4
- Produces: nic — utěsnění dvou cest, které `_ensure_project_access` nepoužívají.

- [ ] **Step 1: Napiš padající testy**

```python
def _share_code(client, token, pid):
    r = client.get(f"/api/v1/projects/{pid}", headers=_auth(token))
    assert r.status_code == 200, r.text
    return r.json()["share_code"]


def test_deleted_project_share_code_is_404(client, admin_token):
    """share_code lookupy NEJDOU přes _ensure_project_access — musí filtrovat samy."""
    pid = _saved_project(client, admin_token, email="sdileny@example.cz")
    code = _share_code(client, admin_token, pid)
    client.delete(f"/api/v1/projects/{pid}", headers=_auth(admin_token))

    r = client.get(f"/api/v1/public/p/{code}")
    assert r.status_code == 404, r.text

    r = client.post("/api/v1/public/join", json={"code": code},
                    headers=_auth(admin_token))
    assert r.status_code == 404, r.text


def test_convert_to_order_rejects_deleted_project(client, admin_token):
    pid = _saved_project(client, admin_token, email="konvert@example.cz")
    client.delete(f"/api/v1/projects/{pid}", headers=_auth(admin_token))

    r = client.post(f"/api/v1/projects/{pid}/convert-to-order",
                    headers=_auth(admin_token))
    assert r.status_code == 404, r.text
```

- [ ] **Step 2: Spusť, ověř že padá**

Run: `./venv/bin/python -m pytest tests/reportgen/test_project_lifecycle.py -q -k "share or convert"`
Expected: FAIL — 200 místo 404.

- [ ] **Step 3: Filtruj v `public_join` a `public_preview`**

V `backend/app/reportgen/router.py` nahraď v **obou** funkcích dotaz:

```python
    p = db.query(Project).filter(Project.share_code == code,
                                 Project.active.is_(True)).first()
```

Hlášky nech (`"Kód neexistuje"` v `public_join`, `"Projekt nenalezen"` v `public_preview`).

- [ ] **Step 4: Filtruj v `convert_to_order`**

V `backend/app/reportgen/fve_router.py` (řádek 271):

```python
    p = db.query(Project).filter(Project.id == project_id,
                                 Project.active.is_(True)).first()
```

- [ ] **Step 5: Spusť testy**

Run: `./venv/bin/python -m pytest tests/reportgen/test_project_lifecycle.py -q`
Expected: PASS (9 testů)

- [ ] **Step 6: Celá sada**

Run: `./venv/bin/python -m pytest tests/reportgen -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/reportgen/router.py backend/app/reportgen/fve_router.py tests/reportgen/test_project_lifecycle.py
git commit -m "fix(projects): aktivni filtr u share_code a convert-to-order"
```

---

### Task 6: RBAC — `buyer` smí uložit, převod jen admin/antelon/sales

**Files:**
- Modify: `backend/app/reportgen/fve_router.py` (`ANY_ROLE` ~řádek 37, `convert_to_order` ~řádky 261–269)
- Modify: `frontend-web/src/components/fve/ContactStep.tsx`
- Test: `tests/reportgen/test_fve_api.py`

**Interfaces:**
- Consumes: `reportgen.auth.hash_password`, `storage.User`
- Produces: `ANY_ROLE` nově obsahuje `buyer`.

- [ ] **Step 1: Napiš padající testy**

Přidej na konec `tests/reportgen/test_fve_api.py`:

```python
# ---------- RBAC: buyer smí uložit, převod jen admin/antelon/sales ----------

def _add_user(db_path, email, role):
    """Vytvoří uživatele přímo v DB — API na vytvoření uživatele neexistuje."""
    import json as _json
    import sqlite3
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


def test_buyer_can_save_analysis(client, admin_token, db_path):
    _add_user(db_path, "buyer1@test.local", "buyer")
    token = _login(client, "buyer2@test.local", "Xx123456!") if False else _login(
        client, "buyer1@test.local", "Xx123456!")
    r = _save(client, token, contact={
        "name": "Kupující", "email": "kupujici@example.cz",
        "phone": "+420777123456"})
    assert r.status_code == 200, r.text


def test_buyer_cannot_convert_to_order(client, admin_token, db_path):
    r = _save(client, admin_token, contact={
        "name": "Ke Konverzi", "email": "kkonverze@example.cz",
        "phone": "+420777123456"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    _add_user(db_path, "buyer@test.local", "buyer")
    token = _login(client, "buyer@test.local", "Xx123456!")
    r = client.post(f"/api/v1/projects/{pid}/convert-to-order",
                    headers=_auth(token))
    assert r.status_code == 403, r.text


def test_sales_can_convert_to_order(client, admin_token, db_path):
    from reportgen.auth import hash_password
    import json as _json
    import sqlite3

    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO users (email, password_hash, role, roles_json) VALUES (?,?,?,?)",
        ("prodejce@test.local", hash_password("Xx123456!"), "sales",
         json.dumps(["sales"])))
    con.commit()
    con.close()
    token = _login(client, "sales@test.local", "Xx123456!")

    pid = _save(client, admin_token, contact={
        "name": "Prodejce", "email": "prodej@example.cz",
        "phone": "+420777123456"}).json()["id"]

    r = client.post(f"/api/v1/projects/{pid}/convert-to-order",
                    headers=_auth(token))
    assert r.status_code == 200, r.text
```

Pozn.: teprve až tenhle soubor poběží, odstraníš duplicitu — `_login` a `_auth`
už v `test_fve_api.py` na začátku jsou, takže je **znovu nedefinuj**.

- [ ] **Step 2: Spusť, ověř že padá**

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_api.py -q -k "buyer or convert_to_order_rejects or save_after_delete"`
Expected: `buyer` uložení FAIL (403 — dnes `ANY_ROLE` buyera nemá), `sales` převod PASS (dnes `is_internal_user` propustí).

- [ ] **Step 3: Rozšiř `ANY_ROLE` o buyera**

V `backend/app/reportgen/fve_router.py` řádek 37:

```python
ANY_ROLE = Depends(require_roles("admin", "antelon", "customer", "buyer"))
```

- [ ] **Step 4: Ověř, kde je `ANY_ROLE` použitý**

Run: `grep -n "ANY_ROLE" backend/app/reportgen/fve_router.py`
Expected: u `save_analysis` a dalších FVE endpointů. Rozšíření o `buyer` je záměr — „Buyer si muze ulozit vypocet". Kdyby některý endpoint buyera vidět neměl, dej mu vlastní `require_roles`, nezužuj `ANY_ROLE`.

- [ ] **Step 5: Zúži `convert_to_order`**

V `backend/app/reportgen/fve_router.py` nahraď kontrolu (řádky 261–269):

```python
    """Převede rozpracovanou analýzu na zakázku: fve_analyza → lead.

    Pouze admin/antelon/sales — je to obchodní rozhodnutí a odpovídá
    pipeline_seed.ALLOWED_LEAD. Zákazník ani buyer analýzu převést nemůže.
    """
    from .pipeline_seed import attach_template

    if not any(user.has_role(r) for r in ("admin", "antelon", "sales")):
        raise HTTPException(403, "Na převod na zakázku nemáte oprávnění")
```

- [ ] **Step 6: Skryj tlačítko ve `ContactStep.tsx`**

V `frontend-web/src/components/fve/ContactStep.tsx` přidej k importům:

```tsx
import { hasAnyRole, useAuth } from "../context/AuthContext";
```

Uvnitř komponenty hned za `export default function ContactStep(...) {`:

```tsx
  const { user } = useAuth();
  const canConvert = hasAnyRole(user, ["admin", "antelon", "sales"]);
```

V JSX nahraď `{!inProject && (` před tlačítkem *Vytvořit zakázku a pokračovat* za:

```tsx
        {!inProject && canConvert && (
```

- [ ] **Step 7: Spusť backend testy**

Run: `./venv/bin/python -m pytest tests/reportgen/test_fve_api.py -q`
Expected: PASS

- [ ] **Step 8: Frontend typecheck**

Run: `cd frontend-web && npx tsc -b`
Expected: bez chyb

- [ ] **Step 9: Celá sada**

Run: `./venv/bin/python -m pytest tests/reportgen -q`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add backend/app/reportgen/fve_router.py frontend-web/src/components/fve/ContactStep.tsx tests/reportgen/test_fve_api.py
git commit -m "feat(rbac): buyer smi ulozit analyzu, prevod jen admin/antelon/sales"
```

---

### Task 7: `remove_step` uvolní vazbu materiálů

**Files:**
- Modify: `backend/app/reportgen/storage.py` (nová funkce za `_seed_rate_cards`, ~řádek 345)
- Modify: `backend/app/reportgen/pipeline_router.py` (`step_admin`, akce `remove_step`, ~řádky 194–200)
- Test: `tests/reportgen/test_project_lifecycle.py`

**Interfaces:**
- Produces: `storage.detach_step_materials(db, step_id) -> None` — uvolní `project_materials.step_id`.

- [ ] **Step 1: Napiš padající test**

```python
def test_detach_step_materials_keeps_material_row(db_path):
    """Smazání kroku nesmí nechat project_materials.step_id odkazovat do prázdna.

    `project_materials.step_id` je nullable a řádek materiálu patří projektu,
    takže se vazba jen uvolní — evidence materiálu zůstává.
    """
    st.init_db(db_path)
    Session = st.get_session_factory(db_path)
    with Session() as s:
        p = st.Project(name="P", customer_name="X", status="lead",
                       type="ostatni", share_code="RMSTEP01")
        m = st.Material(code="M-1", name="Materiál", unit="ks", price=100)
        s.add_all([p, m])
        s.commit()
        s.refresh(p)
        s.refresh(m)
        step = st.ProjectStep(project_id=p.id, step_id=1, status="not_started")
        s.add(step)
        s.commit()
        s.refresh(step)
        pm = st.ProjectMaterial(project_id=p.id, material_id=m.id,
                                step_id=step.id, qty_planned=2)
        s.add(pm)
        s.commit()
        pm_id = pm.id
        step_row_id = step.id

        st.detach_step_materials(s, step_row_id)
        s.commit()

        row = s.get(st.ProjectMaterial, pm_id)
        assert row is not None, "materiál se nesmí smazat"
        assert row.step_id is None
```

- [ ] **Step 2: Spusť, ověř že padá**

Run: `./venv/bin/python -m pytest tests/reportgen/test_project_lifecycle.py::test_detach_step_materials_keeps_material_row -q`
Expected: FAIL — `AttributeError: module 'reportgen.storage' has no attribute 'detach_step_materials'`

- [ ] **Step 3: Implementuj helper**

V `backend/app/reportgen/storage.py` za `_seed_rate_cards`:

```python
def detach_step_materials(db, step_id: int) -> None:
    """Uvolní vazbu materiálů na rušený krok.

    `project_materials.step_id` je nullable a řádek materiálu patří projektu,
    ne kroku — vazba se tedy jen uvolní a evidence zůstává. Bez toho by po
    smazání kroku zůstal sirotek.
    """
    db.query(ProjectMaterial).filter(ProjectMaterial.step_id == step_id).update(
        {ProjectMaterial.step_id: None}, synchronize_session=False)
```

- [ ] **Step 4: Spusť test**

Run: `./venv/bin/python -m pytest tests/reportgen/test_project_lifecycle.py -q`
Expected: PASS (10 testů)

- [ ] **Step 4b: Zavolej helper v `remove_step`**

V `backend/app/reportgen/pipeline_router.py` nahraď blok akce `remove_step`:

```python
    if data.action == "remove_step":
        from .storage import StepEvent, detach_step_materials
        db.query(Notification).filter(Notification.step_id == ps.id).delete()
        db.query(StepEvent).filter(StepEvent.step_id == ps.id).delete()
        # materiály patří projektu — jen uvolníme vazbu na rušený krok
        detach_step_materials(db, ps.id)
        db.delete(ps)
        db.commit()
        return {"status": "removed"}
```

- [ ] **Step 4: Spusť test + celou sadu**

Run: `./venv/bin/python -m pytest tests/reportgen -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/reportgen/storage.py backend/app/reportgen/pipeline_router.py tests/reportgen/test_project_lifecycle.py
git commit -m "fix(pipeline): remove_step uvolni vazbu materialu misto sirotka"
```

---

### Task 8: Záloha produkčních dat a závěrečné ověření

**Files:**
- Data: `data/reportgen.db`

**Interfaces:**
- Consumes: vše z Tasků 1–7
- Produces: ověřený stav pro nasazení

- [ ] **Step 1: Záloha databáze (jednorázově, před nasazením)**

```bash
cd /home/roman/dev/antelon-energy
cp data/reportgen.db data/reportgen.db.bak-2026-10-06
ls -la data/reportgen.db*
```

- [ ] **Step 2: Ověř sweep na skutečných datech**

Run:
```bash
./venv/bin/python -c "
import sys; sys.path.insert(0, 'backend/app'); sys.path.insert(0, 'backend')
from reportgen import storage
storage.init_db()
import sqlite3
con = sqlite3.connect('data/reportgen.db')
print('sirotci po init_db:', con.execute('PRAGMA foreign_key_check').fetchall())
con.close()
"
```
Expected: `sirotci po init_db: []` (před opravou jich bylo 36)

- [ ] **Step 3: Celá testovací sada**

Run: `./venv/bin/python -m pytest tests/reportgen -q`
Expected: PASS, 154 původních + nové

- [ ] **Step 4: Frontend build**

Run: `cd frontend-web && npx tsc -b && npm run build`
Expected: bez chyb

- [ ] **Step 5: Ověření v prohlížeči (playwright, aserce na DOM, ne screenshoty)**

Backend 8051, web 3100. Přihlášení: `zakaznik@antelon.local` / `Zakaznik123!`, `admin@antelon.local` / `Admin123!`.

1. `zakaznik` → nová FVE analýza → karta Kontakt → nový kontakt → *Uložit jako rozpracovanou analýzu* → **200 a projekt se objeví v seznamu** (bod 1)
2. `admin` → otevři projekt → *Vytvořit zakázku a pokračovat* → stav `lead`
3. `buyer` (vytvoř v DB) → tlačítko *Vytvořit zakázku* **není vidět**
4. admin smaže projekt → zmizí ze seznamu, přímý odkaz na `share_code` vrací 404
9. po smazání ulož další analýzu → projde (žádná UNIQUE chyba)

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: zaverecne overeni opravy ukladani"
```