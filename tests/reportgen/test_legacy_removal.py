"""Úklid legacy Streamlitu — co z aplikace zbylo a co ne.

Tyto testy hlídají dvě věci, které se snadno rozsypou při úklidu:

1. Žádný mrtvý endpoint nezůstal viset a žádný potřebný nezmizel.
2. Výpočetní vrstva (`app.fve_analysis`) neví o HTTP — kdyby si tam
   někdy někdo vrátil `HTTPException`, test 3 by to odhalil. Legacy
   Streamlit to vyžadovalo, nové API ne; je to věc vrstvy endpointu.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]  # tests/reportgen/ → tests/ → repo
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


def _paths(app):
    return sorted(app.openapi()["paths"])


def test_health_endpoint_survives_cleanup(main_app):
    """Nejjednodušší pojistka: aplikace vůbec neslaší importovat.

    Po úklidu se v main.py smazal blok importů; když se překlep projde,
    spadne to tady, ne až v produkci.
    """
    assert main_app.app is not None
    assert callable(main_app.read_root)
    assert main_app.read_root() == {"message": "fveAnalyzator API"}


def test_no_legacy_analysis_paths(main_app):
    """Legacy Streamlit endpointy jsou pryč — už je nikdo nevolá.

    Procházelo se to sem: nginx v frontend-web/nginx.conf proxyuje jen
    `/api/`, takže `/analysis/*` ani `/report/*` nebyly přes veřejný web
    dosažitelné nikdy. Bez auth navíc — kdokoli si mohl nechat vygenerovat
    PDF z cizího výsledku.
    """
    paths = _paths(main_app.app)
    for prefix in ("/analysis", "/report/energy", "/report/economic"):
        leaked = [p for p in paths if p.startswith(prefix)]
        assert not leaked, f"legacy endpointy zůstaly: {leaked}"


def test_fve_analysis_api_survives_cleanup(main_app):
    """Nové API je jediné, co musí po úklidu fungovat."""
    paths = _paths(main_app.app)
    for expected in ("/api/v1/fve-analysis/run", "/api/v1/fve-analysis",
                     "/api/v1/projects/{project_id}/convert-to-order"):
        assert expected in paths, f"chybí {expected}"


def test_ote_paths_are_still_there(main_app):
    """OTE je vědomě odložené — skripty uživatel najde později.

    Tento test existuje, aby někdo při úklidu legacy nezabil OTE omylem
    a myslel si, že je to zamýšlené.
    """
    paths = _paths(main_app.app)
    for expected in ("/ote/update", "/ote/status", "/ote/analyze", "/report/ote"):
        assert expected in paths, f"OTE endpoint {expected} zmizel — úklid měl být chirurgický"


def test_analysis_logic_does_not_import_fastapi():
    """Výpočet nemá co vědět o HTTP.

    Legacy Streamlit to vyžadoval (Mapoval ValueError na HTTPException
    uvnitř těla funkce). Nová architektura to má v tenké vrstvě routeru,
    takže `app.fve_analysis` smí importovat pydantic a numpy, ale ne FastAPI.
    """
    src = (BACKEND / "app" / "fve_analysis.py").read_text(encoding="utf-8")
    offending = [
        line.strip()
        for line in src.splitlines()
        if "import" in line and "fastapi" in line
    ]
    assert not offending, f"fve_analysis importuje FastAPI: {offending}"


def test_legacy_wrapper_models_are_gone(main_app):
    """Pydantic modely patřily jen legacy endpointům."""
    for gone in ("EnergyAnalysisInput", "EconomicAnalysisInput", "GeocodingInput"):
        assert not hasattr(main_app, gone), f"{gone} zůstal v main.py"