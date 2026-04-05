# OpenPACS

Self-hosted DICOM PACS system built with FastAPI, PostgreSQL, Redis, and React.

## Stack
- **Backend**: FastAPI + pynetdicom (DICOM SCP) + Celery
- **Database**: PostgreSQL 15
- **Cache/Queue**: Redis 7
- **Frontend**: React + Vite + Cornerstone.js
- **Viewer**: OHIF Viewer
- **Proxy**: Nginx

## Quick Install (Linux)

```bash
curl -fsSL https://raw.githubusercontent.com/jeffthci/openpacs/main/install.sh | sudo bash
```

Or clone and run:

```bash
git clone https://github.com/jeffthci/openpacs.git
cd openpacs
sudo bash install.sh
```

## Update

```bash
sudo openpacs-update
```

## Manual Docker Commands

```bash
# Start
docker compose up -d

# Stop
docker compose down

# Logs
docker compose logs -f

# Rebuild after code change
docker compose build && docker compose up -d

# Run migrations
docker compose exec backend alembic upgrade head
```

## Default Login
- URL: `http://YOUR_SERVER_IP:8080`
- Username: `admin`
- Password: `admin123` **(change this immediately)**

## Directory Structure
```
openpacs/
├── backend/          # FastAPI app + DICOM SCP + Celery
├── frontend/         # React + Vite frontend
├── nginx/            # Nginx reverse proxy config
├── docker-compose.yml
├── install.sh        # Linux installer
└── .env.example      # Environment template
```

## Service Management (after install)
```bash
systemctl start openpacs
systemctl stop openpacs
systemctl status openpacs
```
