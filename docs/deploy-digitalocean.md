# Deploying Stratum (Hosted) to DigitalOcean

This is the **fastest live path** and effectively free for students: the
[GitHub Student Developer Pack](https://education.github.com/pack) grants **$200
of DigitalOcean credit for a year**, and a $6/mo Droplet runs this comfortably —
so it's ~3 years of runway on the credit, with no ARM-capacity lottery.

The same provisioner used for any Ubuntu host applies here:
[`deploy/oracle-setup.sh`](https://github.com/AryanSaini26/CodeAtlas/blob/main/deploy/oracle-setup.sh)
is generic Ubuntu — it installs deps, builds the SPA, and wires up the systemd
service + Caddy (auto-HTTPS) + DuckDNS. The Droplet runs `codeatlas ui` behind
Caddy on `127.0.0.1:8080`; SQLite metadata, per-repo graphs, and checkouts live
under `/var/lib/stratum`.

> Prefer truly $0 long-term? [Oracle Cloud Always Free](deploy-oracle.md) is the
> same script on a free ARM VM (capacity permitting). Migration is just copying
> `/var/lib/stratum` and re-pointing DNS.

## 1. Claim the credit and create the Droplet

- Activate the [Student Pack](https://education.github.com/pack), then redeem the
  DigitalOcean offer (adds the $200 credit to a new account).
- Create a **Droplet**: Ubuntu 22.04 LTS, **Basic / Regular, $6/mo** (1 GB is
  tight for indexing large repos — pick the **2 GB / $12** plan if you'll index
  big repos; still well within the credit). Add your SSH key during creation.
- Networking: DigitalOcean Droplets are internet-reachable by default (no cloud
  security list to edit). The setup script opens 80/443 at the OS firewall.

## 2. Create the DuckDNS domain

- Sign in at [duckdns.org](https://www.duckdns.org) (with GitHub), add a
  subdomain (e.g. `stratum` → `stratum.duckdns.org`), point it at the Droplet's
  public IP, and copy your **token**.

## 3. Run the setup script

SSH in, then:

```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/AryanSaini26/CodeAtlas.git
sudo DOMAIN=stratum.duckdns.org bash CodeAtlas/deploy/oracle-setup.sh
```

## 4. Add secrets

```bash
# GitHub App private key (PEM file, not inline):
sudo cp stratum.*.private-key.pem /etc/stratum/github-app.pem
sudo chown root:stratum /etc/stratum/github-app.pem && sudo chmod 640 /etc/stratum/github-app.pem
# Fill App ID, client id/secret, webhook secret, DuckDNS token:
sudo nano /etc/stratum/stratum.env
sudo systemctl restart stratum
```

## 5. Wire the GitHub App

- **Webhook URL:** `https://stratum.duckdns.org/api/hosted/v1/github/webhook`
- **OAuth callback URL:** `https://stratum.duckdns.org/api/hosted/v1/github/oauth/callback`
- **Setup URL:** `https://stratum.duckdns.org/api/hosted/v1/github/setup`
- Webhook secret matches `STRATUM_GITHUB_WEBHOOK_SECRET`; permissions Contents +
  Metadata read-only; subscribe to **Push**.

## 6. Verify

```bash
curl https://stratum.duckdns.org/health                       # {"status":"ok",...}
curl https://stratum.duckdns.org/api/hosted/v1/github/app     # "configured": true
```

Then open `https://stratum.duckdns.org/welcome`, click **Explore live demo**, and
confirm a real graph loads with no signup.

## Updating later

```bash
sudo bash /opt/stratum/deploy/oracle-update.sh
```
