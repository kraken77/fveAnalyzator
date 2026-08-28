import base64
import io
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
import plotly.io as pio
import datetime

def generate_pdf_report(financials, energy_balance, investment_data, input_params, figures_dict, dataframes_dict, template_path="src/templates"):
    """
    Generates a PDF report from the provided data and figures.
    
    Args:
        financials (dict): Dictionary containing financial metrics.
        energy_balance (dict): Dictionary containing energy balance metrics.
        investment_data (dict): Dictionary containing investment metrics.
        input_params (dict): Dictionary containing input parameters (kwp, battery, etc.).
        figures_dict (dict): Dictionary of Plotly figures.
        dataframes_dict (dict): Dictionary of pandas DataFrames.
        template_path (str): Path to the directory containing templates.
        
    Returns:
        bytes: The generated PDF content.
    """
    
    # 1. Convert Figures to Base64 Images
    images_b64 = {}
    for name, fig in figures_dict.items():
        # Update layout for print (white background)
        fig.update_layout(template="plotly_white")
        # Convert to static image (png)
        img_bytes = pio.to_image(fig, format="png", width=800, height=500, scale=2)
        # Encode to base64
        img_b64 = base64.b64encode(img_bytes).decode('utf-8')
        images_b64[name] = img_b64
        
    # 2. Convert DataFrames to HTML
    tables_html = {}
    for name, df in dataframes_dict.items():
        tables_html[name] = df.to_html(classes='table', index=False, border=0)

    # 3. Prepare Context for Template
    context = {
        "generation_date": datetime.datetime.now().strftime("%d.%m.%Y %H:%M"),
        "params": input_params,
        
        # Financials
        "savings_czk": f"{financials['savings_czk']:,.2f} Kč".replace(",", " ").replace(".", ","),
        "payback_years": financials.get('payback_years', 'N/A'),
        
        # Energy Balance
        "total_consumption_kwh": f"{energy_balance['total_consumption_kwh']:,.0f} kWh".replace(",", " "),
        "total_production_kwh": f"{energy_balance['total_production_kwh']:,.0f} kWh".replace(",", " "),
        "self_consumption_kwh": f"{energy_balance['self_consumption_kwh']:,.0f} kWh".replace(",", " "),
        "total_import_kwh": f"{energy_balance['total_import_kwh']:,.0f} kWh".replace(",", " "),
        "total_export_kwh": f"{energy_balance['total_export_kwh']:,.0f} kWh".replace(",", " "),
        
        # Investment
        "investment_cost": f"{investment_data['investment_cost']:,.0f} Kč".replace(",", " "),
        "final_pv_gain": f"{investment_data['final_pv_gain']:,.0f} Kč".replace(",", " "),
        "final_sp500_net": f"{investment_data['final_sp500_net']:,.0f} Kč".replace(",", " "),
        
        # Images
        "chart_savings_pie": images_b64.get('savings_pie', ''),
        "chart_savings_treemap": images_b64.get('savings_treemap', ''),
        "chart_energy_pie": images_b64.get('energy_pie', ''),
        "chart_energy_treemap": images_b64.get('energy_treemap', ''),
        "chart_monthly_stats": images_b64.get('monthly_stats', ''),
        "chart_daily": images_b64.get('daily_chart', ''),
        "chart_investment": images_b64.get('investment_chart', ''),
        
        # Tables
        "table_energy_data": tables_html.get('energy_data', ''),
        "table_investment_data": tables_html.get('investment_data', '')
    }
    
    # 4. Render HTML Template
    env = Environment(loader=FileSystemLoader(template_path))
    template = env.get_template("report.html")
    html_content = template.render(context)
    
    # 5. Convert to PDF
    pdf_bytes = HTML(string=html_content).write_pdf()
    
    return pdf_bytes
