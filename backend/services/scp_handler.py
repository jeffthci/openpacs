"""
services/scp_handler.py
────────────────────────────────────────────────────────────
pynetdicom C-STORE SCP handler — updated to use async work queue.

Drop-in replacement for the existing synchronous handler.
Key changes vs original:
  1. Writes file to temp location immediately (fast — keeps SCP responsive)
  2. Dispatches ingest_file.delay() to Celery queue
  3. Returns 0x0000 Success as soon as file is safely on disk

This means the calling modality gets a fast ACK and indexing
happens in the background — exactly how real PACS systems work.
"""

import logging
import tempfile
from pathlib import Path
from datetime import datetime

import pydicom
from pynetdicom import AE, evt
from pynetdicom.sop_class import Verification
from pynetdicom.status import GENERAL_STATUS

from config import settings

log = logging.getLogger(__name__)


def handle_store(event):
    """
    EVT_C_STORE handler.
    Writes the DICOM dataset to a staging directory, then
    dispatches async indexing via Celery.
    """
    ds = event.dataset
    ds.file_meta = event.file_meta

    # Build staging path (fast temp storage before indexing moves it)
    staging_dir = Path(settings.DICOM_STAGING_PATH)
    staging_dir.mkdir(parents=True, exist_ok=True)

    sop_uid = str(ds.SOPInstanceUID)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    staging_path = staging_dir / f"{timestamp}_{sop_uid}.dcm"

    try:
        ds.save_as(str(staging_path), write_like_original=False)
        log.debug(f"[SCP] Staged: {staging_path.name}")
    except Exception as e:
        log.error(f"[SCP] Failed to write file: {e}")
        return 0xC000  # Processing failure

    # Dispatch to Celery work queue (non-blocking)
    try:
        from services.work_queue import ingest_file
        ingest_file.delay(str(staging_path))
        log.info(f"[SCP] Queued for ingest: {sop_uid}")
    except Exception as e:
        # If Celery is unavailable, fall back to synchronous ingest
        log.warning(f"[SCP] Celery unavailable ({e}), falling back to sync ingest")
        try:
            from database import SessionLocal
            from services.ingest import index_dicom_file
            db = SessionLocal()
            try:
                index_dicom_file(db, str(staging_path))
            finally:
                db.close()
        except Exception as e2:
            log.error(f"[SCP] Sync ingest failed: {e2}")
            return 0xC000

    return 0x0000  # Success


def handle_echo(event):
    """EVT_C_ECHO handler — C-ECHO verification."""
    log.debug(f"[SCP] C-ECHO from {event.assoc.requestor.ae_title}")
    return 0x0000


def build_scp() -> AE:
    """
    Build and return the configured AE for the C-STORE SCP.
    Call ae.start_server() to start listening.
    """
    from pynetdicom.sop_class import (
        CTImageStorage, MRImageStorage, CRImageStorage,
        DigitalXRayImagePresentationStorage,
        UltrasoundImageStorage, NuclearMedicineImageStorage,
        SecondaryCaptureImageStorage, RTStructureSetStorage,
        XRayAngiographicImageStorage, BreastTomosynthesisImageStorage,
        PositronEmissionTomographyImageStorage,
    )

    ae = AE(ae_title=settings.AE_TITLE)

    # Accept all common storage SOPs
    storage_sops = [
        CTImageStorage,
        MRImageStorage,
        CRImageStorage,
        DigitalXRayImagePresentationStorage,
        UltrasoundImageStorage,
        NuclearMedicineImageStorage,
        SecondaryCaptureImageStorage,
        RTStructureSetStorage,
        XRayAngiographicImageStorage,
        PositronEmissionTomographyImageStorage,
        Verification,
        # Extended SOPs
        "1.2.840.10008.5.1.4.1.1.2.1",   # Enhanced CT
        "1.2.840.10008.5.1.4.1.1.4.1",   # Enhanced MR
        "1.2.840.10008.5.1.4.1.1.4.2",   # Enhanced MR Color
        "1.2.840.10008.5.1.4.1.1.12.1",  # XA
        "1.2.840.10008.5.1.4.1.1.12.1.1",# Enhanced XA
        "1.2.840.10008.5.1.4.1.1.481.3", # RT Structure Set
        "1.2.840.10008.5.1.4.1.1.481.5", # RT Plan
        "1.2.840.10008.5.1.4.1.1.104.1", # Encapsulated PDF
        "1.2.840.10008.5.1.4.1.1.7",     # Secondary Capture
        "1.2.840.10008.5.1.4.1.1.6.1",   # US Image
    ]

    for sop in storage_sops:
        ae.add_supported_context(sop)

    ae.maximum_associations = 10
    ae.maximum_pdu_size = 0  # unlimited

    handlers = [
        (evt.EVT_C_STORE, handle_store),
        (evt.EVT_C_ECHO,  handle_echo),
    ]

    return ae, handlers


def start_scp():
    """Start the DICOM SCP in blocking mode (run in a thread)."""
    ae, handlers = build_scp()
    port = int(settings.DICOM_PORT)
    log.info(f"[SCP] Starting DICOM SCP — AE: {settings.AE_TITLE}, Port: {port}")
    ae.start_server(("", port), evt_handlers=handlers, block=True)
