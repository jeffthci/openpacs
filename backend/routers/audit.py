"""
routers/audit.py
────────────────────────────────────────────────────────────
Audit log query and integrity check endpoints.
Admin-only access required for all routes.

Also includes user management endpoints (create, deactivate,
role assignment) since these are adjacent admin concerns.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user, require_admin
from services.audit import (
    AuditEvent, get_audit_logs, verify_hash_chain, log_event
)

router = APIRouter(prefix="/audit", tags=["Audit & Compliance"])


# ─── Schemas ──────────────────────────────────────────────────────

class AuditLogOut(BaseModel):
    id:            int
    event_type:    str
    event_time:    datetime
    username:      Optional[str]
    ip_address:    Optional[str]
    resource_type: Optional[str]
    resource_id:   Optional[str]
    action:        Optional[str]
    outcome:       str
    description:   Optional[str]
    entry_hash:    Optional[str]

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    username:   str
    email:      str
    password:   str
    role:       str = "viewer"   # viewer | radiologist | admin


class UserOut(BaseModel):
    id:         int
    username:   str
    email:      str
    role:       str
    is_active:  bool
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Audit log endpoints ──────────────────────────────────────────

@router.get("/logs", response_model=List[AuditLogOut])
def query_audit_logs(
    event_type:  Optional[str]      = Query(None),
    username:    Optional[str]      = Query(None),
    resource_id: Optional[str]      = Query(None),
    start_date:  Optional[datetime] = Query(None),
    end_date:    Optional[datetime] = Query(None),
    limit:  int = Query(100, le=1000),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    """Query the HIPAA audit log. Admin only."""
    return get_audit_logs(
        db,
        event_type=event_type,
        username=username,
        resource_id=resource_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


@router.get("/logs/count")
def audit_log_count(
    event_type: Optional[str] = Query(None),
    username:   Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    from models import AuditLog
    q = db.query(AuditLog)
    if event_type:
        q = q.filter(AuditLog.event_type.ilike(f"%{event_type}%"))
    if username:
        q = q.filter(AuditLog.username.ilike(f"%{username}%"))
    return {"count": q.count()}


@router.get("/integrity")
def check_integrity(
    last_n: int = Query(1000, le=10000),
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    """
    Verify hash chain integrity of the audit log.
    Returns INTEGRITY_VIOLATION if any entries have been tampered with.
    """
    report = verify_hash_chain(db, last_n=last_n)
    return report


@router.get("/events")
def list_event_types(_user=Depends(get_current_user)):
    """List all audit event type constants."""
    return [e.value for e in AuditEvent]


# ─── User management ─────────────────────────────────────────────

@router.get("/users", response_model=List[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    from models import User
    return db.query(User).order_by(User.username).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    from models import User
    from passlib.context import CryptContext

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(409, "Username already exists")

    valid_roles = {"viewer", "radiologist", "technician", "admin"}
    if data.role not in valid_roles:
        raise HTTPException(400, f"Role must be one of: {valid_roles}")

    user = User(
        username      = data.username,
        email         = data.email,
        hashed_password = pwd_ctx.hash(data.password),
        role          = data.role,
        is_active     = True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_event(
        db, AuditEvent.USER_CREATE,
        user_id       = current_user.id,
        username      = current_user.username,
        resource_type = "user",
        resource_id   = str(user.id),
        description   = f"Created user {user.username} with role {user.role}",
    )

    return user


@router.put("/users/{user_id}/role")
def update_user_role(
    user_id:  int,
    role:     str,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    from models import User

    valid_roles = {"viewer", "radiologist", "technician", "admin"}
    if role not in valid_roles:
        raise HTTPException(400, f"Role must be one of: {valid_roles}")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    old_role = user.role
    user.role = role
    db.commit()

    log_event(
        db, AuditEvent.USER_UPDATE,
        user_id       = current_user.id,
        username      = current_user.username,
        resource_type = "user",
        resource_id   = str(user_id),
        description   = f"Changed role: {old_role} → {role} for {user.username}",
    )

    return {"user_id": user_id, "username": user.username, "role": role}


@router.put("/users/{user_id}/deactivate")
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    from models import User

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if user.id == current_user.id:
        raise HTTPException(400, "Cannot deactivate yourself")

    user.is_active = False
    db.commit()

    log_event(
        db, AuditEvent.USER_UPDATE,
        user_id       = current_user.id,
        username      = current_user.username,
        resource_type = "user",
        resource_id   = str(user_id),
        description   = f"Deactivated user {user.username}",
    )

    return {"user_id": user_id, "is_active": False}


@router.get("/users/{user_id}/activity")
def user_activity(
    user_id: int,
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    """All audit entries for a specific user — for compliance review."""
    from models import AuditLog
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.user_id == user_id)
        .order_by(AuditLog.event_time.desc())
        .limit(limit)
        .all()
    )
    return logs
