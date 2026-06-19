#!/usr/bin/env bash
#
# Update the DuckDNS A-record to the VM's current public IP. Run by the
# stratum-duckdns.timer every 5 minutes. Reads DUCKDNS_DOMAIN / DUCKDNS_TOKEN
# from the systemd EnvironmentFile (/etc/stratum/stratum.env).
set -euo pipefail

: "${DUCKDNS_DOMAIN:?DUCKDNS_DOMAIN not set}"
: "${DUCKDNS_TOKEN:?DUCKDNS_TOKEN not set}"

# Empty ip= lets DuckDNS detect the caller's public IP automatically.
response="$(curl -fsS "https://www.duckdns.org/update?domains=${DUCKDNS_DOMAIN}&token=${DUCKDNS_TOKEN}&ip=")"
if [[ "${response}" != "OK" ]]; then
  echo "DuckDNS update failed: ${response}" >&2
  exit 1
fi
echo "DuckDNS updated: ${DUCKDNS_DOMAIN}.duckdns.org"
