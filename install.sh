#!/bin/bash
# Doc-KB System Installer
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

# === Check root ===
[[ $EUID -eq 0 ]] || err "Must run as root (sudo)"

# === Detect OS ===
OS="$(uname -s)"
[[ "$OS" == "Linux" ]] || err "Linux only (detected: $OS)"

# === Step 1: Install Docker ===
if ! command -v docker &>/dev/null; then
  info "Installing Docker..."
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
else
  info "Docker already installed ($(docker --version))"
fi

# === Step 2: Install Docker Compose plugin ===
if ! docker compose version &>/dev/null; then
  info "Installing Docker Compose plugin..."
  DOCKER_CONFIG=${DOCKER_CONFIG:-/usr/local/lib/docker/cli-plugins}
  mkdir -p "$DOCKER_CONFIG"
  curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o "$DOCKER_CONFIG/docker-compose"
  chmod +x "$DOCKER_CONFIG/docker-compose"
fi
info "Docker Compose: $(docker compose version)"

# === Step 3: Setup environment ===
if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    warn ".env created from .env.example — EDIT passwords before continuing!"
    warn "  vi .env"
    exit 1
  else
    err ".env.example not found"
  fi
fi
source .env

# === Step 4: Create mount points ===
info "Creating mount points..."
mkdir -p /data/postgres /data/elasticsearch /data/health-reports
# NFS/SMB mounts depend on your environment — see README

# === Step 5: Pull base images ===
info "Pulling base Docker images..."
docker pull pgvector/pgvector:pg17
docker pull elasticsearch:8.17.4
docker pull ollama/ollama:latest

# === Step 6: Build services ===
info "Building services (this may take a while)..."
docker compose build --parallel

# === Step 7: Start services ===
info "Starting all services..."
docker compose up -d --remove-orphans

# === Step 8: Wait for health checks ===
info "Waiting for services to become healthy..."
sleep 10
docker compose ps

# === Step 9: Setup cron jobs ===
info "Setting up cron jobs..."
CRON_FILE=$(mktemp)
crontab -l 2>/dev/null > "$CRON_FILE" || true

# Daily DB backup at 3 AM
if ! grep -q "backup.sh" "$CRON_FILE"; then
  echo "0 3 * * * $REPO_DIR/backup.sh >> /var/log/doc-kb-backup.log 2>&1" >> "$CRON_FILE"
fi

# Pipeline trigger every 6 hours
if ! grep -q "batch-parse" "$CRON_FILE"; then
  echo "0 */6 * * * timeout 300 curl -s -X POST http://localhost:8000/api/documents/batch-parse >> /var/log/doc-kb-pipeline.log 2>&1" >> "$CRON_FILE"
fi

crontab "$CRON_FILE"
rm -f "$CRON_FILE"
info "Cron jobs installed"

# === Step 10: Show info ===
info "=== Installation Complete ==="
echo ""
echo "  Frontend:  http://$(hostname -I | awk '{print $1}')"
echo "  Backend:   http://$(hostname -I | awk '{print $1}'):8000"
echo "  Postgres:  localhost:5432 (user: docadmin / password from .env)"
echo "  Elastic:   localhost:9200"
echo "  Ollama:    localhost:11434"
echo ""
echo "  Next steps:"
echo "    1. Mount your SMB/NFS source to /data/originals (or configure doc_sources via API)"
echo "    2. Access the frontend and add a document source"
echo "    3. The pipeline will automatically scan, parse, enrich, and embed"
echo ""
