#!/usr/bin/env bash
#
# One-shot provisioner for the hosted Stratum control plane on an
# Oracle Cloud Always Free Ubuntu VM. Idempotent — safe to re-run.
#
# Usage (on the VM, as root):
#   sudo DOMAIN=stratum.duckdns.org bash deploy/oracle-setup.sh
#
# It installs system deps, clones the repo to /opt/stratum, builds the SPA,
# installs a systemd service + Caddy (auto-HTTPS) + a DuckDNS updater, and opens
# ports 80/443 at the OS firewall (Oracle images block them by default).
#
# Secrets are NOT handled here — after this runs, fill /etc/stratum/stratum.env
# and drop the GitHub App private key at /etc/stratum/github-app.pem.
# See docs/deploy-oracle.md for the full runbook.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/AryanSaini26/CodeAtlas.git}"
APP_DIR="/opt/stratum"
DATA_DIR="/var/lib/stratum"
ENV_DIR="/etc/stratum"
ENV_FILE="${ENV_DIR}/stratum.env"
SERVICE_USER="stratum"
DOMAIN="${DOMAIN:-}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo DOMAIN=<your>.duckdns.org bash deploy/oracle-setup.sh" >&2
  exit 1
fi

echo "==> Installing system dependencies"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y \
  git curl ca-certificates gnupg build-essential \
  python3 python3-venv python3-dev \
  debian-keyring debian-archive-keyring apt-transport-https

# Preseed iptables-persistent so it installs without an interactive prompt.
echo "iptables-persistent iptables-persistent/autosave_v4 boolean true" | debconf-set-selections
echo "iptables-persistent iptables-persistent/autosave_v6 boolean true" | debconf-set-selections
apt-get install -y netfilter-persistent iptables-persistent

echo "==> Installing Node.js 20 (NodeSource)"
if ! command -v node >/dev/null 2>&1; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi

echo "==> Installing Caddy (official apt repo)"
if ! command -v caddy >/dev/null 2>&1; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y
  apt-get install -y caddy
fi

echo "==> Creating service user and directories"
id -u "${SERVICE_USER}" >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
mkdir -p "${APP_DIR}" "${DATA_DIR}" "${ENV_DIR}"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${DATA_DIR}"

echo "==> Fetching application code into ${APP_DIR}"
if [[ -d "${APP_DIR}/.git" ]]; then
  git -C "${APP_DIR}" pull --ff-only
else
  git clone "${REPO_URL}" "${APP_DIR}"
fi

echo "==> Creating Python venv and installing the package"
if [[ ! -d "${APP_DIR}/.venv" ]]; then
  python3 -m venv "${APP_DIR}/.venv"
fi
"${APP_DIR}/.venv/bin/pip" install --upgrade pip
"${APP_DIR}/.venv/bin/pip" install "${APP_DIR}[all]"

echo "==> Building the dashboard SPA"
( cd "${APP_DIR}/frontend" && npm ci && npm run build )

echo "==> Installing env template (real values are filled in by you)"
if [[ ! -f "${ENV_FILE}" ]]; then
  cp "${APP_DIR}/deploy/stratum.env.example" "${ENV_FILE}"
fi
chown root:"${SERVICE_USER}" "${ENV_FILE}"
chmod 640 "${ENV_FILE}"

echo "==> Installing systemd service"
cp "${APP_DIR}/deploy/stratum.service" /etc/systemd/system/stratum.service

echo "==> Installing DuckDNS updater (5-minute timer)"
install -m 0755 "${APP_DIR}/deploy/duckdns-update.sh" /usr/local/bin/stratum-duckdns-update
cat >/etc/systemd/system/stratum-duckdns.service <<'EOF'
[Unit]
Description=Update DuckDNS record for Stratum
After=network-online.target
[Service]
Type=oneshot
EnvironmentFile=/etc/stratum/stratum.env
ExecStart=/usr/local/bin/stratum-duckdns-update
EOF
cat >/etc/systemd/system/stratum-duckdns.timer <<'EOF'
[Unit]
Description=Run DuckDNS updater every 5 minutes
[Timer]
OnBootSec=1min
OnUnitActiveSec=5min
[Install]
WantedBy=timers.target
EOF

echo "==> Configuring Caddy"
if [[ -n "${DOMAIN}" ]]; then
  sed "s/__DOMAIN__/${DOMAIN}/g" "${APP_DIR}/deploy/Caddyfile" > /etc/caddy/Caddyfile
else
  echo "WARNING: DOMAIN not set; edit /etc/caddy/Caddyfile manually before HTTPS works." >&2
fi

echo "==> Opening ports 80/443 at the OS firewall"
for port in 80 443; do
  iptables -C INPUT -p tcp --dport "${port}" -j ACCEPT 2>/dev/null \
    || iptables -I INPUT -p tcp --dport "${port}" -j ACCEPT
done
netfilter-persistent save

echo "==> Enabling and starting services"
systemctl daemon-reload
systemctl enable --now stratum.service
systemctl enable --now stratum-duckdns.timer
systemctl reload caddy 2>/dev/null || systemctl restart caddy

cat <<EOF

Setup complete. Remaining manual steps:
  1. Edit ${ENV_FILE} with your GitHub App + DuckDNS values.
  2. Copy your GitHub App private key to /etc/stratum/github-app.pem:
       chown root:${SERVICE_USER} /etc/stratum/github-app.pem && chmod 640 /etc/stratum/github-app.pem
  3. sudo systemctl restart stratum
  4. Point the GitHub App webhook URL at https://${DOMAIN:-<your-domain>}/api/hosted/v1/github/webhook
Verify: curl https://${DOMAIN:-<your-domain>}/health
EOF
