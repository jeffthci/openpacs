"""
services/worklist.py
────────────────────────────────────────────────────────────
Modality Worklist (MWL) SCP — DICOM C-FIND handler.

Allows modalities (CT scanner, MRI, etc.) to query the server
for scheduled procedures before scanning a patient.

Flow
────
  1. RIS/HIS creates a WorklistItem via POST /api/worklist
  2. Technologist schedules the patient at the modality
  3. Modality sends C-FIND to our MWL SCP
  4. We return matching WorklistItems as DICOM datasets
  5. Technologist selects patient — correct demographics auto-fill
  6. After scanning, study arrives via C-STORE with matching AccessionNumber

Supported query levels
──────────────────────
  PATIENT  (0008,0052) = PATIENT  — query by patient demographics
  STUDY    (0008,0052) = STUDY    — not standard for MWL, ignored
  WORKLIST (0008,0052) = WORKLIST — standard MWL level
"""

import logging
from datetime import datetime, date
from typing import Optional, List
from pathlib import Path

import pydicom
from pydicom.dataset import Dataset
from pynetdicom import AE, evt
from pynetdicom.sop_class import ModalityWorklistInformationFind
from sqlalchemy.orm import Session

from config import settings

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
#  C-FIND handler
# ══════════════════════════════════════════════════════════════════

def handle_find(event):
    """
    EVT_C_FIND handler for Modality Worklist queries.
    Yields (status, dataset) pairs.
    """
    from database import SessionLocal
    from models import WorklistItem

    identifier = event.identifier
    db = SessionLocal()
    try:
        items = _query_worklist(db, identifier)
        for item in items:
            ds = _item_to_dataset(item)
            yield (0xFF00, ds)  # Pending
    except Exception as e:
        log.error(f"[MWL] C-FIND error: {e}", exc_info=True)
        yield (0xC000, None)  # Processing failure
    finally:
        db.close()

    yield (0x0000, None)  # Success


def _query_worklist(db: Session, identifier: Dataset) -> List:
    """Match C-FIND identifier against WorklistItems."""
    from models import WorklistItem

    q = db.query(WorklistItem).filter(WorklistItem.is_completed == False)  # noqa: E712

    # Patient name wildcard match
    if hasattr(identifier, "PatientName") and str(identifier.PatientName):
        name = str(identifier.PatientName).replace("*", "%").replace("?", "_")
        if "%" in name or "_" in name:
            q = q.filter(WorklistItem.patient_name.ilike(name))
        else:
            q = q.filter(WorklistItem.patient_name.ilike(f"%{name}%"))

    # Patient ID exact match
    if hasattr(identifier, "PatientID") and str(identifier.PatientID):
        q = q.filter(WorklistItem.patient_id == str(identifier.PatientID))

    # Accession number
    if hasattr(identifier, "AccessionNumber") and str(identifier.AccessionNumber):
        q = q.filter(WorklistItem.accession_number == str(identifier.AccessionNumber))

    # Scheduled date range
    if hasattr(identifier, "ScheduledProcedureStepSequence"):
        seq = identifier.ScheduledProcedureStepSequence
        if seq and len(seq) > 0:
            step = seq[0]
            if hasattr(step, "ScheduledProcedureStepStartDate"):
                sdate = str(step.ScheduledProcedureStepStartDate)
                if sdate and sdate != "":
                    if "-" in sdate:
                        start, end = sdate.split("-", 1)
                        if start:
                            q = q.filter(WorklistItem.scheduled_date >= start)
                        if end:
                            q = q.filter(WorklistItem.scheduled_date <= end)
                    else:
                        q = q.filter(WorklistItem.scheduled_date == sdate)
            # Modality
            if hasattr(step, "Modality") and str(step.Modality):
                q = q.filter(WorklistItem.modality == str(step.Modality))
            # AE Title of requesting modality
            if hasattr(step, "ScheduledStationAETitle") and str(step.ScheduledStationAETitle):
                ae = str(step.ScheduledStationAETitle)
                if ae and ae != "":
                    q = q.filter(WorklistItem.station_ae_title == ae)

    return q.order_by(WorklistItem.scheduled_date, WorklistItem.scheduled_time).limit(200).all()


def _item_to_dataset(item) -> Dataset:
    """Convert WorklistItem ORM → DICOM Dataset for C-FIND response."""
    ds = Dataset()
    ds.is_implicit_VR   = False
    ds.is_little_endian = True

    # Patient demographics
    ds.PatientName      = item.patient_name or ""
    ds.PatientID        = item.patient_id   or ""
    ds.PatientBirthDate = item.date_of_birth or ""
    ds.PatientSex       = item.sex or ""

    # Study-level
    ds.AccessionNumber      = item.accession_number or ""
    ds.ReferringPhysicianName = item.referring_physician or ""
    ds.StudyInstanceUID     = item.study_instance_uid or ""
    ds.StudyDescription     = item.study_description or ""
    ds.RequestedProcedureID = item.requested_procedure_id or ""
    ds.RequestedProcedureDescription = item.procedure_description or ""

    # Scheduled Procedure Step Sequence (required by MWL spec)
    step = Dataset()
    step.ScheduledStationAETitle         = item.station_ae_title or settings.AE_TITLE
    step.ScheduledProcedureStepStartDate = item.scheduled_date or ""
    step.ScheduledProcedureStepStartTime = item.scheduled_time or ""
    step.Modality                        = item.modality or ""
    step.ScheduledPerformingPhysicianName = item.performing_physician or ""
    step.ScheduledProcedureStepDescription = item.procedure_description or ""
    step.ScheduledProcedureStepID        = str(item.id)
    step.ScheduledStationName            = item.station_name or ""

    ds.ScheduledProcedureStepSequence = pydicom.sequence.Sequence([step])

    # Additional tags
    ds.SpecificCharacterSet = "ISO_IR 192"  # UTF-8
    ds.SOPClassUID    = ModalityWorklistInformationFind
    ds.SOPInstanceUID = pydicom.uid.generate_uid()

    return ds


# ══════════════════════════════════════════════════════════════════
#  MWL SCP startup
# ══════════════════════════════════════════════════════════════════

def build_mwl_scp() -> tuple:
    ae = AE(ae_title=settings.AE_TITLE)
    ae.add_supported_context(ModalityWorklistInformationFind)
    ae.maximum_associations = 5
    handlers = [(evt.EVT_C_FIND, handle_find)]
    return ae, handlers


def start_mwl_scp(port: Optional[int] = None):
    """Start the MWL SCP — run in a background thread."""
    ae, handlers = build_mwl_scp()
    mwl_port = port or int(getattr(settings, "MWL_PORT", 11113))
    log.info(f"[MWL] Starting Modality Worklist SCP on port {mwl_port}")
    ae.start_server(("", mwl_port), evt_handlers=handlers, block=True)
