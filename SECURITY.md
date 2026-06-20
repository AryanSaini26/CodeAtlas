# Security Policy

## Reporting a vulnerability

Please report security issues privately via
[GitHub Security Advisories](https://github.com/AryanSaini26/CodeAtlas/security/advisories/new)
or by email to **aryan.26.saini@gmail.com**. Do not open a public issue for
suspected vulnerabilities. We aim to acknowledge reports within a few days.

## Security posture

The hosted control plane (Stratum) is built with these protections:

- **Bearer tokens** are stored as salted, memory-hard `scrypt` hashes (never
  plaintext or fast unsalted digests); verification is constant-time.
- **GitHub webhooks** are verified against `X-Hub-Signature-256` when a webhook
  secret is configured, and deduplicated by `X-GitHub-Delivery` to avoid
  duplicate processing.
- **Repo-scoped access:** repo tokens can read only their own repo; the public
  demo token is repo-scoped and read-only.
- **Rate limiting** (token-bucket) protects the public webhook and the remote
  MCP / context endpoints.
- **Served-context scanning:** context packs are scanned for prompt-injection and
  secret-like material, and vendor/generated paths are excluded.
- **Admin metrics + audit log** are disabled unless `STRATUM_ADMIN_TOKEN` is set,
  then gated by a constant-time check. Sensitive actions (token issuance, repo
  activation, sync) are recorded in an append-only audit log.
- **Static analysis:** `codeatlas scan` emits SARIF (secret-like content,
  prompt-injection text, risky paths); CI uploads it to GitHub code scanning.
- **Supply chain:** releases ship a CycloneDX SBOM and an SLSA build-provenance
  attestation (`actions/attest-build-provenance`) on the built artifacts.

## Secrets

No secrets (GitHub App private keys, webhook/client secrets, tokens) are ever
committed. They are provided via environment variables / a secrets manager only.
See `deploy/stratum.env.example`.

## Supported versions

This is an actively developed project; fixes land on `main`.
