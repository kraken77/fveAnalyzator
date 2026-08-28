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
    """
    Spustí energetickou a finanční analýzu na základě vstupních parametrů.
    """
    price_buy = input_data.price_power + input_data.price_distribution
    annual_consumption_kwh = input_data.annual_consumption_mwh * 1000

    # Načtení dat
    consumption_df = load_consumption_data(target_annual_kwh=annual_consumption_kwh)
    try:
        production_df, total_production_actual, total_production_optimal = load_production_data(
            kwp=input_data.kwp,
            latitude=input_data.latitude,
            longitude=input_data.longitude,
            surface_tilt=input_data.surface_tilt,
            surface_azimuth=input_data.surface_azimuth,
            system_loss_factor=input_data.system_loss_factor,
            winter_loss_factor=input_data.winter_loss_factor
        )
    except ValueError as e:
        # This ValueError might be from PVGIS data fetching. Keep it for now.
        raise HTTPException(status_code=400, detail=str(e))


    # Calculate production performance percentage
    production_performance_pct = (total_production_actual / total_production_optimal) * 100 if total_production_optimal > 0 else 0

    # Analýza
    result_df = calculate_energy_balance(
        consumption_df, 
        production_df, 
        appliance_manager, 
        input_data.active_appliances_data, 
        battery_capacity_kwh=input_data.battery_capacity,
        grid_export_limit_kw=input_data.grid_export_limit_kw,
        thermal_battery_capacity_kwh=input_data.thermal_battery_capacity_kwh,
        thermal_battery_charge_power_kw=input_data.thermal_battery_charge_power_kw
    )
    
    
    # Determine sell price based on the selected scheme
    spot_prices_df = None
    if input_data.sell_price_scheme == "spot":
        try:
            conn = sqlite3.connect("data/spot_market.db")
            # We assume 2024 for simulation consistency with consumption/production
            spot_prices_df = pd.read_sql_query("SELECT datetime, price_czk FROM spot_prices WHERE datetime LIKE '2024-%'", conn)
            conn.close()
            spot_prices_df['datetime'] = pd.to_datetime(spot_prices_df['datetime']).dt.tz_localize('UTC')
            # Convert MWh to kWh
            spot_prices_df['price_czk_kwh'] = spot_prices_df['price_czk'] / 1000
        except Exception as e:
            print(f"Error loading spot prices: {e}")
            # Fallback to fixed
    
    if input_data.sell_price_scheme == "community":
        price_sell = input_data.community_sell_price
    elif input_data.sell_price_scheme == "shared":
        price_sell = input_data.shared_sell_price
    elif input_data.sell_price_scheme == "spot" and spot_prices_df is not None:
        # In spot scheme, export revenue is calculated per hour in financials
        # We pass the margin-adjusted price to financials
        price_sell = spot_prices_df.set_index('datetime')['price_czk_kwh'] - input_data.spot_price_margin
    else: # "fixed" or if spot fail
        price_sell = input_data.price_sell
    active_appliances = list(input_data.active_appliances_data.keys())
    financials_data = calculate_financials(result_df, electricity_price_buy=price_buy, electricity_price_sell=price_sell, active_appliances=active_appliances)
    result_df = financials_data['df']

    # Výpočet metrik
    total_consumption = result_df['consumption_kWh'].sum()
    total_production = result_df['production_kWh'].sum()
    self_consumption = total_production - financials_data['total_export_kWh']
    cost_total_consumption = result_df['cost_without_pv_czk'].sum()
    cost_import = result_df['cost_import_czk'].sum()
    revenue_export = financials_data['revenue_export_czk']
    savings_self_consumption = financials_data['savings_self_consumption_czk']

    # Create monthly summary
    result_df['month'] = result_df['datetime'].dt.month
    monthly_agg = result_df.groupby('month').agg({
        'production_kWh': 'sum',
        'consumption_kWh': 'sum',
        'grid_export_kWh': 'sum',
        'grid_import_kWh': 'sum',
        'savings_total_czk': 'sum'
    }).reset_index()
    
    # Calculate self-consumption per month
    monthly_agg['self_consumption_kWh'] = monthly_agg['production_kWh'] - monthly_agg['grid_export_kWh']
    
    # Format for JSON response
    month_names = {
        1: "Leden", 2: "Únor", 3: "Březen", 4: "Duben", 5: "Květen", 6: "Červen",
        7: "Červenec", 8: "Srpen", 9: "Září", 10: "Říjen", 11: "Listopad", 12: "Prosinec"
    }
    monthly_summary = []
    appliance_monthly_summary = []
    
    for month_idx, row in monthly_agg.iterrows():
        month_name = month_names[int(row['month'])]
        monthly_summary.append({
            "month": month_name,
            "production_kwh": float(row['production_kWh']),
            "consumption_kwh": float(row['consumption_kWh']),
            "self_consumption_kwh": float(row['self_consumption_kWh']),
            "export_kwh": float(row['grid_export_kWh']),
            "import_kwh": float(row['grid_import_kWh']),
            "savings_czk": float(row['savings_total_czk'])
        })
        
        # Breakdown by appliance for this month
        month_mask = result_df['month'] == row['month']
        month_df = result_df[month_mask]
        
        month_app_fve_sum = 0
        month_app_grid_sum = 0
        month_app_savings_sum = 0
        month_app_grid_cost_sum = 0
        month_app_hours_sum = 0
        
        for app in active_appliances:
            app_cons = month_df[f'appliance_{app}_consumption_kWh'].sum()
            app_fve = month_df[f'appliance_{app}_self_consumption_kWh'].sum()
            app_grid = month_df[f'appliance_{app}_grid_import_kWh'].sum()
            app_savings = month_df[f'appliance_{app}_savings_czk'].sum()
            app_grid_cost = month_df[f'appliance_{app}_grid_cost_czk'].sum() if f'appliance_{app}_grid_cost_czk' in month_df.columns else 0
            app_hours = (month_df[f'appliance_{app}_consumption_kWh'] > 0.001).sum()
            
            month_app_fve_sum += app_fve
            month_app_grid_sum += app_grid
            month_app_savings_sum += app_savings
            month_app_grid_cost_sum += app_grid_cost
            month_app_hours_sum += int(app_hours)
            
            if app_cons > 0 or app_fve > 0:
                appliance_monthly_summary.append({
                    "month": month_name,
                    "appliance": app,
                    "savings_czk": float(app_savings),
                    "grid_cost_czk": float(app_grid_cost),
                    "fve_kWh": float(app_fve),
                    "grid_kWh": float(app_grid),
                    "total_kWh": float(app_cons),
                    "coverage_pct": float(app_fve / app_cons * 100) if app_cons > 0 else 0,
                    "operating_hours": int(app_hours)
                })
        
        # Base load for this month
        month_total_import = month_df['grid_import_kWh'].sum()
        month_total_self_cons = month_df['production_kWh'].sum() - month_df['grid_export_kWh'].sum()
        month_total_savings_self = month_df['savings_self_consumption_czk'].sum()
        month_total_grid_cost = month_df['cost_import_czk'].sum()
        month_total_cons = month_df['consumption_kWh'].sum()
        
        base_fve_m = max(0, month_total_self_cons - month_app_fve_sum)
        base_grid_m = max(0, month_total_import - month_app_grid_sum)
        base_savings_m = max(0, month_total_savings_self - month_app_savings_sum)
        base_grid_cost_m = max(0, month_total_grid_cost - month_app_grid_cost_sum)
        base_total_m = base_fve_m + base_grid_m
        
        appliance_monthly_summary.append({
            "month": month_name,
            "appliance": "Základní chod",
            "savings_czk": float(base_savings_m),
            "grid_cost_czk": float(base_grid_cost_m),
            "fve_kWh": float(base_fve_m),
            "grid_kWh": float(base_grid_m),
            "total_kWh": float(base_total_m),
            "coverage_pct": float(base_fve_m / base_total_m * 100) if base_total_m > 0 else 0,
            "operating_hours": month_df.shape[0]
        })

        # "CELKEM" (Monthly Total) row
        appliance_monthly_summary.append({
            "month": month_name,
            "appliance": "CELKEM",
            "savings_czk": float(month_total_savings_self),
            "grid_cost_czk": float(month_total_grid_cost),
            "fve_kWh": float(month_total_self_cons),
            "grid_kWh": float(month_total_import),
            "total_kWh": float(month_total_cons),
            "coverage_pct": float(month_total_self_cons / month_total_cons * 100) if month_total_cons > 0 else 0,
            "operating_hours": int(month_app_hours_sum + month_df.shape[0])
        })
    
    # Appliance specific metrics
    appliance_metrics = {}
    for app in active_appliances:
        app_fve = result_df[f'appliance_{app}_self_consumption_kWh'].sum()
        app_grid = result_df[f'appliance_{app}_grid_import_kWh'].sum()
        app_savings_czk = result_df[f'appliance_{app}_savings_czk'].sum()
        app_grid_cost = result_df[f'appliance_{app}_grid_cost_czk'].sum() if f'appliance_{app}_grid_cost_czk' in result_df.columns else 0
        app_hours = (result_df[f'appliance_{app}_consumption_kWh'] > 0.001).sum()
        
        appliance_metrics[app] = {
            "fve_kWh": app_fve,
            "grid_kWh": app_grid,
            "total_kWh": app_fve + app_grid,
            "savings_czk": app_savings_czk,
            "grid_cost_czk": app_grid_cost,
            "operating_hours": int(app_hours),
            "coverage_pct": (app_fve / (app_fve + app_grid) * 100) if (app_fve + app_grid) > 0 else 0
        }

    # Calculate Base Load (Základní chod)
    app_fve_sum = sum(m["fve_kWh"] for m in appliance_metrics.values())
    app_grid_sum = sum(m["grid_kWh"] for m in appliance_metrics.values())
    app_savings_sum = sum(m["savings_czk"] for m in appliance_metrics.values())
    app_grid_cost_sum = sum(m["grid_cost_czk"] for m in appliance_metrics.values())
    app_hours_sum = sum(m["operating_hours"] for m in appliance_metrics.values())

    base_fve = max(0, self_consumption - app_fve_sum)
    base_grid = max(0, financials_data['total_import_kWh'] - app_grid_sum)
    base_savings = max(0, savings_self_consumption - app_savings_sum)
    base_grid_cost = max(0, cost_import - app_grid_cost_sum)
    
    base_load_metrics = {
        "fve_kWh": base_fve,
        "grid_kWh": base_grid,
        "total_kWh": base_fve + base_grid,
        "savings_czk": base_savings,
        "grid_cost_czk": base_grid_cost,
        "operating_hours": 8760,
        "coverage_pct": (base_fve / (base_fve + base_grid) * 100) if (base_fve + base_grid) > 0 else 0
    }

    # Prepare logic for Charts BEFORE adding summary rows to appliance_metrics
    # Use current state of appliance_metrics (only active appliances) + base_load_metrics
    
    # Úspory (Kč)
    savings_labels = list(appliance_metrics.keys()) + ['Základní chod']
    savings_values = [m["savings_czk"] for m in appliance_metrics.values()] + [base_savings]
    
    savings_data = {
        'labels': ['Úspora vlastní spotřebou', 'Příjem z prodeje'],
        'values': [savings_self_consumption, revenue_export],
        'subcategories': {
            'Úspora vlastní spotřebou': {
                'labels': savings_labels,
                'values': savings_values
            }
        }
    }
    
    # Energie (kWh)
    energy_labels = list(appliance_metrics.keys()) + ['Základní chod']
    energy_values = [m["fve_kWh"] for m in appliance_metrics.values()] + [base_fve]
    
    energy_data = {
        'labels': ['Vlastní spotřeba', 'Export do sítě'],
        'values': [self_consumption, financials_data['total_export_kWh']],
        'subcategories': {
            'Vlastní spotřeba': {
                'labels': energy_labels,
                'values': energy_values
            }
        }
    }

    # Now add summaries to appliance_metrics for Frontend Table
    appliance_metrics["Základní chod"] = base_load_metrics
    
    # Add Annual CELKEM
    appliance_metrics["CELKEM"] = {
        "fve_kWh": float(self_consumption),
        "grid_kWh": float(financials_data['total_import_kWh']),
        "total_kWh": float(total_consumption),
        "savings_czk": float(savings_self_consumption),
        "grid_cost_czk": float(cost_import),
        "operating_hours": int(app_hours_sum + 8760),
        "coverage_pct": (self_consumption / total_consumption * 100) if total_consumption > 0 else 0
    }

    recommendations = appliance_manager.get_recommendations(active_appliances)

    # Get detailed appliance definitions for UI/Report
    appliance_details = []
    for app in active_appliances:
        profile = appliance_manager.get_appliance_profile(app)
        if profile:
            logic_desc = profile.get("description", "")
            if profile.get("seasonal", False):
                months = profile.get("seasonal_months", [])
                logic_desc += f" (Sezónní: {str(months)})"
            if profile.get("type") == "EV":
                strat = profile.get("charging_strategy", "weekly")
                charge = profile.get("charge_kwh", 0)
                logic_desc += f" | Strategie: {strat} | Nabití: {charge} kWh"
            elif "daily_hours" in profile:
                    logic_desc += f" | Provoz: {profile['daily_hours']} h/den"
            
            appliance_details.append({
                "name": app,
                "power_kw": profile.get("power_kW", 0),
                "type": profile.get("type", "Standard"),
                "description": logic_desc
            })

    fig_savings_pie = plot_hierarchical_composition(savings_data, unit="Kč")
    fig_savings_treemap = plot_savings_treemap(result_df, price_buy, price_sell, active_appliances)
    fig_energy_pie = plot_hierarchical_composition(energy_data, unit="kWh")
    fig_energy_treemap = plot_energy_treemap(result_df, active_appliances)
    fig_monthly_stats = plot_monthly_stats(result_df)

    energy_balance_kwh_dict = {
        "total_consumption": total_consumption,
        "grid_import": financials_data['total_import_kWh'],
        "grid_export": financials_data['total_export_kWh'],
        "self_consumption": self_consumption,
    }
    return {
        "financial_balance": {
            "annual_savings_czk": financials_data['savings_czk'],
            "cost_without_pv_czk": financials_data['cost_without_pv_czk'],
            "cost_with_pv_czk": financials_data['cost_with_pv_czk'],
        },
        "energy_balance_kwh": energy_balance_kwh_dict,
        "economic_balance_czk": {
            "cost_total_consumption": cost_total_consumption,
            "cost_import": cost_import,
            "revenue_export": revenue_export,
            "savings_self_consumption": savings_self_consumption,
        },
        "plots": {
            "savings_pie": fig_savings_pie.to_json(),
            "savings_treemap": fig_savings_treemap.to_json(),
            "energy_pie": fig_energy_pie.to_json(),
            "energy_treemap": fig_energy_treemap.to_json(),
            "monthly_stats": fig_monthly_stats.to_json(),
        },
        "recommendations": recommendations,
        "appliance_details": appliance_details,
        "appliance_metrics": appliance_metrics,
        "raw_data": result_df.head(100).to_dict(orient='records'),
        "production_details": {
            "total_production_actual": total_production_actual,
            "total_production_optimal": total_production_optimal,
            "production_performance_pct": production_performance_pct
        },
        "kwp": input_data.kwp,
        "battery_capacity": input_data.battery_capacity,
        "annual_consumption_mwh": input_data.annual_consumption_mwh,
        "latitude": input_data.latitude,
        "longitude": input_data.longitude,
        "monthly_summary": monthly_summary,
        "appliance_monthly_summary": appliance_monthly_summary
    }

@app.post("/analysis/economic")
def run_economic_analysis(input_data: EconomicAnalysisInput):
    """
    Spustí analýzu návratnosti investice.
    """
    df = calculate_investment_comparison(
        initial_investment_czk=input_data.investment_cost,
        annual_savings_czk=input_data.annual_savings,
        years=input_data.years,
        sp500_return_pct=input_data.sp500_return,
        inflation_pct=input_data.inflation,
        discount_rate_pct=input_data.discount_rate
    )

    payback_years_series = df[df['PV_Cumulative_CashFlow'] >= 0]['Year']
    payback_years = payback_years_series.min() if not payback_years_series.empty else None

    # Discounted Payback Period
    dpp_series = df[df['PV_Cumulative_DCF'] >= 0]['Year']
    dpp = dpp_series.min() if not dpp_series.empty else None
    
    # NPV is the final value of cumulative Discounted Cash Flow
    npv = df['PV_Cumulative_DCF'].iloc[-1]

    final_pv_gain = df['PV_Cumulative_CashFlow'].iloc[-1]
    final_pv_reinvest_gain = df['PV_Reinvest_Net_Result'].iloc[-1]
    final_sp500_net = df['SP500_Net_Result'].iloc[-1]

    fig_investment = plot_investment_comparison(df)

    return {
        "metrics": {
            "payback_years": int(payback_years) if pd.notna(payback_years) else f"> {input_data.years}",
            "discounted_payback_years": int(dpp) if pd.notna(dpp) else f"> {input_data.years}",
            "npv_czk": npv,
            "final_pv_gain_czk": final_pv_gain,
            "final_pv_reinvest_gain_czk": final_pv_reinvest_gain,
            "final_sp500_net_czk": final_sp500_net,
        },
        "plot": fig_investment.to_json(),
        "raw_data": df.to_dict(orient='records')
    }

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
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=Ekonomicka_Analyza.pdf"}
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
        return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=EnergyReport.pdf"})
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
        return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=OteReport.pdf"})
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
