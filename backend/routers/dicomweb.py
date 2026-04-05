"""
routers/dicomweb.py
────────────────────────────────────────────────────────────
DICOMweb REST API  (QIDO-RS / WADO-RS / STOW-RS)
Compatible with OHIF Viewer, Cornerstone.js, and any
standard DICOMweb client.

Endpoints
---------
QIDO-RS  (Query)
  GET  /wado/studies                        – search studies
  GET  /wado/studies/{studyUID}/series      – search series
  GET  /wado/studies/{studyUID}/series/{seriesUID}/instances  – search instances

WADO-RS  (Retrieve)
  GET  /wado/studies/{studyUID}             – retrieve all instances in study
  GET  /wado/studies/{studyUID}/series/{seriesUID}            – retrieve series
  GET  /wado/studies/{studyUID}/series/{seriesUID}/instances/{instanceUID}
  GET  /wado/studies/{studyUID}/series/{seriesUID}/instances/{instanceUID}/frames/{frames}
  GET  /wado/studies/{studyUID}/series/{seriesUID}/instances/{instanceUID}/metadata

STOW-RS  (Store)
  POST /wado/studies                        – store DICOM instances
  POST /wado/studies/{studyUID}             – store into specific study
"""

import io
import os
import json
import email
import email.policy
from pathlib import Path
from typing import Optional, List
from uuid import uuid4

import pydicom
from pydicom.uid import ExplicitVRLittleEndian
from fastapi import (
    APIRouter, Depends, HTTPException, Request,
    Query, Response, status
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from models import Patient, Study, Series, Instance
from config import settings
from auth import get_current_user

router = APIRouter(prefix="/wado", tags=["DICOMweb"])

# ─── MIME types ──────────────────────────────────────────────────────────────
MIME_DICOM      = "application/dicom"
MIME_JSON       = "application/dicom+json"
MIME_OCTET      = "application/octet-stream"
MULTIPART_DICOM = "multipart/related; type=\"application/dicom\""
MULTIPART_META  = "multipart/related; type=\"application/dicom+json\""


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _study_to_qido(study: Study, patient: Patient) -> dict:
    """Convert ORM Study → QIDO-RS JSON response dict."""
    return {
        "00080020": {"vr": "DA", "Value": [study.study_date or ""]},
        "00080030": {"vr": "TM", "Value": [study.study_time or ""]},
        "00080050": {"vr": "SH", "Value": [study.accession_number or ""]},
        "00080061": {"vr": "CS", "Value": study.modalities_in_study or []},
        "00080090": {"vr": "PN", "Value": [{"Alphabetic": study.referring_physician or ""}]},
        "00081190": {"vr": "UR", "Value": [f"{settings.WADO_BASE_URL}/wado/studies/{study.study_instance_uid}"]},
        "00100010": {"vr": "PN", "Value": [{"Alphabetic": patient.patient_name or ""}]},
        "00100020": {"vr": "LO", "Value": [patient.patient_id or ""]},
        "00100030": {"vr": "DA", "Value": [patient.date_of_birth or ""]},
        "00100040": {"vr": "CS", "Value": [patient.sex or ""]},
        "0020000D": {"vr": "UI", "Value": [study.study_instance_uid]},
        "00200010": {"vr": "SH", "Value": [study.study_id or ""]},
        "00201206": {"vr": "IS", "Value": [str(study.number_of_study_related_series or 0)]},
        "00201208": {"vr": "IS", "Value": [str(study.number_of_study_related_instances or 0)]},
        "00081030": {"vr": "LO", "Value": [study.study_description or ""]},
    }


def _series_to_qido(series: Series) -> dict:
    return {
        "00080060": {"vr": "CS", "Value": [series.modality or ""]},
        "0008103E": {"vr": "LO", "Value": [series.series_description or ""]},
        "00081190": {"vr": "UR", "Value": [
            f"{settings.WADO_BASE_URL}/wado/studies/{series.study.study_instance_uid}"
            f"/series/{series.series_instance_uid}"
        ]},
        "0020000E": {"vr": "UI", "Value": [series.series_instance_uid]},
        "00200011": {"vr": "IS", "Value": [str(series.series_number or 0)]},
        "00201209": {"vr": "IS", "Value": [str(series.number_of_series_related_instances or 0)]},
    }


def _instance_to_qido(instance: Instance, series: Series, study: Study) -> dict:
    return {
        "00080016": {"vr": "UI", "Value": [instance.sop_class_uid or ""]},
        "00080018": {"vr": "UI", "Value": [instance.sop_instance_uid]},
        "00081190": {"vr": "UR", "Value": [
            f"{settings.WADO_BASE_URL}/wado/studies/{study.study_instance_uid}"
            f"/series/{series.series_instance_uid}"
            f"/instances/{instance.sop_instance_uid}"
        ]},
        "00200013": {"vr": "IS", "Value": [str(instance.instance_number or 0)]},
        "00280008": {"vr": "IS", "Value": [str(instance.number_of_frames or 1)]},
        "00280010": {"vr": "US", "Value": [instance.rows or 0]},
        "00280011": {"vr": "US", "Value": [instance.columns or 0]},
    }


def _build_multipart(parts: List[bytes], content_type: str = MIME_DICOM) -> tuple[bytes, str]:
    """Build a multipart/related response body."""
    boundary = uuid4().hex
    body = b""
    for part in parts:
        body += f"\r\n--{boundary}\r\nContent-Type: {content_type}\r\n\r\n".encode()
        body += part
    body += f"\r\n--{boundary}--\r\n".encode()
    mime = f'multipart/related; type="{content_type}"; boundary="{boundary}"'
    return body, mime


def _load_dicom(instance: Instance) -> pydicom.Dataset:
    path = Path(instance.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {instance.file_path}")
    return pydicom.dcmread(str(path))


# ══════════════════════════════════════════════════════════════════════════════
#  QIDO-RS  —  Query
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/studies", summary="QIDO-RS: Search Studies")
def qido_search_studies(
    # Standard QIDO query params
    PatientName:       Optional[str] = Query(None, alias="PatientName"),
    PatientID:         Optional[str] = Query(None, alias="PatientID"),
    StudyDate:         Optional[str] = Query(None, alias="StudyDate"),
    StudyInstanceUID:  Optional[str] = Query(None, alias="StudyInstanceUID"),
    AccessionNumber:   Optional[str] = Query(None, alias="AccessionNumber"),
    ModalitiesInStudy: Optional[str] = Query(None, alias="ModalitiesInStudy"),
    limit:  int = Query(100, alias="_count"),
    offset: int = Query(0,   alias="_offset"),
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    q = db.query(Study).join(Patient)

    if PatientName:
        q = q.filter(Patient.patient_name.ilike(f"%{PatientName}%"))
    if PatientID:
        q = q.filter(Patient.patient_id.ilike(f"%{PatientID}%"))
    if StudyDate:
        # Support range: 20230101-20231231
        if "-" in StudyDate:
            start, end = StudyDate.split("-", 1)
            q = q.filter(Study.study_date >= start, Study.study_date <= end)
        else:
            q = q.filter(Study.study_date == StudyDate)
    if StudyInstanceUID:
        q = q.filter(Study.study_instance_uid == StudyInstanceUID)
    if AccessionNumber:
        q = q.filter(Study.accession_number == AccessionNumber)
    if ModalitiesInStudy:
        q = q.filter(Study.modalities_in_study.contains([ModalitiesInStudy]))

    studies = q.order_by(Study.study_date.desc()).offset(offset).limit(limit).all()
    result = [_study_to_qido(s, s.patient) for s in studies]
    return Response(
        content=json.dumps(result),
        media_type=MIME_JSON,
        headers={"Access-Control-Allow-Origin": "*"},
    )


@router.get("/studies/{study_uid}/series", summary="QIDO-RS: Search Series")
def qido_search_series(
    study_uid: str,
    SeriesInstanceUID: Optional[str] = Query(None, alias="SeriesInstanceUID"),
    Modality:          Optional[str] = Query(None, alias="Modality"),
    limit:  int = Query(100, alias="_count"),
    offset: int = Query(0,   alias="_offset"),
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    study = db.query(Study).filter(Study.study_instance_uid == study_uid).first()
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    q = db.query(Series).filter(Series.study_id == study.id)
    if SeriesInstanceUID:
        q = q.filter(Series.series_instance_uid == SeriesInstanceUID)
    if Modality:
        q = q.filter(Series.modality == Modality)

    series_list = q.offset(offset).limit(limit).all()
    result = [_series_to_qido(s) for s in series_list]
    return Response(
        content=json.dumps(result),
        media_type=MIME_JSON,
        headers={"Access-Control-Allow-Origin": "*"},
    )


@router.get(
    "/studies/{study_uid}/series/{series_uid}/instances",
    summary="QIDO-RS: Search Instances"
)
def qido_search_instances(
    study_uid:  str,
    series_uid: str,
    SOPInstanceUID: Optional[str] = Query(None, alias="SOPInstanceUID"),
    limit:  int = Query(1000, alias="_count"),
    offset: int = Query(0,    alias="_offset"),
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    study  = db.query(Study).filter(Study.study_instance_uid == study_uid).first()
    series = db.query(Series).filter(
        Series.series_instance_uid == series_uid,
        Series.study_id == study.id if study else -1
    ).first()
    if not study or not series:
        raise HTTPException(status_code=404, detail="Study/series not found")

    q = db.query(Instance).filter(Instance.series_id == series.id)
    if SOPInstanceUID:
        q = q.filter(Instance.sop_instance_uid == SOPInstanceUID)

    instances = q.order_by(Instance.instance_number).offset(offset).limit(limit).all()
    result = [_instance_to_qido(i, series, study) for i in instances]
    return Response(
        content=json.dumps(result),
        media_type=MIME_JSON,
        headers={"Access-Control-Allow-Origin": "*"},
    )


# ══════════════════════════════════════════════════════════════════════════════
#  WADO-RS  —  Retrieve
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/studies/{study_uid}", summary="WADO-RS: Retrieve Study")
def wado_retrieve_study(
    study_uid: str,
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    study = db.query(Study).filter(Study.study_instance_uid == study_uid).first()
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    parts = []
    for series in study.series:
        for instance in series.instances:
            parts.append(Path(instance.file_path).read_bytes())

    body, mime = _build_multipart(parts)
    return Response(content=body, media_type=mime)


@router.get("/studies/{study_uid}/series/{series_uid}", summary="WADO-RS: Retrieve Series")
def wado_retrieve_series(
    study_uid:  str,
    series_uid: str,
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    series = db.query(Series).join(Study).filter(
        Study.study_instance_uid  == study_uid,
        Series.series_instance_uid == series_uid,
    ).first()
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    parts = [Path(i.file_path).read_bytes() for i in
             sorted(series.instances, key=lambda x: x.instance_number or 0)]
    body, mime = _build_multipart(parts)
    return Response(content=body, media_type=mime)


@router.get(
    "/studies/{study_uid}/series/{series_uid}/instances/{instance_uid}",
    summary="WADO-RS: Retrieve Instance"
)
def wado_retrieve_instance(
    study_uid:    str,
    series_uid:   str,
    instance_uid: str,
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    instance = _get_instance(db, study_uid, series_uid, instance_uid)
    data = Path(instance.file_path).read_bytes()
    body, mime = _build_multipart([data])
    return Response(content=body, media_type=mime)


@router.get(
    "/studies/{study_uid}/series/{series_uid}/instances/{instance_uid}/frames/{frames}",
    summary="WADO-RS: Retrieve Frames"
)
def wado_retrieve_frames(
    study_uid:    str,
    series_uid:   str,
    instance_uid: str,
    frames:       str,     # e.g. "1,2,3" or "1"
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    instance = _get_instance(db, study_uid, series_uid, instance_uid)
    ds = _load_dicom(instance)

    frame_indices = [int(f) - 1 for f in frames.split(",")]  # DICOM frames are 1-based
    parts = []

    if hasattr(ds, "PixelData"):
        if ds.get("NumberOfFrames", 1) > 1:
            # Multi-frame: extract individual frames
            pixel_array = ds.pixel_array
            for idx in frame_indices:
                if 0 <= idx < len(pixel_array):
                    frame_ds = pydicom.Dataset()
                    frame_ds.file_meta = pydicom.Dataset()
                    frame_ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
                    frame_ds.is_implicit_VR = False
                    frame_ds.is_little_endian = True
                    frame_ds.PixelData = pixel_array[idx].tobytes()
                    buf = io.BytesIO()
                    pydicom.dcmwrite(buf, frame_ds)
                    parts.append(buf.getvalue())
        else:
            # Single frame
            parts.append(Path(instance.file_path).read_bytes())

    body, mime = _build_multipart(parts, MIME_OCTET)
    return Response(content=body, media_type=mime)


@router.get(
    "/studies/{study_uid}/series/{series_uid}/instances/{instance_uid}/metadata",
    summary="WADO-RS: Retrieve Instance Metadata"
)
def wado_retrieve_metadata(
    study_uid:    str,
    series_uid:   str,
    instance_uid: str,
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    instance = _get_instance(db, study_uid, series_uid, instance_uid)
    ds = _load_dicom(instance)

    # Convert pydicom Dataset → DICOMweb JSON (simplified)
    meta = {}
    for elem in ds:
        tag_str = f"{elem.tag.group:04X}{elem.tag.element:04X}"
        vr = elem.VR
        if vr == "SQ":
            continue  # skip sequences for now
        try:
            val = elem.value
            if isinstance(val, bytes):
                continue
            meta[tag_str] = {"vr": vr, "Value": [str(val)] if not isinstance(val, list) else [str(v) for v in val]}
        except Exception:
            pass

    return Response(
        content=json.dumps([meta]),
        media_type=MIME_JSON,
        headers={"Access-Control-Allow-Origin": "*"},
    )


# ══════════════════════════════════════════════════════════════════════════════
#  STOW-RS  —  Store
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/studies", summary="STOW-RS: Store Instances")
@router.post("/studies/{study_uid}", summary="STOW-RS: Store Into Study")
async def stow_store_instances(
    request:   Request,
    study_uid: Optional[str] = None,
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """
    Accept multipart/related DICOM instances and store them.
    Returns a DICOMweb JSON response listing stored/failed UIDs.
    """
    content_type = request.headers.get("content-type", "")
    if "multipart/related" not in content_type:
        raise HTTPException(
            status_code=400,
            detail="Content-Type must be multipart/related"
        )

    body = await request.body()

    # Parse multipart body
    # Build a fake email message so Python's email parser can split it
    boundary = None
    for part in content_type.split(";"):
        part = part.strip()
        if part.startswith("boundary="):
            boundary = part.split("=", 1)[1].strip('"')
            break

    if not boundary:
        raise HTTPException(status_code=400, detail="Missing multipart boundary")

    # Split manually on boundary
    sep = f"--{boundary}".encode()
    raw_parts = body.split(sep)

    stored_uids = []
    failed_uids = []

    for raw_part in raw_parts:
        raw_part = raw_part.strip()
        if not raw_part or raw_part == b"--":
            continue
        # Split headers from body
        if b"\r\n\r\n" in raw_part:
            _headers, dicom_bytes = raw_part.split(b"\r\n\r\n", 1)
        elif b"\n\n" in raw_part:
            _headers, dicom_bytes = raw_part.split(b"\n\n", 1)
        else:
            continue

        dicom_bytes = dicom_bytes.rstrip(b"\r\n")
        if not dicom_bytes:
            continue

        try:
            ds = pydicom.dcmread(io.BytesIO(dicom_bytes))
            sop_uid = str(ds.SOPInstanceUID)

            # Check for duplicate
            existing = db.query(Instance).filter(
                Instance.sop_instance_uid == sop_uid
            ).first()
            if existing:
                # Policy: skip duplicate (configurable — see work_queue.py)
                stored_uids.append(sop_uid)
                continue

            # Determine storage path
            patient_id   = str(getattr(ds, "PatientID", "UNKNOWN"))
            study_uid_ds = str(getattr(ds, "StudyInstanceUID", "UNKNOWN"))
            series_uid_ds = str(getattr(ds, "SeriesInstanceUID", "UNKNOWN"))

            dest_dir = Path(settings.DICOM_STORAGE_PATH) / patient_id / study_uid_ds / series_uid_ds
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_file = dest_dir / f"{sop_uid}.dcm"
            dest_file.write_bytes(dicom_bytes)

            # Index in DB (reuse ingest logic via work queue)
            from services.ingest import index_dicom_file
            index_dicom_file(db, str(dest_file), ds)

            stored_uids.append(sop_uid)

        except Exception as e:
            failed_uids.append({"uid": "unknown", "error": str(e)})

    response_body = {
        "00081190": {"vr": "UR", "Value": [f"{settings.WADO_BASE_URL}/wado/studies"]},
        "00081198": {"vr": "SQ", "Value": [
            {"00081190": {"vr": "UR", "Value": [uid]}} for uid in stored_uids
        ]},
        "00081199": {"vr": "SQ", "Value": failed_uids},
    }

    return Response(
        content=json.dumps(response_body),
        media_type=MIME_JSON,
        status_code=status.HTTP_200_OK,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  Internal helpers
# ══════════════════════════════════════════════════════════════════════════════

def _get_instance(db: Session, study_uid: str, series_uid: str, instance_uid: str) -> Instance:
    instance = (
        db.query(Instance)
        .join(Series)
        .join(Study)
        .filter(
            Study.study_instance_uid   == study_uid,
            Series.series_instance_uid == series_uid,
            Instance.sop_instance_uid  == instance_uid,
        )
        .first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    return instance
