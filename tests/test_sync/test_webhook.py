"""Tests for the GitHub webhook handler."""

import hashlib
import hmac
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from codeatlas.graph.store import GraphStore
from codeatlas.sync.webhook import (
    WebhookHandler,
    _extract_changed_files,
    _pull_latest,
    _verify_signature,
)


@pytest.fixture
def repo_with_files(tmp_path: Path) -> Path:
    f = tmp_path / "main.py"
    f.write_text('def main():\n    return "hello"\n')
    return tmp_path


@pytest.fixture
def webhook_client(repo_with_files: Path) -> TestClient:
    store = GraphStore(":memory:")
    handler = WebhookHandler(store, repo_with_files, auto_pull=False)
    app = handler.create_app()
    return TestClient(app)


@pytest.fixture
def webhook_client_with_secret(repo_with_files: Path) -> tuple[TestClient, str]:
    secret = "test-secret-123"
    store = GraphStore(":memory:")
    handler = WebhookHandler(store, repo_with_files, secret=secret, auto_pull=False)
    app = handler.create_app()
    return TestClient(app), secret


# --- Utility tests ---


def test_extract_changed_files_from_push() -> None:
    payload = {
        "commits": [
            {"added": ["new.py"], "modified": ["old.py"], "removed": []},
            {"added": [], "modified": ["old.py"], "removed": ["deleted.py"]},
        ]
    }
    changed, removed = _extract_changed_files(payload)
    assert "new.py" in changed
    assert "old.py" in changed
    assert "deleted.py" in removed
    assert "deleted.py" not in changed


def test_extract_changed_files_empty() -> None:
    changed, removed = _extract_changed_files({"commits": []})
    assert changed == []
    assert removed == []


def test_verify_signature_valid() -> None:
    secret = "mysecret"
    payload = b'{"test": true}'
    sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert _verify_signature(payload, sig, secret)


def test_verify_signature_invalid() -> None:
    assert not _verify_signature(b"payload", "sha256=wrong", "secret")


# --- Webhook endpoint tests ---


def test_ping_event(webhook_client: TestClient) -> None:
    response = webhook_client.post(
        "/webhook",
        json={},
        headers={"X-GitHub-Event": "ping"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "pong"


def test_non_push_event_ignored(webhook_client: TestClient) -> None:
    response = webhook_client.post(
        "/webhook",
        json={},
        headers={"X-GitHub-Event": "issues"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_push_with_new_file(webhook_client: TestClient, repo_with_files: Path) -> None:
    # Create the file that the "push" will reference
    new_file = repo_with_files / "utils.py"
    new_file.write_text("def helper():\n    pass\n")

    payload = {"commits": [{"added": ["utils.py"], "modified": [], "removed": []}]}
    response = webhook_client.post(
        "/webhook",
        content=json.dumps(payload),
        headers={"X-GitHub-Event": "push", "Content-Type": "application/json"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["parsed"] == 1


def test_push_with_removed_file(webhook_client: TestClient) -> None:
    payload = {"commits": [{"added": [], "modified": [], "removed": ["old.py"]}]}
    response = webhook_client.post(
        "/webhook",
        content=json.dumps(payload),
        headers={"X-GitHub-Event": "push", "Content-Type": "application/json"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["removed"] == 1


def test_push_no_changes(webhook_client: TestClient) -> None:
    payload = {"commits": [{"added": [], "modified": [], "removed": []}]}
    response = webhook_client.post(
        "/webhook",
        content=json.dumps(payload),
        headers={"X-GitHub-Event": "push", "Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "no_changes"


def test_signature_verification_rejects_bad_sig(
    webhook_client_with_secret: tuple[TestClient, str],
) -> None:
    client, _ = webhook_client_with_secret
    response = client.post(
        "/webhook",
        content=b'{"commits":[]}',
        headers={
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": "sha256=invalid",
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 403


def test_signature_verification_accepts_valid_sig(
    webhook_client_with_secret: tuple[TestClient, str],
) -> None:
    client, secret = webhook_client_with_secret
    payload = json.dumps({"commits": []}).encode()
    sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    response = client.post(
        "/webhook",
        content=payload,
        headers={
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": sig,
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 200


# --- _pull_latest unit tests ---


def test_pull_latest_success(tmp_path: Path) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        assert _pull_latest(tmp_path) is True


def test_pull_latest_nonzero_exit(tmp_path: Path) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="conflict")
        assert _pull_latest(tmp_path) is False


def test_pull_latest_exception(tmp_path: Path) -> None:
    with patch("subprocess.run", side_effect=OSError("no git")):
        assert _pull_latest(tmp_path) is False


# --- auto_pull failure path ---


def test_push_git_pull_failed_returns_500(
    repo_with_files: Path,
) -> None:
    store = GraphStore(":memory:")
    handler = WebhookHandler(store, repo_with_files, auto_pull=True)
    app = handler.create_app()
    client = TestClient(app, raise_server_exceptions=False)

    with patch("codeatlas.sync.webhook._pull_latest", return_value=False):
        payload = {"commits": [{"added": ["main.py"], "modified": [], "removed": []}]}
        response = client.post(
            "/webhook",
            content=json.dumps(payload),
            headers={"X-GitHub-Event": "push", "Content-Type": "application/json"},
        )

    assert response.status_code == 500
    assert "error" in response.json()


# --- nonexistent file silently skipped ---


def test_push_nonexistent_file_skipped(webhook_client: TestClient) -> None:
    payload = {"commits": [{"added": ["ghost.py"], "modified": [], "removed": []}]}
    response = webhook_client.post(
        "/webhook",
        content=json.dumps(payload),
        headers={"X-GitHub-Event": "push", "Content-Type": "application/json"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["parsed"] == 0


# --- parse error counted ---


def test_push_parse_error_counted(webhook_client: TestClient, repo_with_files: Path) -> None:
    (repo_with_files / "errfile.py").write_text("x = 1\n")
    payload = {"commits": [{"added": ["errfile.py"], "modified": [], "removed": []}]}

    # Reach into the app's handler to patch its registry
    store = GraphStore(":memory:")
    handler = WebhookHandler(store, repo_with_files, auto_pull=False)
    app = handler.create_app()
    client = TestClient(app)

    with patch.object(handler._registry, "parse_file", side_effect=RuntimeError("boom")):
        response = client.post(
            "/webhook",
            content=json.dumps(payload),
            headers={"X-GitHub-Event": "push", "Content-Type": "application/json"},
        )

    data = response.json()
    assert data["errors"] == 1


# --- Health endpoint ---


def test_health_endpoint(webhook_client: TestClient) -> None:
    response = webhook_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "graph" in data
