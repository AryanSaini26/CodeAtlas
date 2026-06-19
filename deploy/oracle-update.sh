#!/usr/bin/env bash
#
# Redeploy Stratum after pulling new code. Run on the VM as root:
#   sudo bash /opt/stratum/deploy/oracle-update.sh
set -euo pipefail

APP_DIR="/opt/stratum"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash ${APP_DIR}/deploy/oracle-update.sh" >&2
  exit 1
fi

cd "${APP_DIR}"
git pull --ff-only
"${APP_DIR}/.venv/bin/pip" install --quiet "${APP_DIR}[all]"
( cd "${APP_DIR}/frontend" && npm ci && npm run build )
systemctl restart stratum
echo "Stratum updated and restarted. Check: systemctl status stratum"
