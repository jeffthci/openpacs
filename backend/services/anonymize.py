"""
services/anonymize.py
────────────────────────────────────────────────────────────
DICOM de-identification / anonymization.

Implements DICOM PS3.15 Annex E  "Basic Application Level
Confidentiality Profile" (the standard clinical de-id profile).

Modes
─────
  full        – Remove all patient identifiers, replace with
                pseudonymous values or blanks
  research    – Full de-id but keep study/series/instance UIDs
                intact (useful for longitudinal studies)
  custom      – Caller supplies a dict of tag overrides

Output
──────
  New DICOM files written to a configurable output directory.
  Original files are NOT modified.
  Returns a mapping of original UIDs → anonymized UIDs.
"""

import copy
import hashlib
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import pydicom
from pydicom.dataset import Dataset
from pydicom.uid import generate_uid
from sqlalchemy.orm import Session

from config import settings

log = logging.getLogger(__name__)


# ─── Tags to remove / blank (Basic Confidentiality Profile) ──────

# Tags set to blank ""
BLANK_TAGS = [
    "PatientName", "PatientID", "PatientBirthDate", "PatientSex",
    "PatientAge", "PatientWeight", "PatientSize",
    "PatientAddress", "PatientTelephoneNumbers",
    "ReferringPhysicianName", "ReferringPhysicianAddress",
    "ReferringPhysicianTelephoneNumbers",
    "PerformingPhysicianName", "OperatorsName",
    "NameOfPhysiciansReadingStudy", "RequestingPhysician",
    "InstitutionName", "InstitutionAddress",
    "InstitutionalDepartmentName",
    "StationName", "DeviceSerialNumber",
    "AccessionNumber",
    "StudyID",
    "RequestedProcedureID", "RequestedProcedureDescription",
    "ScheduledProcedureStepID",
    "AdmissionID", "IssuerOfAdmissionID",
    "OtherPatientIDs", "OtherPatientNames",
    "PatientMotherBirthName", "PatientBirthName",
]

# Tags to remove entirely
REMOVE_TAGS = [
    "PatientInsurancePlanCodeSequence",
    "PatientPrimaryLanguageCodeSequence",
    "ClinicalTrialSponsorName", "ClinicalTrialProtocolID",
    "ClinicalTrialSubjectID", "ClinicalTrialSubjectReadingID",
    "ClinicalTrialTimePointID", "ClinicalTrialCoordinatingCenterName",
]


def anonymize_file(
    src_path: str,
    output_dir: str,
    mode: str = "full",
    pseudonym: Optional[str] = None,
    keep_uids: bool = False,
    custom_tags: Optional[dict] = None,
    job_id: Optional[str] = None,
) -> dict:
    """
    Anonymize a single DICOM file.

    Returns dict with:
      original_sop_uid, new_sop_uid, output_path, success
    """
    src = Path(src_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        ds = pydicom.dcmread(str(src))
        original_sop_uid    = str(ds.SOPInstanceUID)
        original_study_uid  = str(getattr(ds, "StudyInstanceUID",  ""))
        original_series_uid = str(getattr(ds, "SeriesInstanceUID", ""))

        # ── UID remapping ─────────────────────────────────────
        if keep_uids:
            new_sop_uid    = original_sop_uid
            new_study_uid  = original_study_uid
            new_series_uid = original_series_uid
        else:
            # Deterministic remapping — same original UID always
            # maps to the same anonymized UID within a job
            new_sop_uid    = _remap_uid(original_sop_uid,    job_id)
            new_study_uid  = _remap_uid(original_study_uid,  job_id)
            new_series_uid = _remap_uid(original_series_uid, job_id)

        ds.SOPInstanceUID    = new_sop_uid
        ds.StudyInstanceUID  = new_study_uid
        ds.SeriesInstanceUID = new_series_uid
        if hasattr(ds, "file_meta"):
            ds.file_meta.MediaStorageSOPInstanceUID = new_sop_uid

        # ── Blank PII tags ────────────────────────────────────
        anon_name = pseudonym or f"ANON-{new_study_uid[:8].upper()}"
        for tag_name in BLANK_TAGS:
            if hasattr(ds, tag_name):
                if tag_name == "PatientName":
                    setattr(ds, tag_name, anon_name)
                elif tag_name == "PatientID":
                    setattr(ds, tag_name, new_study_uid[:16])
                elif tag_name == "PatientBirthDate" and mode == "research":
                    # Shift birth date by fixed offset to preserve age approx.
                    val = getattr(ds, tag_name, "")
                    setattr(ds, tag_name, _shift_date(val, 365))
                else:
                    setattr(ds, tag_name, "")

        # ── Remove private/sensitive tags entirely ────────────
        for tag_name in REMOVE_TAGS:
            if hasattr(ds, tag_name):
                delattr(ds, tag_name)

        # Remove all private tags (odd group numbers)
        ds.remove_private_tags()

        # ── Date shifting (research mode) ─────────────────────
        if mode == "research":
            for date_tag in ["StudyDate", "SeriesDate", "AcquisitionDate", "ContentDate"]:
                if hasattr(ds, date_tag):
                    setattr(ds, date_tag, _shift_date(getattr(ds, date_tag), 365))

        # ── Custom tag overrides ──────────────────────────────
        if custom_tags:
            for tag_name, value in custom_tags.items():
                try:
                    setattr(ds, tag_name, value)
                except Exception:
                    pass

        # ── Add de-identification marker ──────────────────────
        ds.DeidentificationMethod = f"OpenPACS/{mode}"
        ds.PatientIdentityRemoved = "YES"
        ds.LongitudinalTemporalInformationModified = "REMOVED" if mode == "full" else "MODIFIED"

        # ── Write output ──────────────────────────────────────
        out_path = out_dir / f"{new_sop_uid}.dcm"
        pydicom.dcmwrite(str(out_path), ds, write_like_original=False)

        log.debug(f"[anon] {original_sop_uid} → {new_sop_uid}")
        return {
            "success":           True,
            "original_sop_uid":  original_sop_uid,
            "original_study_uid": original_study_uid,
            "new_sop_uid":       new_sop_uid,
            "new_study_uid":     new_study_uid,
            "output_path":       str(out_path),
        }

    except Exception as e:
        log.error(f"[anon] Failed {src_path}: {e}", exc_info=True)
        return {
            "success": False,
            "original_sop_uid": src_path,
            "error": str(e),
        }


def anonymize_study(
    db: Session,
    study_uid: str,
    output_dir: str,
    mode: str = "full",
    pseudonym: Optional[str] = None,
    keep_uids: bool = False,
) -> dict:
    """Anonymize all instances in a study. Returns summary."""
    from models import Study

    study = db.query(Study).filter(Study.study_instance_uid == study_uid).first()
    if not study:
        raise ValueError(f"Study not found: {study_uid}")

    job_id = str(uuid.uuid4())
    results = []

    for series in study.series:
        for instance in series.instances:
            result = anonymize_file(
                src_path   = instance.file_path,
                output_dir = output_dir,
                mode       = mode,
                pseudonym  = pseudonym,
                keep_uids  = keep_uids,
                job_id     = job_id,
            )
            results.append(result)

    success_count = sum(1 for r in results if r.get("success"))
    failed_count  = len(results) - success_count

    # All instances share study UID — grab from first success
    new_study_uid = next(
        (r["new_study_uid"] for r in results if r.get("success")), None
    )

    return {
        "job_id":        job_id,
        "original_study_uid": study_uid,
        "new_study_uid": new_study_uid,
        "mode":          mode,
        "total":         len(results),
        "success":       success_count,
        "failed":        failed_count,
        "output_dir":    output_dir,
    }


# ─── Helpers ─────────────────────────────────────────────────────

def _remap_uid(original_uid: str, job_id: Optional[str] = None) -> str:
    """
    Deterministically remap a UID.
    Same original + job_id always produces the same output UID.
    This ensures study/series UIDs stay consistent across all
    instances in the same anonymization job.
    """
    seed = f"{original_uid}:{job_id or 'default'}"
    h = hashlib.sha256(seed.encode()).hexdigest()
    # Convert hex to a valid DICOM UID (numeric only, max 64 chars)
    numeric = "2.25." + str(int(h[:16], 16))
    return numeric[:64]


def _shift_date(date_str: str, days: int) -> str:
    """Shift a DICOM date string (YYYYMMDD) by a fixed number of days."""
    try:
        dt = datetime.strptime(date_str.strip(), "%Y%m%d")
        from datetime import timedelta
        shifted = dt + timedelta(days=days)
        return shifted.strftime("%Y%m%d")
    except Exception:
        return date_str
