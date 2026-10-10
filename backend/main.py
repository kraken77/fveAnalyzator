"""fveAnalyzator — HTTP aplikace.

Frontend je jediný: `frontend-web` (React + Vite). Legacy Streamlit byl
odstraněn, jeho pydantic modely a endpointy s ním.

Co tady je a proč:

* `GET /` — health check.
* `/api/v1/reportgen/*` a `/api/v1/fve-analysis/*` — reportgen routery.
  Veškerá logika FVE analýzy žije v `app.fve_analysis`, která o HTTP
  neví; mapování chyb na HTTP status codes je věc tenké vrstvy routeru.
* `/ote/*` a `/report/ote` — analýza prodeje na spotu. Vědomě odložené
  (chybějí stahovací skripty); endpointy zatím existují, ale data v
  `data/spot_market.db` nejsou. Viz `docs/architektura.md`.

Proč je tu OTE, ačkoli je jediný frontend: historicky se k těmto cestám
chodilo přes Streamlit, ale na rozdíl od `/analysis/*` jsou použitelné
přes veřejný web až po doplnění skriptů — zahozit je teď by znamenalo
zapomenout, kam až analýza sahá.
"""
import logging
import sqlite3
import subprocess
from collections.abc import Callable
from datetime import datetime

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from app.analyzer import analyze_spot_profitability
from app.data_loader import load_production_data
from app.reporting import ReportGenerator

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Filename"],
)

logger = logging.getLogger("fveanalyzator")

# --- ReportGen moduly ---
#
# Každý modul se načítá zvlášť a pád jednoho nesmí vzít ostatní. Dřív byly
# oba routery a inicializace DB v jednom `try`, takže chybějící závislost
# jednoho umlčela i druhý (jeho import se už vůbec neprovedl) a chyba se
# vypsala jen přes `print` do stdout kontejneru — v HTTP odpovědi nebylo
# poznat nic.
#
# Stav načtení se hlásí v `GET /`, takže se rozbitá aplikace nehlásí jako
# zdravá. Detail výjimky jde do logu (s tracebackem), ne do odpovědi —
# `GET /` je bez autentizace.
_module_status: dict[str, str] = {}


def _load(name: str, loader: Callable[[], None]) -> None:
    """Načte modul a zapíše výsledek do `_module_status`. Nikdy nevyhodí."""
    try:
        loader()
    except Exception as exc:  # pragma: no cover — závisí na prostředí
        logger.exception("Modul '%s' se nepodařilo načíst", name)
        _module_status[name] = f"chyba ({type(exc).__name__})"
    else:
        _module_status[name] = "ok"


def _load_reportgen_router() -> None:
    from app.reportgen.router import router

    app.include_router(router)


def _load_fve_router() -> None:
    from app.reportgen.fve_router import router

    app.include_router(router)


def _load_reportgen_db() -> None:
    from app.reportgen.storage import init_db

    init_db()


_load("reportgen", _load_reportgen_router)
_load("fve_analysis", _load_fve_router)
_load("reportgen_db", _load_reportgen_db)


# --- Zdraví aplikace ---

@app.get("/")
def read_root():
    """Health check včetně stavu načtení modulů.

    Při poruše vrací 503, aby se rozbitá aplikace nehlásila jako zdravá.
    Detail chyby je jen v logu, ven jde jméno modulu.
    """
    broken = sorted(name for name, state in _module_status.items() if state != "ok")
    if broken:
        raise HTTPException(
            status_code=503,
            detail=f"Moduly v chybě: {', '.join(broken)}",
        )
    return {"message": "fveAnalyzator API", "modules": dict(_module_status)}


# --- OTE: spotové ceny (odložené, viz docs/architektura.md) ---

class OteAnalysisInput(BaseModel):
    year: int = 2024
    margin: float = 0.4
    fixed_price: float = 2.5


report_gen = ReportGenerator()


@app.post("/ote/update")
def update_ote_data():
    """
    Spustí aktualizaci dat z OTE (stahování + ETL).
    """
    try:
        # 1. Run download script
        subprocess.run(["bash", "download_ote_data.sh"], check=True)

        # 2. Run process script for ALL years to ensure consistency
        subprocess.run(["python3", "process_ote_data.py"], check=True)

        # Re-check db status
        conn = sqlite3.connect("data/spot_market.db")
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(datetime) FROM spot_prices")
        max_date = cursor.fetchone()[0]
        conn.close()

        return {"status": "success", "message": "Data successfully updated.", "latest_data": max_date}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Update failed: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ote/status")
def get_ote_status():
    """
    Vrátí stav OTE databáze (rozsah dostupných dat).
    """
    try:
        conn = sqlite3.connect("data/spot_market.db")
        cursor = conn.cursor()
        cursor.execute("SELECT MIN(datetime), MAX(datetime), COUNT(*) FROM spot_prices")
        row = cursor.fetchone()
        conn.close()

        if row and row[0]:
            return {
                "status": "ok",
                "min_date": row[0],
                "max_date": row[1],
                "count": row[2]
            }
        else:
            return {"status": "empty", "message": "No data found."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/ote/analyze")
def analyze_ote(input_data: OteAnalysisInput):
    """
    Provede analýzu výhodnosti prodeje na spotu vs fixní cena.
    """
    try:
        # Load spot prices
        conn = sqlite3.connect("data/spot_market.db")
        # We need to query by year. SQLite datetime is string 'YYYY-MM-DD...'
        query = f"SELECT * FROM spot_prices WHERE datetime LIKE '{input_data.year}-%'"
        spot_prices_df = pd.read_sql_query(query, conn)
        conn.close()

        if spot_prices_df.empty:
            raise HTTPException(status_code=404, detail=f"No data found for year {input_data.year}")

        # Load 1kWp Production (Optimal)
        # Referenční lokalita Ústí nad Labem (shodná s defaultem FveParams).
        # OTE analýza je obecná — OteAnalysisInput souřadnice neobsahuje,
        # proto se používají vždy tyto pevné.
        prod_df, _, _ = load_production_data(kwp=1.0, latitude=50.6607, longitude=14.03227)

        # Run Analysis
        results = analyze_spot_profitability(
            production_df=prod_df,
            spot_prices_df=spot_prices_df,
            margin_czk_kwh=input_data.margin,
            fixed_price_czk_kwh=input_data.fixed_price,
            analysis_year=input_data.year
        )
        return results
    except Exception as e:
        print("Error in OTE analysis:", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/report/ote")
def generate_ote_report_endpoint(ote_result: dict):
    """
    Generuje PDF report z výsledku OTE analýzy.
    """
    try:
        pdf_bytes = report_gen.generate_ote_report(ote_result)
        fname = f"fve_ote_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{fname}"', "X-Filename": fname})
    except Exception as e:
        print(f"Report Error: {e}")
        return {"status": "error", "message": str(e)}