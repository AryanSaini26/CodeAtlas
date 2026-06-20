# Deploying Stratum (Hosted) to Oracle Cloud Always Free

This is the **long-term $0/month** path: an Oracle Cloud Always Free ARM VM
(up to 4 OCPU / 24 GB RAM, no expiry), a free DuckDNS subdomain, and Caddy for
automatic HTTPS. If A1 capacity is unavailable (common) and you want to go live
now, use [DigitalOcean via the Student Pack](deploy-digitalocean.md) — same
script — and migrate here later. ([Fly.io](deploy-fly.md) is the paid option.)

The VM runs `codeatlas ui`, which serves the hosted API, the remote MCP/context
endpoints, and the dashboard SPA from one process. Caddy terminates TLS and
reverse-proxies to it on `127.0.0.1:8080`. SQLite metadata, per-repo graph DBs,
and checkouts live under `/var/lib/stratum`.

## Two things that trip people up

1. **ARM capacity.** Free A1 instances are often "out of capacity" in busy
   regions. Pick a quieter home region at signup, retry, or use a smaller A1
   shape (1 OCPU / 6 GB is plenty). Don't use the AMD micro (1 GB) — it OOMs on
   real indexing.
2. **Two firewalls.** Oracle's Ubuntu images block every port except 22 at the
   OS level (iptables), *in addition* to the cloud's security list. You must open
   80/443 in **both**. `oracle-setup.sh` handles the OS side; you do the security
   list in the console.

## 1. Create the VM

- Sign up at [oracle.com/cloud/free](https://www.oracle.com/cloud/free/) (card
  for verification; Always Free never charges).
- Create a Compute instance: **Ubuntu 22.04+**, shape **VM.Standard.A1.Flex**
  (1–2 OCPU, 6–12 GB). Upload your SSH public key.
- **Reserve a static public IP** (Networking → reserved public IP, attach to the
  instance) so the address is stable.
- In the instance's **VCN → Security List**, add ingress rules: TCP **80** and
  **443** from `0.0.0.0/0`.

## 2. Create the DuckDNS domain

- Sign in at [duckdns.org](https://www.duckdns.org) (with GitHub).
- Add a subdomain, e.g. `stratum` → `stratum.duckdns.org`.
- Point it at the VM's reserved IP (the updater will keep it current too).
- Copy your DuckDNS **token**.

## 3. Run the setup script

SSH in, then:

```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/AryanSaini26/CodeAtlas.git
sudo DOMAIN=stratum.duckdns.org bash CodeAtlas/deploy/oracle-setup.sh
```

This installs all deps, builds the SPA, installs the systemd service + Caddy +
the DuckDNS timer, and opens the OS firewall. It runs to a single set of
"remaining manual steps" — the secrets.

## 4. Add secrets (the only sensitive step)

```bash
# 4a. The GitHub App private key (PEM file, not inline):
sudo cp stratum.2026-xx-xx.private-key.pem /etc/stratum/github-app.pem
sudo chown root:stratum /etc/stratum/github-app.pem && sudo chmod 640 /etc/stratum/github-app.pem

# 4b. Fill the rest:
sudo nano /etc/stratum/stratum.env     # App ID, client id/secret, webhook secret, DuckDNS token

# 4c. Apply:
sudo systemctl restart stratum
```

`/etc/stratum/stratum.env` and the `.pem` are the only places secrets live —
never in git.

## 5. Wire the GitHub App

In the GitHub App settings:

- **Webhook URL:** `https://stratum.duckdns.org/api/hosted/v1/github/webhook`
- **Setup URL (callback):** `https://stratum.duckdns.org/api/hosted/v1/github/setup`
- **Webhook secret:** matches `STRATUM_GITHUB_WEBHOOK_SECRET`.
- Permissions: **Contents** + **Metadata** read-only. Subscribe to **Push**.

## 6. Verify

```bash
curl https://stratum.duckdns.org/health                       # {"status":"ok",...}
curl https://stratum.duckdns.org/api/hosted/v1/github/app     # "configured": true
```

Then open `https://stratum.duckdns.org/hosted`, install the App on a throwaway
repo, push a commit, and watch the dashboard go `pending → cloning → indexing →
ready`.

## Updating later

```bash
sudo bash /opt/stratum/deploy/oracle-update.sh
```

Pulls latest, reinstalls, rebuilds the SPA, restarts the service.

## Operations

- Logs: `journalctl -u stratum -f` (app), `journalctl -u caddy -f` (TLS/proxy).
- Service: `systemctl status stratum`. It restarts on crash automatically.
- Signup/activation metrics: `codeatlas hosted metrics --hosted-db
  /var/lib/stratum/hosted.db` (or set `STRATUM_ADMIN_TOKEN` and
  `curl -H "X-Stratum-Admin: <token>" https://<domain>/api/hosted/v1/metrics`).
- The background sync worker is in-process (single VM, single process — right for
  this scale). Scaling out later means moving the queue out of process.
