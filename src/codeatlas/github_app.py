"""GitHub App helpers for the Stratum hosted gateway."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
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


def load_github_repositories(
    config: GitHubAppConfig,
    installation_id: str,
) -> GitHubRepoListingResult:
    """Load repositories for an installation from a fixture or GitHub API token.

    Full GitHub App JWT-to-installation-token exchange is a deployment concern.
    This helper keeps CI deterministic with ``STRATUM_GITHUB_REPOS_FIXTURE`` and
    supports real smoke tests with ``STRATUM_GITHUB_INSTALLATION_TOKEN``.
    """
    if config.repos_fixture_path:
        fixture = Path(config.repos_fixture_path)
        payload = parse_webhook_payload(fixture.read_text())
        repos = payload.get("repositories")
        if not isinstance(repos, list):
            raise ValueError("STRATUM_GITHUB_REPOS_FIXTURE must contain a repositories array")
        return GitHubRepoListingResult(source="fixture", repositories=repos)

    if not config.installation_token:
        return GitHubRepoListingResult(source="store", repositories=[])

    url = f"{config.api_base.rstrip('/')}/installation/repositories"
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {config.installation_token}",
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


def process_github_webhook(
    store: HostedStore,
    *,
    event: str,
    delivery_id: str | None,
    payload: dict[str, Any],
    default_team_slug: str = "default",
) -> GitHubWebhookResult:
    """Apply a GitHub webhook payload to hosted metadata and sync when possible."""
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
        try:
            result = store.sync_repo(hosted_repo.id, delivery_id=delivery_id)
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
