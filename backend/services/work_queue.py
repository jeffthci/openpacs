"""
services/work_queue.py
────────────────────────────────────────────────────────────
Async background task queue using Celery + Redis.

Tasks
─────
  ingest_file          – index a received DICOM file
  route_study          – apply routing rules to a study
  compress_instance    – compress a DICOM instance (JPEG2000, etc.)
  purge_expired        – delete studies past retention date
  sync_storage_stats   – update filesystem stats in DB

Queue architecture
──────────────────
  Redis acts as broker + result backend.
  Two queues:
    "high"    – ingest (fast, low latency)
    "default" – routing, compression, stats (can be slow)

Usage
─────
  # From C-STORE handler or STOW-RS:
  ingest_file.delay(file_path="/dicom/storage/pt/study/.../file.dcm")

  # From study creation:
  route_study.delay(study_id=42)

  # Start workers:
  celery -A services.work_queue worker --loglevel=info -Q high,default
"""

import logging
from pathlib import Path
from typing import Optional

from celery import Celery
from celery.utils.log import get_task_logger

from config import settings

log = get_task_logger(__name__)

# ─── App init ─────────────────────────────────────────────────────────────
celery_app = Celery(
    "pacs_worker",
    broker  = settings.REDIS_URL,
    backend = settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer        = "json",
    result_serializer      = "json",
    accept_content         = ["json"],
    timezone               = "UTC",
    enable_utc             = True,
    task_track_started     = True,
    task_acks_late         = True,
    worker_prefetch_multiplier = 1,
    task_routes = {
        "services.work_queue.ingest_file":       {"queue": "high"},
        "services.work_queue.route_study":       {"queue": "default"},
        "services.work_queue.compress_instance": {"queue": "default"},
        "services.work_queue.purge_expired":     {"queue": "default"},
        "services.work_queue.sync_storage_stats":{"queue": "default"},
    },
    beat_schedule = {
        # Run storage stats sync every 5 minutes
        "sync-storage-every-5m": {
            "task": "services.work_queue.sync_storage_stats",
            "schedule": 300.0,
        },
        # Check for expired studies daily at 2 AM
        "purge-expired-daily": {
            "task": "services.work_queue.purge_expired",
            "schedule": 86400.0,
            "options": {"expires": 3600},
        },
    },
)


# ══════════════════════════════════════════════════════════════════════════════
#  Task: ingest_file
# ══════════════════════════════════════════════════════════════════════════════

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    queue="high",
    name="services.work_queue.ingest_file",
)
def ingest_file(self, file_path: str):
    """
    Index a newly received DICOM file into the database.
    Called by C-STORE SCP handler after writing to disk.
    """
    from database import SessionLocal
    from services.ingest import index_dicom_file, DuplicateSOPError

    log.info(f"[ingest_file] Processing: {file_path}")

    db = SessionLocal()
    try:
        instance = index_dicom_file(db, file_path)
        log.info(f"[ingest_file] Done — SOP: {instance.sop_instance_uid}")

        # Trigger routing after successful ingest
        route_study.apply_async(
            kwargs={"study_id": instance.series.study_id},
            countdown=2,  # 2s delay to batch rapid multi-instance sends
        )

        return {"status": "ok", "sop_uid": instance.sop_instance_uid}

    except DuplicateSOPError as exc:
        log.warning(f"[ingest_file] Duplicate SOP — policy=reject: {exc}")
        return {"status": "duplicate", "detail": str(exc)}

    except FileNotFoundError as exc:
        log.error(f"[ingest_file] File not found: {exc}")
        return {"status": "error", "detail": str(exc)}

    except Exception as exc:
        log.error(f"[ingest_file] Error: {exc}", exc_info=True)
        raise self.retry(exc=exc)

    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
#  Task: route_study
# ══════════════════════════════════════════════════════════════════════════════

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="default",
    name="services.work_queue.route_study",
)
def route_study(self, study_id: int):
    """
    Evaluate routing rules against a study and forward to configured destinations.
    Rules are stored in the routing_rules table (see models.py).
    """
    from database import SessionLocal
    from models import Study, RoutingRule, RoutingDestination
    from services.routing import evaluate_and_route

    db = SessionLocal()
    try:
        study = db.query(Study).filter(Study.id == study_id).first()
        if not study:
            log.warning(f"[route_study] Study {study_id} not found")
            return {"status": "not_found"}

        results = evaluate_and_route(db, study)
        log.info(f"[route_study] Study {study_id} routed to {len(results)} destinations")
        return {"status": "ok", "destinations": results}

    except Exception as exc:
        log.error(f"[route_study] Error: {exc}", exc_info=True)
        raise self.retry(exc=exc)

    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
#  Task: compress_instance
# ══════════════════════════════════════════════════════════════════════════════

@celery_app.task(
    bind=True,
    max_retries=2,
    queue="default",
    name="services.work_queue.compress_instance",
)
def compress_instance(self, instance_id: int, target_syntax: str = "1.2.840.10008.1.2.4.90"):
    """
    Compress a DICOM instance to a target transfer syntax.
    Default: JPEG2000 Lossless (1.2.840.10008.1.2.4.90)
    Other options:
      - 1.2.840.10008.1.2.4.91  JPEG2000 Lossy
      - 1.2.840.10008.1.2.4.70  JPEG Lossless
      - 1.2.840.10008.1.2.1     Explicit VR Little Endian (decompress)
    """
    import pydicom
    from database import SessionLocal
    from models import Instance

    db = SessionLocal()
    try:
        instance = db.query(Instance).filter(Instance.id == instance_id).first()
        if not instance:
            return {"status": "not_found"}

        path = Path(instance.file_path)
        if not path.exists():
            return {"status": "file_not_found"}

        ds = pydicom.dcmread(str(path))
        current_syntax = str(getattr(ds.file_meta, "TransferSyntaxUID", ""))

        if current_syntax == target_syntax:
            log.debug(f"[compress] Already in target syntax: {instance_id}")
            return {"status": "already_compressed"}

        # Use gdcm or pylibjpeg for actual compression
        # For now, log intent — full implementation requires gdcm installed
        log.info(f"[compress] Instance {instance_id}: {current_syntax} → {target_syntax}")

        # TODO: ds.compress(target_syntax) when gdcm available
        # ds.save_as(str(path), write_like_original=False)
        # instance.transfer_syntax = target_syntax
        # db.commit()

        return {"status": "ok", "instance_id": instance_id, "target": target_syntax}

    except Exception as exc:
        log.error(f"[compress] Error: {exc}", exc_info=True)
        raise self.retry(exc=exc)

    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
#  Task: purge_expired
# ══════════════════════════════════════════════════════════════════════════════

@celery_app.task(
    queue="default",
    name="services.work_queue.purge_expired",
)
def purge_expired():
    """
    Delete studies that have passed their retention date.
    Retention is set per-partition (or globally via settings.DEFAULT_RETENTION_DAYS).
    """
    from datetime import datetime, timedelta
    from database import SessionLocal
    from models import Study, Series, Instance

    db = SessionLocal()
    deleted = 0
    try:
        retention_days = getattr(settings, "DEFAULT_RETENTION_DAYS", None)
        if not retention_days:
            return {"status": "skipped", "reason": "no retention policy configured"}

        cutoff = datetime.utcnow() - timedelta(days=int(retention_days))
        expired = db.query(Study).filter(
            Study.created_at < cutoff,
            Study.retain_until == None,  # noqa: E711
        ).all()

        for study in expired:
            for series in study.series:
                for instance in series.instances:
                    p = Path(instance.file_path)
                    if p.exists():
                        p.unlink()
                    db.delete(instance)
                db.delete(series)
            db.delete(study)
            deleted += 1

        db.commit()
        log.info(f"[purge] Deleted {deleted} expired studies")
        return {"status": "ok", "deleted": deleted}

    except Exception as exc:
        db.rollback()
        log.error(f"[purge] Error: {exc}", exc_info=True)
        return {"status": "error", "detail": str(exc)}

    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
#  Task: sync_storage_stats
# ══════════════════════════════════════════════════════════════════════════════

@celery_app.task(
    queue="default",
    name="services.work_queue.sync_storage_stats",
)
def sync_storage_stats():
    """
    Update filesystem utilization stats in the storage_filesystem table.
    Used by the admin dashboard to show disk usage per storage root.
    """
    import shutil
    from database import SessionLocal
    from models import StorageFilesystem

    db = SessionLocal()
    try:
        filesystems = db.query(StorageFilesystem).all()
        for fs in filesystems:
            try:
                usage = shutil.disk_usage(fs.path)
                fs.total_bytes     = usage.total
                fs.used_bytes      = usage.used
                fs.available_bytes = usage.free
                fs.percent_used    = round((usage.used / usage.total) * 100, 1)
            except Exception as e:
                log.warning(f"[storage_stats] Cannot stat {fs.path}: {e}")

        db.commit()
        log.debug("[storage_stats] Updated filesystem stats")
        return {"status": "ok", "filesystems": len(filesystems)}

    except Exception as exc:
        db.rollback()
        log.error(f"[storage_stats] Error: {exc}", exc_info=True)
        return {"status": "error"}

    finally:
        db.close()
