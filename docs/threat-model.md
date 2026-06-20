# Threat model

A lightweight threat model for the hosted control plane (Stratum). The CLI/MCP
engine running locally trusts the operator's machine; the analysis below is about
the **internet-facing hosted service**.

## Trust boundaries

```
Untrusted internet ──▶ Caddy (TLS) ──▶ FastAPI app ──▶ SQLite + per-repo graphs
                                         │
GitHub (webhooks, App API) ─────────────┘
AI agents (bearer token) ──▶ remote MCP / context endpoints
```

- **Operator** (full trust): sets secrets, runs the server.
- **Authenticated team/repo tokens** (scoped trust): can read their own team's
  repos and request context. Repo-scoped tokens are limited to one repo.
- **GitHub** (semi-trusted): webhook payloads are attacker-influenceable.
- **Anonymous internet** (untrusted): can reach `/health`, the webhook endpoint,
  and the public read-only demo.

## Threats and mitigations

| Threat | Mitigation |
| --- | --- |
| Forged webhooks | `X-Hub-Signature-256` HMAC verification when a secret is set |
| Duplicate/replayed webhook deliveries | dedupe by `X-GitHub-Delivery` before syncing |
| Stolen/leaked token reuse | salted, memory-hard scrypt token hashes; **revocation** (`/tokens/{id}/revoke`) |
| Cross-tenant access | team/repo-scoped access checks (`repo_accessible`); isolation tests |
| Abuse / DoS of public endpoints | token-bucket rate limiting (per installation / per token+repo) |
| Secret/PII exfiltration via served context | context-security scan + **policy enforcement** (deny-list + redaction) |
| Prompt-injection content in served context | injection scan; vendor/generated paths excluded |
| Leaking aggregate usage | `/metrics` + `/audit` are admin-gated (`STRATUM_ADMIN_TOKEN`, constant-time) |
| Supply-chain tampering | SBOM (CycloneDX) + SLSA build-provenance attestation on releases |
| Secrets in source control | never committed; env / secrets manager only (`stratum.env`) |

## Residual risks

- The public demo token is read-only but reachable by anyone; compute routes are
  rate-limited rather than fully locked down.
- A compromised GitHub App private key would allow installation-token minting —
  it must be stored only in the platform secret store.
- No WAF/IDS layer; rely on the reverse proxy + rate limiting for an MVP.
