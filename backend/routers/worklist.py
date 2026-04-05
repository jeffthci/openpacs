"""
routers/worklist.py
────────────────────────────────────────────────────────────
Modality Worklist (MWL) REST API.

RIS/HIS systems (or manual entry) create WorklistItems here.
Modalities query them via the DICOM C-FIND MWL SCP (services/worklist.py).

Endpoints
─────────
  GET    /api/worklist              list all pending items (with filters)
  POST   /api/worklist              create a scheduled procedure
  GET    /api/worklist/{id}         get single item
  PUT    /api/worklist/{id}         update (reschedule, change modality, etc.)
  DELETE /api/worklist/{id}         cancel a scheduled procedure
  POST   /api/worklist/{id}/complete mark as completed (study received)
  GET    /api/worklist/today        items scheduled for today
  GET    /api/worklist/overdue      items past scheduled date, not completed
"""

from datetime import datetime, date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user, require_admin
from models import WorklistItem

router = APIRouter(prefix="/worklist", tags=["Modality Worklist"])


# ─── Schemas ──────────────────────────────────────────────────────

class WorklistItemCreate(BaseModel):
    patient_name:             str
    patient_id:               str
    date_of_birth:            Optional[str] = None
    sex:                      Optional[str] = None
    accession_number:         Optional[str] = None
    study_instance_uid:       Optional[str] = None
    study_description:        Optional[str] = None
    requested_procedure_id:   Optional[str] = None
    procedure_description:    Optional[str] = None
    modality:                 Optional[str] = None
    scheduled_date:           Optional[str] = None  # YYYYMMDD
    scheduled_time:           Optional[str] = None  # HHMMSS
    station_ae_title:         Optional[str] = None
    station_name:             Optional[str] = None
    performing_physician:     Optional[str] = None
    referring_physician:      Optional[str] = None
    priority:                 Optional[str] = "ROUTINE"  # STAT | URGENT | ROUTINE
    notes:                    Optional[str] = None


class WorklistItemOut(WorklistItemCreate):
    id:           int
    is_completed: bool
    completed_at: Optional[datetime]
    created_at:   datetime
    class Config:
        from_attributes = True


# ─── Endpoints ───────────────────────────────────────────────────

@router.get("", response_model=List[WorklistItemOut])
def list_worklist(
    patient_name:   Optional[str] = Query(None),
    patient_id:     Optional[str] = Query(None),
    modality:       Optional[str] = Query(None),
    scheduled_date: Optional[str] = Query(None),
    show_completed: bool           = Query(False),
    limit:          int            = Query(200),
    offset:         int            = Query(0),
    db: Session     = Depends(get_db),
    _user           = Depends(get_current_user),
):
    q = db.query(WorklistItem)
    if not show_completed:
        q = q.filter(WorklistItem.is_completed == False)  # noqa: E712
    if patient_name:
        q = q.filter(WorklistItem.patient_name.ilike(f"%{patient_name}%"))
    if patient_id:
        q = q.filter(WorklistItem.patient_id == patient_id)
    if modality:
        q = q.filter(WorklistItem.modality == modality.upper())
    if scheduled_date:
        q = q.filter(WorklistItem.scheduled_date == scheduled_date)
    return q.order_by(
        WorklistItem.scheduled_date,
        WorklistItem.scheduled_time
    ).offset(offset).limit(limit).all()


@router.get("/today", response_model=List[WorklistItemOut])
def worklist_today(
    db: Session = Depends(get_db),
    _user       = Depends(get_current_user),
):
    today = date.today().strftime("%Y%m%d")
    return (
        db.query(WorklistItem)
        .filter(
            WorklistItem.scheduled_date == today,
            WorklistItem.is_completed   == False,  # noqa: E712
        )
        .order_by(WorklistItem.scheduled_time)
        .all()
    )


@router.get("/overdue", response_model=List[WorklistItemOut])
def worklist_overdue(
    db: Session = Depends(get_db),
    _user       = Depends(get_current_user),
):
    today = date.today().strftime("%Y%m%d")
    return (
        db.query(WorklistItem)
        .filter(
            WorklistItem.scheduled_date < today,
            WorklistItem.is_completed   == False,  # noqa: E712
        )
        .order_by(WorklistItem.scheduled_date)
        .all()
    )


@router.post("", response_model=WorklistItemOut, status_code=201)
def create_worklist_item(
    data: WorklistItemCreate,
    db:   Session = Depends(get_db),
    _user         = Depends(get_current_user),
):
    import pydicom
    item = WorklistItem(
        **data.dict(),
        study_instance_uid = data.study_instance_uid or str(pydicom.uid.generate_uid()),
        accession_number   = data.accession_number   or _generate_accession(),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/{item_id}", response_model=WorklistItemOut)
def get_worklist_item(
    item_id: int,
    db:      Session = Depends(get_db),
    _user            = Depends(get_current_user),
):
    item = db.query(WorklistItem).filter(WorklistItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Worklist item not found")
    return item


@router.put("/{item_id}", response_model=WorklistItemOut)
def update_worklist_item(
    item_id: int,
    data:    WorklistItemCreate,
    db:      Session = Depends(get_db),
    _user            = Depends(get_current_user),
):
    item = db.query(WorklistItem).filter(WorklistItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Worklist item not found")
    for field, value in data.dict(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=204)
def cancel_worklist_item(
    item_id: int,
    db:      Session = Depends(get_db),
    _user            = Depends(get_current_user),
):
    item = db.query(WorklistItem).filter(WorklistItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Worklist item not found")
    db.delete(item)
    db.commit()


@router.post("/{item_id}/complete", response_model=WorklistItemOut)
def complete_worklist_item(
    item_id: int,
    db:      Session = Depends(get_db),
    _user            = Depends(get_current_user),
):
    """Mark a scheduled procedure as completed (study received)."""
    item = db.query(WorklistItem).filter(WorklistItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Worklist item not found")
    item.is_completed = True
    item.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return item


# ─── Helpers ─────────────────────────────────────────────────────

def _generate_accession() -> str:
    """Generate a unique accession number: ACC-YYYYMMDD-NNNNNN"""
    import random
    today = date.today().strftime("%Y%m%d")
    return f"ACC-{today}-{random.randint(100000, 999999)}"
