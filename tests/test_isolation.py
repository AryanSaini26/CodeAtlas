"""Tenant-isolation and token-lifecycle tests (security 'unhappy paths')."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from codeatlas.api.app import create_app
from codeatlas.graph.store import GraphStore
from codeatlas.hosted import HostedStore, RepoRegistration


def _repo(root: Path) -> Path:
    root.mkdir()
    (root / "app.py").write_text("def hello() -> str:\n    return 'hi'\n")
    return root


def test_repo_scoped_token_cannot_access_other_repo(tmp_path: Path) -> None:
    store = HostedStore(tmp_path / "h.db")
    try:
        store.bootstrap_dev()
        r1 = store.register_repo(RepoRegistration("default", "r1", _repo(tmp_path / "r1")))
        r2 = store.register_repo(RepoRegistration("default", "r2", _repo(tmp_path / "r2")))
        issued = store.create_token(
            subject_type="repo", subject_id=r1.id, name="t", scopes=["context:read"]
        )
        principal = store.verify_token(issued.token)
        assert principal is not None
        assert store.repo_accessible(r1, principal) is True
        assert store.repo_accessible(r2, principal) is False
    finally:
        store.close()


def test_team_token_cannot_access_other_teams_repo(tmp_path: Path) -> None:
    store = HostedStore(tmp_path / "h.db")
    try:
        store.bootstrap_dev()  # team "default"
        repo_a = store.register_repo(RepoRegistration("default", "a", _repo(tmp_path / "a")))
        team_b = store.create_team(slug="teamb", name="Team B")
        issued_b = store.create_token(
            subject_type="team", subject_id=team_b.id, name="b", scopes=["context:read"]
        )
        principal_b = store.verify_token(issued_b.token)
        assert principal_b is not None
        assert store.repo_accessible(repo_a, principal_b) is False
    finally:
        store.close()


def test_revoked_token_fails_verification(tmp_path: Path) -> None:
    store = HostedStore(tmp_path / "h.db")
    try:
        boot = store.bootstrap_dev()
        assert store.verify_token(boot.token) is not None
        store.revoke_token(boot.token_record.id)
        assert store.verify_token(boot.token) is None
        assert any(e.action == "token.revoke" for e in store.list_audit_events())
    finally:
        store.close()


def test_sync_failure_records_audit_event(tmp_path: Path) -> None:
    store = HostedStore(tmp_path / "h.db")
    try:
        store.bootstrap_dev()
        root = _repo(tmp_path / "repo")
        repo = store.register_repo(RepoRegistration("default", "r", root))
        shutil.rmtree(root)
        with pytest.raises(RuntimeError):
            store.run_sync_pipeline(repo.id)
        sync_events = [e for e in store.list_audit_events() if e.action == "repo.sync"]
        assert sync_events and sync_events[0].metadata["status"] == "error"
    finally:
        store.close()


def test_revoked_token_denied_over_http(tmp_path: Path) -> None:
    db = tmp_path / "graph.db"
    GraphStore(db).close()
    app = create_app(db_path=db, hosted_db_path=tmp_path / "hosted.db")
    client = TestClient(app)
    boot = client.post("/api/hosted/v1/dev/bootstrap").json()
    token = boot["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/hosted/v1/repos", headers=headers).status_code == 200

    revoke = client.post(
        f"/api/hosted/v1/tokens/{boot['token_record']['id']}/revoke", headers=headers
    )
    assert revoke.status_code == 200
    assert client.get("/api/hosted/v1/repos", headers=headers).status_code == 401
