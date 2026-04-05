"""
routers/compression.py
────────────────────────────────────────────────────────────
DICOM compression and anonymization job management API.
"""

from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user, require_admin
from models import Study, CompressionJob, AnonymizationJob
from config import settings

router = APIRouter(prefix="/jobs", tags=["Jobs"])

TRANSFER_SYNTAXES = {
    "jpeg2000_lossless": "1.2.840.10008.1.2.4.90",
    "jpeg2000_lossy":    "1.2.840.10008.1.2.4.91",
    "jpeg_lossless":     "1.2.840.10008.1.2.4.70",
    "jpeg_baseline":     "1.2.840.10008.1.2.4.50",
    "rle":               "1.2.840.10008.1.2.5",
    "uncompressed":      "1.2.840.10008.1.2.1",
}


# ─── Compression ─────────────────────────────────────────────────

class CompressRequest(BaseModel):
    study_uid:  str
    syntax:     str = "jpeg2000_lossless"  # key from TRANSFER_SYNTAXES


class JobStatusOut(BaseModel):
    id:          int
    status:      str
    created_at:  datetime
    completed_at: Optional[datetime]
    total:       int
    done:        int
    failed:      int
    class Config:
        from_attributes = True


@router.post("/compress", status_code=202)
def queue_compression(
    req:  CompressRequest,
    db:   Session = Depends(get_db),
    _user         = Depends(get_current_user),
):
    syntax_uid = TRANSFER_SYNTAXES.get(req.syntax)
    if not syntax_uid:
        raise HTTPException(400, f"Unknown syntax '{req.syntax}'. Choose from: {list(TRANSFER_SYNTAXES)}")

    study = db.query(Study).filter(Study.study_instance_uid == req.study_uid).first()
    if not study:
        raise HTTPException(404, "Study not found")

    # Count instances
    total = sum(len(s.instances) for s in study.series)

    job = CompressionJob(
        study_uid      = req.study_uid,
        target_syntax  = syntax_uid,
        syntax_name    = req.syntax,
        status         = "queued",
        total          = total,
        done           = 0,
        failed         = 0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Dispatch Celery tasks per instance
    try:
        from services.work_queue import compress_instance
        from models import Instance, Series as SeriesModel
        instances = (
            db.query(Instance)
            .join(SeriesModel)
            .filter(SeriesModel.study_id == study.id)
            .all()
        )
        for instance in instances:
            compress_instance.apply_async(
                kwargs={"instance_id": instance.id, "target_syntax": syntax_uid, "job_id": job.id}
            )
        job.status = "running"
        db.commit()
    except Exception as e:
        job.status = "error"
        db.commit()
        return {"job_id": job.id, "status": "error", "detail": str(e)}

    return {"job_id": job.id, "status": "queued", "total": total}


@router.get("/compress", response_model=List[JobStatusOut])
def list_compression_jobs(
    limit: int = 50,
    db:    Session = Depends(get_db),
    _user          = Depends(get_current_user),
):
    return db.query(CompressionJob).order_by(CompressionJob.created_at.desc()).limit(limit).all()


@router.get("/compress/{job_id}", response_model=JobStatusOut)
def get_compression_job(
    job_id: int,
    db:     Session = Depends(get_db),
    _user           = Depends(get_current_user),
):
    job = db.query(CompressionJob).filter(CompressionJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    return job


# ─── Anonymization ───────────────────────────────────────────────

class AnonymizeRequest(BaseModel):
    study_uid:  str
    mode:       str = "full"          # full | research | custom
    pseudonym:  Optional[str] = None  # e.g. "RESEARCH-001"
    keep_uids:  bool = False
    import_back: bool = False         # re-import anonymized study into PACS


@router.post("/anonymize", status_code=202)
def queue_anonymization(
    req:  AnonymizeRequest,
    db:   Session = Depends(get_db),
    _user         = Depends(get_current_user),
):
    study = db.query(Study).filter(Study.study_instance_uid == req.study_uid).first()
    if not study:
        raise HTTPException(404, "Study not found")

    if req.mode not in ("full", "research", "custom"):
        raise HTTPException(400, "mode must be full | research | custom")

    total = sum(len(s.instances) for s in study.series)
    import uuid as _uuid
    job = AnonymizationJob(
        study_uid   = req.study_uid,
        mode        = req.mode,
        pseudonym   = req.pseudonym,
        keep_uids   = req.keep_uids,
        import_back = req.import_back,
        status      = "queued",
        total       = total,
        done        = 0,
        failed      = 0,
        job_token   = str(_uuid.uuid4()),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Dispatch to Celery
    try:
        from services.work_queue import run_anonymize_job
        run_anonymize_job.delay(job_id=job.id)
        job.status = "running"
        db.commit()
    except Exception as e:
        job.status = "error"
        db.commit()
        return {"job_id": job.id, "status": "error", "detail": str(e)}

    return {"job_id": job.id, "status": "queued", "total": total, "token": job.job_token}


@router.get("/anonymize", response_model=List[JobStatusOut])
def list_anonymize_jobs(
    limit: int = 50,
    db:    Session = Depends(get_db),
    _user          = Depends(get_current_user),
):
    return db.query(AnonymizationJob).order_by(AnonymizationJob.created_at.desc()).limit(limit).all()


@router.get("/anonymize/{job_id}/download")
def download_anonymized_study(
    job_id: int,
    db:     Session = Depends(get_db),
    _user           = Depends(get_current_user),
):
    """Download the ZIP of anonymized DICOM files."""
    import io, zipfile
    from fastapi.responses import StreamingResponse

    job = db.query(AnonymizationJob).filter(AnonymizationJob.id == job_id).first()
    if not job or job.status != "completed":
        raise HTTPException(404, "Job not found or not yet complete")

    from pathlib import Path
    out_dir = Path(settings.DICOM_STORAGE_PATH) / "anonymized" / job.job_token
    if not out_dir.exists():
        raise HTTPException(404, "Output files not found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in out_dir.glob("*.dcm"):
            zf.write(f, f.name)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=anonymized_{job_id}.zip"},
    )
