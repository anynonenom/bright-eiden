#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  EIDEN × BrightBean Studio — Oracle Cloud Deploy Script
#  Tested on: Ubuntu 22.04 (ARM Ampere A1 & AMD x86_64)
#
#  Usage (run as ubuntu user on a fresh OCI VM):
#    curl -fsSL https://raw.githubusercontent.com/your-repo/main/deploy-oci.sh | bash
#
#  Or clone the repo and run:
#    chmod +x deploy-oci.sh && ./deploy-oci.sh
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/brightbean}"
REPO_URL="${REPO_URL:-}"   # Set this to your git remote URL
BRANCH="${BRANCH:-main}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}[deploy]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC}  $*"; }
err()  { echo -e "${RED}[error]${NC} $*" >&2; exit 1; }
step() { echo -e "\n${CYAN}══ $* ══${NC}"; }

# ── 1. System update ─────────────────────────────────────────
step "System update"
sudo apt-get update -qq
sudo apt-get upgrade -y -qq
sudo apt-get install -y -qq \
    curl git unzip ca-certificates gnupg lsb-release \
    ufw fail2ban htop

# ── 2. Install Docker ────────────────────────────────────────
step "Docker installation"
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "${USER}"
    log "Docker installed. You may need to re-login for group membership."
else
    log "Docker already installed: $(docker --version)"
fi

# Docker Compose (v2 plugin)
if ! docker compose version &>/dev/null; then
    sudo apt-get install -y -qq docker-compose-plugin
fi
log "Docker Compose: $(docker compose version)"

# ── 3. Firewall (UFW) ────────────────────────────────────────
step "Configuring firewall"
sudo ufw --force reset
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh        # port 22
sudo ufw allow 80/tcp     # HTTP  (Caddy — Let's Encrypt challenge)
sudo ufw allow 443/tcp    # HTTPS
sudo ufw allow 443/udp    # HTTP/3
sudo ufw --force enable
log "UFW firewall active"

# IMPORTANT: also open ports 80 and 443 in your OCI Security List / NSG
# OCI Console → Networking → Virtual Cloud Networks → Security Lists

# ── 4. Fail2ban ──────────────────────────────────────────────
step "Hardening with fail2ban"
sudo systemctl enable fail2ban --now
log "fail2ban active"

# ── 5. Application directory ─────────────────────────────────
step "Application setup at ${APP_DIR}"
sudo mkdir -p "${APP_DIR}"
sudo chown "${USER}:${USER}" "${APP_DIR}"

if [[ -n "${REPO_URL}" ]]; then
    if [[ -d "${APP_DIR}/.git" ]]; then
        log "Repository exists — pulling latest"
        git -C "${APP_DIR}" fetch origin
        git -C "${APP_DIR}" reset --hard "origin/${BRANCH}"
    else
        log "Cloning repository"
        git clone --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
    fi
    cd "${APP_DIR}"
else
    warn "REPO_URL not set — skipping git clone."
    warn "Copy your project files to ${APP_DIR} manually, then re-run."
    cd "${APP_DIR}" 2>/dev/null || err "No files found at ${APP_DIR}. Set REPO_URL or copy files first."
fi

# ── 6. Environment file ──────────────────────────────────────
step "Environment configuration"
if [[ ! -f "${APP_DIR}/.env" ]]; then
    if [[ -f "${APP_DIR}/.env.oci.example" ]]; then
        cp "${APP_DIR}/.env.oci.example" "${APP_DIR}/.env"
        warn ".env created from template. EDIT IT NOW before continuing:"
        warn "  nano ${APP_DIR}/.env"
        echo
        echo "Fill in:"
        echo "  • SECRET_KEY + ENCRYPTION_KEY_SALT (generate with python)"
        echo "  • ALLOWED_HOSTS and APP_DOMAIN (your domain)"
        echo "  • POSTGRES_PASSWORD and DATABASE_URL"
        echo "  • STORAGE_BACKEND and OCI Object Storage credentials"
        echo "  • EMAIL settings"
        echo
        read -rp "Press ENTER after editing .env to continue, or Ctrl+C to abort..." _
    else
        err "No .env or .env.oci.example found. Cannot continue."
    fi
else
    log ".env already exists"
fi

# Validate required vars
source "${APP_DIR}/.env"
[[ -z "${SECRET_KEY:-}" ]]      && err "SECRET_KEY is not set in .env"
[[ -z "${APP_DOMAIN:-}" ]]      && err "APP_DOMAIN is not set in .env"
[[ -z "${POSTGRES_PASSWORD:-}" ]] && err "POSTGRES_PASSWORD is not set in .env"
log "Environment validation passed"

# ── 7. Build & deploy ────────────────────────────────────────
step "Building and deploying containers"
cd "${APP_DIR}"

docker compose -f docker-compose.oci.yml pull --quiet 2>/dev/null || true
docker compose -f docker-compose.oci.yml build --quiet

log "Running database migrations"
docker compose -f docker-compose.oci.yml run --rm migrate

log "Collecting static files"
docker compose -f docker-compose.oci.yml run --rm collectstatic

log "Starting all services"
docker compose -f docker-compose.oci.yml up -d --remove-orphans

# ── 8. Create superuser (first run only) ─────────────────────
step "Superuser setup"
echo
echo "To create the admin superuser, run:"
echo "  docker compose -f ${APP_DIR}/docker-compose.oci.yml exec app python manage.py createsuperuser"
echo

# ── 9. Systemd service (auto-start on reboot) ────────────────
step "Systemd auto-start"
sudo tee /etc/systemd/system/brightbean.service > /dev/null <<EOF
[Unit]
Description=BrightBean Studio (Docker Compose)
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${APP_DIR}
ExecStart=/usr/bin/docker compose -f docker-compose.oci.yml up -d --remove-orphans
ExecStop=/usr/bin/docker compose -f docker-compose.oci.yml down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable brightbean
log "brightbean.service registered and enabled"

# ── 10. Status report ────────────────────────────────────────
step "Deployment complete"
echo
echo -e "${GREEN}✓ BrightBean Studio is running${NC}"
echo
docker compose -f "${APP_DIR}/docker-compose.oci.yml" ps
echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Application URL : https://${APP_DOMAIN:-<your-domain>}"
echo " Logs            : docker compose -f ${APP_DIR}/docker-compose.oci.yml logs -f"
echo " Restart         : sudo systemctl restart brightbean"
echo " Update          : git -C ${APP_DIR} pull && sudo systemctl restart brightbean"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
echo -e "${YELLOW}IMPORTANT — OCI Console steps you must do manually:${NC}"
echo "  1. Add Ingress Rules in your Security List / NSG:"
echo "     • Source: 0.0.0.0/0   Protocol: TCP   Port: 80"
echo "     • Source: 0.0.0.0/0   Protocol: TCP   Port: 443"
echo "     • Source: 0.0.0.0/0   Protocol: UDP   Port: 443"
echo "  2. Point your DNS A record to: $(curl -s ifconfig.me 2>/dev/null || echo '<vm-public-ip>')"
echo "  3. Create OCI Object Storage bucket + Customer Secret Keys (for media)"
echo
