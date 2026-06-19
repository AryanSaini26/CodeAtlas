# Hosted MVP

CodeAtlas now includes a local-dev hosted control plane. It is not full SaaS
yet; it is the product-shaped foundation for a hosted team context gateway.

## Local Flow

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

- GitHub OAuth and GitHub App callbacks are represented by local dev bootstrap
  and repo metadata fields.
- Billing is intentionally omitted until hosted repo registration and sync are
  reliable.
- Remote multi-repo MCP routing is not complete in this slice. The connection
  endpoint exposes hosted context API details and local MCP config for the
  repo-specific graph DB.
- CI does not clone external repos or require network credentials.

## Next Step

The natural follow-up is real GitHub onboarding: OAuth login, GitHub App
installation records, webhook-triggered sync jobs, and remote MCP transport
with repo-scoped authorization.
