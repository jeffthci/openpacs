"""
auth.py
────────────────────────────────────────────────────────────
JWT authentication helpers and FastAPI dependencies.

Token endpoint:  POST /api/auth/token   (OAuth2 password flow)
Protected deps:  get_current_user, require_admin
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import User
from config import settings

router   = APIRouter(prefix="/auth", tags=["Auth"])
pwd_ctx  = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2   = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

ALGORITHM      = "HS256"
ACCESS_EXPIRES = timedelta(hours=12)


# ─── Token schemas ───────────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    role:         str
    username:     str


class TokenData(BaseModel):
    user_id:  Optional[int] = None
    username: Optional[str] = None


# ─── Helpers ─────────────────────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)


def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + ACCESS_EXPIRES
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user


# ─── FastAPI dependencies ─────────────────────────────────────────

def get_current_user(
    token: str = Depends(oauth2),
    db: Session = Depends(get_db),
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload  = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise credentials_exc

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


def require_roles(*roles: str):
    """Dependency factory — require one of the given roles."""
    def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(403, f"Role required: {', '.join(roles)}")
        return current_user
    return _check


# ─── Token endpoint ──────────────────────────────────────────────

@router.post("/token", response_model=Token, summary="Get access token")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Update last_login
    user.last_login = datetime.utcnow()
    db.commit()

    token = create_access_token({"sub": str(user.id)})
    return Token(
        access_token=token,
        role=user.role,
        username=user.username,
    )


# ─── Seed admin user on first run ────────────────────────────────

def seed_admin(db: Session) -> None:
    """Create default admin user if no users exist."""
    if db.query(User).count() == 0:
        admin = User(
            username        = "admin",
            email           = "admin@localhost",
            hashed_password = hash_password("admin"),
            role            = "admin",
            is_active       = True,
        )
        db.add(admin)
        db.commit()
        import logging
        logging.getLogger(__name__).warning(
            "Created default admin user (admin/admin) — CHANGE THIS PASSWORD IMMEDIATELY"
        )
