"""
config.py  (updated version — merge with your existing config)
────────────────────────────────────────────────────────────
All new settings needed by Phase 1 gap fixes.
Add these to your existing Settings class.
"""

from pydantic_settings import BaseSettings
from typing import List, Optional
import json


class Settings(BaseSettings):

    # ── Existing settings (keep yours) ───────────────────────────────────
    DATABASE_URL:        str = "postgresql://pacs:pacs@localhost:5432/pacsdb"
    SECRET_KEY:          str = "change-me-in-production"
    DICOM_PORT:          int = 11112
    AE_TITLE:            str = "PACSSERVER"
    DICOM_STORAGE_PATH:  str = "/opt/pacs/storage"

    # ── New: staging directory for async ingest ───────────────────────────
    # Files land here immediately on C-STORE, then get moved by the worker
    DICOM_STAGING_PATH:  str = "/opt/pacs/staging"

    # ── New: DICOMweb base URL (used in QIDO-RS responses) ───────────────
    # Set this to your server's public/LAN address
    WADO_BASE_URL:       str = "http://localhost:8000"

    # ── New: Redis URL for Celery work queue ─────────────────────────────
    REDIS_URL:           str = "redis://localhost:6379/0"

    # ── New: Duplicate SOP handling policy ───────────────────────────────
    # Options: "ignore" | "reject" | "overwrite"
    DUPLICATE_SOP_POLICY: str = "ignore"

    # ── New: Multi-filesystem storage roots ──────────────────────────────
    # JSON list of {"path": str, "type": "primary"|"archive", "max_gb": int}
    # Leave empty to use DICOM_STORAGE_PATH (single-root legacy mode)
    STORAGE_ROOTS_JSON:  str = ""

    @property
    def STORAGE_ROOTS(self) -> List[dict]:
        if self.STORAGE_ROOTS_JSON:
            return json.loads(self.STORAGE_ROOTS_JSON)
        return []

    # ── New: Default retention in days (None = keep forever) ─────────────
    DEFAULT_RETENTION_DAYS: Optional[int] = None

    # ── New: CORS origins for DICOMweb (needed for OHIF) ─────────────────
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    class Config:
        env_file = ".env"


settings = Settings()
