"""Výpočetní logika FVE analýzy.

Jediný zdroj pravdy pro energetickou i ekonomickou analýzu.
Volá ho legacy endpoint /analysis/energy i nový /api/v1/fve-analysis/run.

Vstup i výstup jsou plain dict (JSON-friendly) — žádný FastAPI, žádná DB.
Logika je přesunutá z backend/main.py beze změny.
"""
import importlib
import os
import sqlite3
import sys
from typing import Any, Dict

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))


def _mod(name: str):
    """Naimportuje modul z backend/app/ v obou kontexstech.

    Tady je past, na kterou padá fve_wrap.py: analyzer.py, data_loader.py
    a reporting.py používají relativní importy, backend/app/ nemá __init__.py
    (funguje to jen jako namespace package) a testy importují reportgen
    jako top-level, zatímco main.py jako app.reportgen. Relativní import
    ani top-level import proto v jednom z kontextů spadne.

    Řešení: vždy přes `app.<modul>` a zajistit, že backend/ je v sys.path.
    Oba kontexty pak naimportují stejný objekt.
    """
    backend = os.path.dirname(_HERE)
    if backend not in sys.path:
        sys.path.insert(0, backend)
    return importlib.import_module(f"app.{name}")


# Původně to byly defaulty pydantic modelu EnergyAnalysisInput v backend/main.py.
# Ten model je pryč (legacy Streamlit odstraněn), _DEFAULTS je teď jediné místo,
# kde jsou uložené — a `analysis_param_keys()` je veřejné rozhraní pro
# volající s uloženým JSONem parametrů.
_DEFAULTS = {
    "kwp": 10.0,
    "battery_capacity": 10.0,
    "annual_consumption_mwh": 5.0,
    "price_power": 3.0,
    "price_distribution": 2.0,
    "price_sell": 2.0,
    "active_appliances_data": {},
    # UI default je 10 kW (FveParams i DEFAULT_FVE_PARAMS). Původní None
    # ("bez limitu") byl drift, který odhalil parity test v test_fve_defaults.
    "grid_export_limit_kw": 10.0,
    "sell_price_scheme": "fixed",
    "community_sell_price": 1.5,
    "shared_sell_price": 2.54,
    "spot_price_margin": 0.4,
    "latitude": 50.6607,
    "longitude": 14.03227,
    "surface_tilt": 35,
    "surface_azimuth": 180,
    "thermal_battery_capacity_kwh": 0.0,
    "thermal_battery_charge_power_kw": 2.0,
    "system_loss_factor": 14.0,
    "winter_loss_factor": 10.0,
}


def default_params() -> Dict[str, Any]:
    """Výchozí parametry pro UI.

    active_appliances_data vynecháváme — to je runtime stav, ne nastavení.
    """
    return {k: v for k, v in _DEFAULTS.items() if k != "active_appliances_data"}


def analysis_param_keys() -> set:
    """Klíče, které `run_energy_analysis` čte.

    Volající, kteří mají uložený JSON parametrů získaný od uživatele
    (např. `projects.fve_params_json`), potřebují vědět, co do něj
    poslat — ne aby se dovnitř dostalo všechno, co tam je uložené.
    `default_params()` na to nestačí: ten záměrně vynechává
    `active_appliances_data`, což je runtime stav spotřebičů, ne nastavení.
    """
    return set(_DEFAULTS)


def appliance_catalog() -> list:
    """Seznam spotřebičů z ApplianceManager — UI si ho načte, nehardcoduje."""
    am = _mod("appliance_manager").ApplianceManager()
    out = []
    for name in am.get_all_appliance_names():
        profile = am.get_appliance_profile(name) or {}
        out.append({
            "name": name,
            "power_kw": profile.get("power_kW", 0),
            "type": profile.get("type", "Standard"),
            "description": profile.get("description", ""),
        })
    return out


def run_energy_analysis(params: Dict[str, Any]) -> Dict[str, Any]:
    """Energetická analýza z parametrů.

    Vrací přesně strukturu, kterou dnes vrací endpoint /analysis/energy —
    frontend na ni (i na JSON-stringy v plots) už je postavený.

    ValueError z PVGIS nechá propadnout — vrstva endpointu z něj udělá 400.
    """

    def _p(name: str):
        """Parametr z dictu, jinak default. Používá `in`, ne `or`:
        grid_export_limit_kw=None znamená „bez limitu", ne „ne default".
        """
        return params[name] if name in params else _DEFAULTS[name]

    def _dl():
        return _mod("data_loader")

    viz = _mod("visualizer")

    def _viz(name):
        return getattr(viz, name)

    appliance_manager = _mod("appliance_manager").ApplianceManager()

    price_buy = _p("price_power") + _p("price_distribution")
    annual_consumption_kwh = _p("annual_consumption_mwh") * 1000

    consumption_df = _dl().load_consumption_data(target_annual_kwh=annual_consumption_kwh)
    try:
        production_df, total_production_actual, total_production_optimal = _dl().load_production_data(
            kwp=_p("kwp"),
            latitude=_p("latitude"),
            longitude=_p("longitude"),
            surface_tilt=_p("surface_tilt"),
            surface_azimuth=_p("surface_azimuth"),
            system_loss_factor=_p("system_loss_factor"),
            winter_loss_factor=_p("winter_loss_factor")
        )
    except ValueError:
        # PVGIS nedohaloval data — propadáme dál, endpoint z toho udělá 400
        raise


    # Calculate production performance percentage
    production_performance_pct = (total_production_actual / total_production_optimal) * 100 if total_production_optimal > 0 else 0

    # Analýza
    result_df = _mod("analyzer").calculate_energy_balance(
        consumption_df, 
        production_df, 
        appliance_manager, 
        _p("active_appliances_data"), 
        battery_capacity_kwh=_p("battery_capacity"),
        grid_export_limit_kw=_p("grid_export_limit_kw"),
        thermal_battery_capacity_kwh=_p("thermal_battery_capacity_kwh"),
        thermal_battery_charge_power_kw=_p("thermal_battery_charge_power_kw")
    )


    # Determine sell price based on the selected scheme
    spot_prices_df = None
    if _p("sell_price_scheme") == "spot":
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

    if _p("sell_price_scheme") == "community":
        price_sell = _p("community_sell_price")
    elif _p("sell_price_scheme") == "shared":
        price_sell = _p("shared_sell_price")
    elif _p("sell_price_scheme") == "spot" and spot_prices_df is not None:
        # In spot scheme, export revenue is calculated per hour in financials
        # We pass the margin-adjusted price to financials
        price_sell = spot_prices_df.set_index('datetime')['price_czk_kwh'] - _p("spot_price_margin")
    else: # "fixed" or if spot fail
        price_sell = _p("price_sell")
    active_appliances = list(_p("active_appliances_data").keys())
    financials_data = _mod("analyzer").calculate_financials(result_df, electricity_price_buy=price_buy, electricity_price_sell=price_sell, active_appliances=active_appliances)
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

    fig_savings_pie = _viz("plot_hierarchical_composition")(savings_data, unit="Kč")
    fig_savings_treemap = _viz("plot_savings_treemap")(result_df, price_buy, price_sell, active_appliances)
    fig_energy_pie = _viz("plot_hierarchical_composition")(energy_data, unit="kWh")
    fig_energy_treemap = _viz("plot_energy_treemap")(result_df, active_appliances)
    fig_monthly_stats = _viz("plot_monthly_stats")(result_df)

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
        "kwp": _p("kwp"),
        "battery_capacity": _p("battery_capacity"),
        "annual_consumption_mwh": _p("annual_consumption_mwh"),
        "latitude": _p("latitude"),
        "longitude": _p("longitude"),
        "monthly_summary": monthly_summary,
        "appliance_monthly_summary": appliance_monthly_summary
    }

def run_economic_analysis(params: Dict[str, Any]) -> Dict[str, Any]:
    """Analýza návratnosti investice (FVE vs S&P500 vs reinvestace).

    Investice pochází výhradně ze snímku `fve_materials` (plán 2:
    `compute_investment_cost`). Staré analýzy bez snímku mají fallback
    350 000 Kč — záměrně se nepřepočítávají.
    """

    def _p(name: str, default):
        return params[name] if name in params else default

    investment_cost = _mod("reportgen.materials_service").compute_investment_cost(params)
    investment_breakdown = list(params.get("fve_materials") or [])

    df = _mod("analyzer").calculate_investment_comparison(
        initial_investment_czk=investment_cost,
        annual_savings_czk=float(_p("annual_savings", 30000)),
        years=int(_p("years", 20)),
        sp500_return_pct=float(_p("sp500_return", 8)),
        inflation_pct=float(_p("inflation", 3)),
        discount_rate_pct=float(_p("discount_rate", 8)),
    )

    years = int(_p("years", 20))
    payback_series = df[df["PV_Cumulative_CashFlow"] >= 0]["Year"]
    payback_years = payback_series.min() if not payback_series.empty else None

    dpp_series = df[df["PV_Cumulative_DCF"] >= 0]["Year"]
    dpp = dpp_series.min() if not dpp_series.empty else None

    npv = df["PV_Cumulative_DCF"].iloc[-1]
    final_pv_gain = df["PV_Cumulative_CashFlow"].iloc[-1]
    final_pv_reinvest_gain = df["PV_Reinvest_Net_Result"].iloc[-1]
    final_sp500_net = df["SP500_Net_Result"].iloc[-1]

    try:
        plot = _mod("visualizer").plot_investment_comparison(df).to_json()
    except Exception:
        plot = None

    return {
        "metrics": {
            "payback_years": (int(payback_years) if pd.notna(payback_years)
                              else f"> {years}"),
            "discounted_payback_years": (int(dpp) if pd.notna(dpp)
                                        else f"> {years}"),
            "npv_czk": npv,
            "final_pv_gain_czk": final_pv_gain,
            "final_pv_reinvest_gain_czk": final_pv_reinvest_gain,
            "final_sp500_net_czk": final_sp500_net,
        },
        "investment_cost": investment_cost,
        "investment_breakdown": investment_breakdown,
        "plot": plot,
        "raw_data": df.to_dict(orient="records"),
    }
