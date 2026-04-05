"""
main.py  (updated — shows how to wire in the new routers)
────────────────────────────────────────────────────────────
Drop-in update for your existing main.py.
Adds:
  1. DICOMweb router  (/wado/...)
  2. Admin router     (/admin/...)
  3. CORS headers for OHIF
  4. SCP startup in background thread
"""

import threading
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import engine, Base

# Existing routers (keep yours)
from routers import auth, patients, studies, series, instances, reports, burn

# New routers
from routers.dicomweb import router as dicomweb_router
from routers.admin    import router as admin_router

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown logic."""
    # ── Create DB tables ──────────────────────────────────────────────────
    Base.metadata.create_all(bind=engine)

    # ── Start DICOM SCP in background thread ─────────────────────────────
    from services.scp_handler import start_scp
    scp_thread = threading.Thread(target=start_scp, daemon=True, name="dicom-scp")
    scp_thread.start()
    log.info(f"DICOM SCP started on port {settings.DICOM_PORT}")

    # ── Ensure staging + storage dirs exist ──────────────────────────────
    from pathlib import Path
    Path(settings.DICOM_STAGING_PATH).mkdir(parents=True, exist_ok=True)
    Path(settings.DICOM_STORAGE_PATH).mkdir(parents=True, exist_ok=True)

    yield

    log.info("PACS server shutting down")


app = FastAPI(
    title       = "OpenPACS",
    description = "Self-hosted DICOM PACS Server — Python/FastAPI",
    version     = "2.0.0",
    lifespan    = lifespan,
)

# ── CORS (required for OHIF Viewer running on different port) ─────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins     = settings.cors_origins_list + ["*"],  # tighten in prod
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
    expose_headers    = ["Content-Type", "Content-Length"],
)

# ── Mount all routers ────────────────────────────────────────────────────
app.include_router(auth.router,       prefix="/api")
app.include_router(patients.router,   prefix="/api")
app.include_router(studies.router,    prefix="/api")
app.include_router(series.router,     prefix="/api")
app.include_router(instances.router,  prefix="/api")
app.include_router(reports.router,    prefix="/api")
app.include_router(burn.router,       prefix="/api")

# New
app.include_router(dicomweb_router)   # /wado/studies  etc.
app.include_router(admin_router,      prefix="/api")   # /api/admin/...


@app.get("/health")
def health():
    return {"status": "ok", "ae_title": settings.AE_TITLE}


@app.get("/wado/capabilities")
def wado_capabilities():
    """DICOMweb capabilities response for OHIF auto-discovery."""
    return {
        "qidoSupport": True,
        "wadoSupport": True,
        "stowSupport": True,
        "qidoRoot":    f"{settings.WADO_BASE_URL}/wado",
        "wadoRoot":    f"{settings.WADO_BASE_URL}/wado",
        "wadoUriRoot": f"{settings.WADO_BASE_URL}/wado",
    }
