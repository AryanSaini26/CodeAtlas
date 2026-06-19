"""Tests for Stratum GitHub App helpers."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import subprocess
from pathlib import Path

from codeatlas.github_app import (
    GitHubAppConfig,
    InstallationToken,
    load_github_app_config,
    load_github_repositories,
    mint_installation_token,
    parse_webhook_payload,
    process_github_webhook,
    verify_github_signature,
)
from codeatlas.hosted import HostedStore


def _rsa_keypair() -> tuple[str, str]:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


class _FakeResponse(io.BytesIO):
    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def test_github_app_config_loads_env_and_private_key_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    key = tmp_path / "app.pem"
    key.write_text("private-key")
    monkeypatch.setenv("STRATUM_GITHUB_APP_ID", "123")
    monkeypatch.setenv("STRATUM_GITHUB_CLIENT_ID", "client")
    monkeypatch.setenv("STRATUM_GITHUB_CLIENT_SECRET", "secret")
    monkeypatch.setenv("STRATUM_GITHUB_WEBHOOK_SECRET", "hook")
    monkeypatch.setenv("STRATUM_GITHUB_PRIVATE_KEY_PATH", str(key))
    monkeypatch.setenv("STRATUM_PUBLIC_URL", "https://stratum.example")

    config = load_github_app_config()

    assert config.configured
    assert config.oauth_configured
    assert config.webhook_configured
    assert config.private_key == "private-key"
    assert config.public_url == "https://stratum.example"


def test_github_signature_validation() -> None:
    payload = b'{"zen":"Keep it logically awesome."}'
    secret = "webhook-secret"
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    assert verify_github_signature(payload, f"sha256={digest}", secret)
    assert not verify_github_signature(payload, "sha256=wrong", secret)
    assert verify_github_signature(payload, None, None)


def test_parse_webhook_payload_rejects_non_object() -> None:
    assert parse_webhook_payload(json.dumps({"ok": True})) == {"ok": True}
    try:
        parse_webhook_payload("[]")
    except ValueError as exc:
        assert "JSON object" in str(exc)
    else:
        raise AssertionError("expected non-object payload to fail")


def test_load_github_repositories_from_fixture(tmp_path: Path, monkeypatch) -> None:
    fixture = tmp_path / "repos.json"
    fixture.write_text(
        json.dumps(
            {
                "repositories": [
                    {
                        "id": 1001,
                        "full_name": "AryanSaini26/CodeAtlas",
                        "name": "CodeAtlas",
                        "owner": {"login": "AryanSaini26"},
                    }
                ]
            }
        )
    )
    monkeypatch.setenv("STRATUM_GITHUB_REPOS_FIXTURE", str(fixture))
    config = load_github_app_config()

    result = load_github_repositories(config, "42")

    assert result.source == "fixture"
    assert result.repositories[0]["full_name"] == "AryanSaini26/CodeAtlas"


def test_mint_installation_token_signs_jwt_and_exchanges(monkeypatch) -> None:
    import jwt

    private_pem, public_pem = _rsa_keypair()
    config = GitHubAppConfig(app_id="123456", private_key=private_pem)
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout=15):  # type: ignore[no-untyped-def]
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["auth"] = request.headers.get("Authorization")
        return _FakeResponse(
            json.dumps({"token": "ghs_installtoken", "expires_at": "2026-06-19T12:00:00Z"}).encode()
        )

    monkeypatch.setattr("codeatlas.github_app.urlopen", fake_urlopen)

    result = mint_installation_token(config, "42")

    assert result.token == "ghs_installtoken"
    assert result.expires_at == "2026-06-19T12:00:00Z"
    assert captured["url"].endswith("/app/installations/42/access_tokens")
    assert captured["method"] == "POST"
    # The Authorization JWT must be a valid RS256 assertion issued by the App.
    assertion = str(captured["auth"]).removeprefix("Bearer ")
    decoded = jwt.decode(assertion, public_pem, algorithms=["RS256"])
    assert decoded["iss"] == "123456"


def test_mint_installation_token_requires_key() -> None:
    config = GitHubAppConfig(app_id="123456")
    try:
        mint_installation_token(config, "42")
    except RuntimeError as exc:
        assert "private key" in str(exc)
    else:
        raise AssertionError("expected minting without a private key to fail")


def test_load_github_repositories_mints_token_when_app_configured(monkeypatch) -> None:
    private_pem, _ = _rsa_keypair()
    config = GitHubAppConfig(app_id="123456", private_key=private_pem)

    monkeypatch.setattr(
        "codeatlas.github_app.mint_installation_token",
        lambda cfg, installation_id: InstallationToken(token="ghs_minted"),
    )

    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout=15):  # type: ignore[no-untyped-def]
        captured["auth"] = request.headers.get("Authorization")
        return _FakeResponse(
            json.dumps(
                {"repositories": [{"id": 5, "full_name": "acme/widgets", "name": "widgets"}]}
            ).encode()
        )

    monkeypatch.setattr("codeatlas.github_app.urlopen", fake_urlopen)

    result = load_github_repositories(config, "42")

    assert result.source == "github_api"
    assert result.repositories[0]["full_name"] == "acme/widgets"
    assert captured["auth"] == "Bearer ghs_minted"


def _push_payload(provider_repo_id: int, clone_url: str) -> dict:
    return {
        "installation": {"id": 42, "app_slug": "stratum"},
        "account": {"login": "AryanSaini26", "type": "User", "id": 7},
        "repository": {
            "id": provider_repo_id,
            "full_name": "AryanSaini26/CloneMe",
            "name": "CloneMe",
            "owner": {"login": "AryanSaini26"},
            "clone_url": clone_url,
        },
    }


def test_push_webhook_dedupes_redelivered_delivery_id(tmp_path: Path) -> None:
    store = HostedStore(tmp_path / "hosted.db")
    try:
        store.bootstrap_dev()
        # A real git checkout the push handler can index.
        source = tmp_path / "source"
        source.mkdir()
        (source / "app.py").write_text("def hello() -> str:\n    return 'hi'\n")
        subprocess.run(["git", "init"], cwd=source, check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=source, check=True, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@e.com", "commit", "-m", "init"],
            cwd=source,
            check=True,
            capture_output=True,
        )
        installation = store.upsert_github_installation(
            team_slug="default",
            installation_id="42",
            account_login="AryanSaini26",
            account_type="User",
        )
        store.upsert_github_repository(
            installation_id=installation.installation_id,
            provider_repo_id="2002",
            full_name="AryanSaini26/CloneMe",
            name="CloneMe",
            owner="AryanSaini26",
            clone_url=str(source),
            local_path=str(source),
        )
        store.activate_github_repository("2002", local_path=str(source))

        payload = _push_payload(2002, str(source))
        first = process_github_webhook(
            store, event="push", delivery_id="delivery-xyz", payload=payload
        )
        assert first.status == "ok"

        second = process_github_webhook(
            store, event="push", delivery_id="delivery-xyz", payload=payload
        )
        assert second.status == "duplicate"

        repo = store.get_repo_by_provider_id("2002")
        assert repo is not None
        synced = [e for e in store.list_sync_events(repo.id) if e.delivery_id == "delivery-xyz"]
        assert len(synced) == 1
    finally:
        store.close()
