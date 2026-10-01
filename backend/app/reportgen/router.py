import os
import json
import base64
import re
import unicodedata
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .storage import get_db, User, Project, ProjectUser, ProjectFile, ProjectPhoto, PdfVersion, generate_share_code, init_db
from .auth import hash_password, verify_password, create_access_token, get_current_user, get_current_user_optional, require_roles, can_access_project, is_principal, is_internal_user
from .shelly_parser import parse_shelly_csv, merge_parsed_results, extract_consumption_totals
from .antelon import antelon_analyze
from .antelon_pdf import generate_antelon_pdf
from .pdf_utils import generate_qr_base64, apply_watermark_to_pdf

def _slugify(name: str, maxlen: int = 40) -> str:
    if not name:
        return "projekt"
    # normalize, remove diacritics
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_only).strip("_").lower()
    slug = re.sub(r"_+", "_", slug)
    if len(slug) > maxlen:
        slug = slug[:maxlen].rstrip("_")
    return slug or "projekt"

router = APIRouter(prefix="/api/v1", tags=["reportgen"])

# ---------- Schemas ----------
class RegisterIn(BaseModel):
    email: str
    password: str
    role: str = "customer"

class LoginIn(BaseModel):
    email: str
    password: str

class ProjectCreate(BaseModel):
    name: str
    customer_name: Optional[str] = None
    description: Optional[str] = None

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    customer_name: Optional[str] = None
    description: Optional[str] = None
    antelon_params: Optional[dict] = None
    fve_params: Optional[dict] = None

class ParamsUpdate(BaseModel):
    antelon_params: Optional[dict] = None
    fve_params: Optional[dict] = None

class GenerateIn(BaseModel):
    template: str  # antelon, energy, economic, ote

class PublicJoinIn(BaseModel):
    code: str

# ---------- Helpers ----------
def _project_to_dict(p: Project):
    return {
        "id": p.id,
        "name": p.name,
        "customer_name": p.customer_name,
        "customer_email": p.customer_email,
        "customer_phone": p.customer_phone,
        "description": p.description,
        "owner_id": p.owner_id,
        "share_code": p.share_code,
        "type": p.type,
        "status": p.status,
        "tech": p.tech,
        "antelon_params": json.loads(p.antelon_params_json) if p.antelon_params_json else {},
        "fve_params": json.loads(p.fve_params_json) if p.fve_params_json else {},
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }

def _ensure_project_access(project_id: int, user, db: Session):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Projekt nenalezen")
    # admin/antelon + interní role je možno vše; customer jen owner/link
    if user is None:
        raise HTTPException(401, "Neautorizováno")
    if not can_access_project(user, p, db):
        raise HTTPException(403, "Bez přístupu k projektu")
    return p

def _get_parsed_for_project(project_id: int, db: Session):
    files = db.query(ProjectFile).filter(ProjectFile.project_id == project_id).all()
    if not files:
        return None
    results = []
    for f in files:
        try:
            content = open(f.path, "rb").read()
            parsed = parse_shelly_csv(content)
            results.append(parsed)
        except Exception as e:
            # skip broken file but warn
            continue
    if not results:
        return None
    if len(results) == 1:
        return results[0]
    # merge
    try:
        return merge_parsed_results(results)
    except ValueError as e:
        raise HTTPException(400, str(e))

# Ensure DB initialized on import
try:
    init_db()
except Exception as e:
    print(f"reportgen init_db error: {e}")

# ---------- Auth ----------
@router.post("/auth/register")
def register(data: RegisterIn, db: Session = Depends(get_db)):
    email = data.email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(400, "Email již registrován")
    # Only allow customer self-register; admin/antelon creation requires admin
    role = "customer"
    if data.role in ("admin", "antelon"):
        role = "customer"
    user = User(email=email, password_hash=hash_password(data.password), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token({"sub": user.email, "role": user.role, "roles": user.roles})
    return {"access_token": token, "token_type": "bearer", "user": {"id": user.id, "email": user.email, "role": user.role, "roles": user.roles}}

@router.post("/auth/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    email = data.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Neplatné přihlášení")
    token = create_access_token({"sub": user.email, "role": user.role, "roles": user.roles})
    return {"access_token": token, "token_type": "bearer", "user": {"id": user.id, "email": user.email, "role": user.role, "roles": user.roles}}

@router.get("/auth/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "role": user.role, "roles": user.roles}

# ---------- Projects ----------
@router.get("/projects")
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if is_principal(user) or is_internal_user(user):
        projects = db.query(Project).order_by(Project.updated_at.desc()).all()
    else:
        # customer: owned + shared
        owned = db.query(Project).filter(Project.owner_id == user.id).all()
        shared_ids = [r.project_id for r in db.query(ProjectUser).filter(ProjectUser.user_id == user.id).all()]
        shared = db.query(Project).filter(Project.id.in_(shared_ids)).all() if shared_ids else []
        # deduplicate
        seen = set()
        projects = []
        for p in owned + shared:
            if p.id not in seen:
                projects.append(p)
                seen.add(p.id)
        projects.sort(key=lambda x: x.updated_at or datetime.min, reverse=True)
    return [_project_to_dict(p) for p in projects]

@router.post("/projects")
def create_project(data: ProjectCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not (user.has_role("admin") or user.has_role("antelon")):
        raise HTTPException(403, "Jen Antelon může vytvářet projekty")
    code = generate_share_code()
    # ensure unique
    while db.query(Project).filter(Project.share_code == code).first():
        code = generate_share_code()
    p = Project(
        name=data.name,
        customer_name=data.customer_name,
        description=data.description,
        owner_id=user.id,
        share_code=code,
        antelon_params_json=json.dumps({"kwp": 25, "battery_kwh": 15, "soc_min_pct": 30, "texts": {}}),
        fve_params_json=json.dumps({}),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _project_to_dict(p)

@router.get("/projects/{project_id}")
def get_project(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    return _project_to_dict(p)

@router.put("/projects/{project_id}")
def update_project(project_id: int, data: ProjectUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    if not (user.has_role("admin") or user.has_role("antelon")):
        raise HTTPException(403, "Jen Antelon může upravovat projekt")
    if data.name is not None:
        p.name = data.name
    if data.customer_name is not None:
        p.customer_name = data.customer_name
    if data.description is not None:
        p.description = data.description
    if data.antelon_params is not None:
        p.antelon_params_json = json.dumps(data.antelon_params)
    if data.fve_params is not None:
        p.fve_params_json = json.dumps(data.fve_params)
    p.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(p)
    return _project_to_dict(p)

@router.delete("/projects/{project_id}")
def delete_project(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    if not (user.has_role("admin") or user.has_role("antelon")):
        raise HTTPException(403, "Jen Antelon může mazat")
    db.delete(p)
    db.commit()
    return {"status": "ok"}

@router.put("/projects/{project_id}/params")
def update_params(project_id: int, data: ParamsUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    if not (user.has_role("admin") or user.has_role("antelon")):
        raise HTTPException(403, "Jen Antelon může měnit parametry")
    if data.antelon_params is not None:
        p.antelon_params_json = json.dumps(data.antelon_params)
    if data.fve_params is not None:
        p.fve_params_json = json.dumps(data.fve_params)
    p.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(p)
    return _project_to_dict(p)

# ---------- Files ----------
@router.post("/projects/{project_id}/files")
async def upload_files(project_id: int, files: List[UploadFile] = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    if not (user.has_role("admin") or user.has_role("antelon")):
        raise HTTPException(403, "Jen Antelon může nahrávat data")
    saved = []
    for f in files:
        content = await f.read()
        # Validate parser
        try:
            parse_shelly_csv(content)
        except Exception as e:
            raise HTTPException(400, f"Soubor {f.filename} nelze parsovat: {e}")
        # Save to FS
        proj_dir = os.path.join(os.path.dirname(db.bind.url.database) if db.bind.url.database else "data", f"projects/{project_id}")
        # Use storage DB path dir as base
        # Determine base dir: directory of reportgen.db
        db_path = db.bind.url.database
        base_dir = os.path.dirname(db_path) if db_path and db_path != ":memory:" else "data"
        proj_dir = os.path.join(base_dir, f"projects/{project_id}")
        os.makedirs(proj_dir, exist_ok=True)
        safe_name = f.filename.replace("/", "_").replace("\\", "_")
        dest = os.path.join(proj_dir, safe_name)
        # handle duplicate filename
        if os.path.exists(dest):
            base, ext = os.path.splitext(safe_name)
            dest = os.path.join(proj_dir, f"{base}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{ext}")
            safe_name = os.path.basename(dest)
        with open(dest, "wb") as out:
            out.write(content)
        pf = ProjectFile(project_id=project_id, kind="consumption_daily", filename=safe_name, path=dest)
        db.add(pf)
        saved.append(safe_name)
    db.commit()
    return {"saved": saved}

@router.get("/projects/{project_id}/files")
def list_files(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_project_access(project_id, user, db)
    files = db.query(ProjectFile).filter(ProjectFile.project_id == project_id).all()
    return [{"id": f.id, "filename": f.filename, "path": f.path, "uploaded_at": f.uploaded_at.isoformat() if f.uploaded_at else None} for f in files]

@router.delete("/projects/{project_id}/files/{file_id}")
def delete_file(project_id: int, file_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_project_access(project_id, user, db)
    if not (user.has_role("admin") or user.has_role("antelon")):
        raise HTTPException(403, "Jen Antelon může mazat soubory")
    pf = db.query(ProjectFile).filter(ProjectFile.id == file_id, ProjectFile.project_id == project_id).first()
    if not pf:
        raise HTTPException(404, "Soubor nenalezen")
    try:
        if os.path.exists(pf.path):
            os.remove(pf.path)
    except:
        pass
    db.delete(pf)
    db.commit()
    return {"status": "ok"}

# ---------- Data preview ----------
@router.get("/projects/{project_id}/data")
def project_data(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    parsed = _get_parsed_for_project(project_id, db)
    if not parsed:
        return {"parsed": None, "kpi": None, "phase": None, "warnings": [], "gaps": [], "complete_days": []}
    antelon_params = json.loads(p.antelon_params_json) if p.antelon_params_json else {}
    analysis = antelon_analyze(parsed, antelon_params)
    # Build serializable response
    cons_totals = analysis["cons_totals"]
    cons_list = []
    if not cons_totals.empty:
        for _, row in cons_totals.iterrows():
            cons_list.append({"date": row["date"].isoformat(), "total_kwh": float(row["total_kwh"]) if row["total_kwh"] is not None else None, "missing": bool(row["missing"])})
    # Make kpi JSON serializable (numpy -> python)
    kpi_clean = {}
    for k, v in analysis["kpi"].items():
        if k == "complete_df":
            continue
        if hasattr(v, 'item'):
            try:
                v = v.item()
            except:
                pass
        kpi_clean[k] = float(v) if isinstance(v, float) or str(type(v)).find('numpy') != -1 else v
        # ensure int
        if isinstance(kpi_clean[k], float) and k == "n_complete":
            kpi_clean[k] = int(kpi_clean[k])
    gr = analysis["green_red"]
    green_red_clean = {k: float(v) if hasattr(v, 'item') or isinstance(v, float) else v for k, v in gr.items() if k != "hourly"}
    return {
        "parsed": {"blocks": [{"title": b["title"], "rows": len(b["df"])} for b in parsed["blocks"]]},
        "kpi": kpi_clean,
        "phase": {k: float(v) for k, v in analysis["phase_pct"].items()},
        "warnings": analysis["warnings"],
        "gaps": [d.isoformat() for d in analysis["gaps"]],
        "complete_days": [d.isoformat() for d in analysis["complete_days"]],
        "cons_daily": cons_list,
        "green_red": green_red_clean,
    }

# ---------- Share / QR ----------
@router.post("/projects/{project_id}/share")
def create_share(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    if not (user.has_role("admin") or user.has_role("antelon")):
        raise HTTPException(403, "Jen Antelon může sdílet")
    # regenerate if needed? keep existing
    host = os.environ.get("RG_PUBLIC_URL", "http://localhost:3000")
    url = f"{host}/p/{p.share_code}"
    qr_b64 = generate_qr_base64(url)
    return {"code": p.share_code, "url": url, "qr_b64": qr_b64}

@router.post("/public/join")
def public_join(data: PublicJoinIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    code = data.code.strip().upper()
    p = db.query(Project).filter(Project.share_code == code).first()
    if not p:
        raise HTTPException(404, "Kód neexistuje")
    # add user to project
    exists = db.query(ProjectUser).filter(ProjectUser.project_id == p.id, ProjectUser.user_id == user.id).first()
    if not exists:
        db.add(ProjectUser(project_id=p.id, user_id=user.id))
        db.commit()
    return {"status": "ok", "project_id": p.id}

@router.get("/public/p/{code}")
def public_preview(code: str, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user_optional)):
    code = code.strip().upper()
    p = db.query(Project).filter(Project.share_code == code).first()
    if not p:
        raise HTTPException(404, "Projekt nenalezen")
    antelon_params = json.loads(p.antelon_params_json) if p.antelon_params_json else {}
    parsed = None
    try:
        parsed = _get_parsed_for_project(p.id, db)
    except:
        parsed = None
    # Build teaser data
    teaser = {
        "project": {"id": p.id, "name": p.name, "customer_name": p.customer_name, "share_code": p.share_code},
        "is_authenticated": user is not None,
        "is_linked": False,
        "kpi": None,
        "phase": None,
        "sections": [],
    }
    if user:
        teaser["is_linked"] = is_principal(user) or is_internal_user(user) or (p.owner_id == user.id) or \
            (db.query(ProjectUser).filter(ProjectUser.project_id == p.id, ProjectUser.user_id == user.id).first() is not None)
    # KPI teaser: always visible basic
    if parsed:
        try:
            analysis = antelon_analyze(parsed, antelon_params)
            teaser["kpi"] = {k: v for k, v in analysis["kpi"].items() if k != "complete_df"}
            teaser["phase"] = analysis["phase_pct"]
            # Sections list with visibility
            visibility = antelon_params.get("visibility", {})
            default_vis = {"s1": "full", "s2": "full", "s3": "full", "s4": "full", "s5": "full", "s5b": "teaser", "s6": "teaser", "s7": "teaser", "s8": "full", "s9": "full"}
            for sid, default in default_vis.items():
                vis = visibility.get(sid, default)
                # For teaser view, decide blur
                should_blur = False
                full_viewer = user and (is_principal(user) or is_internal_user(user))
                if vis == "internal" and not full_viewer:
                    should_blur = True
                elif vis == "teaser" and not teaser["is_linked"] and not full_viewer:
                    should_blur = True
                teaser["sections"].append({"id": sid, "visibility": vis, "blur": should_blur})
        except Exception as e:
            teaser["error"] = str(e)
    else:
        teaser["sections"] = []
    return teaser

# ---------- Photos ----------
@router.get("/projects/{project_id}/photos")
def list_photos(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_project_access(project_id, user, db)
    photos = db.query(ProjectPhoto).filter(ProjectPhoto.project_id == project_id).order_by(ProjectPhoto.position).all()
    return [{"id": ph.id, "filename": ph.filename, "caption": ph.caption, "position": ph.position} for ph in photos]

@router.post("/projects/{project_id}/photos")
async def upload_photo(project_id: int, file: UploadFile = File(...), caption: str = Form(""), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    if not (user.has_role("admin") or user.has_role("antelon")):
        raise HTTPException(403, "Jen Antelon může nahrávat fotky")
    content = await file.read()
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(400, "Fotka příliš velká (max 15 MB)")
    db_path = db.bind.url.database
    base_dir = os.path.dirname(db_path) if db_path and db_path != ":memory:" else "data"
    proj_dir = os.path.join(base_dir, f"projects/{project_id}", "photos")
    os.makedirs(proj_dir, exist_ok=True)
    safe = file.filename.replace("/", "_")
    dest = os.path.join(proj_dir, safe)
    if os.path.exists(dest):
        base, ext = os.path.splitext(safe)
        dest = os.path.join(proj_dir, f"{base}_{datetime.utcnow().strftime('%H%M%S')}{ext}")
        safe = os.path.basename(dest)
    with open(dest, "wb") as out:
        out.write(content)
    max_pos = db.query(ProjectPhoto).filter(ProjectPhoto.project_id == project_id).count()
    ph = ProjectPhoto(project_id=project_id, filename=safe, path=dest, caption=caption, position=max_pos)
    db.add(ph)
    db.commit()
    db.refresh(ph)
    return {"id": ph.id, "filename": ph.filename}

@router.delete("/projects/{project_id}/photos/{photo_id}")
def delete_photo(project_id: int, photo_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_project_access(project_id, user, db)
    if not (user.has_role("admin") or user.has_role("antelon")):
        raise HTTPException(403, "Jen Antelon")
    ph = db.query(ProjectPhoto).filter(ProjectPhoto.id == photo_id, ProjectPhoto.project_id == project_id).first()
    if not ph:
        raise HTTPException(404, "Foto nenalezena")
    try:
        if os.path.exists(ph.path):
            os.remove(ph.path)
    except:
        pass
    db.delete(ph)
    db.commit()
    return {"status": "ok"}

# ---------- Generate & PDF ----------
@router.post("/projects/{project_id}/generate")
def generate_pdf(project_id: int, data: GenerateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _ensure_project_access(project_id, user, db)
    if not (user.has_role("admin") or user.has_role("antelon")):
        raise HTTPException(403, "Jen Antelon může generovat PDF")
    template = data.template
    if template not in ("antelon", "energy", "economic", "ote"):
        raise HTTPException(400, "Neznámá šablona")

    # Determine next version
    last = db.query(PdfVersion).filter(PdfVersion.project_id == project_id, PdfVersion.template == template).order_by(PdfVersion.version.desc()).first()
    next_ver = (last.version + 1) if last else 1

    db_path = db.bind.url.database
    base_dir = os.path.dirname(db_path) if db_path and db_path != ":memory:" else "data"
    pdf_dir = os.path.join(base_dir, f"projects/{project_id}", "pdfs")
    os.makedirs(pdf_dir, exist_ok=True)
    filename = f"{template}_v{next_ver}.pdf"
    file_path = os.path.join(pdf_dir, filename)

    pdf_bytes = None
    params_snapshot = {}

    if template == "antelon":
        antelon_params = json.loads(p.antelon_params_json) if p.antelon_params_json else {}
        parsed = _get_parsed_for_project(project_id, db)
        if not parsed:
            raise HTTPException(400, "Žádná data k vygenerování reportu")
        analysis = antelon_analyze(parsed, antelon_params)
        visibility = antelon_params.get("visibility", {})
        pdf_bytes = generate_antelon_pdf(analysis, p, antelon_params, visibility)
        params_snapshot = antelon_params
    else:
        # fve wrap - reuse app.fve_analysis, the single source of truth
        fve_params = json.loads(p.fve_params_json) if p.fve_params_json else {}
        try:
            if template == "energy":
                from app.fve_analysis import analysis_param_keys, run_energy_analysis
                # Filter fve_params to valid fields
                valid = {k: v for k, v in fve_params.items() if k in analysis_param_keys()}
                result = run_energy_analysis(valid)
                from app.reporting import ReportGenerator
                rg = ReportGenerator()
                pdf_bytes = rg.generate_energy_report(result)
                params_snapshot = fve_params
            elif template == "economic":
                from app.fve_analysis import (analysis_param_keys,
                                              run_economic_analysis,
                                              run_energy_analysis)
                eco_keys = {"annual_savings", "investment_cost", "years",
                            "sp500_return", "inflation", "discount_rate"}
                # Need annual_savings - compute via energy if missing
                if "annual_savings" not in fve_params or fve_params["annual_savings"] is None:
                    valid_e = {k: v for k, v in fve_params.items() if k in analysis_param_keys()}
                    er = run_energy_analysis(valid_e)
                    fve_params["annual_savings"] = er["financial_balance"]["annual_savings_czk"]
                    p.fve_params_json = json.dumps(fve_params)
                    db.commit()
                valid = {k: v for k, v in fve_params.items() if k in eco_keys}
                result = run_economic_analysis(valid)
                from app.reporting import ReportGenerator
                rg = ReportGenerator()
                pdf_bytes = rg.generate_economic_report(result)
                params_snapshot = fve_params
            elif template == "ote":
                import sys
                sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
                from main import OteAnalysisInput, analyze_ote
                valid = {k: v for k, v in fve_params.items() if k in OteAnalysisInput.model_fields}
                input_data = OteAnalysisInput(**valid)
                result = analyze_ote(input_data)
                from app.reporting import ReportGenerator
                rg = ReportGenerator()
                pdf_bytes = rg.generate_ote_report(result)
                params_snapshot = fve_params
        except HTTPException:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(500, f"Generování {template} selhalo: {e}")

    if pdf_bytes is None:
        raise HTTPException(500, "PDF se nepodařilo vygenerovat")

    with open(file_path, "wb") as out:
        out.write(pdf_bytes)

    pv = PdfVersion(project_id=project_id, template=template, version=next_ver, file_path=file_path, params_snapshot_json=json.dumps(params_snapshot), created_by=user.id)
    db.add(pv)
    db.commit()
    db.refresh(pv)
    return {"id": pv.id, "template": pv.template, "version": pv.version, "created_at": pv.created_at.isoformat()}

@router.get("/projects/{project_id}/pdfs")
def list_pdfs(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_project_access(project_id, user, db)
    pvs = db.query(PdfVersion).filter(PdfVersion.project_id == project_id).order_by(PdfVersion.created_at.desc()).all()
    return [{"id": pv.id, "template": pv.template, "version": pv.version, "created_at": pv.created_at.isoformat() if pv.created_at else None, "created_by": pv.created_by} for pv in pvs]

@router.get("/projects/{project_id}/pdfs/{pdf_id}/download")
def download_pdf(project_id: int, pdf_id: int, mode: str = Query("full"), user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    # Access check: if user is None (anonymous), allow only if project exists and pdf exists, but apply watermark
    pv = db.query(PdfVersion).filter(PdfVersion.id == pdf_id, PdfVersion.project_id == project_id).first()
    if not pv:
        raise HTTPException(404, "PDF nenalezeno")
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Projekt nenalezen")

    # Authorization
    is_anonymous = user is None
    is_linked = False
    if user:
        if is_principal(user) or is_internal_user(user):
            is_linked = True
        elif project.owner_id == user.id:
            is_linked = True
        else:
            link = db.query(ProjectUser).filter(ProjectUser.project_id == project_id, ProjectUser.user_id == user.id).first()
            is_linked = link is not None
    # Anonymous or non-linked customer: allow download but with watermark for antelon template? Per spec: anonymous = watermark, customer linked = clean
    # So only anonymous gets watermark; linked customer gets clean

    if not os.path.exists(pv.file_path):
        raise HTTPException(404, "Soubor neexistuje na disku")

    pdf_bytes = open(pv.file_path, "rb").read()

    # Apply watermark for anonymous only, and only for antelon template (per feedback: B) watermark jen anonym)
    if is_anonymous:
        pdf_bytes = apply_watermark_to_pdf(pdf_bytes)

    slug = _slugify(project.name)
    # sjednotit template na ote (uzivatel psal eto, ale backend pouziva ote)
    tmpl = pv.template.lower().replace("eto", "ote")
    filename = f"{slug}_{tmpl}_v{pv.version}.pdf"
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename=\"{filename}\"', "X-Filename": filename})

# ---------- OTE ----------
@router.get("/ote/status")
def ote_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Reuse existing logic
    import sqlite3
    import os
    candidates = [
        os.path.join(os.path.dirname(db.bind.url.database) if db.bind.url.database and db.bind.url.database != ":memory:" else "data", "spot_market.db"),
        "data/spot_market.db",
        "/app/data/spot_market.db",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "spot_market.db")),
    ]
    db_path = next((p for p in candidates if os.path.exists(p)), candidates[0])
    if not os.path.exists(db_path):
        return {"status": "empty", "message": "DB neexistuje"}
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT MIN(datetime), MAX(datetime), COUNT(*) FROM spot_prices")
        row = cur.fetchone()
        conn.close()
        if row and row[0]:
            return {"status": "ok", "min_date": row[0], "max_date": row[1], "count": row[2]}
        return {"status": "empty"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post("/ote/update")
def ote_update(user: User = Depends(require_roles("admin", "antelon")), db: Session = Depends(get_db)):
    import subprocess, sqlite3
    try:
        subprocess.run(["bash", "download_ote_data.sh"], check=True, cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
        subprocess.run(["python3", "process_ote_data.py"], check=True, cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
        return {"status": "success"}
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"Update failed: {e}")
    except Exception as e:
        raise HTTPException(500, str(e))

# ---------- Admin appliances ----------
@router.get("/admin/appliances")
def list_appliances(user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    from app.appliance_manager import ApplianceManager
    am = ApplianceManager()
    return [{"name": k, "profile": v, "active": True} for k, v in am.appliances.items()]

@router.get("/admin/users")
def list_users(user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [{"id": u.id, "email": u.email, "role": u.role, "roles": u.roles, "created_at": u.created_at.isoformat() if u.created_at else None} for u in users]

def _role_val(role):
    from .storage import ROLES
    if role in ROLES:
        return role
    return None

@router.put("/admin/users/{user_id}")
def update_user_role(user_id: int, role: str = Form(...), user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    role = _role_val(role)
    if not role:
        raise HTTPException(400, "Neplatná role")
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(404, "Uživatel nenalezen")
    target.set_roles([role] + [r for r in target.roles if r != role])
    db.commit()
    return {"status": "ok", "role": role, "roles": target.roles}

class RolesIn(BaseModel):
    roles: list

@router.put("/admin/users/{user_id}/roles")
def update_user_roles(user_id: int, data: RolesIn, user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    from .storage import ROLES
    bad = [r for r in data.roles if r not in ROLES]
    if bad:
        raise HTTPException(400, f"Neplatné role: {bad}")
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(404, "Uživatel nenalezen")
    target.set_roles(data.roles)
    db.commit()
    return {"status": "ok", "roles": target.roles}

# ---------- Dispečink (M1) ----------
from .pipeline_router import router as pipeline_router
router.include_router(pipeline_router)
