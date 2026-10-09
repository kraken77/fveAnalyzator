"""M1 — extrakce logiky z main.py do app.fve_analysis.

Import přes `app.` (ne relativně, ne top-level) — vysvětlení v plánu M1.1.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "backend") not in sys.path:
    sys.path.insert(0, str(REPO / "backend"))

from app.fve_analysis import (  # noqa: E402
    appliance_catalog,
    default_params,
    run_energy_analysis,
    run_economic_analysis,
)


def test_default_params_cover_streamlit_settings():
    """Výchozí parametry musí být kompletní — UI staví na nich políčka."""
    p = default_params()
    for key in (
        "kwp", "battery_capacity", "annual_consumption_mwh", "price_power",
        "price_distribution", "price_sell", "sell_price_scheme",
        "community_sell_price", "shared_sell_price", "spot_price_margin",
        "latitude", "longitude", "surface_tilt", "surface_azimuth",
        "grid_export_limit_kw", "system_loss_factor", "winter_loss_factor",
        "thermal_battery_capacity_kwh", "thermal_battery_charge_power_kw",
    ):
        assert key in p, f"chybí parametr {key}"
    # defaultní souřadnice jsou v weather_cache.db → testy běží offline
    # (cache obsahuje i Ústí 50.6607, 14.0323; shoda do 0.001)
    assert (p["latitude"], p["longitude"]) == (50.6607, 14.03227)


def test_appliance_catalog_matches_manager():
    """Katalog musí pocházet z ApplianceManager, ne z hardcoded seznamu.

    Počet je 20, ne 17 jako v legacy Streamlitu: ten má starší seznam
    checkboxů, backend v appliance_manager.py má kompletní (navíc
    'Bojler', 'EV - Jaecoo 7' a 'EV - Enyaq' bez časového variantního
    rozlišení). Backend je zdroj pravdy — když se seznam rozroste,
    test to odhalí.
    """
    cat = appliance_catalog()
    assert len(cat) == 20
    assert {"name", "power_kw", "type", "description"} == set(cat[0].keys())
    assert any(c["name"] == "Bazén - Filtrace" for c in cat)


def test_run_energy_analysis_returns_full_structure():
    """Struktura musí být 1:1 s tím, co dnes vrací /analysis/energy."""
    r = run_energy_analysis({"kwp": 10.0, "annual_consumption_mwh": 5.0})

    assert sorted(r.keys()) == [
        "annual_consumption_mwh", "appliance_details", "appliance_metrics",
        "appliance_monthly_summary", "battery_capacity", "economic_balance_czk",
        "energy_balance_kwh", "financial_balance", "kwp", "latitude",
        "longitude", "monthly_summary", "plots", "production_details",
        "raw_data", "recommendations",
    ]
    assert {"grid_import", "grid_export", "self_consumption",
            "total_consumption"} == set(r["energy_balance_kwh"].keys())
    assert {"cost_total_consumption", "cost_import", "revenue_export",
            "savings_self_consumption"} == set(r["economic_balance_czk"].keys())
    assert {"annual_savings_czk", "cost_without_pv_czk",
            "cost_with_pv_czk"} == set(r["financial_balance"].keys())


def test_plots_are_json_strings():
    """pio.to_json() vrací string. React to parsuje — nesmí to být dict.

    Regresní pojistka: kdyby někdo přidal json.loads(), string by se rozpadl
    a graf by přestal fungovat bez jakékoli chyby v testech struktur.
    """
    r = run_energy_analysis({"kwp": 10.0})
    assert r["plots"], "žádné grafy se nevygenerovaly"
    for name, value in r["plots"].items():
        assert isinstance(value, str), f"{name} není string, ale {type(value)}"
        assert value.startswith("{"), f"{name} není platný JSON"


def test_run_energy_analysis_respects_params():
    """Větší FVE → větší výroba."""
    maly = run_energy_analysis({"kwp": 5.0, "annual_consumption_mwh": 5.0})
    velky = run_energy_analysis({"kwp": 20.0, "annual_consumption_mwh": 5.0})
    assert (velky["production_details"]["total_production_actual"]
            > maly["production_details"]["total_production_actual"])


def test_grid_export_limit_changes_balance():
    """Limit exportu musí měnit bilanci — jinak je parametr ignorován."""
    bez = run_energy_analysis({"kwp": 20.0, "grid_export_limit_kw": None})
    s = run_energy_analysis({"kwp": 20.0, "grid_export_limit_kw": 0.0})
    assert (s["energy_balance_kwh"]["grid_export"]
            < bez["energy_balance_kwh"]["grid_export"])


def test_battery_increases_self_consumption():
    s = run_energy_analysis({"kwp": 10.0, "battery_capacity": 0.0})
    b = run_energy_analysis({"kwp": 10.0, "battery_capacity": 20.0})
    assert (b["energy_balance_kwh"]["self_consumption"]
            >= s["energy_balance_kwh"]["self_consumption"])


def test_economic_analysis_metrics():
    r = run_economic_analysis({
        "annual_savings": 30000, "investment_cost": 350000, "years": 20,
    })
    assert {"payback_years", "discounted_payback_years", "npv_czk",
            "final_pv_gain_czk", "final_pv_reinvest_gain_czk",
            "final_sp500_net_czk"} == set(r["metrics"].keys())
    assert isinstance(r["plot"], str)

def test_economic_analysis_returns_investment_from_materials():
    """Investice se počítá ze snímku fve_materials, ne z tvrdých 350 000."""
    materials = [
        {"material_id": 1, "code": "PAN-550", "category": "panel",
         "rating": 550, "qty": 19, "unit_price": 2500.0, "line_total": 47500.0},
        {"material_id": 2, "code": "INV-10", "category": "inverter",
         "rating": 10, "qty": 1, "unit_price": 45000.0, "line_total": 45000.0},
    ]
    r = run_economic_analysis({
        "annual_savings": 25000.0, "fve_materials": materials, "years": 20,
    })
    assert r["investment_cost"] == 92500.0
    assert r["investment_breakdown"] == materials


def test_economic_analysis_legacy_investment_fallback():
    """Bez snímku (staré analýzy, explicitní zadání) platí fallback 350 000.

    Staré analýzy se záměrně nepřepočítávají — chování jako dřív.
    """
    r = run_economic_analysis({"annual_savings": 30000, "years": 20})
    assert r["investment_cost"] == 350000.0
    assert r["investment_breakdown"] == []


def test_production_performance_never_exceeds_100_pct():
    """Optimum hledá přes sklon a bere winter_loss → poměr ≤ 100 % (bod 4b)."""
    r = run_energy_analysis({"kwp": 10.0})
    pct = r["production_details"]["production_performance_pct"]
    assert pct <= 100.0 + 1e-6, f"production_performance_pct={pct}"
