"""
routers/users.py
────────────────────────────────────────────────────────────
User management API  (admin-only write, self-read).

GET    /api/auth/users           – list all users (admin)
POST   /api/auth/users           – create user (admin)
GET    /api/auth/users/{id}      – get user (admin or self)
PUT    /api/auth/users/{id}      – update user (admin, or self for email/password)
DELETE /api/auth/users/{id}      – delete user (admin)
GET    /api/auth/me              – get current user
PUT    /api/auth/me              – update own profile
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from database import get_db
from models import User
from auth import get_current_user, require_admin

router  = APIRouter(prefix="/auth", tags=["Auth / Users"])
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ─── Schemas ────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username:  str
    email:     str
    password:  str
    role:      str = "viewer"
    is_active: bool = True


class UserUpdate(BaseModel):
    username:  Optional[str]  = None
    email:     Optional[str]  = None
    password:  Optional[str]  = None
    role:      Optional[str]  = None
    is_active: Optional[bool] = None


class UserOut(BaseModel):
    id:         int
    username:   str
    email:      str
    role:       str
    is_active:  bool
    created_at: Optional[datetime]
    last_login: Optional[datetime]

    class Config:
        from_attributes = True


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/users", response_model=List[UserOut], summary="List all users")
def list_users(
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    return db.query(User).order_by(User.username).all()


@router.post("/users", response_model=UserOut, status_code=201, summary="Create user")
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(400, f"Username '{data.username}' already taken")
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(400, f"Email '{data.email}' already registered")

    valid_roles = {"viewer", "technician", "radiologist", "admin"}
    if data.role not in valid_roles:
        raise HTTPException(400, f"Invalid role. Must be one of: {valid_roles}")

    user = User(
        username        = data.username,
        email           = data.email,
        hashed_password = pwd_ctx.hash(data.password),
        role            = data.role,
        is_active       = data.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users/{user_id}", response_model=UserOut, summary="Get user")
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Admin can see any user; others can only see themselves
    if current_user.role != "admin" and current_user.id != user_id:
        raise HTTPException(403, "Access denied")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    return user


@router.put("/users/{user_id}", response_model=UserOut, summary="Update user")
def update_user(
    user_id: int,
    data:    UserUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    # Non-admins can only update their own email/password, not role
    is_admin = current_user.role == "admin"
    is_self  = current_user.id == user_id

    if not is_admin and not is_self:
        raise HTTPException(403, "Access denied")

    if data.username  is not None and is_admin: user.username  = data.username
    if data.email     is not None:              user.email     = data.email
    if data.role      is not None and is_admin: user.role      = data.role
    if data.is_active is not None and is_admin: user.is_active = data.is_active
    if data.password  is not None:
        user.hashed_password = pwd_ctx.hash(data.password)

    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=204, summary="Delete user")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    if current_user.id == user_id:
        raise HTTPException(400, "Cannot delete your own account")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    db.delete(user)
    db.commit()


@router.get("/me", response_model=UserOut, summary="Get current user")
def get_me(current_user=Depends(get_current_user)):
    return current_user


@router.put("/me", response_model=UserOut, summary="Update own profile")
def update_me(
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if data.email    is not None: current_user.email    = data.email
    if data.password is not None: current_user.hashed_password = pwd_ctx.hash(data.password)
    # Cannot change own role
    db.commit()
    db.refresh(current_user)
    return current_user
