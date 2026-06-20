# Deploying Stratum (Hosted) to Google Cloud (Always Free)

Google Cloud's **Always Free** tier includes one `e2-micro` VM (in `us-west1`,
`us-central1`, or `us-east1`) with a 30 GB persistent disk — a real Linux box, so
the same generic provisioner
([`deploy/oracle-setup.sh`](https://github.com/AryanSaini26/CodeAtlas/blob/main/deploy/oracle-setup.sh))
runs here unchanged.

> **RAM caveat.** `e2-micro` has ~1 GB RAM. It runs the control plane and serves
> context fine, but indexing a *large* repo or building FAISS embeddings can be
> slow or OOM. Seed a **small** demo repo (Flask is fine) and avoid the
> `[search]` extra on this box. Need more headroom later? Move to Oracle Always
> Free ARM (more RAM) or a paid VM — migration is just copying `/var/lib/stratum`.

## 1. Create the VM

- In the [Cloud Console](https://console.cloud.google.com) → Compute Engine →
  **Create instance**.
- Region: **us-west1 / us-central1 / us-east1** (required for Always Free).
- Machine type: **e2-micro**. Boot disk: **Ubuntu 22.04 LTS**, 30 GB standard.
- Under **Firewall**, check **Allow HTTP traffic** and **Allow HTTPS traffic**
  (creates the 80/443 ingress rules). Add your SSH key under Security.
- After creation, **reserve a static external IP** (VPC network → IP addresses →
  promote the ephemeral IP) so the address is stable.

## 2. Create the DuckDNS domain

- Sign in at [duckdns.org](https://www.duckdns.org), add a subdomain (e.g.
  `stratum` → `stratum.duckdns.org`), point it at the VM's static IP, copy the
  **token**.

## 3. Run the setup script

SSH in (browser SSH or `gcloud compute ssh`), then:

```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/AryanSaini26/CodeAtlas.git
sudo DOMAIN=stratum.duckdns.org bash CodeAtlas/deploy/oracle-setup.sh
```

## 4. Add secrets

```bash
sudo cp stratum.*.private-key.pem /etc/stratum/github-app.pem
sudo chown root:stratum /etc/stratum/github-app.pem && sudo chmod 640 /etc/stratum/github-app.pem
sudo nano /etc/stratum/stratum.env     # App ID, client id/secret, webhook secret, DuckDNS token
sudo systemctl restart stratum
```

## 5. Wire the GitHub App

- **Webhook URL:** `https://stratum.duckdns.org/api/hosted/v1/github/webhook`
- **OAuth callback URL:** `https://stratum.duckdns.org/api/hosted/v1/github/oauth/callback`
- **Setup URL:** `https://stratum.duckdns.org/api/hosted/v1/github/setup`
- Webhook secret matches `STRATUM_GITHUB_WEBHOOK_SECRET`; Contents + Metadata
  read-only; subscribe to **Push** (and **Pull request** once the PR bot is live).

## 6. Verify + seed the demo

```bash
curl https://stratum.duckdns.org/health                       # ok
curl https://stratum.duckdns.org/api/hosted/v1/github/app     # "configured": true
# Seed a small read-only demo, then set the printed values in stratum.env:
sudo -u stratum /opt/stratum/.venv/bin/codeatlas hosted seed-demo \
  --hosted-db /var/lib/stratum/hosted.db --repo https://github.com/pallets/flask.git
```

## Updating later

```bash
sudo bash /opt/stratum/deploy/oracle-update.sh
```
