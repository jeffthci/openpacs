"""
routers/wado_uri.py
────────────────────────────────────────────────────────────
WADO-URI (legacy) and thumbnail endpoints.

WADO-URI  (PS3.18 §9.4 legacy, pre-DICOMweb)
  GET /wado?requestType=WADO&studyUID=...&seriesUID=...&objectUID=...

Thumbnail
  GET /wado/studies/{studyUID}/series/{seriesUID}/instances/{instanceUID}/thumbnail
  GET /wado/studies/{studyUID}/series/{seriesUID}/thumbnail   (first instance)
  GET /wado/studies/{studyUID}/thumbnail                      (first series/instance)

Bulk metadata  (OHIF perf optimisation)
  GET /wado/studies/{studyUID}/series/{seriesUID}/instances/metadata
      → returns all instance metadata for a series in one call

These complement dicomweb.py — mount both routers on the same /wado prefix.
"""

import io
import logging
from pathlib import Path
from typing import Optional

import pydicom
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from PIL import Image
from sqlalchemy.orm import Session

from database import get_db
from models import Study, Series, Instance
from auth import get_current_user

log = logging.getLogger(__name__)

router = APIRouter(prefix="/wado", tags=["WADO-URI / Thumbnails"])


# ══════════════════════════════════════════════════════════════════════════════
#  WADO-URI  (legacy)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("", summary="WADO-URI legacy retrieve")
def wado_uri(
    requestType: str  = Query(...),
    studyUID:    str  = Query(...),
    seriesUID:   str  = Query(...),
    objectUID:   str  = Query(...),
    contentType: str  = Query("application/dicom"),
    rows:        Optional[int] = Query(None),
    columns:     Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    if requestType != "WADO":
        raise HTTPException(400, "requestType must be WADO")

    instance = (
        db.query(Instance)
        .join(Series).join(Study)
        .filter(
            Study.study_instance_uid   == studyUID,
            Series.series_instance_uid == seriesUID,
            Instance.sop_instance_uid  == objectUID,
        )
        .first()
    )
    if not instance:
        raise HTTPException(404, "Instance not found")

    path = Path(instance.file_path)
    if not path.exists():
        raise HTTPException(404, "File not found on disk")

    if contentType in ("image/jpeg", "image/png"):
        img_bytes = _render_instance_image(path, rows, columns,
                                           fmt="JPEG" if "jpeg" in contentType else "PNG")
        return Response(content=img_bytes, media_type=contentType)

    # Default: return raw DICOM
    return Response(
        content=path.read_bytes(),
        media_type="application/dicom",
        headers={
            "Content-Disposition": f'attachment; filename="{objectUID}.dcm"',
            "Access-Control-Allow-Origin": "*",
        },
    )


# ══════════════════════════════════════════════════════════════════════════════
#  Thumbnail endpoints
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/studies/{study_uid}/series/{series_uid}/instances/{instance_uid}/thumbnail",
    summary="Thumbnail for a specific instance"
)
def instance_thumbnail(
    study_uid:    str,
    series_uid:   str,
    instance_uid: str,
    rows: int = Query(128, ge=32, le=512),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    instance = _get_instance(db, study_uid, series_uid, instance_uid)
    img_bytes = _render_instance_image(Path(instance.file_path), rows, rows, fmt="JPEG")
    return Response(content=img_bytes, media_type="image/jpeg",
                    headers={"Cache-Control": "max-age=86400",
                             "Access-Control-Allow-Origin": "*"})


@router.get(
    "/studies/{study_uid}/series/{series_uid}/thumbnail",
    summary="Thumbnail for a series (middle instance)"
)
def series_thumbnail(
    study_uid:  str,
    series_uid: str,
    rows: int = Query(128, ge=32, le=512),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    series = (
        db.query(Series).join(Study)
        .filter(Study.study_instance_uid == study_uid,
                Series.series_instance_uid == series_uid)
        .first()
    )
    if not series:
        raise HTTPException(404, "Series not found")

    instances = sorted(series.instances, key=lambda i: i.instance_number or 0)
    if not instances:
        raise HTTPException(404, "No instances in series")

    # Pick the middle frame for a representative thumbnail
    mid = instances[len(instances) // 2]
    img_bytes = _render_instance_image(Path(mid.file_path), rows, rows, fmt="JPEG")
    return Response(content=img_bytes, media_type="image/jpeg",
                    headers={"Cache-Control": "max-age=86400",
                             "Access-Control-Allow-Origin": "*"})


@router.get(
    "/studies/{study_uid}/thumbnail",
    summary="Thumbnail for a study (first series, middle instance)"
)
def study_thumbnail(
    study_uid: str,
    rows: int = Query(128, ge=32, le=512),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    study = db.query(Study).filter(Study.study_instance_uid == study_uid).first()
    if not study or not study.series:
        raise HTTPException(404, "Study not found or empty")

    first_series = sorted(study.series, key=lambda s: s.series_number or 0)[0]
    instances = sorted(first_series.instances, key=lambda i: i.instance_number or 0)
    if not instances:
        raise HTTPException(404, "No instances found")

    mid = instances[len(instances) // 2]
    img_bytes = _render_instance_image(Path(mid.file_path), rows, rows, fmt="JPEG")
    return Response(content=img_bytes, media_type="image/jpeg",
                    headers={"Cache-Control": "max-age=86400",
                             "Access-Control-Allow-Origin": "*"})


# ══════════════════════════════════════════════════════════════════════════════
#  Bulk series metadata  (OHIF performance optimisation)
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/studies/{study_uid}/series/{series_uid}/instances/metadata",
    summary="All instance metadata for a series (bulk fetch)"
)
def series_instances_metadata(
    study_uid:  str,
    series_uid: str,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """
    Returns metadata for ALL instances in a series in one response.
    OHIF uses this to pre-load the entire series metadata without
    making N individual /instances/{uid}/metadata calls.
    """
    import json
    series = (
        db.query(Series).join(Study)
        .filter(Study.study_instance_uid == study_uid,
                Series.series_instance_uid == series_uid)
        .first()
    )
    if not series:
        raise HTTPException(404, "Series not found")

    results = []
    for instance in sorted(series.instances, key=lambda i: i.instance_number or 0):
        path = Path(instance.file_path)
        if not path.exists():
            continue
        try:
            ds = pydicom.dcmread(str(path), stop_before_pixels=True)
            meta = _dataset_to_dicomweb_json(ds)
            results.append(meta)
        except Exception as e:
            log.warning(f"Skipping metadata for {instance.sop_instance_uid}: {e}")

    return Response(
        content=json.dumps(results),
        media_type="application/dicom+json",
        headers={"Access-Control-Allow-Origin": "*"},
    )


# ══════════════════════════════════════════════════════════════════════════════
#  Internal helpers
# ══════════════════════════════════════════════════════════════════════════════

def _render_instance_image(
    path: Path,
    rows: Optional[int],
    columns: Optional[int],
    fmt: str = "JPEG",
) -> bytes:
    """Render a DICOM instance to JPEG/PNG bytes."""
    if not path.exists():
        raise HTTPException(404, f"File not found: {path}")

    try:
        ds = pydicom.dcmread(str(path))

        if not hasattr(ds, "PixelData"):
            raise HTTPException(422, "Instance has no pixel data")

        arr = ds.pixel_array.astype(float)

        # Handle multi-frame — take middle frame
        if arr.ndim == 3 and arr.shape[0] > 1:
            arr = arr[arr.shape[0] // 2]
        elif arr.ndim == 3:
            arr = arr[0]

        # Apply window/level if available
        wc = _float_val(ds, "WindowCenter")
        ww = _float_val(ds, "WindowWidth")
        if wc is not None and ww is not None:
            lo = wc - ww / 2
            hi = wc + ww / 2
            arr = np.clip(arr, lo, hi)
            arr = ((arr - lo) / (hi - lo) * 255).astype(np.uint8)
        else:
            # Auto window
            arr_min, arr_max = arr.min(), arr.max()
            if arr_max > arr_min:
                arr = ((arr - arr_min) / (arr_max - arr_min) * 255).astype(np.uint8)
            else:
                arr = np.zeros_like(arr, dtype=np.uint8)

        # Handle RGB
        if arr.ndim == 3 and arr.shape[2] in (3, 4):
            img = Image.fromarray(arr.astype(np.uint8), mode="RGB" if arr.shape[2] == 3 else "RGBA")
        else:
            img = Image.fromarray(arr.astype(np.uint8), mode="L")

        # Resize if requested
        if rows or columns:
            target_h = rows    or img.height
            target_w = columns or img.width
            img = img.resize((target_w, target_h), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format=fmt, quality=85)
        return buf.getvalue()

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Thumbnail render error for {path}: {e}")
        # Return a 1x1 gray pixel as fallback
        img = Image.new("L", (128, 128), color=64)
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return buf.getvalue()


def _float_val(ds, keyword):
    try:
        val = getattr(ds, keyword, None)
        if val is None:
            return None
        if hasattr(val, "__iter__") and not isinstance(val, str):
            val = list(val)[0]
        return float(val)
    except Exception:
        return None


def _dataset_to_dicomweb_json(ds: pydicom.Dataset) -> dict:
    """Convert a pydicom Dataset to DICOMweb JSON format."""
    meta = {}
    for elem in ds:
        if elem.VR == "SQ":
            continue
        tag_str = f"{elem.tag.group:04X}{elem.tag.element:04X}"
        try:
            val = elem.value
            if isinstance(val, bytes):
                continue
            if isinstance(val, pydicom.sequence.Sequence):
                continue
            if isinstance(val, pydicom.uid.UID):
                val = str(val)
            meta[tag_str] = {
                "vr": elem.VR,
                "Value": [str(val)] if not isinstance(val, (list, pydicom.multival.MultiValue))
                         else [str(v) for v in val]
            }
        except Exception:
            pass
    return meta


def _get_instance(db: Session, study_uid: str, series_uid: str, instance_uid: str) -> Instance:
    instance = (
        db.query(Instance).join(Series).join(Study)
        .filter(
            Study.study_instance_uid   == study_uid,
            Series.series_instance_uid == series_uid,
            Instance.sop_instance_uid  == instance_uid,
        )
        .first()
    )
    if not instance:
        raise HTTPException(404, "Instance not found")
    return instance
