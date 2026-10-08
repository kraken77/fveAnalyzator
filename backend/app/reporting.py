import os
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
from datetime import datetime
import plotly.io as pio
import base64
import json
import pandas as pd
from .appliance_manager import ApplianceManager

class ReportGenerator:
    def __init__(self, templates_dir="templates"):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # directs to backend/
        self.templates_dir = os.path.join(base_dir, templates_dir)
        self.env = Environment(loader=FileSystemLoader(self.templates_dir))
        self.appliance_manager = ApplianceManager()

    def _format_czk(self, value):
        if value is None: return "-"
        return f"{value:,.0f} Kč".replace(",", " ")

    def _format_kwh(self, value):
        if value is None: return "-"
        return f"{value:,.0f}".replace(",", " ")
    
    def _format_number(self, value, decimal=2):
        if value is None: return "-"
        return f"{value:,.{decimal}f}".replace(",", " ")

    def _build_context(self, data, economic=None):
        """Postaví Jinja kontext pro energy_report.html.

        Oddělené od vykreslení (WeasyPrint), aby šel kontext testovat
        bez Chrome/kaleida — `plotly.io.to_image` se v testech mockuje.
        `economic` je volitelný; bez něj se ekonomická sekce i přílohy
        A–D vynechají (chování jako dřív).
        """
        plots_json = data.get("plots", {})
        charts_b64 = {}

        plot_mapping = {
            "monthly_stats": "monthly_stats",
            "energy_treemap": "energy_treemap",
            "savings_treemap": "savings_treemap",
            "energy_pie": "energy_pie",
            "savings_pie": "savings_pie",
        }
        for key, plot_id in plot_mapping.items():
            if plot_id in plots_json:
                try:
                    fig = pio.from_json(plots_json[plot_id])
                    fig.update_layout(template="plotly_white",
                                      width=800, height=450)
                    img_bytes = pio.to_image(fig, format="png")
                    charts_b64[key] = base64.b64encode(img_bytes).decode("utf-8")
                except Exception as e:
                    print(f"Error generating plot {key}: {e}")

        if economic and economic.get("plot"):
            try:
                fig = pio.from_json(economic["plot"])
                fig.update_layout(template="plotly_white", width=800, height=450)
                img_bytes = pio.to_image(fig, format="png")
                charts_b64["investment"] = base64.b64encode(img_bytes).decode("utf-8")
            except Exception as e:
                print(f"Error generating investment plot: {e}")

        context = {
            "generation_date": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "kwp": data.get("kwp", 0.0),
            "battery_capacity": data.get("battery_capacity", 0.0),
            "annual_consumption": data.get("annual_consumption_mwh", 0.0),
            "latitude": data.get("latitude", 50.6607),
            "longitude": data.get("longitude", 14.03227),

            "annual_savings_czk": self._format_czk(
                data.get("financial_balance", {}).get("annual_savings_czk")),
            "roi_years": self._format_number(
                data.get("investment_metrics", {}).get("roi_years"), 1),
            "self_consumption_kwh": self._format_kwh(
                data.get("energy_balance_kwh", {}).get("self_consumption")),
            "export_kwh": self._format_kwh(
                data.get("energy_balance_kwh", {}).get("grid_export")),

            "balance": {
                "total_consumption_kwh": self._format_kwh(
                    data.get("energy_balance_kwh", {}).get("total_consumption")),
                "total_cost_czk": self._format_czk(
                    data.get("economic_balance_czk", {}).get("cost_total_consumption")),
                "grid_import_kwh": self._format_kwh(
                    data.get("energy_balance_kwh", {}).get("grid_import")),
                "import_cost_czk": self._format_czk(
                    data.get("economic_balance_czk", {}).get("cost_import")),
                "grid_export_kwh": self._format_kwh(
                    data.get("energy_balance_kwh", {}).get("grid_export")),
                "export_revenue_czk": self._format_czk(
                    data.get("economic_balance_czk", {}).get("revenue_export")),
                "self_consumption_kwh": self._format_kwh(
                    data.get("energy_balance_kwh", {}).get("self_consumption")),
                "savings_self_ozk": self._format_czk(
                    data.get("economic_balance_czk", {}).get("savings_self_consumption")),
            },

            "appliance_metrics": [],
            "inflation_energy": data.get("investment_context", {}).get(
                "energy_inflation_rate", 2.0),
            "degradation": data.get("investment_context", {}).get(
                "panel_degradation_rate", 0.5),

            "chart_monthly_stats": charts_b64.get("monthly_stats"),
            "chart_energy_treemap": charts_b64.get("energy_treemap"),
            "chart_savings_treemap": charts_b64.get("savings_treemap"),
            "chart_energy_pie": charts_b64.get("energy_pie"),
            "chart_savings_pie": charts_b64.get("savings_pie"),
            "chart_investment": charts_b64.get("investment"),
            "recommendations": data.get("recommendations", []),
            "monthly_summary": data.get("monthly_summary", []),
            "appliance_monthly_summary": data.get("appliance_monthly_summary", []),
        }

        # Process Appliance Metrics
        if "appliance_metrics" in data:
            for name, metrics in data["appliance_metrics"].items():
                total = metrics.get("total_kWh", 0)
                fve = metrics.get("fve_kWh", 0)
                grid = metrics.get("grid_kWh", 0)
                grid_cost = metrics.get("grid_cost_czk", 0)
                hours = metrics.get("operating_hours", 0)
                coverage = (fve / total * 100) if total > 0 else 0
                profile = self.appliance_manager.get_appliance_profile(name)
                description = profile.get("description", "") if profile else ""

                context["appliance_metrics"].append({
                    "name": name,
                    "description": description,
                    "total_kwh": self._format_kwh(total),
                    "fve_kwh": self._format_kwh(fve),
                    "grid_kwh": self._format_kwh(grid),
                    "grid_cost_czk": self._format_czk(grid_cost),
                    "operating_hours": hours,
                    "coverage_pct": self._format_number(coverage, 1),
                    "savings_czk": self._format_czk(metrics.get("savings_czk")),
                })

        # Appliance Definitions / Configuration Details
        appliance_definitions = []
        if "appliance_metrics" in data:
            active_apps = [k for k in data["appliance_metrics"].keys()
                           if k not in ["Základní chod", "CELKEM"]]
            for app in sorted(active_apps):
                profile = self.appliance_manager.get_appliance_profile(app)
                if profile:
                    logic_desc = profile.get("description", "")
                    if profile.get("seasonal", False):
                        logic_desc += f" (Sezónní: {profile.get('seasonal_months', [])})"
                    if profile.get("type") == "EV":
                        logic_desc += (f" | Strategie: {profile.get('charging_strategy', 'weekly')}"
                                       f" | Nabití: {profile.get('charge_kwh', 0)} kWh")
                    elif "daily_hours" in profile:
                        logic_desc += f" | Provoz: {profile['daily_hours']} h/den"

                    appliance_definitions.append({
                        "name": app,
                        "power": f"{profile.get('power_kW', 0)} kW",
                        "type": profile.get("type", "Standard"),
                        "description": logic_desc,
                    })
        context["appliance_definitions"] = appliance_definitions

        # Ekonomická část (nepovinná)
        econ = economic or {}
        metrics = econ.get("metrics", {})
        context["economic"] = economic
        context["investment_cost_czk"] = self._format_czk(econ.get("investment_cost"))
        context["econ_payback"] = metrics.get("payback_years")
        context["econ_dpp"] = metrics.get("discounted_payback_years")
        context["econ_npv"] = self._format_czk(metrics.get("npv_czk"))
        context["econ_final_pv_gain"] = self._format_czk(metrics.get("final_pv_gain_czk"))
        context["econ_final_pv_reinvest_gain"] = self._format_czk(
            metrics.get("final_pv_reinvest_gain_czk"))
        context["econ_final_sp500_net"] = self._format_czk(
            metrics.get("final_sp500_net_czk"))
        context["investment_breakdown"] = [
            {
                "name": row.get("name") or row.get("code") or "-",
                "rating": (self._format_number(row.get("rating"), 0)
                           if row.get("rating") is not None else "-"),
                "qty": (self._format_number(row.get("qty"), 0)
                        if row.get("qty") is not None else "-"),
                "unit_price": self._format_czk(row.get("unit_price")),
                "line_total": self._format_czk(row.get("line_total")),
            }
            for row in (econ.get("investment_breakdown") or [])
        ]
        context["economic_year_rows"] = [
            {
                "year": row.get("Year"),
                "pv_cumulative_cashflow": self._format_czk(
                    row.get("PV_Cumulative_CashFlow")),
                "pv_reinvest_net_result": self._format_czk(
                    row.get("PV_Reinvest_Net_Result")),
                "pv_cumulative_dcf": self._format_czk(row.get("PV_Cumulative_DCF")),
                "sp500_total_value": self._format_czk(row.get("SP500_Total_Value")),
                "sp500_net_result": self._format_czk(row.get("SP500_Net_Result")),
            }
            for row in (econ.get("raw_data") or [])
        ]
        return context

    def generate_energy_report(self, data, economic=None):
        """Generuje PDF energetické (+ ekonomické) analýzy.

        `economic` je volitelný — bez něj se vynechá sekce Ekonomická
        analýza i Přílohy A–D (chování jako dřív).
        """
        context = self._build_context(data, economic)
        template = self.env.get_template("energy_report.html")
        html_content = template.render(context)
        pdf_bytes = HTML(string=html_content).write_pdf()
        return pdf_bytes

    def generate_economic_report(self, data):
        """
        Generates PDF for Economic analysis only.
        """
        template = self.env.get_template("economic_report.html")
        
        # Plot optimization
        chart_b64 = None
        if "plot" in data:
             try:
                fig = pio.from_json(data["plot"])
                fig.update_layout(template="plotly_white", width=800, height=450)
                img_bytes = pio.to_image(fig, format="png")
                chart_b64 = base64.b64encode(img_bytes).decode('utf-8')
             except Exception as e:
                print(f"Error generating investment plot: {e}")

        # Metrics and Table formatting
        metrics = data.get("metrics", {})
        raw_data = data.get("raw_data", [])
        formatted_raw_data = []
        for row in raw_data:
            formatted_raw_data.append({
                "Year": row.get("Year"),
                "PV_Cumulative_CashFlow": self._format_czk(row.get("PV_Cumulative_CashFlow")),
                "PV_Reinvest_Net_Result": self._format_czk(row.get("PV_Reinvest_Net_Result")),
                "SP500_Gross_Gain": self._format_czk(row.get("SP500_Gross_Gain")),
                "SP500_Net_Result": self._format_czk(row.get("SP500_Net_Result")),
                "SP500_Total_Value": self._format_czk(row.get("SP500_Total_Value"))
            })

        context = {
            "generation_date": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "investment_cost": self._format_czk(data.get("investment_cost")),
            "annual_savings": self._format_czk(data.get("annual_savings")),
            "years": data.get("years"),
            "sp500_return": data.get("sp500_return"),
            "inflation": data.get("inflation"),
            "discount_rate": data.get("discount_rate"),
            "payback_years": metrics.get("payback_years"),
            "discounted_payback_years": metrics.get("discounted_payback_years"),
            "npv": self._format_czk(metrics.get("npv_czk")),
            "final_pv_gain": self._format_czk(metrics.get("final_pv_gain_czk")),
            "final_pv_reinvest_gain": self._format_czk(metrics.get("final_pv_reinvest_gain_czk")),
            "final_sp500_net": self._format_czk(metrics.get("final_sp500_net_czk")),
            "chart_investment": chart_b64,
            "raw_data": formatted_raw_data
        }
        
        html_content = template.render(context)
        pdf_bytes = HTML(string=html_content).write_pdf()
        return pdf_bytes

    def generate_ote_report(self, data):
        """
        Generates PDF for OTE analysis.
        """
        template = self.env.get_template("ote_report.html")
        
        monthly_data_formatted = []
        for row in data.get("monthly_data", []):
            monthly_data_formatted.append({
                "month": row.get("month_name"),
                "production_kwh": self._format_kwh(row.get("production_kwh")),
                "revenue_spot": self._format_czk(row.get("revenue_spot_czk")),
                "avg_price": self._format_czk(row.get("avg_price_czk_mwh")),
                "revenue_fix": self._format_czk(row.get("revenue_fixed_czk"))
            })
            
        spot_total = data.get("total_revenue_spot", 0)
        fix_total = data.get("total_revenue_fixed", 0)
        diff = spot_total - fix_total
        
        context = {
            "generation_date": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "year": data.get("year", 2024),
            "margin": self._format_number(data.get("margin", 0.4)),
            "fixed_price": self._format_number(data.get("fixed_price", 2.5)),
            
            "total_spot_czk": self._format_czk(spot_total),
            "total_fix_czk": self._format_czk(fix_total),
            "diff_czk": self._format_czk(diff),
            "diff_val": diff,
            
            "monthly_data": monthly_data_formatted
        }
        
        html_content = template.render(context)
        pdf_bytes = HTML(string=html_content).write_pdf()
        return pdf_bytes
