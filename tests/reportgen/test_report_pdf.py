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


def _render(data, economic=None):
    """Postaví kontext a vyrenderuje šablonu — bez WeasyPrint."""
    gen = ReportGenerator()
    with patch("app.reporting.pio.to_image", return_value=b"PNG"):
        ctx = gen._build_context(data, economic)
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
