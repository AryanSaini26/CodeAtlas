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
codeatlas hosted github refresh-repos \
  --hosted-db .codeatlas/hosted.db \
  --installation <installation-id>
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
STRATUM_GITHUB_INSTALLATION_TOKEN
STRATUM_GITHUB_API_BASE
STRATUM_GITHUB_REPOS_FIXTURE
```

Current GitHub routes:

```text
GET  /api/hosted/v1/github/app
GET  /api/hosted/v1/github/setup
POST /api/hosted/v1/github/installations
GET  /api/hosted/v1/github/installations
POST /api/hosted/v1/github/installations/{id}/repos
GET  /api/hosted/v1/github/installations/{id}/repos?refresh=true
POST /api/hosted/v1/github/repos/{provider_repo_id}/activate
POST /api/hosted/v1/github/repos/{provider_repo_id}/sync
POST /api/hosted/v1/github/webhook
```

Activation can map a GitHub repository to a local checkout path, or use the
stored `clone_url` to create a hosted checkout under
`.codeatlas/checkouts/<provider_repo_id>`. Sync then uses the same per-repo
graph DB path as the local hosted flow.

Repo listing is deliberately CI-safe. In local tests and demos,
`STRATUM_GITHUB_REPOS_FIXTURE` can point at a JSON file with a `repositories`
array. In a real deployment, `STRATUM_GITHUB_INSTALLATION_TOKEN` can be used to
call GitHub's installation repository endpoint. Full JWT-to-installation-token
exchange is the next production hardening step.

## Remote Context/MCP Endpoint

Each synced repo exposes a repo-scoped MCP-compatible JSON endpoint:

```text
POST /api/hosted/v1/repos/{repo_id}/remote-mcp
Authorization: Bearer <repo-or-team-token>
X-Stratum-Audience: repo:{repo_id}
```

Supported methods in this slice:

- `tools/call` with tool name `stratum.context`, `codeatlas.context`, or
  `context`.
- `resources/read` for `codeatlas://graph/summary`.

Every context response includes deterministic security scan metadata under
`security`, including prompt-injection-like instructions, secret-like content,
and generated/vendor path warnings.

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

## Verified

Status of the four pre-Phase-1 hardening gaps (each closed in code with tests):

- **Live GitHub repo listing (no fixtures outside tests):** `load_github_repositories`
  now mints a real installation token when the App is configured —
  `mint_installation_token` signs an RS256 JWT with the App private key and
  exchanges it at `POST /app/installations/{id}/access_tokens`. Fixtures are
  used only when `STRATUM_GITHUB_REPOS_FIXTURE` is set (CI/tests).
- **Token hashing:** bearer tokens are stored as salted, memory-hard
  `hashlib.scrypt` digests (`scrypt$N$r$p$salt$digest`), not raw SHA-256;
  `verify_token` narrows by public prefix then compares in constant time.
- **Webhook idempotency:** the push handler checks `X-GitHub-Delivery` against
  recorded `sync_events.delivery_id` and returns `status="duplicate"` (200,
  no re-sync) on a GitHub redelivery.
- **GitHub App activation:** activating a repo with no local path clones via
  `clone_url` into the managed `checkouts/` tree; local-path registration is
  reserved for `hosted register-repo` dev mode.

## Background Sync and Rate Limiting

Push webhooks return immediately after queuing work on an in-process background
worker (`SyncJobWorker`, a single-threaded pool), so GitHub never times out a
slow clone/index and redelivers it. Each repo walks a sync lifecycle —
`never -> pending -> cloning -> indexing -> ready/failed` — surfaced on the
dashboard (with `last_error` on failure), which auto-polls while a sync is in
flight. The worker refreshes the working tree before indexing, so a push
indexes the just-pushed commit.

The public webhook endpoint (per installation) and the remote MCP / context
endpoints (per token + repo) are protected by an in-memory token-bucket rate
limiter. Limits are tunable via `STRATUM_WEBHOOK_RATE_CAPACITY`/`_REFILL` and
`STRATUM_MCP_RATE_CAPACITY`/`_REFILL`; over-limit requests get `429` with a
`Retry-After` header. This is per-process (one deployment at MVP scale), not a
distributed limiter.

## Intentional Stubs

- GitHub OAuth is still represented by local dev bootstrap and bearer tokens.
  GitHub setup callbacks, fixture/token-backed repo refresh, hosted checkout,
  and webhook fixture replay are implemented.
- Billing is intentionally omitted until hosted repo registration and sync are
  reliable.
- Full streamable remote MCP transport is not complete in this slice. The
  remote endpoint accepts a small MCP-compatible JSON shape over the existing
  hosted API auth model.
- CI does not clone external repos or require network credentials.

## Next Step

The natural follow-up is production GitHub onboarding: OAuth login,
self-serve signup, a public landing page, and a live public deployment
(`STRATUM_PUBLIC_URL`). JWT-to-installation-token exchange, background sync
workers, and endpoint rate limiting are implemented — see the sections above.
