"""
main.py — complete final version
Replace your existing main.py with this file.
"""

import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import engine, Base

# ── Original routers (keep yours) ────────────────────────────────
from routers import auth, patients, studies, series, instances, reports, burn

# ── Phase 1: DICOMweb + Admin ─────────────────────────────────────
from routers.dicomweb import router as dicomweb_router
from routers.admin    import router as admin_router

# ── Phase 2: WADO-URI + thumbnails ───────────────────────────────
from routers.wado_uri import router as wado_uri_router

# ── Phase 5: Partitions ───────────────────────────────────────────
from routers.partitions import router as partitions_router

# ── Phase 6: Audit log + users ────────────────────────────────────
from routers.audit       import router as audit_router
from routers.users       import router as users_router
from routers.worklist    import router as worklist_router
from routers.stats       import router as stats_router
from routers.compression import router as compression_router

# ── Audit middleware ──────────────────────────────────────────────
from services.audit import AuditMiddleware

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Create all DB tables ──────────────────────────────────────
    Base.metadata.create_all(bind=engine)

    # ── Ensure required directories exist ────────────────────────
    Path(settings.DICOM_STAGING_PATH).mkdir(parents=True, exist_ok=True)
    Path(settings.DICOM_STORAGE_PATH).mkdir(parents=True, exist_ok=True)

    # ── Start DICOM SCP ───────────────────────────────────────────
    from services.scp_handler import start_scp
    scp_thread = threading.Thread(
        target=start_scp, daemon=True, name="dicom-scp"
    )
    scp_thread.start()
    log.info(f"DICOM SCP started — AE: {settings.AE_TITLE}, Port: {settings.DICOM_PORT}")

    # ── Start per-partition SCP servers ──────────────────────────
    try:
        from database import SessionLocal
        from services.partitions import start_partition_servers
        db = SessionLocal()
        try:
            start_partition_servers(db)
        finally:
            db.close()
    except Exception as e:
        log.warning(f"Partition SCPs not started: {e}")

    yield

    log.info("OpenPACS shutting down")


app = FastAPI(
    title       = "OpenPACS",
    description = "Self-hosted DICOM PACS — Python/FastAPI. ClearCanvas feature-parity build.",
    version     = "2.0.0",
    lifespan    = lifespan,
    docs_url    = "/api/docs",
    redoc_url   = "/api/redoc",
    openapi_url = "/api/openapi.json",
)

# ── CORS ──────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins     = settings.cors_origins_list,
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
    expose_headers    = ["Content-Type", "Content-Length", "Content-Disposition"],
)

# ── Audit middleware ───────────────────────────────────────────────
app.add_middleware(AuditMiddleware)

# ── Original API routes ───────────────────────────────────────────
app.include_router(auth.router,      prefix="/api")
app.include_router(patients.router,  prefix="/api")
app.include_router(studies.router,   prefix="/api")
app.include_router(series.router,    prefix="/api")
app.include_router(instances.router, prefix="/api")
app.include_router(reports.router,   prefix="/api")
app.include_router(burn.router,      prefix="/api")

# ── New routes ────────────────────────────────────────────────────
app.include_router(dicomweb_router)              # /wado/*
app.include_router(wado_uri_router)              # /wado (legacy) + thumbnails
app.include_router(admin_router,    prefix="/api")  # /api/admin/*
app.include_router(partitions_router, prefix="/api") # /api/partitions/*
app.include_router(audit_router,       prefix="/api")   # /api/audit/*
app.include_router(users_router,       prefix="/api")   # /api/auth/users
app.include_router(worklist_router,    prefix="/api")   # /api/worklist/*
app.include_router(stats_router,       prefix="/api")   # /api/stats/*
app.include_router(compression_router, prefix="/api")   # /api/compression/*


# ── Utility endpoints ────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health_check():
    return {
        "status":   "ok",
        "ae_title": settings.AE_TITLE,
        "version":  "2.0.0",
    }


@app.get("/wado/capabilities", tags=["DICOMweb"])
def wado_capabilities():
    """DICOMweb capability advertisement for OHIF auto-discovery."""
    base = settings.WADO_BASE_URL
    return {
        "qidoSupport":  True,
        "wadoSupport":  True,
        "stowSupport":  True,
        "qidoRoot":     f"{base}/wado",
        "wadoRoot":     f"{base}/wado",
        "wadoUriRoot":  f"{base}/wado",
        "supportsWildcard":        True,
        "supportsFuzzyMatching":   True,
        "enableStudyLazyLoad":     True,
        "imageRendering":          "wadors",
        "thumbnailRendering":      "wadors",
    }


@app.get("/ohif-config.js", tags=["System"])
def ohif_config_js():
    """
    Serve OHIF Viewer configuration dynamically.
    Mount this URL as the OHIF app-config.js source.
    """
    from fastapi.responses import Response
    base = settings.WADO_BASE_URL
    js = f"""window.config = {{
  routerBasename: '/',
  defaultDataSourceName: 'dicomweb',
  dataSources: [{{
    namespace: '@ohif/extension-default.dataSourcesModule.dicomweb',
    sourceName: 'dicomweb',
    configuration: {{
      friendlyName: 'OpenPACS',
      name: 'OpenPACS',
      wadoUriRoot:  '{base}/wado',
      qidoRoot:     '{base}/wado',
      wadoRoot:     '{base}/wado',
      qidoSupportsIncludeField: true,
      supportsReject:           false,
      imageRendering:           'wadors',
      thumbnailRendering:       'wadors',
      enableStudyLazyLoad:      true,
      supportsFuzzyMatching:    true,
      supportsWildcard:         true,
      staticWado:               false,
      singlepart:               false,
    }},
  }}],
}};
"""
    return Response(content=js, media_type="application/javascript")
