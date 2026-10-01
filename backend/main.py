import sys
import os
import subprocess
from datetime import datetime
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import pandas as pd

# Add the 'app' directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.data_loader import load_consumption_data, load_production_data
from app.analyzer import calculate_energy_balance, calculate_financials, calculate_investment_comparison, analyze_spot_profitability
microseconds = 0 # Dummy variable to fix syntax if needed or just clean line
from app.visualizer import plot_energy_balance_daily, plot_monthly_stats, plot_investment_comparison, plot_savings_treemap, plot_savings_composition, plot_energy_treemap, plot_hierarchical_composition
from app.appliance_manager import ApplianceManager
from app.geocoder import get_coordinates
from app import fve_analysis
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
import sqlite3

appliance_manager = ApplianceManager()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Filename"],
)

# ReportGen module
try:
    from app.reportgen.router import router as reportgen_router
    from app.reportgen.storage import init_db as reportgen_init_db
    app.include_router(reportgen_router)
    reportgen_init_db()
except Exception as e:
    print(f"ReportGen init failed: {e}")

class EnergyAnalysisInput(BaseModel):
    kwp: float = 10.0
    battery_capacity: float = 10.0
    annual_consumption_mwh: float = 5.0
    price_power: float = 3.0
    price_distribution: float = 2.0
    price_sell: float = 2.0
    active_appliances_data: dict = {}
    grid_export_limit_kw: Optional[float] = None
    sell_price_scheme: str = "fixed" # "fixed", "community", "shared", "spot"
    community_sell_price: Optional[float] = 1.5
    shared_sell_price: Optional[float] = 2.54
    spot_price_margin: Optional[float] = 0.4
    latitude: float = 50.0880
    longitude: float = 14.4208
    surface_tilt: int = 35
    surface_azimuth: int = 180
    thermal_battery_capacity_kwh: Optional[float] = 0.0
    thermal_battery_charge_power_kw: Optional[float] = 2.0
    system_loss_factor: float = 14.0
    winter_loss_factor: float = 10.0

class EconomicAnalysisInput(BaseModel):
    annual_savings: float
    investment_cost: float = 350000.0
    years: int = 20
    sp500_return: float = 8.0
    inflation: float = 3.0
    discount_rate: float = 8.0

class OteAnalysisInput(BaseModel):
    year: int = 2024
    margin: float = 0.4
    fixed_price: float = 2.5

class GeocodingInput(BaseModel):
    address: str

@app.get("/")
def read_root():
    return {"message": "fveAnalyzator API"}

@app.post("/analysis/energy")
def run_energy_analysis(input_data: EnergyAnalysisInput):
    """Legacy endpoint (Streamlit). Deleguje do app.fve_analysis."""
    try:
        return fve_analysis.run_energy_analysis(
            input_data.model_dump(exclude_none=False)
        )
    except ValueError as e:
        # PVGIS nedohaloval data pro zadané souřadnice — stejná hláška
        # jako před přesunem, legacy Streamlit na ni spoléhá
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/analysis/economic")
def run_economic_analysis(input_data: EconomicAnalysisInput):
    """Legacy endpoint (Streamlit). Deleguje do app.fve_analysis."""
    return fve_analysis.run_economic_analysis(
        input_data.model_dump(exclude_none=False)
    )

@app.post("/report/economic")
def run_economic_report(data: dict):
    """
    Generates a PDF report for Economic Analysis.
    """
    try:
        from app.reporting import ReportGenerator
        report_gen = ReportGenerator()
        pdf_bytes = report_gen.generate_economic_report(data)
        
        from fastapi import Response
        fname = f"fve_economic_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{fname}"', "X-Filename": fname}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

@app.post("/analysis/geocoding")
def geocode_address(input_data: GeocodingInput):
    """
    Převede adresu na GPS souřadnice (lat, lon).
    """
    result = get_coordinates(input_data.address)
    if not result:
        raise HTTPException(status_code=404, detail="Adresa nebyla nalezena.")
    return result

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

# --- Reporting Module ---
from app.reporting import ReportGenerator
from fastapi.responses import Response

report_gen = ReportGenerator()

@app.post("/report/energy")
def generate_energy_report_endpoint(analysis_result: dict):
    """
    Generates PDF report for Energy Analysis.
    Expects the full JSON result from /analysis/energy calculation.
    """
    try:
        pdf_bytes = report_gen.generate_energy_report(analysis_result)
        fname = f"fve_energy_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{fname}"', "X-Filename": fname})
    except Exception as e:
        # In production, log error
        print(f"Report Error: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/report/ote")
def generate_ote_report_endpoint(ote_result: dict):
    """
    Generates PDF report for OTE Analysis.
    """
    try:
        pdf_bytes = report_gen.generate_ote_report(ote_result)
        fname = f"fve_ote_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{fname}"', "X-Filename": fname})
    except Exception as e:
        print(f"Report Error: {e}")
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
