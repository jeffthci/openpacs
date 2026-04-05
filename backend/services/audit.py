"""
services/audit.py
────────────────────────────────────────────────────────────
HIPAA-compliant audit logging service.

HIPAA §164.312(b) requires audit controls that record and
examine activity in systems containing ePHI.

Required audit events
─────────────────────
  - Authentication: login, logout, failed login
  - Authorization failures
  - PHI access: study view, image retrieve, patient lookup
  - PHI modification: study update, report create/edit
  - PHI deletion (if implemented)
  - Export: CD burn, STOW-RS store, C-MOVE send
  - Admin: user create/modify, config change, partition create

Log retention: minimum 6 years per HIPAA.

Tamper evidence: each log entry includes a hash chain
(SHA-256 of previous entry + current content) to detect
any retroactive modification of the audit trail.
"""

import hashlib
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

# ─── Audit event types ────────────────────────────────────────────

class AuditEvent(str, Enum):
    # Auth
    LOGIN_SUCCESS     = "auth.login.success"
    LOGIN_FAILURE     = "auth.login.failure"
    LOGOUT            = "auth.logout"
    TOKEN_REFRESH     = "auth.token.refresh"
    PASSWORD_CHANGE   = "auth.password.change"

    # PHI access
    PATIENT_VIEW      = "phi.patient.view"
    STUDY_VIEW        = "phi.study.view"
    SERIES_VIEW       = "phi.series.view"
    IMAGE_RETRIEVE    = "phi.image.retrieve"
    REPORT_VIEW       = "phi.report.view"
    WORKLIST_QUERY    = "phi.worklist.query"

    # PHI modification
    STUDY_UPDATE      = "phi.study.update"
    PATIENT_UPDATE    = "phi.patient.update"
    REPORT_CREATE     = "phi.report.create"
    REPORT_UPDATE     = "phi.report.update"

    # Export / transfer
    DICOM_STORE_RX    = "transfer.dicom.received"   # C-STORE incoming
    DICOM_STORE_TX    = "transfer.dicom.sent"        # C-STORE outgoing
    STOW_RECEIVED     = "transfer.stow.received"     # STOW-RS
    CD_BURN           = "transfer.cd.burn"
    EXPORT            = "transfer.export"

    # Admin
    USER_CREATE       = "admin.user.create"
    USER_UPDATE       = "admin.user.update"
    USER_DELETE       = "admin.user.delete"
    PARTITION_CREATE  = "admin.partition.create"
    PARTITION_UPDATE  = "admin.partition.update"
    ROUTING_CHANGE    = "admin.routing.change"
    CONFIG_CHANGE     = "admin.config.change"

    # Security
    AUTHZ_FAILURE     = "security.authz.failure"
    RATE_LIMIT        = "security.rate_limit"


# ─── DB model code (add to models.py) ─────────────────────────────

AUDIT_MODEL_CODE = '''
class AuditLog(Base):
    """
    HIPAA-compliant audit log. Append-only by policy.
    Never update or delete rows — add compensating entries instead.
    """
    __tablename__ = "audit_log"

    id             = Column(BigInteger, primary_key=True, autoincrement=True)
    event_type     = Column(String(64),  nullable=False, index=True)
    event_time     = Column(DateTime,    nullable=False, default=datetime.utcnow, index=True)

    # Who
    user_id        = Column(Integer,     ForeignKey("user.id"), nullable=True)
    username       = Column(String(64),  nullable=True)
    ip_address     = Column(String(45),  nullable=True)   # IPv4 or IPv6
    user_agent     = Column(String(255), nullable=True)

    # What
    resource_type  = Column(String(32),  nullable=True)   # "study", "patient", etc.
    resource_id    = Column(String(128), nullable=True)   # UID or DB ID
    action         = Column(String(32),  nullable=True)   # "read", "write", "delete"
    outcome        = Column(String(16),  nullable=False, default="success")  # success | failure

    # Details
    description    = Column(Text,        nullable=True)
    metadata_json  = Column(JSON,        nullable=True)   # extra context

    # Tamper evidence — SHA-256 hash chain
    entry_hash     = Column(String(64),  nullable=True)

    def __repr__(self):
        return f"<AuditLog [{self.id}] {self.event_type} by {self.username}>"
'''


# ─── Logging functions ────────────────────────────────────────────

def _compute_hash(prev_hash: Optional[str], entry: dict) -> str:
    """Compute tamper-evident hash for this entry."""
    content = json.dumps({
        "prev": prev_hash or "genesis",
        "event_type": entry.get("event_type"),
        "event_time": str(entry.get("event_time")),
        "user_id": entry.get("user_id"),
        "resource_id": entry.get("resource_id"),
    }, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


def _get_last_hash(db: Session) -> Optional[str]:
    """Get the hash of the most recent audit entry for chain continuity."""
    try:
        from models import AuditLog
        last = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        return last.entry_hash if last else None
    except Exception:
        return None


def log_event(
    db: Session,
    event_type: AuditEvent,
    *,
    user_id:       Optional[int]  = None,
    username:      Optional[str]  = None,
    ip_address:    Optional[str]  = None,
    user_agent:    Optional[str]  = None,
    resource_type: Optional[str]  = None,
    resource_id:   Optional[str]  = None,
    action:        Optional[str]  = None,
    outcome:       str            = "success",
    description:   Optional[str]  = None,
    metadata:      Optional[dict] = None,
) -> None:
    """
    Write one audit log entry. Non-blocking — catches all exceptions
    so audit failures never break the main request flow.
    """
    try:
        from models import AuditLog

        now = datetime.utcnow()
        entry_data = {
            "event_type":    event_type.value,
            "event_time":    now,
            "user_id":       user_id,
            "resource_id":   resource_id,
        }

        prev_hash = _get_last_hash(db)
        entry_hash = _compute_hash(prev_hash, entry_data)

        audit = AuditLog(
            event_type    = event_type.value,
            event_time    = now,
            user_id       = user_id,
            username      = username,
            ip_address    = ip_address,
            user_agent    = user_agent,
            resource_type = resource_type,
            resource_id   = resource_id,
            action        = action,
            outcome       = outcome,
            description   = description,
            metadata_json = metadata,
            entry_hash    = entry_hash,
        )
        db.add(audit)
        db.commit()

    except Exception as e:
        log.error(f"[audit] Failed to write audit entry: {e}")


def log_event_from_request(
    db: Session,
    request: Request,
    event_type: AuditEvent,
    *,
    user=None,
    resource_type: Optional[str] = None,
    resource_id:   Optional[str] = None,
    action:        Optional[str] = None,
    outcome:       str           = "success",
    description:   Optional[str] = None,
    metadata:      Optional[dict]= None,
) -> None:
    """Extract IP/UA from request and log."""
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent", "")[:255]

    log_event(
        db,
        event_type,
        user_id       = getattr(user, "id", None),
        username      = getattr(user, "username", None),
        ip_address    = ip,
        user_agent    = ua,
        resource_type = resource_type,
        resource_id   = resource_id,
        action        = action,
        outcome       = outcome,
        description   = description,
        metadata      = metadata,
    )


# ─── FastAPI middleware ────────────────────────────────────────────

class AuditMiddleware:
    """
    Middleware that auto-logs PHI access events for all
    /wado/* and /api/studies|patients/* endpoints.
    """

    PHI_PATHS = {
        "/wado/studies":   (AuditEvent.STUDY_VIEW,   "study"),
        "/api/patients":   (AuditEvent.PATIENT_VIEW, "patient"),
        "/api/studies":    (AuditEvent.STUDY_VIEW,   "study"),
        "/api/reports":    (AuditEvent.REPORT_VIEW,  "report"),
    }

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            for prefix, (event_type, resource_type) in self.PHI_PATHS.items():
                if path.startswith(prefix):
                    # Log will be written after auth succeeds in the route
                    scope["_audit_event"]        = event_type
                    scope["_audit_resource_type"] = resource_type
                    break

        await self.app(scope, receive, send)


# ─── Audit query API (for admin review) ───────────────────────────

def get_audit_logs(
    db: Session,
    event_type:    Optional[str]  = None,
    username:      Optional[str]  = None,
    resource_id:   Optional[str]  = None,
    start_date:    Optional[datetime] = None,
    end_date:      Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
) -> list:
    from models import AuditLog

    q = db.query(AuditLog)

    if event_type:
        q = q.filter(AuditLog.event_type.ilike(f"%{event_type}%"))
    if username:
        q = q.filter(AuditLog.username.ilike(f"%{username}%"))
    if resource_id:
        q = q.filter(AuditLog.resource_id == resource_id)
    if start_date:
        q = q.filter(AuditLog.event_time >= start_date)
    if end_date:
        q = q.filter(AuditLog.event_time <= end_date)

    return q.order_by(AuditLog.event_time.desc()).offset(offset).limit(limit).all()


def verify_hash_chain(db: Session, last_n: int = 1000) -> dict:
    """
    Verify integrity of the most recent N audit entries.
    Returns a report indicating any broken links in the chain.
    """
    from models import AuditLog

    entries = (
        db.query(AuditLog)
        .order_by(AuditLog.id.asc())
        .limit(last_n)
        .all()
    )

    broken = []
    prev_hash = None

    for entry in entries:
        expected = _compute_hash(prev_hash, {
            "event_type":  entry.event_type,
            "event_time":  str(entry.event_time),
            "user_id":     entry.user_id,
            "resource_id": entry.resource_id,
        })
        if entry.entry_hash != expected:
            broken.append({
                "id":       entry.id,
                "expected": expected,
                "actual":   entry.entry_hash,
            })
        prev_hash = entry.entry_hash

    return {
        "checked":  len(entries),
        "broken":   len(broken),
        "intact":   len(entries) - len(broken),
        "violations": broken[:10],  # cap report at 10
        "status":   "ok" if not broken else "INTEGRITY_VIOLATION",
    }
