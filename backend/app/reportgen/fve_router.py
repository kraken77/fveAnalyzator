"""API pro fveAnalysis — energetická a ekonomická analýza jako první krok zakázky.

Oddělený router, protože router.py už má 700+ řádků a fveAnalysis je
samostatná funkční oblast.

Výpočet deleguje do app.fve_analysis — tady je jen auth, validace a DB.
"""
import json
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from .auth import (
    can_access_project,
    get_current_user,
    hash_password,
    is_internal_user,
    require_roles,
)
from .storage import (
    Project,
    ProjectStep,
    ProjectUser,
    PipelineStep,
    User,
    generate_share_code,
    get_db,
)

router = APIRouter(prefix="/api/v1", tags=["fve-analysis"])

# Analýzu smí spočítat i zákazník — je to nástroj, ne interní proces.
ANY_ROLE = require_roles("admin", "antelon", "customer")


class FveParams(BaseModel):
    """Parametry analýzy. Všechny mají default, takže klient může poslat
    jen to, co uživatel změnil."""

    kwp: float = Field(default=10.0, ge=0.1, le=50.0)
    battery_capacity: float = Field(default=10.0, ge=0.0, le=100.0)
    annual_consumption_mwh: float = Field(default=5.0, ge=0.1, le=100.0)
    price_power: float = Field(default=3.0, ge=0.0)
    price_distribution: float = Field(default=2.0, ge=0.0)
    price_sell: float = Field(default=2.0, ge=0.0)
    sell_price_scheme: str = "fixed"  # fixed | community | shared | spot
    community_sell_price: float = 1.5
    shared_sell_price: float = 2.54
    spot_price_margin: float = 0.4
    latitude: float = Field(default=50.0880, ge=-90.0, le=90.0)
    longitude: float = Field(default=14.4208, ge=-180.0, le=180.0)
    surface_tilt: int = Field(default=35, ge=0, le=90)
    surface_azimuth: int = Field(default=180, ge=0, le=359)
    grid_export_limit_kw: float | None = 10.0
    system_loss_factor: float = Field(default=14.0, ge=0.0, le=50.0)
    winter_loss_factor: float = Field(default=10.0, ge=0.0, le=100.0)
    thermal_battery_capacity_kwh: float = 0.0
    thermal_battery_charge_power_kw: float = 2.0
    active_appliances: list[str] = []  # názvy, ne dict jako u Streamlitu

    @field_validator("sell_price_scheme")
    @classmethod
    def _valid_scheme(cls, v: str) -> str:
        if v not in ("fixed", "community", "shared", "spot"):
            raise ValueError(f"Neznámé schéma prodeje: {v}")
        return v

    def to_analysis_params(self) -> dict:
        """Převod na tvar, jaký čeká app.fve_analysis.

        active_appliances (list) → active_appliances_data (dict), protože
        tak to posílá i legacy Streamlit a tak to bere ApplianceManager.
        """
        d = self.model_dump()
        names = d.pop("active_appliances")
        d["active_appliances_data"] = {n: {} for n in names}
        return d


class Contact(BaseModel):
    """Kontakt je povinný vždy — bez něj nemá analýza v pipeline smysl."""

    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    # Bez min_length: „+420 777 123 456" má 16 znaků, ale „777123456"
    # má jen 9 a je platný. min_length=9 by odmítl "+42077712" (11 znaků,
    # 8 číslic) — a naopak by pustil "         " (9 mezer). Počítáme
    # číslice, ne znaky.
    phone: str = Field(max_length=40)

    @field_validator("phone")
    @classmethod
    def _phone_has_digits(cls, v: str) -> str:
        if len([c for c in v if c.isdigit()]) < 9:
            raise ValueError("Telefon musí obsahovat alespoň 9 číslic")
        return v


class SaveAnalysisIn(BaseModel):
    params: FveParams
    contact: Contact
    name: str | None = None  # název projektu; jinak se odvodí z kontaktu


@router.post("/fve-analysis/run")
def run_analysis(params: FveParams, user: User = Depends(ANY_ROLE)):
    """Spustí analýzu. Bez uložení — jen výsledky.

    Dostupné pro zákazníka: analýzu si smí spočítat sám, uložení
    je jiný krok (POST /fve-analysis).
    """
    from app.fve_analysis import run_energy_analysis

    try:
        return run_energy_analysis(params.to_analysis_params())
    except ValueError as e:
        # PVGIS nedohaloval meteorologická data pro zadané souřadnice
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/fve-analysis/geocode")
def geocode(payload: dict, user: User = Depends(ANY_ROLE)):
    """Geokódování obce nebo města.

    Záměrně *název obce*, ne adresa: Open-Meteo geocoding je name search.
    "Praha" najde, "Praha 1" nebo "Vodičkova 5" ne. UI to musí vysvětlit
    místo, ne vracet tichou chybu, jinak uživatel neví proč adresa nenašla.
    """
    address = (payload or {}).get("address", "").strip()
    if not address:
        raise HTTPException(400, "Zadejte název obce")
    from app.geocoder import get_coordinates

    result = get_coordinates(address)
    if not result:
        raise HTTPException(
            404,
            f"Nebylo nalezeno žádné místo pro „{address}“. Zkuste název obce nebo města.",
        )
    # get_coordinates vrací lat/lon; FveParams má latitude/longitude —
    # přejmenovat tady, ne aby si frontend pamatoval dvě podoby.
    return {
        "latitude": result["lat"],
        "longitude": result["lon"],
        "display_name": result.get("display_name", ""),
    }


@router.get("/fve-analysis/appliances")
def list_appliances(user: User = Depends(ANY_ROLE)):
    """Katalog spotřebičů — UI si ho načte, nehardcoduje."""
    from app.fve_analysis import appliance_catalog

    return {"appliances": appliance_catalog()}


@router.post("/fve-analysis/economic")
def run_economic(params: dict, user: User = Depends(ANY_ROLE)):
    """Ekonomická analýza návratnosti (investice vs S&P500 vs reinvest)."""
    from app.fve_analysis import run_economic_analysis

    return run_economic_analysis(params or {})


@router.post("/fve-analysis/report/energy")
def energy_pdf(result: dict, user: User = Depends(ANY_ROLE)):
    """PDF energetické analýzy. Reuse legacy generátor, ale pod /api/v1
    a s auth — legacy /report/energy je bez obou a client má
    baseURL=/api/v1, takže by se netrefil."""
    from app.reporting import ReportGenerator

    if not result or "energy_balance_kwh" not in result:
        raise HTTPException(400, "Chybí výsledek analýzy")
    try:
        pdf_bytes = ReportGenerator().generate_energy_report(result)
    except Exception as e:
        raise HTTPException(500, f"PDF se nepodařilo vygenerovat: {e}")
    fname = f"fve_energy_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"',
                 "X-Filename": fname},
    )


def _create_customer(db: Session, contact: Contact) -> User:
    """Nový zákazník z kontaktu. Heslo je náhodné — reset je mimo scope,
    zákazník se poprvé přihlásí přes flow obnovy hesla."""
    u = User(
        email=contact.email.lower().strip(),
        password_hash=hash_password(secrets.token_urlsafe(24)),
        role="customer",
    )
    u.set_roles(["customer"])
    db.add(u)
    db.flush()
    return u


@router.post("/fve-analysis")
def save_analysis(payload: SaveAnalysisIn, user: User = Depends(ANY_ROLE),
                  db: Session = Depends(get_db)):
    """Uloží rozpracovanou analýzu jako projekt ve stavu fve_analyza.

    owner_id je ten, kdo uložil; vazba v project_users patří zákazníkovi
    z kontaktu. Tím zákazník vidí svou vlastní analýzu (viz
    can_access_project) a přiřazení zůstává správné, i když analýzu
    uložil obchodník za zákazníka.
    """
    c = payload.contact
    email = c.email.lower().strip()
    existing = db.query(User).filter(User.email == email).first()
    customer = existing or _create_customer(db, c)

    name = (payload.name or "").strip() or f"FVE analýza — {c.name}"
    p = Project(
        name=name,
        customer_name=c.name,
        customer_email=email,
        customer_phone=c.phone,
        owner_id=user.id,
        status="fve_analyza",
        type="ostatni",
        share_code=generate_share_code(),
        fve_params_json=json.dumps(payload.params.model_dump(), ensure_ascii=False),
        antelon_params_json=json.dumps({}, ensure_ascii=False),
    )
    db.add(p)
    db.flush()

    db.add(ProjectUser(project_id=p.id, user_id=customer.id))
    db.commit()
    db.refresh(p)

    return {
        "id": p.id,
        "status": p.status,
        "share_code": p.share_code,
        "customer_id": customer.id,
        "customer_created": existing is None,  # True = právě vznikl
    }


# Kroky, které fveAnalysis fakticky dodává — označíme jako hotové, ať je
# obchodník nedělá znovu.
#
# Porovnává se ZAČÁTEK názvu, ne přesná shoda: v šablonách se krok jmenuje
# „první indikativní nabídka dle telefonátu - tel/email", takže shoda na
# celý řetězec by nesedla nikdy a funkce by tiše nedělala nic.
# Řešíme podle názvu, ne ID, protože ID se liší mezi instalacemi.
ANALYSIS_SUPPLIED_STEPS = ("první indikativní nabídka", "Zjištění roční spotřeby")


@router.post("/projects/{project_id}/convert-to-order")
def convert_to_order(project_id: int, user: User = Depends(ANY_ROLE),
                     db: Session = Depends(get_db)):
    """Převede rozpracovanou analýzu na zakázku: fve_analyza → lead.

    Pouze admin/antelon — je to obchodní rozhodnutí, zákazník svou analýzu
    převést nemůže.
    """
    from .pipeline_seed import attach_template

    if not is_internal_user(user):
        raise HTTPException(403, "Na převod na zakázku nemáte oprávnění")

    p = db.query(Project).filter(Project.id == project_id,
                                 Project.active.is_(True)).first()
    if not p:
        raise HTTPException(404, "Projekt nenalezen")
    if not can_access_project(user, p, db):
        raise HTTPException(403, "Bez přístupu k projektu")
    if p.status != "fve_analyza":
        raise HTTPException(409, f"Projekt je ve stavu {p.status}, ne fve_analyza")

    # parametry analýzy do definice zakázky
    fve_params = json.loads(p.fve_params_json) if p.fve_params_json else {}
    antelon = json.loads(p.antelon_params_json) if p.antelon_params_json else {}
    antelon["kwp"] = fve_params.get("kwp")
    antelon["battery_capacity"] = fve_params.get("battery_capacity")
    antelon["thermal_battery_capacity_kwh"] = fve_params.get(
        "thermal_battery_capacity_kwh", 0.0)
    antelon["fve_analysis_source"] = {"project": p.id, "share_code": p.share_code}
    p.antelon_params_json = json.dumps(antelon, ensure_ascii=False)

    p.status = "lead"
    # přes mapování, ne p.type přímo — p.type může být hodnota mimo
    # slovník šablon a bez fallbacku by to skončilo ValueError
    from .pipeline_seed import TEMPLATE_CODE_BY_TYPE

    attach_template(db, p, TEMPLATE_CODE_BY_TYPE.get(p.type, "ostatni"))

    # kroky, které analýza dodala, označ jako hotové s odkazem na zdroj.
    # Název kroku je v pipeline_steps, ne přímo v project_steps — join.
    wanted = tuple(n.lower() for n in ANALYSIS_SUPPLIED_STEPS)
    rows = (db.query(ProjectStep, PipelineStep.name)
            .join(PipelineStep, ProjectStep.step_id == PipelineStep.id)
            .filter(ProjectStep.project_id == p.id)
            .all())
    for step, name in rows:
        if name and name.strip().lower().startswith(wanted):
            step.status = "done"
            step.done_at = datetime.utcnow()
            step.note = f"Dodáno FVE analýzou (projekt #{p.id})"

    db.commit()
    db.refresh(p)
    return {"id": p.id, "status": p.status, "type": p.type}
