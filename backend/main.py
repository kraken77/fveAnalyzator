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
import sqlite3
import subprocess
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

# ReportGen module. Pozor: oba routery se importují v jednom try — kdyby
# jeden spadl (chybějící závislost), zmizel by i druhý, a chyba by se
# vypsala jen do stdout kontejneru, ne do odpovědi. Oba moduly musejí
# být healthy, aby byl API živý; viz .superpowers ledger (Ruling 4).
try:
    from app.reportgen.router import router as reportgen_router
    from app.reportgen.fve_router import router as fve_router
    from app.reportgen.storage import init_db as reportgen_init_db

    app.include_router(reportgen_router)
    app.include_router(fve_router)
    reportgen_init_db()
except Exception as e:  # pragma: no cover — závisí na prostředí
    print(f"ReportGen init failed: {e}")


# --- Zdraví aplikace ---

@app.get("/")
def read_root():
    return {"message": "fveAnalyzator API"}


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
        # Using generic location (Prague) for general analysis if not specified
        # or we could require coords in input, but simple is better for this tool.
        prod_df, _, _ = load_production_data(kwp=1.0, latitude=50.0880, longitude=14.4208)

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