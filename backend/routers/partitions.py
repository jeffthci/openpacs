"""
routers/partitions.py
────────────────────────────────────────────────────────────
Virtual AE Partition management API.

CRUD endpoints for partition configuration plus
partition-scoped DICOMweb QIDO-RS queries.

Partition-scoped QIDO-RS
─────────────────────────
  GET /partitions/{ae_title}/wado/studies
      → returns only studies belonging to this partition

This lets you share one PACS server between departments
(Radiology, Cardiology, Ortho) with complete study isolation.
"""

import json
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user, require_admin
from config import settings

router = APIRouter(prefix="/partitions", tags=["Partitions"])


# ── Pydantic schemas ───────────────────────────────────────────────

class PartitionCreate(BaseModel):
    ae_title:         str
    description:      str = ""
    storage_prefix:   str = ""
    storage_quota_gb: Optional[int] = None
    dicom_port:       Optional[int] = None
    accept_any_ae:    bool = False
    isolated_qido:    bool = True
    retention_days:   Optional[int] = None


class PartitionOut(PartitionCreate):
    id:         int
    is_active:  bool
    created_at: datetime
    class Config:
        from_attributes = True


# ── CRUD ───────────────────────────────────────────────────────────

@router.get("", response_model=List[PartitionOut])
def list_partitions(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    from models import Partition
    return db.query(Partition).order_by(Partition.ae_title).all()


@router.post("", response_model=PartitionOut, status_code=201)
def create_partition(
    data: PartitionCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    from models import Partition
    from pathlib import Path

    ae = data.ae_title.strip().upper()
    if len(ae) > 16:
        raise HTTPException(400, "AE Title max 16 characters")

    existing = db.query(Partition).filter(Partition.ae_title == ae).first()
    if existing:
        raise HTTPException(409, f"Partition {ae} already exists")

    # Create storage directory
    if data.storage_prefix:
        storage_dir = Path(settings.DICOM_STORAGE_PATH) / data.storage_prefix
        storage_dir.mkdir(parents=True, exist_ok=True)

    partition = Partition(ae_title=ae, **{k: v for k, v in data.dict().items() if k != "ae_title"})
    db.add(partition)
    db.commit()
    db.refresh(partition)
    return partition


@router.get("/{ae_title}", response_model=PartitionOut)
def get_partition(
    ae_title: str,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    from models import Partition
    p = db.query(Partition).filter(Partition.ae_title == ae_title.upper()).first()
    if not p:
        raise HTTPException(404, "Partition not found")
    return p


@router.put("/{ae_title}", response_model=PartitionOut)
def update_partition(
    ae_title: str,
    data: PartitionCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    from models import Partition
    p = db.query(Partition).filter(Partition.ae_title == ae_title.upper()).first()
    if not p:
        raise HTTPException(404, "Partition not found")

    for k, v in data.dict().items():
        if k != "ae_title":
            setattr(p, k, v)

    db.commit()
    db.refresh(p)
    return p


@router.delete("/{ae_title}", status_code=204)
def delete_partition(
    ae_title: str,
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    from models import Partition
    p = db.query(Partition).filter(Partition.ae_title == ae_title.upper()).first()
    if not p:
        raise HTTPException(404, "Partition not found")

    study_count = len(p.studies) if hasattr(p, "studies") else 0
    if study_count > 0:
        raise HTTPException(
            409,
            f"Partition has {study_count} studies. Reassign or delete them first."
        )

    db.delete(p)
    db.commit()


@router.post("/{ae_title}/activate", summary="Toggle partition active state")
def toggle_partition(
    ae_title: str,
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    from models import Partition
    p = db.query(Partition).filter(Partition.ae_title == ae_title.upper()).first()
    if not p:
        raise HTTPException(404, "Partition not found")
    p.is_active = not p.is_active
    db.commit()
    return {"ae_title": p.ae_title, "is_active": p.is_active}


# ── Partition-scoped QIDO-RS ───────────────────────────────────────

@router.get(
    "/{ae_title}/wado/studies",
    summary="QIDO-RS scoped to a partition"
)
def partition_qido_studies(
    ae_title:    str,
    PatientName: Optional[str] = Query(None),
    PatientID:   Optional[str] = Query(None),
    StudyDate:   Optional[str] = Query(None),
    limit: int   = Query(100, alias="_count"),
    offset: int  = Query(0,   alias="_offset"),
    db: Session  = Depends(get_db),
    _user=Depends(get_current_user),
):
    from models import Partition, Study, Patient
    from routers.dicomweb import _study_to_qido

    partition = db.query(Partition).filter(
        Partition.ae_title == ae_title.upper()
    ).first()
    if not partition:
        raise HTTPException(404, "Partition not found")

    q = db.query(Study).join(Patient).filter(Study.partition_id == partition.id)

    if PatientName:
        q = q.filter(Patient.patient_name.ilike(f"%{PatientName}%"))
    if PatientID:
        q = q.filter(Patient.patient_id.ilike(f"%{PatientID}%"))
    if StudyDate:
        q = q.filter(Study.study_date == StudyDate)

    studies = q.order_by(Study.study_date.desc()).offset(offset).limit(limit).all()
    result = [_study_to_qido(s, s.patient) for s in studies]

    return Response(
        content=json.dumps(result),
        media_type="application/dicom+json",
        headers={"Access-Control-Allow-Origin": "*"},
    )


@router.get("/{ae_title}/stats", summary="Per-partition statistics")
def partition_stats(
    ae_title: str,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    from models import Partition, Study, Series, Instance
    from sqlalchemy import func

    partition = db.query(Partition).filter(
        Partition.ae_title == ae_title.upper()
    ).first()
    if not partition:
        raise HTTPException(404, "Partition not found")

    study_count = db.query(Study).filter(Study.partition_id == partition.id).count()
    series_count = (
        db.query(Series).join(Study)
        .filter(Study.partition_id == partition.id)
        .count()
    )
    instance_count = (
        db.query(Instance).join(Series).join(Study)
        .filter(Study.partition_id == partition.id)
        .count()
    )

    # Disk usage for this partition's storage prefix
    disk_used_gb = 0
    if partition.storage_prefix:
        from pathlib import Path
        storage_path = Path(settings.DICOM_STORAGE_PATH) / partition.storage_prefix
        if storage_path.exists():
            disk_used_gb = round(
                sum(f.stat().st_size for f in storage_path.rglob("*") if f.is_file())
                / (1024 ** 3), 3
            )

    return {
        "ae_title":     partition.ae_title,
        "is_active":    partition.is_active,
        "studies":      study_count,
        "series":       series_count,
        "instances":    instance_count,
        "disk_used_gb": disk_used_gb,
        "quota_gb":     partition.storage_quota_gb,
        "quota_pct":    round(disk_used_gb / partition.storage_quota_gb * 100, 1)
                        if partition.storage_quota_gb else None,
    }
