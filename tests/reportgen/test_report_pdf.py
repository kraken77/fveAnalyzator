"""reporting.py — kontext PDF bez Chrome a bez WeasyPrint.

Host venv nemá Chrome, takže `plotly.io.to_image` (kaleido) se mockuje.
Pracuje se rovnou s Jinja kontextem / renderem šablony — WeasyPrint se
použije jen v testu odolnosti na konci souboru.
"""
import logging
import sys
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "backend") not in sys.path:
    sys.path.insert(0, str(REPO / "backend"))

from app.reporting import ReportGenerator  # noqa: E402


def _energy_data():
    return {
        "kwp": 10.0,
        "battery_capacity": 10.0,
        "annual_consumption_mwh": 5.0,
        "latitude": 50.6607,
        "longitude": 14.03227,
        "financial_balance": {
            "annual_savings_czk": 25000.0,
            "cost_without_pv_czk": 35000.0,
            "cost_with_pv_czk": 10000.0,
        },
        "energy_balance_kwh": {
            "total_consumption": 5000.0,
            "grid_import": 3000.0,
            "grid_export": 2000.0,
            "self_consumption": 2000.0,
        },
        "economic_balance_czk": {
            "cost_total_consumption": 35000.0,
            "cost_import": 21000.0,
            "revenue_export": 5000.0,
            "savings_self_consumption": 10000.0,
        },
        "plots": {key: "{}" for key in (
            "monthly_stats", "energy_treemap", "savings_treemap",
            "energy_pie", "savings_pie")},
        "recommendations": ["**Zvažte baterii**"],
        "appliance_metrics": {},
        "appliance_monthly_summary": [],
        "monthly_summary": [],
        "raw_data": [],
    }


def _economic():
    """Tvar odpovědi run_economic_analysis (Task 2) — včetně investice."""
    return {
        "metrics": {
            "payback_years": 8,
            "discounted_payback_years": 11,
            "npv_czk": 100000.0,
            "final_pv_gain_czk": 200000.0,
            "final_pv_reinvest_gain_czk": 250000.0,
            "final_sp500_net_czk": 150000.0,
        },
        "investment_cost": 300000.0,
        "investment_breakdown": [
            {"material_id": 1, "code": "PAN-550", "name": "Panel 550 Wp",
             "category": "panel", "rating": 550, "qty": 19,
             "unit_price": 2500.0, "line_total": 47500.0},
        ],
        "plot": "{}",
        "raw_data": [
            {"Year": 0, "PV_Cumulative_CashFlow": -300000.0,
             "PV_Reinvest_Net_Result": -300000.0, "PV_Cumulative_DCF": -300000.0,
             "SP500_Total_Value": 300000.0, "SP500_Net_Result": 0.0},
            {"Year": 1, "PV_Cumulative_CashFlow": -275000.0,
             "PV_Reinvest_Net_Result": -275000.0, "PV_Cumulative_DCF": -274000.0,
             "SP500_Total_Value": 324000.0, "SP500_Net_Result": 24000.0},
        ],
    }


def test_context_without_economic_has_no_economic_keys():
    """Bez ekonomiky se sekce i přílohy vynechají (chování jako dřív)."""
    ctx = ReportGenerator()._build_context(_energy_data())
    assert ctx["economic"] is None
    assert ctx["investment_cost_czk"] == "-"
    assert ctx["economic_year_rows"] == []
    assert ctx["investment_breakdown"] == []


def test_context_includes_investment_and_years():
    ctx = ReportGenerator()._build_context(_energy_data(), _economic())
    assert ctx["economic"] is not None
    assert ctx["investment_cost_czk"] == "300 000 Kč"
    assert ctx["econ_payback"] == 8
    assert ctx["investment_breakdown"][0]["name"] == "Panel 550 Wp"
    assert ctx["investment_breakdown"][0]["line_total"] == "47 500 Kč"
    assert len(ctx["economic_year_rows"]) == 2
    assert ctx["economic_year_rows"][1]["pv_cumulative_dcf"] != "-"


def test_all_six_charts_reach_context():
    """5 grafů z data["plots"] + investiční z economic["plot"]."""
    with patch("app.reporting.pio.to_image", return_value=b"PNG"):
        ctx = ReportGenerator()._build_context(_energy_data(), _economic())
    for key in ("chart_monthly_stats", "chart_energy_treemap",
                "chart_savings_treemap", "chart_energy_pie",
                "chart_savings_pie", "chart_investment"):
        assert ctx[key], f"graf {key} se do kontextu nedostal"


def test_breakdown_tolerates_missing_name_and_rating():
    """Snímek nemusí mít name/rating — tabulka se nesmí zhroutit."""
    eco = _economic()
    eco["investment_breakdown"] = [
        {"code": "INS-MONT", "category": "install", "qty": 1,
         "unit_price": 120000.0, "line_total": 120000.0},
    ]
    ctx = ReportGenerator()._build_context(_energy_data(), eco)
    row = ctx["investment_breakdown"][0]
    assert row["name"] == "INS-MONT"  # fallback na code
    assert row["rating"] == "-"
    assert row["qty"] == "1"


def test_report_survives_chart_failure():
    """Když to_image spadne, PDF se stejně vygeneruje (bez grafů)."""
    with patch("app.reporting.pio.to_image",
               side_effect=RuntimeError("no chrome")):
        pdf = ReportGenerator().generate_energy_report(_energy_data())
    assert pdf[:4] == b"%PDF"


def _render(data, economic=None, sections=None, variant="company", params=None):
    """Postaví kontext a vyrenderuje šablonu — bez WeasyPrint."""
    gen = ReportGenerator()
    with patch("app.reporting.pio.to_image", return_value=b"PNG"):
        ctx = gen._build_context(data, economic, variant, sections, params)
    return gen.env.get_template("energy_report.html").render(ctx)


def test_template_has_economic_section_and_appendices_when_economic():
    html = _render(_energy_data(), _economic())
    for text in ("Ekonomická analýza", "Příloha A", "Příloha B",
                 "Příloha C", "Příloha D", "Ekonomický plán",
                 "Složení investice", "300 000 Kč", "Panel 550 Wp"):
        assert text in html, f"v PDF chybí: {text}"


def test_template_omits_economic_section_without_economic():
    html = _render(_energy_data(), None)
    for text in ("Ekonomická analýza", "Příloha A", "Příloha B",
                 "Příloha C", "Příloha D"):
        assert text not in html, f"bez ekonomiky nemá být v PDF: {text}"


def test_appendix_headings_break_to_new_page():
    """Přílohy musí začínat na vlastní stránce (WeasyPrint break-before)."""
    html = _render(_energy_data(), _economic())
    assert html.count("break-before: page") >= 4


def test_chart_failure_is_logged_with_type(caplog):
    """Chyba grafu musí být v logu s typem výjimky, ne prázdná hláška.

    Před opravou se logovalo přes `print(f"...: {e}")`, a když `str(e)`
    začínalo dvěma `\n`, v logu zůstala prázdná hláška.
    """
    with patch("app.reporting.pio.to_image",
               side_effect=RuntimeError("no chrome")):
        with caplog.at_level(logging.ERROR):
            ReportGenerator().generate_energy_report(_energy_data())
    assert "RuntimeError" in caplog.text


def test_input_params_rows_cover_all_meaningful_inputs():
    params = {
        "kwp": 10.0, "battery_capacity": 10.0, "annual_consumption_mwh": 5.0,
        "latitude": 50.6607, "longitude": 14.03227,
        "price_power": 3.0, "price_distribution": 2.0,
        "sell_price_scheme": "shared", "price_sell": 2.0,
        "shared_sell_price": 2.54, "spot_price_margin": 0.4,
        "surface_tilt": 35, "surface_azimuth": 180,
        "grid_export_limit_kw": 10.0, "system_loss_factor": 14.0,
        "winter_loss_factor": 10.0, "thermal_battery_capacity_kwh": 0.0,
        "thermal_battery_charge_power_kw": 2.0, "active_appliances": ["Bazén"],
        "bom_mode": "components", "panel_material_id": 1,
    }
    rows = ReportGenerator()._build_input_params(params)
    labels = {r["label"]: r["value"] for r in rows}
    assert "Cena silové energie" in labels
    assert "Cena distribuce" in labels
    assert labels["Schéma prodeje"] == "Sdílení"
    assert "2.54" in labels["Výkupní cena (sdílení)"]
    assert labels["Sklon střechy"] == "35°"
    assert labels["Limit exportu do sítě"] == "10.0 kW"
    assert labels["Aktivní spotřebiče"] == "Bazén"
    # interní/technické se neuvádí
    assert "bom_mode" not in " ".join(labels)
    assert all("material_id" not in lbl for lbl in labels)


def test_input_params_empty_params_use_backend_defaults():
    rows = ReportGenerator()._build_input_params(None)
    labels = {r["label"]: r["value"] for r in rows}
    assert labels["Instalovaný výkon"] == "10.0 kWp"
    assert labels["Výkupní cena"] == "2.00 Kč/kWh"  # default scheme=fixed, price_sell=2.0


def test_input_params_null_export_limit_means_no_limit():
    rows = ReportGenerator()._build_input_params({"grid_export_limit_kw": None})
    labels = {r["label"]: r["value"] for r in rows}
    assert labels["Limit exportu do sítě"] == "bez limitu"


def test_context_default_sections_full_report():
    ctx = ReportGenerator()._build_context(_energy_data(), _economic())
    assert ctx["variant"] == "company"
    assert ctx["variant_label"] == "interní"
    assert "economic_metrics" in ctx["sections"]
    assert "investment_composition" in ctx["sections"]
    assert ctx["sections"][0] == "intro"
    assert ctx["sections"][-1] == "glossary"


def test_context_customer_variant_summary_and_label():
    ctx = ReportGenerator()._build_context(
        _energy_data(), _economic(), variant="customer")
    assert ctx["variant_label"] == "nabídka pro zákazníka"
    assert "FVE 10.0 kWp" in ctx["investment_summary_text"]
    assert "10.0 kWh" in ctx["investment_summary_text"]
    # detailní rozpis zůstává v kontextu (šablona ho pro zákazníka nepoužije)
    assert ctx["investment_breakdown"][0]["name"] == "Panel 550 Wp"


def test_context_subset_and_order():
    ctx = ReportGenerator()._build_context(
        _energy_data(), _economic(),
        sections=["intro", "summary", "recommendations",
                  "economic_metrics", "investment_composition", "glossary"])
    assert ctx["sections"] == ["intro", "summary", "recommendations",
                               "economic_metrics", "investment_composition", "glossary"]


def test_context_drops_economic_sections_without_economic():
    ctx = ReportGenerator()._build_context(_energy_data(), None, sections=None)
    assert "economic_metrics" not in ctx["sections"]
    assert "investment_composition" not in ctx["sections"]
    assert ctx["sections"][0] == "intro"


def test_context_input_params_rows_present():
    ctx = ReportGenerator()._build_context(
        _energy_data(), _economic(),
        params={"price_power": 4.5, "sell_price_scheme": "fixed"})
    labels = {r["label"]: r["value"] for r in ctx["input_params_rows"]}
    assert labels["Cena silové energie"] == "4.50 Kč/kWh"


def test_render_respects_sections_subset_and_order():
    html = _render(_energy_data(), _economic(), sections=[
        "intro", "summary", "recommendations",
        "economic_metrics", "investment_composition", "glossary"])
    assert "Doporučené strategie" in html
    # vynechaný oddíl v PDF není
    assert "Měsíční Bilance" not in html
    assert "Příloha A" not in html
    # pořadí: Doporučení před Ekonomickou analýzou
    assert html.index("Doporučené strategie") < html.index("Ekonomická analýza")


def test_render_reorder_moves_section():
    html = _render(_energy_data(), _economic(), sections=[
        "intro", "summary", "energy_balance", "monthly_stats",
        "economic_metrics", "investment_composition", "glossary"])
    assert html.index("Energetická Bilance") < html.index("Měsíční Statistika")


def test_render_has_intro_captions_and_glossary():
    html = _render(_energy_data(), _economic(), params={"price_power": 3.0})
    assert "Jak číst tento report" in html
    assert "Slovníček pojmů" in html
    assert "NPV" in html  # slovníček
    assert "Cena silové energie" in html  # tabulka vstupů


def test_input_params_section_uses_rows_not_hardcoded():
    html = _render(_energy_data(), _economic(), params={"price_power": 7.77})
    assert "7.77 Kč/kWh" in html


def test_customer_variant_shows_aggregate_not_breakdown():
    html = _render(_energy_data(), _economic(), variant="customer")
    assert "FVE 10.0 kWp + baterie 10.0 kWh" in html
    assert "300 000 Kč" in html
    assert "Panel 550 Wp" not in html   # žádný rozpis komponent
    assert "Cena/ks" not in html


def test_company_variant_shows_breakdown():
    html = _render(_energy_data(), _economic(), variant="company")
    assert "Panel 550 Wp" in html
    assert "Cena/ks" in html





