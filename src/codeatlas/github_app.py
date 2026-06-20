"""GitHub App helpers for the Stratum hosted gateway."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import BaseModel

from codeatlas.hosted import HostedStore


class GitHubAppConfig(BaseModel):
    app_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    webhook_secret: str | None = None
    private_key: str | None = None
    private_key_path: str | None = None
    public_url: str | None = None
    installation_token: str | None = None
    api_base: str = "https://api.github.com"
    oauth_base: str = "https://github.com"
    repos_fixture_path: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.app_id and (self.private_key or self.private_key_path))

    @property
    def oauth_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @property
    def webhook_configured(self) -> bool:
        return bool(self.webhook_secret)


class GitHubWebhookResult(BaseModel):
    event: str
    delivery_id: str | None = None
    status: str
    message: str
    repo_id: str | None = None
    provider_repo_id: str | None = None
    sync_event_id: str | None = None


class GitHubRepoListingResult(BaseModel):
    source: str
    repositories: list[dict[str, Any]]


class InstallationToken(BaseModel):
    token: str
    expires_at: str | None = None


def load_github_app_config() -> GitHubAppConfig:
    """Load Stratum GitHub App settings from environment variables."""
    private_key = os.environ.get("STRATUM_GITHUB_PRIVATE_KEY")
    private_key_path = os.environ.get("STRATUM_GITHUB_PRIVATE_KEY_PATH")
    if private_key is None and private_key_path:
        path = Path(private_key_path)
        if path.is_file():
            private_key = path.read_text()
    return GitHubAppConfig(
        app_id=os.environ.get("STRATUM_GITHUB_APP_ID"),
        client_id=os.environ.get("STRATUM_GITHUB_CLIENT_ID"),
        client_secret=os.environ.get("STRATUM_GITHUB_CLIENT_SECRET"),
        webhook_secret=os.environ.get("STRATUM_GITHUB_WEBHOOK_SECRET"),
        private_key=private_key,
        private_key_path=private_key_path,
        public_url=os.environ.get("STRATUM_PUBLIC_URL"),
        installation_token=os.environ.get("STRATUM_GITHUB_INSTALLATION_TOKEN"),
        api_base=os.environ.get("STRATUM_GITHUB_API_BASE", "https://api.github.com"),
        oauth_base=os.environ.get("STRATUM_GITHUB_OAUTH_BASE", "https://github.com"),
        repos_fixture_path=os.environ.get("STRATUM_GITHUB_REPOS_FIXTURE"),
    )


def verify_github_signature(payload: bytes, signature: str | None, secret: str | None) -> bool:
    """Verify GitHub's X-Hub-Signature-256 header when a secret is configured."""
    if not secret:
        return True
    if not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def parse_webhook_payload(raw: str | bytes | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("GitHub webhook payload must be a JSON object")
    return value


def _installation_fields(payload: dict[str, Any]) -> dict[str, Any] | None:
    installation = payload.get("installation")
    account = payload.get("account") or {}
    if not isinstance(installation, dict):
        return None
    account = account if isinstance(account, dict) else {}
    return {
        "installation_id": str(installation.get("id") or ""),
        "account_login": str(account.get("login") or "unknown"),
        "account_type": str(account.get("type") or "Organization"),
        "account_id": str(account["id"]) if account.get("id") is not None else None,
        "app_slug": str(installation["app_slug"]) if installation.get("app_slug") else None,
        "permissions": installation.get("permissions")
        if isinstance(installation.get("permissions"), dict)
        else {},
    }


def _repo_fields(repo: dict[str, Any], installation_id: str | None) -> dict[str, Any] | None:
    if not isinstance(repo, dict):
        return None
    provider_repo_id = repo.get("id")
    full_name = repo.get("full_name")
    if provider_repo_id is None or not full_name or not installation_id:
        return None
    owner = repo.get("owner") if isinstance(repo.get("owner"), dict) else {}
    owner_login = owner.get("login") if isinstance(owner, dict) else None
    return {
        "installation_id": installation_id,
        "provider_repo_id": str(provider_repo_id),
        "full_name": str(full_name),
        "name": str(repo.get("name") or str(full_name).split("/")[-1]),
        "owner": str(owner_login or str(full_name).split("/")[0]),
        "private": bool(repo.get("private", False)),
        "default_branch": str(repo["default_branch"]) if repo.get("default_branch") else None,
        "clone_url": str(repo["clone_url"]) if repo.get("clone_url") else None,
    }


def _resolve_private_key(config: GitHubAppConfig) -> str | None:
    if config.private_key:
        return config.private_key
    if config.private_key_path:
        path = Path(config.private_key_path)
        if path.is_file():
            return path.read_text()
    return None


def mint_installation_token(
    config: GitHubAppConfig,
    installation_id: str,
) -> InstallationToken:
    """Mint a short-lived installation access token via the GitHub App flow.

    Signs a JWT with the App private key (RS256), then exchanges it at
    ``POST /app/installations/{id}/access_tokens`` for a ~1h installation token.
    PyJWT is imported lazily so the core package stays dependency-light; install
    the ``hosted`` extra to enable minting.
    """
    if not config.app_id:
        raise RuntimeError("STRATUM_GITHUB_APP_ID is required to mint installation tokens")
    private_key = _resolve_private_key(config)
    if not private_key:
        raise RuntimeError("GitHub App private key is required to mint installation tokens")
    try:
        import jwt
    except ImportError as exc:  # pragma: no cover - exercised via env without extra
        raise RuntimeError(
            "PyJWT is required to mint GitHub installation tokens; install codeatlas[hosted]"
        ) from exc

    now = int(time.time())
    # iat is backdated 60s to tolerate clock skew; GitHub caps exp at 10 minutes.
    assertion = jwt.encode(
        {"iat": now - 60, "exp": now + 540, "iss": config.app_id},
        private_key,
        algorithm="RS256",
    )
    url = f"{config.api_base.rstrip('/')}/app/installations/{installation_id}/access_tokens"
    request = Request(
        url,
        data=b"",
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {assertion}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"GitHub installation token exchange failed: HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"GitHub installation token exchange failed: {exc.reason}") from exc
    payload = json.loads(raw)
    token = payload.get("token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("GitHub installation token response did not contain a token")
    expires_at = payload.get("expires_at")
    return InstallationToken(
        token=token,
        expires_at=str(expires_at) if expires_at is not None else None,
    )


def load_github_repositories(
    config: GitHubAppConfig,
    installation_id: str,
) -> GitHubRepoListingResult:
    """Load repositories for an installation.

    Resolution order: a deterministic fixture (CI), a pre-supplied installation
    token (smoke tests), or a freshly minted installation token from the App
    private key (real deployment). Returns an empty ``store`` result when the App
    is unconfigured so unauthenticated dev environments degrade gracefully.
    """
    if config.repos_fixture_path:
        fixture = Path(config.repos_fixture_path)
        payload = parse_webhook_payload(fixture.read_text())
        repos = payload.get("repositories")
        if not isinstance(repos, list):
            raise ValueError("STRATUM_GITHUB_REPOS_FIXTURE must contain a repositories array")
        return GitHubRepoListingResult(source="fixture", repositories=repos)

    token = config.installation_token
    if not token and config.configured:
        token = mint_installation_token(config, installation_id).token
    if not token:
        return GitHubRepoListingResult(source="store", repositories=[])

    url = f"{config.api_base.rstrip('/')}/installation/repositories"
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"GitHub repo listing failed: HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"GitHub repo listing failed: {exc.reason}") from exc
    payload = json.loads(raw)
    repos = payload.get("repositories")
    if not isinstance(repos, list):
        raise ValueError("GitHub repo listing response did not contain repositories")
    return GitHubRepoListingResult(source="github_api", repositories=repos)


def refresh_github_repositories(
    store: HostedStore,
    *,
    installation_id: str,
    config: GitHubAppConfig,
) -> GitHubRepoListingResult:
    listing = load_github_repositories(config, installation_id)
    if not listing.repositories:
        return listing
    for repo in listing.repositories:
        fields = _repo_fields(repo, installation_id)
        if fields:
            store.upsert_github_repository(**fields)
    return listing


def _process_pull_request(
    store: HostedStore,
    *,
    config: GitHubAppConfig | None,
    payload: dict[str, Any],
    delivery_id: str | None,
) -> GitHubWebhookResult:
    """Post/refresh a blast-radius comment on an opened/updated PR."""
    action = str(payload.get("action") or "")
    if action not in {"opened", "synchronize", "reopened"}:
        return GitHubWebhookResult(
            event="pull_request",
            delivery_id=delivery_id,
            status="ignored",
            message=f"pull_request action {action!r} ignored",
        )
    installation = _installation_fields(payload)
    installation_id = installation["installation_id"] if installation else None
    _repo = payload.get("repository")
    repo_payload = _repo if isinstance(_repo, dict) else {}
    _pr = payload.get("pull_request")
    pr_payload = _pr if isinstance(_pr, dict) else {}
    provider_repo_id = str(repo_payload.get("id")) if repo_payload.get("id") is not None else None
    full_name = str(repo_payload.get("full_name") or "")
    number = pr_payload.get("number")
    if not (
        config
        and config.configured
        and installation_id
        and provider_repo_id
        and "/" in full_name
        and number
    ):
        return GitHubWebhookResult(
            event="pull_request",
            delivery_id=delivery_id,
            status="ignored",
            message="pull_request missing config or required fields",
            provider_repo_id=provider_repo_id,
        )
    hosted_repo = store.get_repo_by_provider_id(provider_repo_id)
    if hosted_repo is None:
        return GitHubWebhookResult(
            event="pull_request",
            delivery_id=delivery_id,
            status="ignored",
            message="github repository is not activated in Stratum",
            provider_repo_id=provider_repo_id,
        )
    owner, repo_name = full_name.split("/", 1)
    try:
        token = mint_installation_token(config, installation_id).token
        changed_files = list_pr_changed_files(config, token, owner, repo_name, int(number))
        body = build_pr_impact_comment(hosted_repo.graph_db_path, changed_files)
        outcome = upsert_pr_comment(config, token, owner, repo_name, int(number), body)
    except Exception as exc:
        return GitHubWebhookResult(
            event="pull_request",
            delivery_id=delivery_id,
            status="error",
            message=str(exc),
            repo_id=hosted_repo.id,
            provider_repo_id=provider_repo_id,
        )
    return GitHubWebhookResult(
        event="pull_request",
        delivery_id=delivery_id,
        status="ok",
        message=f"pr impact comment {outcome}",
        repo_id=hosted_repo.id,
        provider_repo_id=provider_repo_id,
    )


def process_github_webhook(
    store: HostedStore,
    *,
    event: str,
    delivery_id: str | None,
    payload: dict[str, Any],
    default_team_slug: str = "default",
    enqueue_sync: Callable[..., Any] | None = None,
    config: GitHubAppConfig | None = None,
) -> GitHubWebhookResult:
    """Apply a GitHub webhook payload to hosted metadata and sync when possible.

    When ``enqueue_sync`` is provided, a push schedules the sync off the request
    path (returning ``status="queued"``) instead of cloning/indexing inline, so
    the webhook responds before GitHub's delivery timeout. Without it the sync
    runs synchronously (used by direct unit tests and the CLI). ``config`` enables
    the PR review bot (needs a token + GitHub API base).
    """
    installation = _installation_fields(payload)
    if installation and installation["installation_id"]:
        store.create_team(slug=default_team_slug, name="Default Team")
        store.upsert_github_installation(team_slug=default_team_slug, **installation)

    if event == "ping":
        return GitHubWebhookResult(
            event=event,
            delivery_id=delivery_id,
            status="ok",
            message="pong",
        )

    installation_id = installation["installation_id"] if installation else None

    if event == "pull_request":
        return _process_pull_request(store, config=config, payload=payload, delivery_id=delivery_id)

    if event in {"installation", "installation_repositories"}:
        repositories = payload.get("repositories") or payload.get("repositories_added") or []
        if isinstance(repositories, list):
            for repo_payload in repositories:
                fields = _repo_fields(repo_payload, installation_id)
                if fields:
                    store.upsert_github_repository(**fields)
        return GitHubWebhookResult(
            event=event,
            delivery_id=delivery_id,
            status="ok",
            message="installation metadata stored",
        )

    if event == "push":
        repo_payload = payload.get("repository")
        fields = (
            _repo_fields(repo_payload, installation_id) if isinstance(repo_payload, dict) else None
        )
        if fields:
            store.upsert_github_repository(**fields)
        provider_repo_id = fields["provider_repo_id"] if fields else None
        if not provider_repo_id:
            return GitHubWebhookResult(
                event=event,
                delivery_id=delivery_id,
                status="ignored",
                message="push payload did not include a repository id",
            )
        store.update_github_webhook_delivery(
            provider_repo_id=provider_repo_id,
            delivery_id=delivery_id,
            event=event,
        )
        hosted_repo = store.get_repo_by_provider_id(provider_repo_id)
        if hosted_repo is None:
            return GitHubWebhookResult(
                event=event,
                delivery_id=delivery_id,
                status="ignored",
                message="github repository is not activated in Stratum",
                provider_repo_id=provider_repo_id,
            )
        if store.delivery_already_processed(hosted_repo.id, delivery_id):
            return GitHubWebhookResult(
                event=event,
                delivery_id=delivery_id,
                status="duplicate",
                message="delivery already processed; skipping re-sync",
                repo_id=hosted_repo.id,
                provider_repo_id=provider_repo_id,
            )
        if enqueue_sync is not None:
            enqueue_sync(
                hosted_repo.id,
                delivery_id=delivery_id,
                github_provider_repo_id=provider_repo_id,
            )
            return GitHubWebhookResult(
                event=event,
                delivery_id=delivery_id,
                status="queued",
                message="sync queued from GitHub push webhook",
                repo_id=hosted_repo.id,
                provider_repo_id=provider_repo_id,
            )
        try:
            result = store.run_sync_pipeline(
                hosted_repo.id,
                delivery_id=delivery_id,
                github_provider_repo_id=provider_repo_id,
            )
        except RuntimeError as exc:
            events = store.list_sync_events(hosted_repo.id, limit=1)
            return GitHubWebhookResult(
                event=event,
                delivery_id=delivery_id,
                status="error",
                message=str(exc),
                repo_id=hosted_repo.id,
                provider_repo_id=provider_repo_id,
                sync_event_id=events[0].id if events else None,
            )
        return GitHubWebhookResult(
            event=event,
            delivery_id=delivery_id,
            status="ok",
            message="repo synced from GitHub push webhook",
            repo_id=result.repo.id,
            provider_repo_id=provider_repo_id,
            sync_event_id=result.event.id,
        )

    repo_payload = payload.get("repository")
    if isinstance(repo_payload, dict):
        fields = _repo_fields(repo_payload, installation_id)
        if fields:
            github_repo = store.upsert_github_repository(**fields)
            store.update_github_webhook_delivery(
                provider_repo_id=github_repo.provider_repo_id,
                delivery_id=delivery_id,
                event=event,
            )
    return GitHubWebhookResult(
        event=event,
        delivery_id=delivery_id,
        status="ignored",
        message=f"event {event!r} recorded without sync",
    )


class GitHubOAuthUser(BaseModel):
    github_id: str
    login: str
    email: str | None = None
    name: str | None = None


def build_oauth_authorize_url(
    config: GitHubAppConfig,
    *,
    state: str,
    redirect_uri: str,
) -> str:
    """Build the GitHub 'Sign in with GitHub' authorize URL for the dashboard."""
    params = {
        "client_id": config.client_id or "",
        "redirect_uri": redirect_uri,
        "scope": "read:user user:email",
        "state": state,
        "allow_signup": "true",
    }
    return f"{config.oauth_base.rstrip('/')}/login/oauth/authorize?{urlencode(params)}"


def exchange_oauth_code(
    config: GitHubAppConfig,
    *,
    code: str,
    redirect_uri: str,
) -> str:
    """Exchange an OAuth ``code`` for a user access token."""
    data = urlencode(
        {
            "client_id": config.client_id or "",
            "client_secret": config.client_secret or "",
            "code": code,
            "redirect_uri": redirect_uri,
        }
    ).encode("utf-8")
    request = Request(
        f"{config.oauth_base.rstrip('/')}/login/oauth/access_token",
        data=data,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"GitHub OAuth token exchange failed: HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"GitHub OAuth token exchange failed: {exc.reason}") from exc
    payload = json.loads(raw)
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        # GitHub returns 200 with an "error" field on bad codes.
        detail = payload.get("error_description") or payload.get("error") or "no access_token"
        raise RuntimeError(f"GitHub OAuth token exchange failed: {detail}")
    return token


def _github_get(url: str, access_token: str) -> Any:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {access_token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Stratum",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"GitHub API call failed: HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"GitHub API call failed: {exc.reason}") from exc


def fetch_github_user(
    access_token: str, *, api_base: str = "https://api.github.com"
) -> GitHubOAuthUser:
    """Fetch the authenticated user's profile (and a verified email if needed)."""
    base = api_base.rstrip("/")
    profile = _github_get(f"{base}/user", access_token)
    if not isinstance(profile, dict) or profile.get("id") is None or not profile.get("login"):
        raise RuntimeError("GitHub user response was missing id/login")
    email = profile.get("email")
    if not email:
        # Public email may be hidden; pick the primary verified address.
        emails = _github_get(f"{base}/user/emails", access_token)
        if isinstance(emails, list):
            primary = next(
                (
                    e.get("email")
                    for e in emails
                    if isinstance(e, dict) and e.get("primary") and e.get("verified")
                ),
                None,
            )
            email = primary
    return GitHubOAuthUser(
        github_id=str(profile["id"]),
        login=str(profile["login"]),
        email=str(email) if email else None,
        name=str(profile["name"]) if profile.get("name") else None,
    )


PR_BOT_MARKER = "<!-- stratum-pr-bot -->"


def build_pr_impact_comment(
    graph_db_path: Path | str,
    changed_files: list[str],
    *,
    max_listed: int = 10,
) -> str:
    """Build a Markdown blast-radius comment for a PR from the indexed graph.

    For each changed file we find its symbols and their dependents — the
    downstream code that may be affected. No working tree needed; this reads the
    existing graph.
    """
    from codeatlas.graph.store import GraphStore

    store = GraphStore(Path(graph_db_path))
    try:
        changed_symbols = 0
        affected: dict[str, tuple[str, str]] = {}  # id -> (qualified_name, file)
        affected_files: set[str] = set()
        for file_path in changed_files:
            symbols = store.get_symbols_in_file(file_path)
            changed_symbols += len(symbols)
            for sym in symbols:
                for rel in store.get_dependents(sym.id):
                    dep = store.get_symbol_by_id(rel.source_id)
                    if dep is None or dep.file_path in changed_files:
                        continue
                    affected[dep.id] = (dep.qualified_name, dep.file_path)
                    affected_files.add(dep.file_path)
    finally:
        store.close()

    lines = [
        "## 🛰️ Stratum impact analysis",
        "",
        f"This PR touches **{len(changed_files)} file(s)** / **{changed_symbols} symbol(s)**.",
    ]
    if affected:
        lines.append(
            f"Downstream blast radius: **{len(affected)} symbol(s)** across "
            f"**{len(affected_files)} file(s)** may be affected."
        )
        lines += ["", "**Most affected:**"]
        for _id, (name, file) in sorted(affected.items(), key=lambda kv: kv[1])[:max_listed]:
            lines.append(f"- `{name}` — {file}")
        if len(affected) > max_listed:
            lines.append(f"- …and {len(affected) - max_listed} more")
    else:
        lines.append("No downstream dependents found for the changed symbols. ✅")
    lines += ["", f"_Measured from the CodeAtlas graph._ {PR_BOT_MARKER}"]
    return "\n".join(lines)


def _github_post(url: str, token: str, data: dict[str, Any]) -> Any:
    request = Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Stratum",
            "Content-Type": "application/json",
        },
    )
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _github_patch(url: str, token: str, data: dict[str, Any]) -> Any:
    request = Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        method="PATCH",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Stratum",
            "Content-Type": "application/json",
        },
    )
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def list_pr_changed_files(
    config: GitHubAppConfig, token: str, owner: str, repo: str, number: int
) -> list[str]:
    base = config.api_base.rstrip("/")
    payload = _github_get(f"{base}/repos/{owner}/{repo}/pulls/{number}/files?per_page=100", token)
    if not isinstance(payload, list):
        return []
    return [
        str(item["filename"]) for item in payload if isinstance(item, dict) and item.get("filename")
    ]


def upsert_pr_comment(
    config: GitHubAppConfig,
    token: str,
    owner: str,
    repo: str,
    number: int,
    body: str,
) -> str:
    """Update the existing Stratum bot comment if present, else create one."""
    base = config.api_base.rstrip("/")
    existing = _github_get(
        f"{base}/repos/{owner}/{repo}/issues/{number}/comments?per_page=100", token
    )
    if isinstance(existing, list):
        for comment in existing:
            if isinstance(comment, dict) and PR_BOT_MARKER in str(comment.get("body", "")):
                _github_patch(
                    f"{base}/repos/{owner}/{repo}/issues/comments/{comment['id']}",
                    token,
                    {"body": body},
                )
                return "updated"
    _github_post(f"{base}/repos/{owner}/{repo}/issues/{number}/comments", token, {"body": body})
    return "created"
