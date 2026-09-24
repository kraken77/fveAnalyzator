"""Dispečink — administrační routy (M1.3.3)."""

import os
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .auth import require_roles
from .storage import User, get_db

router = APIRouter(prefix="/admin", tags=["dispecink"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/import/dispecink")
async def import_dispecink_endpoint(
    file: UploadFile = File(...),
    user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """Import historických zakázek z Excelu „PROCESNÍ DISPEČINK".

    Soubor se uloží do data/imports/ a projde idempotentním importem
    (duplicita podle (name, type) proti obsahu DB před importem).
    """
    content = await file.read()
    if not content:
        raise HTTPException(400, "Prázdný soubor")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Soubor je příliš velký (max 10 MB)")

    os.makedirs("data/imports", exist_ok=True)
    fname = f"dispecink_{datetime.utcnow():%Y%m%d%H%M%S}.xlsx"
    path = os.path.join("data", "imports", fname)
    with open(path, "wb") as f:
        f.write(content)

    from .import_dispecink import import_dispecink

    try:
        result = import_dispecink(path, db)
    except Exception as e:
        raise HTTPException(400, f"Import selhal: {e}")
    result["saved_as"] = fname
    return result