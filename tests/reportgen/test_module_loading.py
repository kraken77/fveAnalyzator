"""Načítání reportgen modulů v `main.py` — izolace a viditelnost poruchy.

Dřív byly oba routery a inicializace DB v **jednom** `try`:

    try:
        from app.reportgen.router import router
        from app.reportgen.fve_router import router as fve_router
        from app.reportgen.storage import init_db
        app.include_router(...)
        init_db()
    except Exception as e:
        print(f"ReportGen init failed: {e}")

Dvě chyby, které to mělo:

1. Chybějící závislost jednoho routeru umlčela i druhý (import druhého se
   už vůbec neprovedl) — výsledkem bylo API, kterému zmizela půlka cest.
2. `print` jde do stdout kontejneru bez úrovně a bez jména loggeru, takže
   se to v `docker logs` ztratí mezi přístupovými logy. V HTTP odpovědi
   nebylo poznat nic.

Tyto testy hlídají, že:
* pád jednoho modulu ostatní nechá běžet,
* porucha je zapsaná ve stavu, který vrací `GET /`,
* `GET /` při poruše vrací 503, ne 200 (aby se rozbitá aplikace
  nehlásila jako zdravá),
* ven se neposílá detail výjimky (endpoint je bez autentizace).
"""
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"


@pytest.fixture(scope="module")
def main_app():
    """Importuje backend.main s backend/ na sys.path, jako to dělá kontejner."""
    import os

    old_cwd = os.getcwd()
    sys.path.insert(0, str(BACKEND))
    try:
        os.chdir(BACKEND)
        import main

        return main
    finally:
        os.chdir(old_cwd)
        sys.path.pop(0)


# --- Zdravý stav ---------------------------------------------------------


def test_all_modules_report_ok_when_they_load(main_app):
    """V testovacím prostředí se mají načíst všechny moduly."""
    assert main_app._module_status == {
        "reportgen": "ok",
        "fve_analysis": "ok",
        "planning": "ok",
        "reportgen_db": "ok",
    }


def test_health_returns_module_status_when_healthy(main_app):
    body = main_app.read_root()
    assert body["message"] == "fveAnalyzator API"
    assert body["modules"]["fve_analysis"] == "ok"


# --- Izolace -------------------------------------------------------------


def test_broken_module_does_not_silence_the_healthy_one(main_app, monkeypatch):
    """Jádro opravy: dva moduly, jeden spadne, druhý musí doběhnout."""
    ran = []
    status = {}
    monkeypatch.setattr(main_app, "_module_status", status)

    def broken():
        ran.append("broken")
        raise ImportError("chybějící závislost")

    def healthy():
        ran.append("healthy")

    main_app._load("broken_mod", broken)
    main_app._load("healthy_mod", healthy)

    assert ran == ["broken", "healthy"], "pád prvního zastavil druhý"
    assert status["broken_mod"].startswith("chyba (ImportError")
    assert status["healthy_mod"] == "ok"


def test_load_never_raises(main_app, monkeypatch):
    """`_load` musí spolknout i úplně neočekávanou výjimku."""
    monkeypatch.setattr(main_app, "_module_status", {})

    def explosion():
        raise SystemError("něco úplně jiného")

    main_app._load("boom", explosion)  # nesmí vyhodit

    assert main_app._module_status["boom"] == "chyba (SystemError)"


# --- Viditelnost poruchy -------------------------------------------------


def test_health_returns_503_when_a_module_is_broken(main_app, monkeypatch):
    """Rozbitá aplikace se nesmí hlásit jako zdravá."""
    monkeypatch.setattr(
        main_app,
        "_module_status",
        {"reportgen": "ok", "fve_analysis": "chyba (ImportError)", "reportgen_db": "ok"},
    )

    with pytest.raises(HTTPException) as excinfo:
        main_app.read_root()

    assert excinfo.value.status_code == 503
    assert "fve_analysis" in excinfo.value.detail


def test_health_does_not_leak_exception_details(main_app, monkeypatch):
    """Detail výjimky zůstává v logu — `GET /` je bez autentizace."""
    monkeypatch.setattr(
        main_app,
        "_module_status",
        {"reportgen": "chyba (ModuleNotFoundError)"},
    )

    with pytest.raises(HTTPException) as excinfo:
        main_app.read_root()

    message = str(excinfo.value.detail)
    assert "ModuleNotFoundError" not in message
    assert "reportgen" in message


def test_no_print_of_startup_errors(main_app):
    """Startup chyby patří do loggeru, ne do `print`."""
    src = (BACKEND / "main.py").read_text(encoding="utf-8")
    assert "ReportGen init failed" not in src, "v main.py zůstal print z původní opravy"
    assert "logger.exception" in src, "main.py nemá logování s úrovní"
