import io
import base64
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from PIL import Image, ImageFilter, ImageDraw, ImageFont
import qrcode

NAVY = "#0b1f33"
GREEN = "#2fbf71"
ORANGE = "#f28e2b"
GRAY = "#566472"

def fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")

def plot_daily_consumption(complete_df):
    """
    complete_df: DataFrame with date, total_kwh, missing
    Returns base64 png
    """
    fig, ax = plt.subplots(figsize=(8, 3.2))
    if complete_df.empty:
        ax.text(0.5, 0.5, "Žádná data", ha="center")
        ax.axis("off")
        return fig_to_base64(fig)
    dates = complete_df["date"].astype(str)
    vals = complete_df["total_kwh"]
    ax.bar(range(len(vals)), vals, color=NAVY, width=0.7)
    # weekday/weekend averages
    weekday_avg = complete_df[complete_df["weekday"]]["total_kwh"].mean() if "weekday" in complete_df else vals.mean()
    weekend_avg = complete_df[~complete_df["weekday"]]["total_kwh"].mean() if "weekday" in complete_df else vals.mean()
    if not (vals.isna().all()):
        ax.axhline(weekday_avg, color=GREEN, linestyle="--", linewidth=1.2, label=f"Průměr pracovní den {weekday_avg:.1f} kWh")
        ax.axhline(weekend_avg, color=ORANGE, linestyle="--", linewidth=1.2, label=f"Průměr víkend {weekend_avg:.1f} kWh")
        ax.legend(fontsize=7, loc="upper right")
    ax.set_xticks(range(len(dates)))
    ax.set_xticklabels([d[5:] for d in dates], rotation=45, fontsize=7)
    ax.set_ylabel("kWh / den", fontsize=8)
    ax.set_title("Denní spotřeba — kompletní dny", fontsize=9, color=NAVY)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    return fig_to_base64(fig)

def plot_consumption_vs_production(hourly_df):
    fig, ax = plt.subplots(figsize=(8, 3.2))
    hours = hourly_df["hour"]
    cons = hourly_df["consumption_kwh"]
    prod = hourly_df["production_kwh"]
    ax.plot(hours, cons, color=NAVY, linewidth=1.8, marker="o", markersize=3, label="Model spotřeby, pracovní den")
    ax.plot(hours, prod, color=GREEN, linewidth=1.8, marker="o", markersize=3, label="Model výroby FVE")
    # fill
    ax.fill_between(hours, cons, prod, where=(prod > cons), color=GREEN, alpha=0.25, label="Zelená plocha")
    ax.fill_between(hours, cons, prod, where=(cons > prod), color="#fca5a5", alpha=0.4, label="Červená plocha")
    ax.set_xlabel("Hodina dne", fontsize=8)
    ax.set_ylabel("kWh = h", fontsize=8)
    ax.set_title("Spotřeba proti výrobě FVE", fontsize=9, color=NAVY)
    ax.set_xticks(range(0, 24, 2))
    ax.legend(fontsize=6, loc="upper left", ncol=2)
    fig.tight_layout()
    return fig_to_base64(fig)

def plot_battery(batt_15, batt_20):
    fig, ax = plt.subplots(figsize=(8, 3.2))
    hours = batt_15["hour"]
    ax.plot(hours, batt_15["soc_pct"], color=NAVY, linewidth=1.8, label="15 kWh")
    ax.plot(hours, batt_20["soc_pct"], color=GREEN, linewidth=1.8, label="20 kWh")
    ax.axhline(30, color="gray", linestyle="--", linewidth=1, label="30% rezerva")
    ax.set_ylim(0, 105)
    ax.set_xlabel("Hodina dne", fontsize=8)
    ax.set_ylabel("SoC %", fontsize=8)
    ax.set_title("Chování baterie (SoC)", fontsize=9, color=NAVY)
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig_to_base64(fig)

def generate_qr_base64(url: str) -> str:
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color=NAVY, back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def apply_watermark_to_pdf(pdf_bytes: bytes, text: str = "NÁVRH — KONFIDENCIÁLNÍ") -> bytes:
    """
    Apply diagonal watermark to each page using PyMuPDF if available, else reportlab fallback.
    If neither available, return original.
    """
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            rect = page.rect
            # Draw diagonal text
            page.draw_text = page.insert_text
            # Use red transparent
            page.insert_text(
                fitz.Point(rect.width * 0.15, rect.height * 0.5),
                text,
                fontsize=40,
                color=(0.9, 0.2, 0.2),
                rotate=30,
                overlay=True,
            )
            # Add transparent rect overlay? simple
        out = io.BytesIO()
        doc.save(out)
        return out.getvalue()
    except Exception:
        pass
    # Fallback: reportlab overlay
    try:
        from PyPDF2 import PdfReader, PdfWriter
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import landscape, A4
        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()
        # Create watermark page
        w, h = landscape(A4)  # approximate 842x595, close to 960x540
        # Use first page size
        if len(reader.pages) > 0:
            box = reader.pages[0].mediabox
            w = float(box.width)
            h = float(box.height)
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(w, h))
        c.setFillColorRGB(0.9, 0.2, 0.2, alpha=0.15)
        c.setFont("Helvetica-Bold", 48)
        c.saveState()
        c.translate(w/2, h/2)
        c.rotate(30)
        c.drawCentredString(0, 0, text)
        c.restoreState()
        c.save()
        buf.seek(0)
        watermark = PdfReader(buf).pages[0]
        for page in reader.pages:
            page.merge_page(watermark)
            writer.add_page(page)
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()
    except Exception:
        return pdf_bytes

def blur_image_base64(b64: str, radius: int = 12) -> str:
    data = base64.b64decode(b64)
    img = Image.open(io.BytesIO(data))
    blurred = img.filter(ImageFilter.GaussianBlur(radius))
    # Overlay text
    draw = ImageDraw.Draw(blurred, "RGBA")
    # Semi-transparent banner
    w, h = blurred.size
    # Try to load font, fallback
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    except:
        font = ImageFont.load_default()
    text = "Zpracováno — dostupné po připojení"
    # Draw rectangle
    draw.rectangle([(w*0.2, h*0.4), (w*0.8, h*0.6)], fill=(11, 31, 51, 200))
    # Center text
    bbox = draw.textbbox((0,0), text, font=font)
    tw = bbox[2]-bbox[0]
    th = bbox[3]-bbox[1]
    draw.text(((w-tw)/2, (h-th)/2), text, fill="white", font=font)
    buf = io.BytesIO()
    blurred.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")
