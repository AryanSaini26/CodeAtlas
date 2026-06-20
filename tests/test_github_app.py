"""Tests for Stratum GitHub App helpers."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import subprocess
from pathlib import Path

from codeatlas.github_app import (
    PR_BOT_MARKER,
    GitHubAppConfig,
    InstallationToken,
    build_oauth_authorize_url,
    build_pr_impact_comment,
    exchange_oauth_code,
    fetch_github_user,
    load_github_app_config,
    load_github_repositories,
    mint_installation_token,
    parse_webhook_payload,
    process_github_webhook,
    verify_github_signature,
)
from codeatlas.hosted import HostedStore, RepoRegistration


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


def test_build_oauth_authorize_url() -> None:
    config = GitHubAppConfig(client_id="cid", client_secret="sec")
    url = build_oauth_authorize_url(config, state="xyz", redirect_uri="https://s.example/cb")
    assert url.startswith("https://github.com/login/oauth/authorize?")
    assert "client_id=cid" in url
    assert "state=xyz" in url
    assert "redirect_uri=https%3A%2F%2Fs.example%2Fcb" in url


def test_exchange_oauth_code_returns_token(monkeypatch) -> None:
    config = GitHubAppConfig(client_id="cid", client_secret="sec")
    monkeypatch.setattr(
        "codeatlas.github_app.urlopen",
        lambda req, timeout=15: _FakeResponse(json.dumps({"access_token": "gho_x"}).encode()),
    )
    assert exchange_oauth_code(config, code="c", redirect_uri="https://s/cb") == "gho_x"


def test_exchange_oauth_code_rejects_error_response(monkeypatch) -> None:
    config = GitHubAppConfig(client_id="cid", client_secret="sec")
    monkeypatch.setattr(
        "codeatlas.github_app.urlopen",
        lambda req, timeout=15: _FakeResponse(
            json.dumps({"error": "bad_verification_code"}).encode()
        ),
    )
    try:
        exchange_oauth_code(config, code="c", redirect_uri="https://s/cb")
    except RuntimeError as exc:
        assert "bad_verification_code" in str(exc)
    else:
        raise AssertionError("expected a bad code to fail")


def test_fetch_github_user_uses_profile_email(monkeypatch) -> None:
    monkeypatch.setattr(
        "codeatlas.github_app.urlopen",
        lambda req, timeout=15: _FakeResponse(
            json.dumps({"id": 42, "login": "Aryan", "name": "A", "email": "a@e.com"}).encode()
        ),
    )
    user = fetch_github_user("tok")
    assert user.github_id == "42"
    assert user.login == "Aryan"
    assert user.email == "a@e.com"


def test_fetch_github_user_falls_back_to_primary_verified_email(monkeypatch) -> None:
    responses = iter(
        [
            _FakeResponse(json.dumps({"id": 7, "login": "NoEmail", "email": None}).encode()),
            _FakeResponse(
                json.dumps([{"email": "p@e.com", "primary": True, "verified": True}]).encode()
            ),
        ]
    )
    monkeypatch.setattr("codeatlas.github_app.urlopen", lambda req, timeout=15: next(responses))
    user = fetch_github_user("tok")
    assert user.email == "p@e.com"


def test_build_pr_impact_comment(tmp_path: Path) -> None:
    store = HostedStore(tmp_path / "hosted.db")
    try:
        store.bootstrap_dev()
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / "auth.py").write_text("def login(user: str) -> str:\n    return user\n")
        repo = store.register_repo(
            RepoRegistration(team_slug="default", name="r", local_path=repo_dir)
        )
        store.run_sync_pipeline(repo.id)
        body = build_pr_impact_comment(repo.graph_db_path, ["auth.py"])
        assert PR_BOT_MARKER in body
        assert "impact analysis" in body
    finally:
        store.close()


def test_pull_request_webhook_posts_impact_comment(tmp_path: Path, monkeypatch) -> None:
    store = HostedStore(tmp_path / "hosted.db")
    try:
        store.bootstrap_dev()
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / "auth.py").write_text("def login(user: str) -> str:\n    return user\n")
        store.upsert_github_installation(
            team_slug="default", installation_id="42", account_login="o", account_type="User"
        )
        store.upsert_github_repository(
            installation_id="42",
            provider_repo_id="1001",
            full_name="o/r",
            name="r",
            owner="o",
            local_path=str(repo_dir),
        )
        activated = store.activate_github_repository("1001", local_path=str(repo_dir))
        store.run_sync_pipeline(activated.id)

        captured: dict[str, str] = {}
        monkeypatch.setattr(
            "codeatlas.github_app.mint_installation_token",
            lambda c, i: InstallationToken(token="t"),
        )
        monkeypatch.setattr(
            "codeatlas.github_app.list_pr_changed_files",
            lambda c, t, o, r, n: ["auth.py"],
        )

        def fake_upsert(c, t, o, r, n, body):  # type: ignore[no-untyped-def]
            captured["body"] = body
            return "created"

        monkeypatch.setattr("codeatlas.github_app.upsert_pr_comment", fake_upsert)

        payload = {
            "action": "opened",
            "installation": {"id": 42},
            "account": {"login": "o", "type": "User", "id": 1},
            "repository": {"id": 1001, "full_name": "o/r"},
            "pull_request": {"number": 7},
        }
        config = GitHubAppConfig(app_id="1", private_key="x")
        result = process_github_webhook(
            store, event="pull_request", delivery_id="d", payload=payload, config=config
        )
        assert result.status == "ok"
        assert PR_BOT_MARKER in captured["body"]

        # Unconfigured app -> ignored, no crash.
        ignored = process_github_webhook(
            store, event="pull_request", delivery_id="d2", payload=payload, config=None
        )
        assert ignored.status == "ignored"
    finally:
        store.close()
