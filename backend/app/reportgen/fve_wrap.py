import pandas as pd
from typing import Dict, Any

def run_fve_energy(params: dict) -> Dict[str, Any]:
    """
    Wrapper over analyzer pipeline. params expected to be EnergyAnalysisInput-like dict.
    Returns dict with same structure as /analysis/energy endpoint.
    """
    import sys, os
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    from data_loader import load_consumption_data, load_production_data
    from analyzer import calculate_energy_balance, calculate_financials
    from appliance_manager import ApplianceManager
    from visualizer import plot_energy_balance_daily  # not needed for report but can generate
    import plotly.io as pio

    kwp = float(params.get("kwp", 10))
    battery = float(params.get("battery_capacity", 10))
    annual_mwh = float(params.get("annual_consumption_mwh", 5))
    price_power = float(params.get("price_power", 3))
    price_dist = float(params.get("price_distribution", 2))
    price_sell = float(params.get("price_sell", 2))
    active = params.get("active_appliances_data", {})
    lat = float(params.get("latitude", 50.6607))
    lon = float(params.get("longitude", 14.03227))
    tilt = int(params.get("surface_tilt", 35))
    azim = int(params.get("surface_azimuth", 180))
    sys_loss = float(params.get("system_loss_factor", 14))
    win_loss = float(params.get("winter_loss_factor", 10))
    grid_limit = params.get("grid_export_limit_kw")
    if grid_limit is not None:
        grid_limit = float(grid_limit)

    consumption_df = load_consumption_data(target_annual_kwh=annual_mwh*1000)
    production_df, total_actual, total_optimal = load_production_data(
        kwp=kwp, latitude=lat, longitude=lon, surface_tilt=tilt, surface_azimuth=azim,
        system_loss_factor=sys_loss, winter_loss_factor=win_loss
    )
    am = ApplianceManager()
    result_df = calculate_energy_balance(
        consumption_df, production_df, am, active,
        battery_capacity_kwh=battery,
        grid_export_limit_kw=grid_limit,
        thermal_battery_capacity_kwh=float(params.get("thermal_battery_capacity_kwh", 0) or 0),
        thermal_battery_charge_power_kw=float(params.get("thermal_battery_charge_power_kw", 2) or 2),
    )
    # financials
    price_buy = price_power + price_dist
    # sell price scheme handling simplified
    sell_scheme = params.get("sell_price_scheme", "fixed")
    price_sell_val = price_sell
    if sell_scheme == "community":
        price_sell_val = float(params.get("community_sell_price", 1.5))
    elif sell_scheme == "shared":
        price_sell_val = float(params.get("shared_sell_price", 2.54))
    # spot handled as fixed for now (full spot needs DB)

    financials_data = calculate_financials(result_df, electricity_price_buy=price_buy, electricity_price_sell=price_sell_val, active_appliances=list(active.keys()))
    result_df = financials_data["df"]

    total_cons = result_df["consumption_kWh"].sum()
    total_prod = result_df["production_kWh"].sum()
    # Generate a simple plot for report (optional)
    try:
        fig = plot_energy_balance_daily(result_df)
        plot_json = pio.to_json(fig)
    except Exception:
        plot_json = None

    return {
        "result_df_head": result_df.head(5).to_dict(orient="records"),
        "total_consumption": float(total_cons),
        "total_production": float(total_prod),
        "financials": financials_data.get("financials", {}),
        "plots": {"energy_daily": plot_json} if plot_json else {},
        "params": params,
        "_full_df": result_df,  # for internal use
    }

def run_fve_economic(params: dict, annual_savings: float = None):
    from analyzer import calculate_investment_comparison
    from visualizer import plot_investment_comparison
    import plotly.io as pio

    # If annual_savings not provided, try to compute via energy run
    if annual_savings is None:
        annual_savings = float(params.get("annual_savings", 30000))
    inv_cost = float(params.get("investment_cost", 350000))
    years = int(params.get("years", 20))
    sp500 = float(params.get("sp500_return", 8))
    infl = float(params.get("inflation", 3))
    disc = float(params.get("discount_rate", 8))

    result = calculate_investment_comparison(
        initial_investment_czk=inv_cost,
        annual_savings_czk=annual_savings,
        years=years,
        sp500_return_pct=sp500,
        inflation_pct=infl,
        discount_rate_pct=disc,
    )
    try:
        fig = plot_investment_comparison(result)
        plot_json = pio.to_json(fig)
    except Exception:
        plot_json = None

    return {
        **result,
        "plot": plot_json,
        "params": params,
    }

def run_fve_ote(params: dict):
    import sys, os
    import sqlite3
    import pandas as pd
    sys_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "spot_market.db")
    # Try multiple locations
    candidates = [
        sys_path,
        "/app/data/spot_market.db",
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "data", "spot_market.db"),
        "data/spot_market.db",
    ]
    db_path = next((p for p in candidates if os.path.exists(p)), candidates[0])
    year = int(params.get("year", 2024))
    margin = float(params.get("margin", 0.4))
    fixed = float(params.get("fixed_price", 2.5))

    conn = sqlite3.connect(db_path)
    spot_df = pd.read_sql_query(f"SELECT * FROM spot_prices WHERE datetime LIKE '{year}-%'", conn)
    conn.close()
    if spot_df.empty:
        raise ValueError(f"No OTE data for year {year}")

    # Load 1kWp production
    from data_loader import load_production_data
    from analyzer import analyze_spot_profitability
    prod_df, _, _ = load_production_data(kwp=1.0, latitude=50.6607, longitude=14.03227)

    # Prepare spot_prices_df expected columns: datetime, price_czk ?
    # analyze_spot_profitability expects production_df, spot_prices_df, margin, fixed
    results = analyze_spot_profitability(
        production_df=prod_df,
        spot_prices_df=spot_df,
        margin_czk_kwh=margin,
        fixed_price_czk_kwh=fixed,
        analysis_year=year,
    )
    return results
