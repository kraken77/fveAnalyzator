import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .storage import get_db, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

JWT_SECRET = os.environ.get("RG_JWT_SECRET", "dev-secret-change-me")
JWT_ALG = "HS256"
JWT_EXPIRE_DAYS = 7

def hash_password(password: str) -> str:
    # bcrypt 72 byte limit - truncate
    if isinstance(password, str):
        # encode to bytes to check length
        b = password.encode('utf-8')
        if len(b) > 72:
            password = b[:72].decode('utf-8', errors='ignore')
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    if isinstance(plain, str):
        b = plain.encode('utf-8')
        if len(b) > 72:
            plain = b[:72].decode('utf-8', errors='ignore')
    return pwd_context.verify(plain, hashed)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(days=JWT_EXPIRE_DAYS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALG)

def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if credentials is None:
        return None
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        email: str = payload.get("sub")
        if email is None:
            return None
    except JWTError:
        return None
    user = db.query(User).filter(User.email == email).first()
    return user

def get_current_user(
    user: Optional[User] = Depends(get_current_user_optional),
):
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Neautorizováno")
    return user

def require_roles(*roles):
    """Multi-role check: uživatel musí mít alespoň jednu z rolí (user.roles,
    fallback na primární user.role — zpětná kompatibilita)."""
    def _checker(user: User = Depends(get_current_user)):
        if not any(user.has_role(r) for r in roles):
            raise HTTPException(status_code=403, detail="Nedostatečná oprávnění")
        return user
    return _checker

# Zaměstnanecké role s interní viditelností (dispečink, interní materiály,
# interní PDF). Drží se synchronně se storage.ROLES mínus "customer" —
# hlídá test_internal_roles. Neznámá/překlepnutá role interní přístup NEDÁVÁ
# (dřív stačilo být „cokoli jiného než customer“, což bylo příliš benevolentní).
INTERNAL_ROLES = frozenset({
    "admin", "antelon", "sales", "designer", "warehouse", "buyer",
    "subsidy", "connection", "roofer", "electrician", "inspector",
})


def is_internal_user(user: Optional[User]) -> bool:
    """Interní rolí vidí zaměstnanec všechny zakázky v dispečinku."""
    if user is None:
        return False
    roles = list(user.roles or [])
    if not roles and user.role:
        roles = [user.role]
    return any(r in INTERNAL_ROLES for r in roles)


def is_principal(user: Optional[User]) -> bool:
    """Vedení: admin ⊃ antelon (multi-role bezpečné)."""
    return user is not None and (user.has_role("admin") or user.has_role("antelon"))


def can_access_project(user: Optional[User], project, db: Session) -> bool:
    if user is None:
        return False
    if is_principal(user):
        return True
    if is_internal_user(user):
        return True
    if project.owner_id == user.id:
        return True
    # check project_users
    from .storage import ProjectUser
    link = db.query(ProjectUser).filter(ProjectUser.project_id == project.id, ProjectUser.user_id == user.id).first()
    return link is not None
