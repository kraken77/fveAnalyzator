import os
import base64
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
from .antelon import antelon_analyze
from .pdf_utils import plot_daily_consumption, plot_consumption_vs_production, plot_battery

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates_antelon")

DEFAULT_TEXTS = {
    "cover_title": "Pentagon",
    "cover_subtitle": "Návrh fotovoltaické elektrárny a bateriového úložiště",
    "cover_note": "Zpracováno z dat Shelly datalogeru | zákaznický podklad pro rozhodnutí",
    "cover_footer_note": "Výstup obsahuje i model porovnání spotřeby s výrobou FVE a ukázku, kdy pomáhá baterie.",
    "s1_title": "1. Shrnutí výsledků z dat",
    "s1_sub": "Základní vyhodnocení pro nabídku FVE",
    "s1_bullets": "• Objekt má typický administrativní profil: výrazně vyšší odběr v pracovních dnech.\n• Velikost FVE je vhodné volit podle denní vlastní spotřeby, ne pouze podle ročního součtu.\n• Doporučené řešení je FVE {kwp} kWp s baterií {battery} kWh.",
    "s2_title": "2. Pracovní den vs víkend",
    "s2_sub": "Administrativní objekt má vysoký potenciál přímé vlastní spotřeby přes den",
    "s2_conclusion_title": "Závěr pro návrh FVE",
    "s2_conclusion": "• Doporučená FVE {kwp} kWp dobře pokrývá denní pracovní spotřebu.\n• V létě bude vznikat přebytek hlavně v poledních hodinách a o víkendech.\n• Baterie má dávat smysl ekonomicky: nemá být příliš velká, ale má zachytit denní přebytky a večerní/noční odběr.",
    "s3_title": "3. Fázové zatížení",
    "s3_sub": "Důležité pro kontrolu zapojení a rozdělení jednofázových okruhů",
    "s4_title": "4. Doporučené řešení k nabídce",
    "s4_sub": "Návrh bez preferování značek — pouze výkon a kapacita",
    "s5_title": "5. Spotřeba proti výrobě FVE",
    "s5_sub": "Model typického pracovního dne pro doporučenou variantu {kwp} kWp",
    "s5b_title": "5b. Objem zelené a červené plochy",
    "s6_title": "6. Odchylka výroby a spotřeby",
    "s7_title": "7. Chování baterie",
    "s8_title": "8. Porovnání variant FVE",
    "s9_title": "9. Doporučení a další postup",
}

def _fill(text: str, ctx: dict):
    try:
        return text.format(**ctx)
    except:
        return text

def generate_antelon_pdf(analysis: dict, project, antelon_params: dict, visibility: dict = None):
    """
    analysis: from antelon_analyze
    project: Project ORM
    antelon_params: dict with overrides (title, texts, variants, etc.)
    visibility: dict section_id -> full|teaser|internal
    """
    kpi = analysis["kpi"]
    phase = analysis["phase_pct"]
    hourly = analysis["hourly"]
    green_red = analysis["green_red"]
    # Merge params
    ctx_params = {
        "kwp": analysis["params"]["kwp"],
        "battery": analysis["params"]["battery_kwh"],
        "soc_min": analysis["params"]["soc_min"],
    }
    # Texts with defaults + overrides
    texts = {**DEFAULT_TEXTS}
    if antelon_params:
        for k, v in antelon_params.get("texts", {}).items():
            if v:
                texts[k] = v
        # also allow top-level overrides
        for k in ["cover_title", "cover_subtitle"]:
            if antelon_params.get(k):
                texts[k] = antelon_params[k]

    # Fill placeholders
    filled = {k: _fill(v, ctx_params) for k, v in texts.items()}

    # Plots
    try:
        plot_daily_b64 = plot_daily_consumption(kpi["complete_df"])
    except Exception as e:
        plot_daily_b64 = ""
    try:
        plot_prod_b64 = plot_consumption_vs_production(hourly)
    except Exception as e:
        plot_prod_b64 = ""
    try:
        plot_batt_b64 = plot_battery(analysis["battery_15"], analysis["battery_20"])
    except Exception as e:
        plot_batt_b64 = ""

    # Prepare context for Jinja
    context = {
        "project": project,
        "customer_name": project.customer_name or "—",
        "kpi": kpi,
        "phase": phase,
        "green_red": green_red,
        "hourly": hourly,
        "variants": analysis["variants"],
        "params": analysis["params"],
        "texts": filled,
        "plot_daily": plot_daily_b64,
        "plot_prod": plot_prod_b64,
        "plot_batt": plot_batt_b64,
        "warnings": analysis.get("warnings", []),
        "gaps": analysis.get("gaps", []),
        "complete_days": analysis.get("complete_days", []),
        "visibility": visibility or {},
        # Formatted
        "fmt_total": f"{kpi['total_kwh']:.0f}",
        "fmt_avg": f"{kpi['avg_daily']:.1f}",
        "fmt_annual": f"{kpi['annual_mwh']:.1f}",
        "fmt_weekday": f"{kpi['weekday_avg']:.1f}",
        "fmt_weekend": f"{kpi['weekend_avg']:.1f}",
        "fmt_green": f"{green_red['green_kwh']:.1f}",
        "fmt_red": f"{green_red['red_kwh']:.1f}",
        "fmt_prod": f"{green_red['prod_total']:.1f}",
    }

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    template = env.get_template("report.html")
    html_str = template.render(**context)

    pdf_bytes = HTML(string=html_str, base_url=TEMPLATE_DIR).write_pdf()
    return pdf_bytes
