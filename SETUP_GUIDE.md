# OpenPACS — Complete Setup Guide

## What This Package Contains

This is a full upgrade to your existing DICOM radiology system,
closing all Phase 1–6 gaps identified in the gap analysis.

### New capabilities vs the original build

| Phase | Feature | Status |
|-------|---------|--------|
| 1 | DICOMweb (QIDO-RS / WADO-RS / STOW-RS) | ✅ Built |
| 1 | Duplicate SOP UID handling (configurable policy) | ✅ Built |
| 1 | Multi-filesystem storage with tiering | ✅ Built |
| 1 | Async work queue (Celery + Redis) | ✅ Built |
| 2 | WADO-URI legacy + thumbnail endpoint | ✅ Built |
| 3 | Admin UI (stats, storage, routing, queue) | ✅ Built |
| 3 | Analytics dashboard | ✅ Built |
| 4 | Auto-routing rules engine | ✅ Built |
| 4 | DICOM compression management | ✅ Built |
| 5 | Virtual AE partitions | ✅ Built |
| 5 | Per-partition ports, quotas, isolation | ✅ Built |
| 6 | HIPAA audit log (all access events) | ✅ Built |
| 6 | User management (roles: viewer/tech/radiologist/admin) | ✅ Built |
| + | OHIF Viewer integration | ✅ Built |
| + | Modality Worklist (MWL) SCP + API | ✅ Built |
| + | DICOM anonymization service | ✅ Built |
| + | Schedule management UI | ✅ Built |

---

## Prerequisites

Install these on your Windows machine before starting:

1. **Python 3.11+** — python.org/downloads
2. **Node.js 20 LTS** — nodejs.org
3. **PostgreSQL 15** — postgresql.org/download/windows
4. **Redis** — one of:
   - Docker Desktop (easiest): `docker run -d -p 6379:6379 redis:7-alpine`
   - Redis for Windows: github.com/microsoftarchive/redis/releases
5. **Git** — git-scm.com

---

## Step 1 — Merge files into your existing project

Your existing project structure should look like:

```
your-pacs-project/
├── backend/
│   ├── main.py              ← your original
│   ├── models.py            ← your original
│   ├── auth.py              ← your original
│   ├── database.py          ← your original
│   ├── config.py            ← your original
│   └── routers/
│       ├── auth.py
│       ├── patients.py
│       ├── studies.py
│       ├── series.py
│       ├── instances.py
│       ├── reports.py
│       └── burn.py
└── frontend/
    └── src/
        └── pages/
            ├── Login.jsx    ← your original
            ├── Worklist.jsx ← your original
            ├── Study.jsx    ← your original
            └── ... etc
```

### What to replace vs add

**REPLACE these files entirely** (new versions in this package):
```
backend/models.py          ← consolidated model with all new tables
backend/config.py          ← adds new settings (REDIS_URL, etc.)
backend/main.py            ← use main_final.py as your new main.py
frontend/src/App.jsx       ← updated routing + nav
frontend/src/pages/Worklist.jsx
```

**ADD these new files** (copy directly, no conflict):
```
backend/routers/dicomweb.py
backend/routers/admin.py
backend/routers/audit.py
backend/routers/partitions.py
backend/routers/compression.py
backend/routers/stats.py
backend/routers/users.py
backend/routers/worklist.py
backend/routers/wado_uri.py

backend/services/ingest.py
backend/services/work_queue.py
backend/services/routing.py
backend/services/scp_handler.py
backend/services/partitions.py
backend/services/audit.py
backend/services/worklist.py
backend/services/anonymize.py

backend/alembic/
backend/alembic.ini
backend/database.py        (if you don't have one already)

frontend/src/lib/api.js
frontend/src/hooks/useAuth.js
frontend/src/hooks/useStudies.js
frontend/src/components/StudyTable.jsx
frontend/src/components/FilterBar.jsx
frontend/src/components/StudyActions.jsx
frontend/src/components/DICOMTagBrowser.jsx
frontend/src/main.jsx
frontend/src/pages/Admin.jsx
frontend/src/pages/Users.jsx
frontend/src/pages/Partitions.jsx
frontend/src/pages/AuditLog.jsx
frontend/src/pages/Analytics.jsx
frontend/src/pages/OHIFViewer.jsx
frontend/src/pages/WorklistMgmt.jsx
frontend/src/pages/Upload.jsx   (replace if older)
frontend/src/pages/Burn.jsx     (replace if older)

frontend/package.json
frontend/vite.config.js
frontend/index.html
frontend/Dockerfile.dev

ohif-config.js
docker-compose.yml
nginx.conf
.env.example
```

**Rename main_final.py → main.py** (or keep both and point uvicorn at main_final):
```bash
cd backend
cp main_final.py main.py   # overwrites the old one
```

---

## Step 2 — Configure environment

```bash
cd your-pacs-project
cp .env.example .env
```

Open `.env` and set:

```env
# Required — change these
DATABASE_URL=postgresql://pacs:YOUR_PASSWORD@localhost:5432/pacsdb
SECRET_KEY=<run: python -c "import secrets; print(secrets.token_hex(32))">
WADO_BASE_URL=http://YOUR_SERVER_IP:8000

# DICOM identity
AE_TITLE=OPENPACS
DICOM_PORT=11112

# Storage paths (create these directories)
DICOM_STORAGE_PATH=C:/pacs/storage    # Windows
DICOM_STAGING_PATH=C:/pacs/staging    # Windows
# or on Linux:
# DICOM_STORAGE_PATH=/opt/pacs/storage
# DICOM_STAGING_PATH=/opt/pacs/staging

# Redis
REDIS_URL=redis://localhost:6379/0

# Duplicate handling
DUPLICATE_SOP_POLICY=ignore
```

---

## Step 3 — Create PostgreSQL database

Open pgAdmin or psql:

```sql
CREATE USER pacs WITH PASSWORD 'YOUR_PASSWORD';
CREATE DATABASE pacsdb OWNER pacs;
GRANT ALL PRIVILEGES ON DATABASE pacsdb TO pacs;
```

---

## Step 4 — Install backend dependencies

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate

pip install -r requirements.txt
```

---

## Step 5 — Run database migration

This creates all tables in one shot:

```bash
cd backend
# Make sure venv is active and .env is in place
alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade  -> pacs_phases_001, add_all_pacs_phases
```

If you see errors about existing tables (from your original build), run:
```bash
alembic stamp head   # marks current state without running migrations
```
Then manually add any missing columns shown in the migration.

---

## Step 6 — Create storage directories

```bash
# Windows
mkdir C:\pacs\storage
mkdir C:\pacs\staging

# Linux
mkdir -p /opt/pacs/storage /opt/pacs/staging
```

---

## Step 7 — Start all services

Open **4 terminal windows** (all in your project root, venv active):

**Terminal 1 — FastAPI server:**
```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2 — Celery worker (handles ingest + routing):**
```bash
cd backend
celery -A services.work_queue worker --loglevel=info -Q high,default --concurrency=4
```

**Terminal 3 — Celery beat (handles scheduled tasks):**
```bash
cd backend
celery -A services.work_queue beat --loglevel=info
```

**Terminal 4 — React frontend:**
```bash
cd frontend
npm install     # first time only
npm run dev
```

---

## Step 8 — Verify everything is running

| Service | URL / Port | Expected response |
|---------|-----------|-------------------|
| FastAPI  | http://localhost:8000/health | `{"status":"ok"}` |
| API docs | http://localhost:8000/docs | Swagger UI |
| QIDO-RS  | http://localhost:8000/wado/studies | `[]` (empty JSON array) |
| React app | http://localhost:5173 | Login screen |
| DICOM SCP | port 11112 | Listen for C-ECHO |

Test the DICOM SCP with a C-ECHO:
```bash
# Using dcm4che storescu/echoscu (if installed):
echoscu -c OPENPACS@localhost:11112

# Or from any DICOM workstation / modality simulator
```

---

## Step 9 — First login

Navigate to **http://localhost:5173**

Default admin credentials created during migration:
- Username: `admin`
- Password: `admin123`

**Change this immediately** in Users → Edit → admin.

---

## Step 10 — Set up OHIF Viewer (optional)

### Quick start with Docker:
```bash
docker run -d \
  -p 3000:80 \
  -v ./ohif-config.js:/usr/share/nginx/html/app-config.js \
  --name ohif \
  ohif/app:latest
```

Edit `ohif-config.js` first — change this line:
```javascript
const WADO_ROOT = "http://YOUR_SERVER_IP:8000/wado";
```

Then open http://localhost:3000 — OHIF should show your study worklist.

### From within the React app:
Navigate to **OHIF Viewer** in the sidebar — it opens OHIF in an iframe.

---

## Step 11 — Docker Compose (full stack, optional)

If you want everything containerized:

```bash
# Edit docker-compose.yml — change passwords and WADO_BASE_URL

docker compose up -d db redis
docker compose up -d backend worker beat
docker compose up -d frontend
docker compose --profile ohif up -d ohif

# View logs
docker compose logs -f backend
docker compose logs -f worker
```

Production with nginx:
```bash
cd frontend && npm run build   # build static files first
docker compose --profile prod up -d nginx
```

---

## Step 12 — Configure routing rules

After the first study arrives, set up auto-routing:

1. Go to **Admin → Routing Rules → New Rule**
2. Example — send all CT to a workstation:
   - Name: `CT to Reading Room`
   - Priority: `10`
   - Conditions: `modality = CT`
   - Destination: `AE=CTWS, Host=192.168.1.50, Port=104`

---

## Step 13 — Configure virtual partitions (optional)

If you need multiple logical PACS instances (e.g., separate Radiology and Cardiology):

1. Go to **Partitions → New Partition**
2. Set a unique AE Title (e.g., `CARDIO`) and optionally a separate DICOM port
3. Modalities can send to `CARDIO@yourserver:11113` and studies will be isolated

---

## Troubleshooting

**"celery not found" error:**
```bash
pip install celery[redis]
```

**"Cannot connect to Redis":**
```bash
docker run -d -p 6379:6379 redis:7-alpine
# or check: redis-cli ping
```

**Migration fails with "relation already exists":**
```bash
alembic stamp head   # mark DB as up-to-date without running migration
```

**DICOM SCP won't start (port in use):**
```bash
# Check what's on 11112
netstat -ano | findstr :11112   # Windows
lsof -i :11112                  # Linux
```

**OHIF shows blank / "No studies found":**
- Check `WADO_BASE_URL` in `.env` matches your actual server IP
- Check CORS: `CORS_ORIGINS` in `.env` must include OHIF's port (`:3000`)
- Test: `curl http://localhost:8000/wado/studies` — should return `[]`

**Studies arrive but don't appear in UI:**
- Check Celery worker is running: **Admin → Work Queue** should show workers online
- If offline, ingest runs synchronously — should still work but slower
- Check staging dir: `ls /opt/pacs/staging` — files shouldn't pile up there

---

## Architecture reference

```
Modalities (CT, MR, CR, US)
        │
        │ DICOM C-STORE (port 11112)
        ▼
  ┌─────────────────────────────────┐
  │   DICOM SCP (pynetdicom)        │
  │   Writes to /staging            │
  │   Dispatches to Celery queue    │
  └─────────┬───────────────────────┘
            │
            ▼
  ┌─────────────────────────────────┐
  │   Redis (task broker)           │
  └─────────┬───────────────────────┘
            │
  ┌─────────▼───────────────────────┐
  │   Celery Worker                 │
  │   - index_dicom_file()          │
  │   - route_study()               │
  │   - compress_instance()         │
  └─────────┬───────────────────────┘
            │
  ┌─────────▼──────────┐  ┌────────────────────┐
  │   PostgreSQL        │  │   Filesystem        │
  │   (metadata index)  │  │   (DICOM files)     │
  └─────────┬───────────┘  └────────────────────┘
            │
  ┌─────────▼───────────────────────────────────┐
  │   FastAPI (port 8000)                       │
  │                                             │
  │   /api/*         REST API (studies, etc.)   │
  │   /wado/*        DICOMweb (QIDO/WADO/STOW)  │
  │   /api/admin/*   Admin endpoints            │
  │   /api/audit/*   HIPAA audit log            │
  │   /api/auth/*    Auth + users               │
  │   /api/partitions/* Virtual AE partitions   │
  └──────────────┬──────────────────────────────┘
                 │
       ┌─────────┴─────────┐
       ▼                   ▼
  React App          OHIF Viewer
  (port 5173)        (port 3000)
```

---

## File structure reference

```
your-pacs-project/
├── .env                          ← your secrets (never commit)
├── .env.example                  ← template
├── docker-compose.yml
├── nginx.conf                    ← production reverse proxy
├── ohif-config.js                ← OHIF datasource config
│
├── backend/
│   ├── main.py                   ← FastAPI app entry point
│   ├── models.py                 ← All SQLAlchemy models
│   ├── database.py               ← DB session setup
│   ├── auth.py                   ← JWT auth helpers
│   ├── config.py                 ← Settings (reads .env)
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       └── pacs_phases_001.py  ← single migration for all phases
│   ├── routers/
│   │   ├── dicomweb.py           ← QIDO-RS / WADO-RS / STOW-RS
│   │   ├── admin.py              ← storage, routing rules, queue status
│   │   ├── audit.py              ← HIPAA audit log queries
│   │   ├── partitions.py         ← virtual AE partition CRUD
│   │   ├── compression.py        ← compression job management
│   │   ├── stats.py              ← analytics data endpoints
│   │   ├── users.py              ← user management
│   │   ├── worklist.py           ← MWL scheduled procedures
│   │   └── wado_uri.py           ← legacy WADO + thumbnails
│   └── services/
│       ├── ingest.py             ← DICOM indexing (used by SCP + STOW)
│       ├── work_queue.py         ← Celery tasks
│       ├── routing.py            ← auto-routing rules engine
│       ├── scp_handler.py        ← pynetdicom C-STORE/C-ECHO handlers
│       ├── partitions.py         ← partition SCP management
│       ├── audit.py              ← audit logging middleware
│       ├── worklist.py           ← MWL C-FIND handler
│       └── anonymize.py         ← DICOM anonymization
│
└── frontend/
    ├── package.json
    ├── vite.config.js
    ├── index.html
    ├── Dockerfile.dev
    └── src/
        ├── main.jsx              ← React entry point
        ├── App.jsx               ← Router + sidebar layout
        ├── lib/
        │   └── api.js            ← Axios with JWT
        ├── hooks/
        │   ├── useAuth.js        ← auth state
        │   └── useStudies.js     ← worklist data fetching
        ├── components/
        │   ├── StudyTable.jsx    ← sortable paginated table
        │   ├── FilterBar.jsx     ← search/filter controls
        │   ├── StudyActions.jsx  ← study action buttons
        │   └── DICOMTagBrowser.jsx ← DICOM tag viewer
        └── pages/
            ├── Login.jsx
            ├── Worklist.jsx      ← main study list
            ├── Study.jsx         ← study detail
            ├── Viewer.jsx        ← Cornerstone.js image viewer
            ├── Report.jsx        ← radiology report editor
            ├── Patients.jsx      ← patient list
            ├── Upload.jsx        ← STOW-RS file upload
            ├── Burn.jsx          ← CD/ISO burn
            ├── OHIFViewer.jsx    ← OHIF iframe
            ├── WorklistMgmt.jsx  ← MWL schedule management
            ├── Admin.jsx         ← server administration
            ├── Users.jsx         ← user management
            ├── Partitions.jsx    ← virtual AE partitions
            ├── AuditLog.jsx      ← HIPAA audit log viewer
            └── Analytics.jsx     ← usage analytics dashboard
```
