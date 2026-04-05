"""
services/ingest.py
────────────────────────────────────────────────────────────
Shared DICOM ingestion logic.

Used by:
  - pynetdicom C-STORE SCP handler (network receive)
  - STOW-RS endpoint (HTTP receive)
  - Manual file import CLI

Handles:
  - Duplicate SOP UID detection with configurable policy
  - Patient / Study / Series / Instance upsert
  - Filesystem organisation
  - Tag extraction + DB indexing
"""

import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

import pydicom
from pydicom.dataset import Dataset
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from models import Patient, Study, Series, Instance
from config import settings

log = logging.getLogger(__name__)


# ─── Duplicate policy options ─────────────────────────────────────────────
POLICY_REJECT    = "reject"     # refuse duplicate, return error
POLICY_OVERWRITE = "overwrite"  # replace existing file + DB row
POLICY_IGNORE    = "ignore"     # silently skip, return success


def _tag(ds: Dataset, keyword: str, default: str = "") -> str:
    """Safe tag extraction — never raises."""
    try:
        val = getattr(ds, keyword, None)
        return str(val).strip() if val is not None else default
    except Exception:
        return default


def _tag_int(ds: Dataset, keyword: str, default: Optional[int] = None) -> Optional[int]:
    try:
        val = getattr(ds, keyword, None)
        return int(val) if val is not None else default
    except Exception:
        return default


def get_or_create_patient(db: Session, ds: Dataset) -> Patient:
    patient_id = _tag(ds, "PatientID", "UNKNOWN")
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        patient = Patient(
            patient_id    = patient_id,
            patient_name  = _tag(ds, "PatientName"),
            date_of_birth = _tag(ds, "PatientBirthDate"),
            sex           = _tag(ds, "PatientSex"),
        )
        db.add(patient)
        db.flush()
        log.info(f"Created patient: {patient_id}")
    return patient


def get_or_create_study(db: Session, ds: Dataset, patient: Patient) -> Study:
    study_uid = _tag(ds, "StudyInstanceUID")
    if not study_uid:
        raise ValueError("DICOM file missing StudyInstanceUID")

    study = db.query(Study).filter(Study.study_instance_uid == study_uid).first()
    if not study:
        study = Study(
            patient_id              = patient.id,
            study_instance_uid      = study_uid,
            study_date              = _tag(ds, "StudyDate"),
            study_time              = _tag(ds, "StudyTime"),
            study_description       = _tag(ds, "StudyDescription"),
            study_id                = _tag(ds, "StudyID"),
            accession_number        = _tag(ds, "AccessionNumber"),
            referring_physician     = _tag(ds, "ReferringPhysicianName"),
            modalities_in_study     = [],
        )
        db.add(study)
        db.flush()
        log.info(f"Created study: {study_uid}")
    return study


def get_or_create_series(db: Session, ds: Dataset, study: Study) -> Series:
    series_uid = _tag(ds, "SeriesInstanceUID")
    if not series_uid:
        raise ValueError("DICOM file missing SeriesInstanceUID")

    series = db.query(Series).filter(Series.series_instance_uid == series_uid).first()
    if not series:
        series = Series(
            study_id             = study.id,
            series_instance_uid  = series_uid,
            series_number        = _tag_int(ds, "SeriesNumber"),
            series_description   = _tag(ds, "SeriesDescription"),
            modality             = _tag(ds, "Modality"),
            body_part_examined   = _tag(ds, "BodyPartExamined"),
            performed_procedure  = _tag(ds, "PerformedProcedureStepDescription"),
        )
        db.add(series)
        db.flush()

        # Update modalities list on study
        modality = _tag(ds, "Modality")
        if modality and modality not in (study.modalities_in_study or []):
            mods = list(study.modalities_in_study or [])
            mods.append(modality)
            study.modalities_in_study = mods

        log.info(f"Created series: {series_uid}")
    return series


def check_duplicate(db: Session, sop_uid: str, policy: str) -> tuple[bool, Optional[Instance]]:
    """
    Returns (is_duplicate, existing_instance).
    is_duplicate=True means caller should handle according to policy.
    """
    existing = db.query(Instance).filter(
        Instance.sop_instance_uid == sop_uid
    ).first()
    return (existing is not None, existing)


def index_dicom_file(db: Session, file_path: str, ds: Optional[Dataset] = None) -> Instance:
    """
    Core ingest function. Reads DICOM file, upserts all DB records.
    Returns the Instance ORM object.

    Duplicate handling is governed by settings.DUPLICATE_SOP_POLICY:
      - "reject"    → raises DuplicateSOPError
      - "overwrite" → updates existing record + file
      - "ignore"    → returns existing record unchanged
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"DICOM file not found: {file_path}")

    if ds is None:
        ds = pydicom.dcmread(str(path))

    sop_uid = _tag(ds, "SOPInstanceUID")
    if not sop_uid:
        raise ValueError(f"File has no SOPInstanceUID: {file_path}")

    # ── Duplicate check ───────────────────────────────────────────────────
    policy = getattr(settings, "DUPLICATE_SOP_POLICY", POLICY_IGNORE)
    is_dup, existing = check_duplicate(db, sop_uid, policy)

    if is_dup:
        if policy == POLICY_REJECT:
            raise DuplicateSOPError(f"SOP {sop_uid} already exists (policy=reject)")
        elif policy == POLICY_IGNORE:
            log.debug(f"Duplicate SOP ignored: {sop_uid}")
            return existing
        elif policy == POLICY_OVERWRITE:
            log.info(f"Overwriting SOP: {sop_uid}")
            # Delete old file if different path
            if existing.file_path != str(path) and Path(existing.file_path).exists():
                Path(existing.file_path).unlink()
            db.delete(existing)
            db.flush()

    # ── Upsert hierarchy ──────────────────────────────────────────────────
    patient = get_or_create_patient(db, ds)
    study   = get_or_create_study(db, ds, patient)
    series  = get_or_create_series(db, ds, study)

    # ── Build destination path using configured storage roots ─────────────
    dest_path = _resolve_storage_path(ds, path, patient.patient_id, study.study_instance_uid, series.series_instance_uid, sop_uid)

    # Move file if it landed in a temp location
    if str(path) != str(dest_path):
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        path.rename(dest_path)
        path = dest_path

    # ── Create Instance record ────────────────────────────────────────────
    instance = Instance(
        series_id         = series.id,
        sop_instance_uid  = sop_uid,
        sop_class_uid     = _tag(ds, "SOPClassUID"),
        instance_number   = _tag_int(ds, "InstanceNumber"),
        file_path         = str(path),
        file_size         = path.stat().st_size,
        transfer_syntax   = getattr(ds.file_meta, "TransferSyntaxUID", None) if hasattr(ds, "file_meta") else None,
        rows              = _tag_int(ds, "Rows"),
        columns           = _tag_int(ds, "Columns"),
        number_of_frames  = _tag_int(ds, "NumberOfFrames", 1),
        bits_allocated    = _tag_int(ds, "BitsAllocated"),
        photometric       = _tag(ds, "PhotometricInterpretation"),
        window_center     = _tag(ds, "WindowCenter"),
        window_width      = _tag(ds, "WindowWidth"),
        acquired_at       = _parse_datetime(
                                _tag(ds, "AcquisitionDate"),
                                _tag(ds, "AcquisitionTime")
                            ),
    )
    db.add(instance)

    # ── Update study-level counts ─────────────────────────────────────────
    study.number_of_study_related_series    = db.query(Series).filter(Series.study_id == study.id).count()
    study.number_of_study_related_instances = (
        db.query(Instance)
        .join(Series)
        .filter(Series.study_id == study.id)
        .count()
    ) + 1  # +1 for the one we just added (not committed yet)

    series.number_of_series_related_instances = (
        db.query(Instance).filter(Instance.series_id == series.id).count()
    ) + 1

    try:
        db.commit()
        db.refresh(instance)
        log.info(f"Indexed SOP {sop_uid} → {path}")
    except IntegrityError:
        db.rollback()
        # Race condition — another worker got there first; return existing
        existing = db.query(Instance).filter(Instance.sop_instance_uid == sop_uid).first()
        return existing

    return instance


def _resolve_storage_path(
    ds: Dataset,
    current_path: Path,
    patient_id: str,
    study_uid: str,
    series_uid: str,
    sop_uid: str,
) -> Path:
    """
    Determine the canonical storage path for a DICOM file.

    Uses STORAGE_ROOTS from settings — a list of dicts:
      [{"path": "/mnt/fast", "type": "primary", "max_gb": 500},
       {"path": "/mnt/archive", "type": "archive", "max_gb": 10000}]

    For now, picks the first available root with space.
    Later phases add tiering logic.
    """
    roots = getattr(settings, "STORAGE_ROOTS", None)
    if roots:
        # Pick first root with space
        for root_config in roots:
            root = Path(root_config["path"])
            if root.exists():
                break
    else:
        # Fallback to single legacy path
        root = Path(settings.DICOM_STORAGE_PATH)

    return root / patient_id / study_uid / series_uid / f"{sop_uid}.dcm"


def _parse_datetime(date_str: str, time_str: str) -> Optional[datetime]:
    try:
        date_str = date_str.strip()
        time_str = time_str.strip()[:6]  # HHMMSS
        if date_str and time_str:
            return datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")
        elif date_str:
            return datetime.strptime(date_str, "%Y%m%d")
    except Exception:
        pass
    return None


class DuplicateSOPError(Exception):
    """Raised when duplicate SOP policy is 'reject'."""
    pass
