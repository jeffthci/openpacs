"""
routers/admin.py
────────────────────────────────────────────────────────────
Admin API endpoints for managing the PACS server:
  - Storage filesystem CRUD
  - Routing rule CRUD
  - Work queue status / monitoring
  - Server stats (study count, disk usage, etc.)
"""

import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import (
    Study, Series, Instance, Patient,
    StorageFilesystem, RoutingRule, RoutingDestination,
)
from auth import get_current_user, require_admin
from config import settings

router = APIRouter(prefix="/admin", tags=["Admin"])


# ══════════════════════════════════════════════════════════════════════════════
#  Pydantic schemas
# ══════════════════════════════════════════════════════════════════════════════

class FilesystemCreate(BaseModel):
    path:       str
    label:      str = ""
    tier:       str = "primary"
    max_gb:     Optional[int] = None
    is_writable: bool = True


class FilesystemOut(FilesystemCreate):
    id:              int
    is_active:       bool
    total_bytes:     int
    used_bytes:      int
    available_bytes: int
    percent_used:    float
    class Config:
        from_attributes = True


class DestinationCreate(BaseModel):
    ae_title:    str
    host:        str
    port:        int = 104
    description: str = ""


class RoutingRuleCreate(BaseModel):
    name:          str
    description:   str = ""
    priority:      int = 100
    is_active:     bool = True
    stop_on_match: bool = True
    conditions:    dict = {}
    destinations:  List[DestinationCreate] = []


class RoutingRuleOut(BaseModel):
    id:            int
    name:          str
    description:   str
    priority:      int
    is_active:     bool
    stop_on_match: bool
    conditions:    dict
    destinations:  List[DestinationCreate]
    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════════════════════
#  Server stats dashboard
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/stats", summary="Server overview stats")
def get_stats(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    patient_count  = db.query(Patient).count()
    study_count    = db.query(Study).count()
    series_count   = db.query(Series).count()
    instance_count = db.query(Instance).count()

    # Disk usage from storage roots
    filesystems = db.query(StorageFilesystem).filter(StorageFilesystem.is_active == True).all()
    total_gb    = sum(fs.total_bytes     for fs in filesystems) / (1024**3)
    used_gb     = sum(fs.used_bytes      for fs in filesystems) / (1024**3)
    free_gb     = sum(fs.available_bytes for fs in filesystems) / (1024**3)

    # Fallback to single path if no filesystems configured
    if not filesystems:
        try:
            usage = shutil.disk_usage(settings.DICOM_STORAGE_PATH)
            total_gb = usage.total / (1024**3)
            used_gb  = usage.used  / (1024**3)
            free_gb  = usage.free  / (1024**3)
        except Exception:
            total_gb = used_gb = free_gb = 0

    return {
        "patients":  patient_count,
        "studies":   study_count,
        "series":    series_count,
        "instances": instance_count,
        "storage": {
            "total_gb": round(total_gb, 2),
            "used_gb":  round(used_gb,  2),
            "free_gb":  round(free_gb,  2),
            "percent":  round((used_gb / total_gb * 100) if total_gb else 0, 1),
        },
        "server": {
            "ae_title":    settings.AE_TITLE,
            "dicom_port":  settings.DICOM_PORT,
            "wado_base":   settings.WADO_BASE_URL,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Storage filesystem management
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/filesystems", response_model=List[FilesystemOut])
def list_filesystems(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    return db.query(StorageFilesystem).all()


@router.post("/filesystems", response_model=FilesystemOut, status_code=201)
def add_filesystem(
    data: FilesystemCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    path = Path(data.path)
    if not path.exists():
        raise HTTPException(400, f"Path does not exist: {data.path}")

    fs = StorageFilesystem(**data.dict())
    try:
        usage = shutil.disk_usage(data.path)
        fs.total_bytes     = usage.total
        fs.used_bytes      = usage.used
        fs.available_bytes = usage.free
        fs.percent_used    = round(usage.used / usage.total * 100, 1)
    except Exception:
        pass

    db.add(fs)
    db.commit()
    db.refresh(fs)
    return fs


@router.delete("/filesystems/{fs_id}", status_code=204)
def remove_filesystem(
    fs_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    fs = db.query(StorageFilesystem).filter(StorageFilesystem.id == fs_id).first()
    if not fs:
        raise HTTPException(404, "Filesystem not found")
    db.delete(fs)
    db.commit()


# ══════════════════════════════════════════════════════════════════════════════
#  Routing rules management
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/routing/rules", response_model=List[RoutingRuleOut])
def list_routing_rules(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    return db.query(RoutingRule).order_by(RoutingRule.priority).all()


@router.post("/routing/rules", response_model=RoutingRuleOut, status_code=201)
def create_routing_rule(
    data: RoutingRuleCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    rule = RoutingRule(
        name          = data.name,
        description   = data.description,
        priority      = data.priority,
        is_active     = data.is_active,
        stop_on_match = data.stop_on_match,
        conditions    = data.conditions,
    )
    db.add(rule)
    db.flush()

    for dest_data in data.destinations:
        dest = RoutingDestination(rule_id=rule.id, **dest_data.dict())
        db.add(dest)

    db.commit()
    db.refresh(rule)
    return rule


@router.put("/routing/rules/{rule_id}", response_model=RoutingRuleOut)
def update_routing_rule(
    rule_id: int,
    data: RoutingRuleCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    rule = db.query(RoutingRule).filter(RoutingRule.id == rule_id).first()
    if not rule:
        raise HTTPException(404, "Rule not found")

    rule.name          = data.name
    rule.description   = data.description
    rule.priority      = data.priority
    rule.is_active     = data.is_active
    rule.stop_on_match = data.stop_on_match
    rule.conditions    = data.conditions

    # Replace destinations
    for d in rule.destinations:
        db.delete(d)
    db.flush()
    for dest_data in data.destinations:
        dest = RoutingDestination(rule_id=rule.id, **dest_data.dict())
        db.add(dest)

    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/routing/rules/{rule_id}", status_code=204)
def delete_routing_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    rule = db.query(RoutingRule).filter(RoutingRule.id == rule_id).first()
    if not rule:
        raise HTTPException(404, "Rule not found")
    db.delete(rule)
    db.commit()


@router.post("/routing/rules/{rule_id}/test", summary="Test a routing rule against a study")
def test_routing_rule(
    rule_id:   int,
    study_uid: str,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Dry-run a routing rule against a specific study (no actual forwarding)."""
    from services.routing import _rule_matches

    rule  = db.query(RoutingRule).filter(RoutingRule.id == rule_id).first()
    study = db.query(Study).filter(Study.study_instance_uid == study_uid).first()
    if not rule:
        raise HTTPException(404, "Rule not found")
    if not study:
        raise HTTPException(404, "Study not found")

    matches = _rule_matches(rule, study)
    return {
        "rule_id":   rule_id,
        "study_uid": study_uid,
        "matches":   matches,
        "conditions": rule.conditions,
        "study_modalities": study.modalities_in_study,
        "study_description": study.study_description,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Work queue status
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/queue/status", summary="Work queue health + pending task count")
def queue_status(_user=Depends(get_current_user)):
    try:
        from services.work_queue import celery_app
        inspect = celery_app.control.inspect(timeout=2)
        active  = inspect.active()  or {}
        reserved = inspect.reserved() or {}

        active_count   = sum(len(v) for v in active.values())
        reserved_count = sum(len(v) for v in reserved.values())

        return {
            "status":   "ok",
            "active":   active_count,
            "reserved": reserved_count,
            "workers":  list(active.keys()),
        }
    except Exception as e:
        return {
            "status": "unavailable",
            "detail": str(e),
            "note":   "Start Celery workers to enable background processing",
        }


@router.post("/queue/retry-failed", summary="Retry all failed ingest tasks")
def retry_failed_ingests(_user=Depends(require_admin)):
    """Re-queue any DICOM files in the staging directory that failed ingest."""
    from services.work_queue import ingest_file

    staging_dir = Path(settings.DICOM_STAGING_PATH)
    if not staging_dir.exists():
        return {"queued": 0}

    queued = 0
    for f in staging_dir.glob("*.dcm"):
        ingest_file.delay(str(f))
        queued += 1

    return {"queued": queued}
