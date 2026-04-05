"""
services/partitions.py
────────────────────────────────────────────────────────────
Virtual AE Partitions — multiple logical PACS on one server.

Each partition has:
  - Its own AE Title
  - Its own DICOM port (or shared port with AE routing)
  - Its own storage path prefix
  - Its own routing rules
  - Optional independent access control

This mirrors ClearCanvas ImageServer's partition system exactly.

Architecture
────────────
  Single pynetdicom AE listens on the primary port.
  On each association, we inspect the Called AE Title and
  dispatch to the correct partition's handlers.

  Additional ports can be configured — each partition can
  optionally own a dedicated port via multiple AE instances.
"""

import logging
import threading
from pathlib import Path
from typing import Optional, List

from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


# ── DB Model (add to models.py) ───────────────────────────────────

PARTITION_MODEL_CODE = '''
class Partition(Base):
    """
    A virtual PACS partition — logical isolation of studies within
    one physical server. Mirrors ClearCanvas ImageServer Partitions.
    """
    __tablename__ = "partition"

    id               = Column(Integer, primary_key=True, index=True)
    ae_title         = Column(String(16), unique=True, nullable=False, index=True)
    description      = Column(String(255), default="")
    is_active        = Column(Boolean, default=True)

    # Storage
    storage_prefix   = Column(String(128), default="")   # subdir under DICOM_STORAGE_PATH
    storage_quota_gb = Column(Integer, nullable=True)

    # DICOM network
    dicom_port       = Column(Integer, nullable=True)    # None = use primary server port
    accept_any_ae    = Column(Boolean, default=False)    # accept studies from any calling AE

    # DICOMweb isolation
    # If True, QIDO-RS for this partition only shows its own studies
    isolated_qido    = Column(Boolean, default=True)

    # Retention
    retention_days   = Column(Integer, nullable=True)

    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship back to studies that belong to this partition
    studies = relationship("Study", back_populates="partition",
                            cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Partition {self.ae_title}>"
'''

# ── Partition-aware SCP handler ───────────────────────────────────

def build_multi_partition_scp(partitions: list):
    """
    Build a single AE that handles multiple partitions.
    Routes incoming associations to the correct partition
    based on the Called AE Title.
    """
    from pynetdicom import AE, evt
    from pynetdicom.sop_class import (
        CTImageStorage, MRImageStorage, CRImageStorage,
        DigitalXRayImagePresentationStorage, UltrasoundImageStorage,
        NuclearMedicineImageStorage, SecondaryCaptureImageStorage,
        RTStructureSetStorage, Verification,
    )
    from config import settings

    ae = AE(ae_title=settings.AE_TITLE)  # Primary AE title

    # Accept all storage SOPs for all partitions
    storage_sops = [
        CTImageStorage, MRImageStorage, CRImageStorage,
        DigitalXRayImagePresentationStorage, UltrasoundImageStorage,
        NuclearMedicineImageStorage, SecondaryCaptureImageStorage,
        RTStructureSetStorage, Verification,
        "1.2.840.10008.5.1.4.1.1.2.1",
        "1.2.840.10008.5.1.4.1.1.4.1",
        "1.2.840.10008.5.1.4.1.1.104.1",
    ]
    for sop in storage_sops:
        ae.add_supported_context(sop)

    ae.maximum_associations = 30

    # Build AE title → partition mapping
    partition_map = {p.ae_title.strip().upper(): p for p in partitions}
    # Also map primary AE
    partition_map[settings.AE_TITLE.strip().upper()] = None  # None = default partition

    def handle_store(event):
        called_ae = event.assoc.acceptor.ae_title.strip().upper()
        partition = partition_map.get(called_ae)

        ds = event.dataset
        ds.file_meta = event.file_meta

        from pathlib import Path
        from datetime import datetime

        # Determine staging path (partition-specific subdirectory)
        if partition and partition.storage_prefix:
            staging_dir = Path(settings.DICOM_STAGING_PATH) / partition.storage_prefix
        else:
            staging_dir = Path(settings.DICOM_STAGING_PATH)

        staging_dir.mkdir(parents=True, exist_ok=True)

        sop_uid = str(ds.SOPInstanceUID)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        staging_path = staging_dir / f"{timestamp}_{sop_uid}.dcm"

        try:
            ds.save_as(str(staging_path), write_like_original=False)
        except Exception as e:
            log.error(f"[partition-scp] Write failed: {e}")
            return 0xC000

        # Queue ingest with partition_id if applicable
        try:
            from services.work_queue import ingest_file
            kwargs = {"file_path": str(staging_path)}
            if partition:
                kwargs["partition_id"] = partition.id
            ingest_file.apply_async(kwargs=kwargs)
        except Exception as e:
            log.warning(f"[partition-scp] Celery unavailable: {e}")
            # Sync fallback
            from database import SessionLocal
            from services.ingest import index_dicom_file
            db = SessionLocal()
            try:
                index_dicom_file(db, str(staging_path),
                                 partition_id=partition.id if partition else None)
            finally:
                db.close()

        return 0x0000

    def handle_echo(event):
        return 0x0000

    handlers = [
        (evt.EVT_C_STORE, handle_store),
        (evt.EVT_C_ECHO,  handle_echo),
    ]

    return ae, handlers


def start_partition_servers(db: Session):
    """
    Start dedicated SCP servers for partitions that have their own port.
    Each runs in its own daemon thread.
    """
    from models import Partition
    from pynetdicom import AE, evt
    from config import settings

    partitions = db.query(Partition).filter(
        Partition.is_active == True,
        Partition.dicom_port != None,
    ).all()

    threads = []
    for partition in partitions:
        if partition.dicom_port == settings.DICOM_PORT:
            continue  # already handled by primary SCP

        ae = AE(ae_title=partition.ae_title)
        # Add storage contexts
        from pynetdicom.sop_class import (
            CTImageStorage, MRImageStorage, Verification
        )
        for sop in [CTImageStorage, MRImageStorage, Verification]:
            ae.add_supported_context(sop)

        port = partition.dicom_port
        part_id = partition.id

        def make_handler(pid):
            def handler(event):
                ds = event.dataset
                ds.file_meta = event.file_meta
                from pathlib import Path
                from datetime import datetime
                staging = Path(settings.DICOM_STAGING_PATH) / f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}_{ds.SOPInstanceUID}.dcm"
                staging.parent.mkdir(parents=True, exist_ok=True)
                ds.save_as(str(staging))
                try:
                    from services.work_queue import ingest_file
                    ingest_file.apply_async(kwargs={"file_path": str(staging), "partition_id": pid})
                except Exception:
                    pass
                return 0x0000
            return handler

        t = threading.Thread(
            target=lambda a=ae, p=port, h=make_handler(part_id): a.start_server(
                ("", p), evt_handlers=[(evt.EVT_C_STORE, h)], block=True
            ),
            daemon=True,
            name=f"scp-partition-{partition.ae_title}",
        )
        t.start()
        threads.append(t)
        log.info(f"[partition] Started SCP for {partition.ae_title} on port {port}")

    return threads
