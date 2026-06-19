# Stratum Hosted MVP

Stratum is the hosted team context gateway powered by the open-source CodeAtlas
engine. The current implementation is a local-dev hosted control plane plus a
GitHub App sync foundation. It is not full SaaS yet, but it exercises the
product path without requiring live GitHub OAuth credentials, Stripe, external
cloning, or paid APIs in CI.

## Local Dev Flow

```bash
codeatlas hosted bootstrap --hosted-db .codeatlas/hosted.db
codeatlas hosted register-repo \
  --hosted-db .codeatlas/hosted.db \
  --team default \
  --path . \
  --name codeatlas
codeatlas hosted sync --hosted-db .codeatlas/hosted.db --repo codeatlas
codeatlas ui --db .codeatlas/graph.db --hosted-db .codeatlas/hosted.db
```

Open `/hosted` in the UI. Paste the bootstrap bearer token into the token field
if it is not already stored in the browser.

The `stratum` console script is an alias to the same CLI. Existing
`codeatlas ...` commands remain the compatibility surface for the package,
imports, docs, and current users.

## What It Provides

- SQLite metadata for users, teams, memberships, repos, tokens, and sync
  events.
- Bearer tokens with SHA-256 hashes stored server-side and only a visible
  prefix retained for display.
- Repo registration by local path, with one graph DB per registered repo.
- Hosted sync that indexes the registered repo, records parsed/skipped/error
  counts, captures the current git commit SHA when available, and updates index
  freshness.
- Authenticated hosted context endpoint:
  `/api/hosted/v1/repos/{repo_id}/context?q=...`.
- Dashboard view for repo status, graph stats, sync history, context preview,
  and connection details.
- GitHub App metadata tables for installations, provider repositories,
  activation state, webhook delivery IDs, and last webhook event.
- GitHub webhook ingestion with `X-Hub-Signature-256` validation whenever
  `STRATUM_GITHUB_WEBHOOK_SECRET` is configured.

## GitHub App Mode

The GitHub App path is product-shaped but still local-first:

```bash
codeatlas hosted github status --hosted-db .codeatlas/hosted.db
codeatlas hosted github webhook-test \
  --hosted-db .codeatlas/hosted.db \
  --delivery tests/fixtures/github_push_webhook.json
codeatlas hosted github sync --hosted-db .codeatlas/hosted.db --repo <repo-id-or-name>
```

Supported environment variables:

```text
STRATUM_GITHUB_APP_ID
STRATUM_GITHUB_CLIENT_ID
STRATUM_GITHUB_CLIENT_SECRET
STRATUM_GITHUB_WEBHOOK_SECRET
STRATUM_GITHUB_PRIVATE_KEY
STRATUM_GITHUB_PRIVATE_KEY_PATH
STRATUM_PUBLIC_URL
```

Current GitHub routes:

```text
GET  /api/hosted/v1/github/app
POST /api/hosted/v1/github/installations
GET  /api/hosted/v1/github/installations
POST /api/hosted/v1/github/installations/{id}/repos
GET  /api/hosted/v1/github/installations/{id}/repos
POST /api/hosted/v1/github/repos/{provider_repo_id}/activate
POST /api/hosted/v1/github/webhook
```

Activation currently maps a GitHub repository to a local checkout path, then
uses the same per-repo graph DB sync path as the local hosted flow. Hosted
cloning/job execution is intentionally left for the next slice.

## API Shape

All hosted endpoints except `/api/hosted/v1/dev/bootstrap` require:

```text
Authorization: Bearer <token>
```

Important endpoints:

```text
POST /api/hosted/v1/dev/bootstrap
GET  /api/hosted/v1/repos
POST /api/hosted/v1/repos
POST /api/hosted/v1/repos/{repo_id}/sync
GET  /api/hosted/v1/repos/{repo_id}/stats
GET  /api/hosted/v1/repos/{repo_id}/sync-events
GET  /api/hosted/v1/repos/{repo_id}/context
GET  /api/hosted/v1/repos/{repo_id}/connection
```

The existing local graph API remains under `/api/v1` and keeps its existing
`X-API-Key` behavior.

## Intentional Stubs

- GitHub OAuth and GitHub App setup callbacks are represented by local dev
  bootstrap, metadata endpoints, and webhook fixture replay.
- Billing is intentionally omitted until hosted repo registration and sync are
  reliable.
- Remote multi-repo MCP routing is not complete in this slice. The connection
  endpoint exposes hosted context API details and local MCP config for the
  repo-specific graph DB.
- CI does not clone external repos or require network credentials.

## Next Step

The natural follow-up is real GitHub onboarding: OAuth login, GitHub App
installation callback handling, GitHub API repo listing, hosted clone/index
jobs, and remote MCP transport with repo-scoped authorization.
