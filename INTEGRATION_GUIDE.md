# OpenPACS Phase 1 Gap Fix — Integration Guide

## What was built

This package closes all 4 Phase 1 gaps identified in the gap analysis:

| Gap | Fix | Files |
|-----|-----|-------|
| DICOMweb (WADO-RS / STOW-RS / QIDO-RS) | Full DICOMweb router | `routers/dicomweb.py` |
| Duplicate SOP handling | Policy-based dedup in ingest service | `services/ingest.py` |
| Multi-filesystem storage | StorageFilesystem model + routing | `models_additions.py`, `services/ingest.py` |
| Async work queue | Celery + Redis workers | `services/work_queue.py` |

Bonus additions:
- Auto-routing rules engine (`services/routing.py`)
- Admin API (`routers/admin.py`)
- Admin UI page (`frontend/src/pages/Admin.jsx`)
- OHIF Viewer integration (`ohif-config.js`, `frontend/src/pages/OHIFViewer.jsx`)
- Full Docker Compose stack (`docker-compose.yml`)

---

## Step 1 — Copy files into your project

```
your-project/
├── backend/
│   ├── routers/
│   │   ├── dicomweb.py          ← NEW
│   │   └── admin.py             ← NEW
│   ├── services/
│   │   ├── ingest.py            ← NEW (replaces your old ingest logic)
│   │   ├── work_queue.py        ← NEW
│   │   ├── routing.py           ← NEW
│   │   └── scp_handler.py       ← NEW (replaces your old SCP handler)
│   ├── models_additions.py      ← NEW (merge into your models.py)
│   ├── config.py                ← MERGE new settings in
│   ├── main.py                  ← MERGE router registrations in
│   └── requirements.txt         ← MERGE new dependencies
├── frontend/src/pages/
│   ├── Admin.jsx                ← NEW
│   └── OHIFViewer.jsx           ← NEW
├── ohif-config.js               ← NEW
└── docker-compose.yml           ← REPLACE / MERGE
```

---

## Step 2 — Merge models_additions.py into your models.py

Add these classes to your existing `models.py`:
- `StorageFilesystem`
- `RoutingRule`
- `RoutingDestination`

Add these columns to your existing `Study` model:
```python
calling_ae_title = Column(String(16), nullable=True)
retain_until     = Column(DateTime, nullable=True)
created_at       = Column(DateTime, default=datetime.utcnow)
```

Add these columns to your existing `Instance` model:
```python
acquired_at     = Column(DateTime, nullable=True)
transfer_syntax = Column(String(64), nullable=True)
```

---

## Step 3 — Run the Alembic migration

The migration script is embedded in `models_additions.py` as the
`MIGRATION_SCRIPT` string. Copy it to a new file in `alembic/versions/`:

```bash
# Copy the migration
python -c "from models_additions import MIGRATION_SCRIPT; print(MIGRATION_SCRIPT)" \
  > alembic/versions/a1b2c3d4e5f6_add_pacs_phase1_gaps.py

# Run it
alembic upgrade head
```

---

## Step 4 — Update .env

Add these variables to your `.env`:

```env
# New settings
DICOM_STAGING_PATH=/opt/pacs/staging
WADO_BASE_URL=http://YOUR_SERVER_IP:8000
REDIS_URL=redis://localhost:6379/0
DUPLICATE_SOP_POLICY=ignore
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

---

## Step 5 — Install new dependencies

```bash
pip install celery[redis] redis pynetdicom pydicom
# or
pip install -r requirements.txt
```

---

## Step 6 — Start Redis

```bash
# Docker (easiest)
docker run -d -p 6379:6379 redis:7-alpine

# Or via docker compose
docker compose up -d redis
```

---

## Step 7 — Start Celery workers

Open two extra terminal windows alongside your FastAPI server:

```bash
# Terminal 2 — Celery worker (processes ingest + routing)
celery -A services.work_queue worker --loglevel=info -Q high,default

# Terminal 3 — Celery beat scheduler (storage stats, purge)
celery -A services.work_queue beat --loglevel=info
```

Or use Docker Compose:
```bash
docker compose up worker beat
```

---

## Step 8 — Add routes to your React app

In your `src/App.jsx` or router file, add:

```jsx
import Admin      from "./pages/Admin";
import OHIFViewer from "./pages/OHIFViewer";

// In your routes:
<Route path="/admin"  element={<Admin />} />
<Route path="/ohif"   element={<OHIFViewer />} />
```

Add a link to Admin in your sidebar/nav:
```jsx
<NavLink to="/admin">Admin</NavLink>
<NavLink to="/ohif">OHIF Viewer</NavLink>
```

---

## Step 9 — Set up OHIF (optional)

### Option A: Docker
```bash
docker compose --profile ohif up ohif
```
Then open http://localhost:3000

### Option B: Self-hosted OHIF
```bash
git clone https://github.com/OHIF/Viewers
cd Viewers
yarn install
# Copy ohif-config.js → platform/app/public/app-config.js
yarn run dev
```

### Option C: Use iframe (already built)
Navigate to `/ohif` in your existing React app — it iframes OHIF.

---

## Step 10 — Verify DICOMweb is working

```bash
# Test QIDO-RS (should return JSON array of studies)
curl http://localhost:8000/wado/studies

# Test with OHIF — open OHIF and it should show your worklist
open http://localhost:3000

# Or test with dcm4che storescu to send a DICOM file
storescu -c OPENPACS@localhost:11112 yourfile.dcm
```

---

## Architecture after upgrade

```
Modality (CT/MR/CR)
        │ C-STORE (DICOM)
        ▼
   DICOM SCP (port 11112)
        │ writes to /staging
        │ dispatches ingest_file.delay()
        ▼
   Redis Queue ──────────────────────────────────┐
        │                                         │
        ▼                                         ▼
   Celery Worker                           Celery Beat
   - index_dicom_file()                    - sync_storage_stats (5min)
   - route_study()                         - purge_expired (daily)
        │
        ▼
   PostgreSQL + Filesystem
        │
        ▼
   FastAPI (port 8000)
   ├── /api/*          ← existing REST API
   ├── /wado/*         ← NEW DICOMweb (QIDO/WADO/STOW)
   ├── /api/admin/*    ← NEW admin endpoints
   └── /ohif-config.js ← NEW OHIF config endpoint
        │
        ▼
   OHIF Viewer (port 3000)  ──── connects to /wado/*
   React App   (port 5173)  ──── connects to /api/* + /wado/*
```

---

## Routing rule examples

After deploying, create routing rules via the Admin UI or API:

```json
// Route all CT to a CT workstation
{
  "name": "CT to Workstation",
  "priority": 10,
  "conditions": {"modality": "CT"},
  "destinations": [{"ae_title": "CT_WS", "host": "192.168.1.50", "port": 104}]
}

// Route MRI room studies to archive
{
  "name": "MRI Archive",
  "priority": 20,
  "conditions": {"calling_ae": "MRI_RM1"},
  "destinations": [{"ae_title": "ARCHIVE", "host": "192.168.1.100", "port": 11112}]
}

// Catch-all default route
{
  "name": "Default Archive",
  "priority": 999,
  "conditions": {},
  "stop_on_match": false,
  "destinations": [{"ae_title": "BACKUP_PACS", "host": "192.168.1.200", "port": 104}]
}
```
