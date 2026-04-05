#!/bin/bash
# ===========================================================================
#  OpenPACS Linux Installer v1.1.0
#  Pulls code from GitHub: github.com/jeffthci/openpacs
#  Supports: Ubuntu 20.04, 22.04 / Debian 11, 12
#  Run as root: sudo bash install.sh
# ===========================================================================
set -e

VERSION="1.1.0"
REPO_URL="https://github.com/jeffthci/openpacs.git"
INSTALL_DIR="/opt/openpacs"
DATA_DIR="/var/lib/openpacs"
LOG_FILE="/var/log/openpacs-install.log"

# ---- COLORS ----
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; GRAY='\033[0;37m'; NC='\033[0m'

step() { echo -e "\n${CYAN}>>> $1${NC}";        echo "[$(date '+%H:%M:%S')] STEP $1" >> "$LOG_FILE"; }
ok()   { echo -e "  ${GREEN}[OK]${NC} $1";     echo "[$(date '+%H:%M:%S')]  OK  $1" >> "$LOG_FILE"; }
warn() { echo -e "  ${YELLOW}[!!]${NC} $1";    echo "[$(date '+%H:%M:%S')] WRN $1" >> "$LOG_FILE"; }
info() { echo -e "  ${GRAY}...${NC} $1";       echo "[$(date '+%H:%M:%S')] INF $1" >> "$LOG_FILE"; }
fail() { echo -e "\n  ${RED}[FAIL]${NC} $1";   echo "[$(date '+%H:%M:%S')] FAIL $1" >> "$LOG_FILE"
         echo "  Log: $LOG_FILE"; exit 1; }

mkdir -p "$(dirname "$LOG_FILE")"
echo "[$(date)] Install started" >> "$LOG_FILE"

# ---- BANNER ----
clear
echo -e "${CYAN}"
echo "  +------------------------------------------------------------+"
echo "  |  OpenPACS v${VERSION}  -  Linux Installer                 |"
echo "  |  Source: github.com/jeffthci/openpacs                     |"
echo "  +------------------------------------------------------------+"
echo -e "${NC}"

# ---- ROOT CHECK ----
[ "$EUID" -ne 0 ] && fail "Run as root: sudo bash install.sh"

# ---- DETECT OS ----
step "Detecting OS..."
[ ! -f /etc/os-release ] && fail "/etc/os-release not found"
. /etc/os-release
OS_ID="$ID"
info "OS: $PRETTY_NAME"
case "$OS_ID" in
    ubuntu|debian) ok "Supported OS" ;;
    *) warn "Untested OS: $OS_ID - proceeding anyway" ;;
esac

# ---- CONFIGURATION ----
step "Configuration..."
AE_TITLE="${AE_TITLE:-OPENPACS}"
DICOM_PORT="${DICOM_PORT:-11112}"
WEB_PORT="${WEB_PORT:-8080}"
API_PORT="${API_PORT:-8000}"
STORAGE_PATH="${STORAGE_PATH:-$DATA_DIR/storage}"

if [ -z "$SILENT" ]; then
    read -p "  AE Title        [$AE_TITLE]:   " v; [ -n "$v" ] && AE_TITLE="$v"
    read -p "  DICOM Port      [$DICOM_PORT]: " v; [ -n "$v" ] && DICOM_PORT="$v"
    read -p "  Web Port        [$WEB_PORT]:   " v; [ -n "$v" ] && WEB_PORT="$v"
    read -p "  API Port        [$API_PORT]:   " v; [ -n "$v" ] && API_PORT="$v"
    read -p "  Storage Path    [$STORAGE_PATH]: " v; [ -n "$v" ] && STORAGE_PATH="$v"
    echo ""
    read -p "  Proceed? [Y/n]: " confirm
    [[ "$confirm" =~ ^[nN] ]] && exit 0
fi
info "AE=$AE_TITLE  DICOM=$DICOM_PORT  Web=$WEB_PORT  API=$API_PORT"

# ---- DIRECTORIES ----
step "Creating directories..."
mkdir -p \
    "$INSTALL_DIR" \
    "$DATA_DIR/logs" \
    "$STORAGE_PATH" \
    "$DATA_DIR/staging" \
    "$DATA_DIR/postgres" \
    "$DATA_DIR/redis"
ok "Directories created"

# ---- SYSTEM PACKAGES ----
step "Installing system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq 2>&1 | tail -1
apt-get install -y -qq \
    curl wget git unzip \
    ca-certificates gnupg lsb-release \
    openssl 2>&1 | tail -3
ok "System packages installed"

# ---- DOCKER ----
step "Installing Docker..."
if command -v docker &>/dev/null && docker compose version &>/dev/null; then
    ok "Docker already installed: $(docker --version | grep -oP '\d+\.\d+\.\d+' | head -1)"
else
    info "Adding Docker APT repository..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL "https://download.docker.com/linux/$OS_ID/gpg" \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/$OS_ID $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -qq 2>&1 | tail -1
    apt-get install -y -qq \
        docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin 2>&1 | tail -3
    systemctl enable --now docker
    ok "Docker installed"
fi

# Final check
docker compose version &>/dev/null || fail "docker compose plugin not available"
ok "Docker Compose ready"

# ---- GITHUB AUTH ----
step "GitHub authentication..."
echo ""
echo -e "  ${YELLOW}Repo is private - a GitHub Personal Access Token is required.${NC}"
echo "  Create one at: https://github.com/settings/tokens/new"
echo "  Required scope: repo"
echo ""

if [ -z "$GITHUB_TOKEN" ]; then
    read -s -p "  Enter GitHub token: " GITHUB_TOKEN
    echo ""
fi
[ -z "$GITHUB_TOKEN" ] && fail "GitHub token is required"

info "Verifying token..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: token $GITHUB_TOKEN" \
    "https://api.github.com/repos/jeffthci/openpacs")
[ "$HTTP_CODE" != "200" ] && fail "Token invalid or repo not accessible (HTTP $HTTP_CODE)"
ok "GitHub token verified"

AUTHED_URL="https://${GITHUB_TOKEN}@github.com/jeffthci/openpacs.git"

# ---- CLONE OR UPDATE ----
step "Fetching code from GitHub..."
if [ -d "$INSTALL_DIR/.git" ]; then
    info "Repository already exists — pulling latest..."
    cd "$INSTALL_DIR"
    git remote set-url origin "$AUTHED_URL"
    git pull origin main 2>&1 | tail -3
    ok "Code updated"
else
    info "Cloning repository..."
    [ -d "$INSTALL_DIR" ] && rm -rf "$INSTALL_DIR"
    git clone "$AUTHED_URL" "$INSTALL_DIR" 2>&1 | tail -3
    ok "Repository cloned"
fi

# Remove token from remote URL for security
cd "$INSTALL_DIR"
git remote set-url origin "https://github.com/jeffthci/openpacs.git"

# ---- SERVER IP ----
SERVER_IP=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K\S+' | head -1)
[ -z "$SERVER_IP" ] && SERVER_IP=$(hostname -I | awk '{print $1}')
[ -z "$SERVER_IP" ] && SERVER_IP="localhost"
info "Server IP: $SERVER_IP"

# ---- SECRETS ----
# Preserve existing secrets on re-run
if [ -f "$INSTALL_DIR/.env" ]; then
    info "Preserving existing secrets from .env"
    SECRET_KEY=$(grep '^SECRET_KEY=' "$INSTALL_DIR/.env" | cut -d= -f2-)
    DB_PASS=$(grep '^POSTGRES_PASSWORD=' "$INSTALL_DIR/.env" | cut -d= -f2-)
fi
SECRET_KEY="${SECRET_KEY:-$(openssl rand -hex 32)}"
DB_PASS="${DB_PASS:-$(openssl rand -hex 16)}"

# ---- WRITE .env ----
step "Writing .env configuration..."
cat > "$INSTALL_DIR/.env" << ENV
# OpenPACS Configuration
# Generated by installer on $(date)

# Database
DATABASE_URL=postgresql://pacs:${DB_PASS}@db:5432/pacsdb
POSTGRES_DB=pacsdb
POSTGRES_USER=pacs
POSTGRES_PASSWORD=${DB_PASS}

# Security
SECRET_KEY=${SECRET_KEY}
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480

# DICOM
AE_TITLE=${AE_TITLE}
DICOM_PORT=${DICOM_PORT}
DICOM_STORAGE_PATH=/opt/pacs/storage
DICOM_STAGING_PATH=/opt/pacs/staging
DUPLICATE_SOP_POLICY=ignore

# Ports
API_PORT=${API_PORT}
WEB_PORT=${WEB_PORT}

# URLs
WADO_BASE_URL=http://${SERVER_IP}:${API_PORT}
REDIS_URL=redis://redis:6379/0
CORS_ORIGINS=http://localhost:${WEB_PORT},http://${SERVER_IP}:${WEB_PORT},http://localhost:3000
VITE_API_URL=http://${SERVER_IP}:${API_PORT}
VITE_OHIF_URL=http://${SERVER_IP}:3000
ENV
ok ".env written"

# ---- WRITE OVERRIDE ----
step "Writing docker-compose.override.yml..."
cat > "$INSTALL_DIR/docker-compose.override.yml" << OVERRIDE
version: "3.9"
services:
  backend:
    restart: always
    ports:
      - "${API_PORT}:8000"
      - "${DICOM_PORT}:11112/tcp"
      - "${DICOM_PORT}:11112/udp"
    volumes:
      - ${STORAGE_PATH}:/opt/pacs/storage
      - ${DATA_DIR}/staging:/opt/pacs/staging
  worker:
    restart: always
    volumes:
      - ${STORAGE_PATH}:/opt/pacs/storage
      - ${DATA_DIR}/staging:/opt/pacs/staging
  beat:
    restart: always
  frontend:
    restart: always
    ports:
      - "${WEB_PORT}:5173"
  db:
    restart: always
    volumes:
      - ${DATA_DIR}/postgres:/var/lib/postgresql/data
  redis:
    restart: always
    volumes:
      - ${DATA_DIR}/redis:/data
OVERRIDE
ok "docker-compose.override.yml written"

# Validate YAML before proceeding
cd "$INSTALL_DIR"
docker compose config --quiet 2>/dev/null && ok "Compose config valid" \
    || fail "docker-compose config invalid - check .env and override file"

# ---- PULL BASE IMAGES ----
step "Pulling base images..."
cd "$INSTALL_DIR"
docker compose pull 2>&1 | grep -E "Pulled|Skipped|Error" || true
ok "Base images pulled"

# ---- BUILD APP IMAGES ----
step "Building application images (first run takes several minutes)..."
cd "$INSTALL_DIR"
docker compose build 2>&1
ok "Images built"

# ---- START ----
step "Starting OpenPACS containers..."
cd "$INSTALL_DIR"
docker compose up -d --remove-orphans
ok "Containers started"

# Show status
docker compose ps

# ---- WAIT FOR API ----
step "Waiting for API to be ready..."
READY=0
for i in $(seq 1 40); do
    if curl -sf "http://localhost:${API_PORT}/health" &>/dev/null; then
        READY=1
        break
    fi
    sleep 5
    info "  Still waiting... (${i}/40)"
done
if [ $READY -eq 1 ]; then
    ok "API is ready on port $API_PORT"
else
    warn "API did not respond in time - check logs: cd $INSTALL_DIR && docker compose logs backend"
fi

# ---- DB MIGRATION + ADMIN USER ----
step "Running database migrations..."
sleep 3
cd "$INSTALL_DIR"
docker compose exec -T backend alembic upgrade head 2>&1 \
    && ok "Migrations complete" \
    || warn "Migration issue - may need a moment, retry: docker compose exec backend alembic upgrade head"

step "Creating admin user..."
docker compose exec -T backend python -c "
import sys
sys.path.insert(0, '/app')
from database import SessionLocal
from models import User
from passlib.context import CryptContext
db = SessionLocal()
if not db.query(User).filter(User.username == 'admin').first():
    db.add(User(
        username='admin',
        email='admin@localhost',
        hashed_password=CryptContext(schemes=['bcrypt']).hash('admin123'),
        role='admin',
        is_active=True
    ))
    db.commit()
    print('Admin user created: admin / admin123')
else:
    print('Admin user already exists')
db.close()
" 2>&1 || warn "Admin user creation deferred - will complete on first API call"

# ---- FIREWALL ----
step "Configuring firewall..."
if command -v ufw &>/dev/null; then
    ufw allow "$WEB_PORT/tcp"   comment "OpenPACS Web"   2>/dev/null || true
    ufw allow "$API_PORT/tcp"   comment "OpenPACS API"   2>/dev/null || true
    ufw allow "$DICOM_PORT/tcp" comment "OpenPACS DICOM" 2>/dev/null || true
    ok "UFW rules added (ports $WEB_PORT, $API_PORT, $DICOM_PORT)"
elif command -v firewall-cmd &>/dev/null; then
    firewall-cmd --permanent --add-port="$WEB_PORT/tcp"   2>/dev/null || true
    firewall-cmd --permanent --add-port="$API_PORT/tcp"   2>/dev/null || true
    firewall-cmd --permanent --add-port="$DICOM_PORT/tcp" 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
    ok "firewalld rules added"
else
    info "No firewall detected - ensure ports $WEB_PORT, $API_PORT, $DICOM_PORT are open"
fi

# ---- SYSTEMD SERVICE ----
step "Installing systemd service..."
cat > /etc/systemd/system/openpacs.service << SERVICE
[Unit]
Description=OpenPACS DICOM Server
Documentation=https://github.com/jeffthci/openpacs
After=network-online.target docker.service
Requires=docker.service
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${INSTALL_DIR}
ExecStart=/usr/bin/docker compose up -d --remove-orphans
ExecStop=/usr/bin/docker compose down
ExecReload=/usr/bin/docker compose up -d --remove-orphans
StandardOutput=journal
StandardError=journal
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable openpacs
ok "openpacs.service installed and enabled at boot"

# ---- UPDATE SCRIPT ----
step "Installing update script..."
cat > /usr/local/bin/openpacs-update << 'UPDATESCRIPT'
#!/bin/bash
# OpenPACS Update Script - pulls latest code and restarts
set -e
INSTALL_DIR="/opt/openpacs"
GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

[ "$EUID" -ne 0 ] && echo "Run as root: sudo openpacs-update" && exit 1

echo -e "\n${CYAN}>>> OpenPACS Update${NC}"

GITHUB_TOKEN="${1:-$GITHUB_TOKEN}"
if [ -z "$GITHUB_TOKEN" ]; then
    read -s -p "  GitHub token: " GITHUB_TOKEN; echo ""
fi
[ -z "$GITHUB_TOKEN" ] && echo "Token required" && exit 1

echo "  ... Pulling latest code..."
cd "$INSTALL_DIR"
git remote set-url origin "https://${GITHUB_TOKEN}@github.com/jeffthci/openpacs.git"
git pull origin main
git remote set-url origin "https://github.com/jeffthci/openpacs.git"

echo "  ... Rebuilding images..."
docker compose build

echo "  ... Restarting containers..."
docker compose up -d --remove-orphans

echo "  ... Running migrations..."
sleep 5
docker compose exec -T backend alembic upgrade head 2>/dev/null || true

echo -e "\n${GREEN}  [OK] OpenPACS updated successfully${NC}"
echo ""
docker compose ps
UPDATESCRIPT

chmod +x /usr/local/bin/openpacs-update
ok "openpacs-update installed at /usr/local/bin/openpacs-update"

# ---- SAVE CONFIG ----
cat > /etc/openpacs.conf << CONF
VERSION=${VERSION}
INSTALL_DIR=${INSTALL_DIR}
DATA_DIR=${DATA_DIR}
SERVER_IP=${SERVER_IP}
AE_TITLE=${AE_TITLE}
DICOM_PORT=${DICOM_PORT}
WEB_PORT=${WEB_PORT}
API_PORT=${API_PORT}
STORAGE_PATH=${STORAGE_PATH}
REPO=https://github.com/jeffthci/openpacs
INSTALLED=$(date '+%Y-%m-%d %H:%M:%S')
CONF

# ---- DONE ----
echo ""
echo -e "${GREEN}  +------------------------------------------------------------+${NC}"
echo -e "${GREEN}  |  OpenPACS v${VERSION} installed successfully!              |${NC}"
echo -e "${GREEN}  |                                                            |${NC}"
echo -e "${GREEN}  |  Web UI:    http://${SERVER_IP}:${WEB_PORT}                   |${NC}"
echo -e "${GREEN}  |  API:       http://${SERVER_IP}:${API_PORT}                   |${NC}"
echo -e "${GREEN}  |  DICOM SCP: ${SERVER_IP}:${DICOM_PORT}  AE: ${AE_TITLE}            |${NC}"
echo -e "${GREEN}  |                                                            |${NC}"
echo -e "${GREEN}  |  Login:  admin / admin123  (change immediately!)          |${NC}"
echo -e "${GREEN}  |                                                            |${NC}"
echo -e "${GREEN}  |  systemctl start|stop|status openpacs                     |${NC}"
echo -e "${GREEN}  |  sudo openpacs-update          (pull & redeploy)          |${NC}"
echo -e "${GREEN}  |  cd /opt/openpacs && docker compose logs -f               |${NC}"
echo -e "${GREEN}  +------------------------------------------------------------+${NC}"
echo ""
