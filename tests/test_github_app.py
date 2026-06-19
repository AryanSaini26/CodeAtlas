"""Tests for Stratum GitHub App helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

from codeatlas.github_app import (
    load_github_app_config,
    load_github_repositories,
    parse_webhook_payload,
    verify_github_signature,
)


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
