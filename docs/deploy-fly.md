# Deploying Stratum (Hosted) to Fly.io

This is the runbook for putting the hosted control plane on a real public URL.
The repository ships everything needed except the secrets — those are set in
Fly's secret store and **never committed**.

The image (`deploy/Dockerfile`) builds the dashboard SPA and runs
`codeatlas ui`, which serves the hosted API, the remote MCP/context endpoints,
and the dashboard from a single FastAPI process. SQLite metadata, per-repo
graph DBs, and checkouts live on a persistent Fly volume mounted at `/data`.

## Prerequisites

- A [Fly.io](https://fly.io) account and the `fly` CLI (`fly auth login`).
- A registered GitHub App (App ID, client ID/secret, webhook secret, and a
  generated private key `.pem`). You will point its webhook + setup URLs at the
  deployed domain in the last step.

## 1. Create the app and volume

```bash
# Pick a unique app name; update `app = ...` in fly.toml to match.
fly apps create stratum-hosted

# Persistent storage for SQLite + checkouts (same region as the app).
fly volumes create stratum_data --region iad --size 1
```

## 2. Set secrets (never commit these)

```bash
fly secrets set \
  STRATUM_GITHUB_APP_ID="123456" \
  STRATUM_GITHUB_CLIENT_ID="Iv1.xxxxxxxx" \
  STRATUM_GITHUB_CLIENT_SECRET="xxxxxxxx" \
  STRATUM_GITHUB_WEBHOOK_SECRET="$(openssl rand -hex 32)" \
  STRATUM_GITHUB_PRIVATE_KEY="$(cat path/to/stratum.private-key.pem)"
```

The webhook secret you set here must match the one configured in the GitHub
App. The private key is the full PEM contents (newlines preserved); Fly stores
it encrypted.

## 3. Deploy

```bash
fly deploy
```

## 4. Wire the public URL back to the GitHub App

```bash
# Use the domain Fly assigned (or your custom domain).
fly secrets set STRATUM_PUBLIC_URL="https://stratum-hosted.fly.dev"
```

Then in the GitHub App settings:

- **Webhook URL:** `https://<your-domain>/api/hosted/v1/github/webhook`
- **Setup URL (callback):** `https://<your-domain>/api/hosted/v1/github/setup`
- **Webhook secret:** the same value as `STRATUM_GITHUB_WEBHOOK_SECRET`.

Verify liveness and config:

```bash
curl https://<your-domain>/health
curl https://<your-domain>/api/hosted/v1/github/app   # configured: true
```

## Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `STRATUM_GITHUB_APP_ID` | yes | Mint installation tokens (JWT issuer). |
| `STRATUM_GITHUB_PRIVATE_KEY` (or `_PATH`) | yes | Signs the App JWT. |
| `STRATUM_GITHUB_WEBHOOK_SECRET` | yes | Verifies `X-Hub-Signature-256`. |
| `STRATUM_GITHUB_CLIENT_ID` / `_SECRET` | for OAuth | Dashboard "Sign in with GitHub" (Phase 2). |
| `STRATUM_PUBLIC_URL` | yes | Base URL used in setup/webhook callbacks. |
| `PORT` | no | Listen port (Fly sets 8080 via `fly.toml`). |
| `STRATUM_WEBHOOK_RATE_CAPACITY` / `_REFILL` | no | Per-installation webhook rate limit. |
| `STRATUM_MCP_RATE_CAPACITY` / `_REFILL` | no | Per token+repo remote-context rate limit. |

> Never commit any of the GitHub App secret values. `fly secrets` and the
> GitHub App settings are the only places they belong.

## Notes

- This is a single-process, single-volume deployment — right-sized for the MVP.
  The background sync worker is in-process; scaling horizontally later means
  moving the queue out of process (Redis/Celery), which is intentionally
  deferred.
- `auto_stop_machines` lets the app scale to zero when idle; the first request
  after idle pays a cold start. Set `min_machines_running = 1` (default here) to
  keep it warm for demos.
