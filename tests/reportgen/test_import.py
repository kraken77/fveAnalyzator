"""Import Dispečink XLSX (M1.3)."""

import glob
import io
import os
import unicodedata
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def find_xlsx():
    """Najde PROCESNÍ DISPEČINK.xlsx (NFD/NFC robustně)."""
    cands = glob.glob(str(REPO_ROOT / "Podklady" / "Procesy" / "*.xlsx"))
    assert cands, "XLSX nenalezen v Podklady/Procesy"
    for c in cands:
        base = unicodedata.normalize("NFC", os.path.basename(c))
        if base.upper().startswith("PROCESNÍ DISPEČINK".upper()):
            return c
    return cands[0]


XLSX_PATH = find_xlsx()


def test_parse_xlsx_returns_rows(db):
    from reportgen.import_dispecink import parse_dispecink_xlsx

    rows = parse_dispecink_xlsx(XLSX_PATH)
    assert len(rows) >= 30
    assert len(rows) == 34

    by_name = {r["name"]: r for r in rows}
    assert "Havlík Milan" in by_name
    hav = by_name["Havlík Milan"]
    assert hav["type"] == "rd"
    assert hav["tech"] == "DEYE"
    assert hav["status"] == "active"
    assert hav["steps"]["lead_zaevidovani"]["done"]
    assert hav["steps"]["lead_zaevidovani"]["done_at"].isoformat() == "2026-08-01"

    brada = by_name["Brada"]
    assert brada["status"] == "active"
    chaloupka = by_name["Chaloupka"]
    assert chaloupka["status"] == "cancelled"


def test_parse_type_mapping(db):
    from reportgen.import_dispecink import map_zakazka_type

    assert map_zakazka_type("RD") == "rd"
    assert map_zakazka_type("byt") == "byt"
    assert map_zakazka_type("Firma") == "firma"
    assert map_zakazka_type("bojler") == "bojler"
    assert map_zakazka_type("rozšíření") == "rozsireni"
    assert map_zakazka_type("ostatní") == "ostatni"
    assert map_zakazka_type("") == "ostatni"
    assert map_zakazka_type(None) == "ostatni"


def test_import_dispecink_count_and_idempotence(db):
    from reportgen.import_dispecink import import_dispecink, parse_dispecink_xlsx

    expected = len(parse_dispecink_xlsx(XLSX_PATH))
    first = import_dispecink(XLSX_PATH, db)
    assert first["imported"] == expected
    assert first["skipped"] == 0

    second = import_dispecink(XLSX_PATH, db)
    assert second["imported"] == 0
    assert second["skipped"] == expected

    from reportgen.storage import Project
    # 34 zakázek + demo projekty ze seedu init_db
    assert db.query(Project).count() >= expected


def test_import_sample_project_pipeline(db):
    from reportgen.import_dispecink import import_dispecink
    from reportgen.storage import (Project, ProjectPipeline, ProjectStep,
                                   PipelineStep, StepEvent)

    import_dispecink(XLSX_PATH, db)

    p = db.query(Project).filter(Project.name == "Havlík Milan").one()
    assert p.type == "rd"
    assert p.status == "active"
    assert p.tech == "DEYE"

    pp = db.query(ProjectPipeline).filter(ProjectPipeline.project_id == p.id).one()
    rd_tpl_steps = db.query(PipelineStep).filter(PipelineStep.template_id == pp.template_id).count()
    inst = db.query(ProjectStep).filter(ProjectStep.project_id == p.id).all()
    assert len(inst) == rd_tpl_steps
    assert len(inst) >= 55

    # kroky hotové z dat
    by_code = {}
    rows = (db.query(ProjectStep, PipelineStep)
            .join(PipelineStep, ProjectStep.step_id == PipelineStep.id)
            .filter(ProjectStep.project_id == p.id).all())
    for ps, s in rows:
        by_code[s.code] = ps
    assert by_code["lead_zaevidovani"].status == "done"
    assert by_code["lead_zaevidovani"].done_at.date().isoformat() == "2026-08-01"
    assert by_code["lead_telefon"].status == "done"
    assert by_code["lead_telefon"].done_at.date().isoformat() == "2026-08-02"
    assert by_code["tech_posouzeni"].status == "done"
    # ne-vyplněné kroky zůstávají not_started
    assert by_code["konecna_faktura"].status == "not_started"

    # událost done vznikla
    ev = (db.query(StepEvent)
          .join(ProjectStep, StepEvent.step_id == ProjectStep.id)
          .filter(ProjectStep.project_id == p.id,
                  StepEvent.action == "done").count())
    assert ev >= 2


def test_import_notes_and_cancelled(db):
    from reportgen.import_dispecink import import_dispecink
    from reportgen.storage import (Project, ProjectStep, PipelineStep)

    import_dispecink(XLSX_PATH, db)

    krinert = db.query(Project).filter(Project.name == "Krinert").one()
    rows = (db.query(ProjectStep, PipelineStep)
            .join(PipelineStep, ProjectStep.step_id == PipelineStep.id)
            .filter(ProjectStep.project_id == krinert.id).all())
    by_code = {s.code: ps for ps, s in rows}
    assert by_code["dotacni_uspora"].status == "not_started"
    assert by_code["dotacni_uspora"].note and "Zamítnuto" in by_code["dotacni_uspora"].note

    chaloupka = db.query(Project).filter(Project.name == "Chaloupka").one()
    assert chaloupka.status == "cancelled"


def test_import_date_variants(db):
    """Datumové varianty: 'a' mark, rozsah '10-15.9.2026' (konec), Excel seria, rozsah '21.9.-22.9.'."""
    from reportgen.import_dispecink import import_dispecink
    from reportgen.storage import (Project, ProjectStep, PipelineStep, StepEvent)

    import_dispecink(XLSX_PATH, db)

    def step(name, code, typ="rd"):
        p = db.query(Project).filter(Project.name == name, Project.type == typ).one()
        return (db.query(ProjectStep, PipelineStep)
                .join(PipelineStep, ProjectStep.step_id == PipelineStep.id)
                .filter(ProjectStep.project_id == p.id, PipelineStep.code == code)
                .one())

    # 'a' marker -> done
    ps, s = step("Havlík Milan", "tech_posouzeni")
    assert ps.status == "done"

    # rozsah 10-15.9.2026 -> konec rozsahu (15.9.), Kvízová vyměna elektroměru
    ps, s = step("Kvízová", "vymena_elektromeru")
    assert ps.status == "done"
    assert ps.done_at.date().isoformat() == "2026-09-15"

    # datetime buňka 2026-09-15 (Brada, sdílení v komunitě - zasláno)
    ps, s = step("Brada", "sdileni_komunita")
    assert ps.status == "done"
    assert ps.done_at.date().isoformat() == "2026-09-15"

    # rozsah 21.9.-22.9. -> konec 22.9. (Křička, elektro-montáž)
    ps, s = step("Křička", "elektro_montaz")
    assert ps.status == "done"
    assert ps.done_at.date().isoformat() == "2026-09-22"

    # události done existují
    p = db.query(Project).filter(Project.name == "Havlík Milan").one()
    evs = {e.action for e in db.query(StepEvent).filter(StepEvent.project_id == p.id).all()}
    assert "done" in evs


@pytest.fixture
def admin_token(client):
    resp = client.post("/api/v1/auth/login",
                       json={"email": "admin@test.local", "password": "Admin123!"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
def customer_token(client):
    resp = client.post("/api/v1/auth/login",
                       json={"email": "zakaznik@test.local", "password": "Zakaznik123!"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_import_endpoint_requires_admin(client, customer_token):
    from reportgen.import_dispecink import parse_dispecink_xlsx

    files = {"file": ("dispecink.xlsx", open(XLSX_PATH, "rb").read(),
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp = client.post("/api/v1/admin/import/dispecink",
                       headers={"Authorization": f"Bearer {customer_token}"},
                       files=files)
    assert resp.status_code == 403


def test_import_endpoint_requires_admin(client, customer_token):
    from reportgen.import_dispecink import parse_dispecink_xlsx

    files = {"file": ("dispecink.xlsx", open(XLSX_PATH, "rb").read(),
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp = client.post("/api/v1/admin/import/dispecink",
                       headers={"Authorization": f"Bearer {customer_token}"},
                       files=files)
    assert resp.status_code == 403


def test_import_endpoint_ok(client, admin_token):
    from reportgen.import_dispecink import parse_dispecink_xlsx
    expected = len(parse_dispecink_xlsx(XLSX_PATH))
    data = open(XLSX_PATH, "rb").read()
    files = {"file": ("dispecink.xlsx", data,
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp = client.post("/api/v1/admin/import/dispecink",
                       headers={"Authorization": f"Bearer {admin_token}"},
                       files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["imported"] == expected
    assert body["skipped"] == 0

    resp2 = client.post("/api/v1/admin/import/dispecink",
                        headers={"Authorization": f"Bearer {admin_token}"},
                        files=files)
    assert resp2.status_code == 200
    assert resp2.json()["imported"] == 0
    assert resp2.json()["skipped"] == expected