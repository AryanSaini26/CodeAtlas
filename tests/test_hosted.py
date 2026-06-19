"""Tests for the hosted-MVP metadata store."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from codeatlas.hosted import HostedStore, RepoRegistration, _hash_token, _verify_token_hash
from codeatlas.hosted_worker import SyncJobWorker


def _repo(root: Path) -> Path:
    root.mkdir()
    (root / "app.py").write_text("def hello(name: str) -> str:\n    return f'hi {name}'\n")
    return root


def _git_repo(root: Path) -> Path:
    repo = _repo(root)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-m",
            "initial",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


def test_hosted_migrations_are_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "hosted.db"
    first = HostedStore(db)
    first.close()
    second = HostedStore(db)
    try:
        assert second.list_teams() == []
    finally:
        second.close()


def test_hosted_bootstrap_token_and_repo_crud(tmp_path: Path) -> None:
    store = HostedStore(tmp_path / "hosted.db")
    try:
        bootstrap = store.bootstrap_dev()
        principal = store.verify_token(bootstrap.token)
        assert principal is not None
        assert principal.team_id == bootstrap.team.id

        repo = store.register_repo(
            RepoRegistration(
                team_slug="default",
                name="fixture",
                local_path=_repo(tmp_path / "repo"),
            )
        )
        assert repo.name == "fixture"
        assert Path(repo.graph_db_path).parent.name == "graphs"
        assert store.list_repos(team_id=bootstrap.team.id)[0].id == repo.id

        issued = store.create_token(
            subject_type="repo",
            subject_id=repo.id,
            name="repo token",
            scopes=["context:read"],
        )
        repo_principal = store.verify_token(issued.token)
        assert repo_principal is not None
        assert repo_principal.repo_id == repo.id
        assert store.verify_token("wrong") is None
    finally:
        store.close()


def test_token_hash_is_salted_scrypt_not_raw_sha256() -> None:
    encoded = _hash_token("cat_secret")
    # Salted scrypt: scheme-tagged, and never a bare 64-char SHA-256 hex digest.
    assert encoded.startswith("scrypt$")
    assert len(encoded.split("$")) == 6
    assert not (len(encoded) == 64 and all(c in "0123456789abcdef" for c in encoded))
    # Random salt per call => same input yields different stored hashes.
    assert encoded != _hash_token("cat_secret")
    assert _verify_token_hash("cat_secret", encoded)
    assert not _verify_token_hash("cat_wrong", encoded)


def test_stored_token_hash_uses_scrypt(tmp_path: Path) -> None:
    store = HostedStore(tmp_path / "hosted.db")
    try:
        bootstrap = store.bootstrap_dev()
        row = store._conn.execute(
            "SELECT token_hash FROM tokens WHERE id = ?",
            (bootstrap.token_record.id,),
        ).fetchone()
        assert str(row["token_hash"]).startswith("scrypt$")
        # The verification path still resolves a live principal.
        principal = store.verify_token(bootstrap.token)
        assert principal is not None
    finally:
        store.close()


def test_github_activation_clones_when_no_local_path(tmp_path: Path) -> None:
    store = HostedStore(tmp_path / "hosted.db")
    try:
        store.bootstrap_dev()
        source_repo = _git_repo(tmp_path / "source")
        installation = store.upsert_github_installation(
            team_slug="default",
            installation_id="42",
            account_login="AryanSaini26",
            account_type="User",
        )
        store.upsert_github_repository(
            installation_id=installation.installation_id,
            provider_repo_id="3003",
            full_name="AryanSaini26/AppFlow",
            name="AppFlow",
            owner="AryanSaini26",
            clone_url=str(source_repo),
        )

        # GitHub App flow: no local_path supplied anywhere -> must clone via clone_url.
        activated = store.activate_github_repository("3003")

        assert activated.provider == "github"
        assert Path(activated.local_path).parent.name == "checkouts"
        assert Path(activated.local_path, ".git").is_dir()
    finally:
        store.close()


def test_hosted_sync_writes_graph_stats_and_events(tmp_path: Path) -> None:
    store = HostedStore(tmp_path / "hosted.db")
    try:
        store.bootstrap_dev()
        repo = store.register_repo(
            RepoRegistration(
                team_slug="default",
                name="fixture",
                local_path=_repo(tmp_path / "repo"),
            )
        )
        result = store.sync_repo(repo.id)
        assert result.event.status == "success"
        assert result.event.parsed >= 1
        assert Path(result.repo.graph_db_path).exists()
        stats = store.repo_stats(repo.id)
        assert stats["files"] >= 1
        assert stats["symbols"] >= 1
        assert store.list_sync_events(repo.id)[0].id == result.event.id
    finally:
        store.close()


def test_github_installation_repo_activation_and_delivery_sync(tmp_path: Path) -> None:
    store = HostedStore(tmp_path / "hosted.db")
    try:
        store.bootstrap_dev()
        repo_path = _repo(tmp_path / "repo")
        installation = store.upsert_github_installation(
            team_slug="default",
            installation_id="42",
            account_login="AryanSaini26",
            account_type="User",
            permissions={"contents": "read"},
        )
        github_repo = store.upsert_github_repository(
            installation_id=installation.installation_id,
            provider_repo_id="1001",
            full_name="AryanSaini26/CodeAtlas",
            name="CodeAtlas",
            owner="AryanSaini26",
            private=False,
            default_branch="main",
            clone_url="https://github.com/AryanSaini26/CodeAtlas.git",
            local_path=str(repo_path),
        )

        activated = store.activate_github_repository(github_repo.provider_repo_id)
        assert activated.provider == "github"
        assert activated.provider_repo == "AryanSaini26/CodeAtlas"
        assert store.get_repo_by_provider_id("1001") is not None

        result = store.sync_repo(activated.id, delivery_id="delivery-1")
        assert result.event.status == "success"
        assert result.event.delivery_id == "delivery-1"

        store.update_github_webhook_delivery(
            provider_repo_id="1001",
            delivery_id="delivery-1",
            event="push",
        )
        refreshed = store.get_github_repository("1001")
        assert refreshed.activated_repo_id == activated.id
        assert refreshed.last_webhook_delivery_id == "delivery-1"
        assert refreshed.last_webhook_event == "push"
    finally:
        store.close()


def test_provision_github_login_is_idempotent(tmp_path: Path) -> None:
    store = HostedStore(tmp_path / "hosted.db")
    try:
        first = store.provision_github_login(
            github_id="42", login="Aryan", email="a@e.com", name="Aryan Saini"
        )
        principal = store.verify_token(first.token)
        assert principal is not None
        assert principal.team_id == first.team.id
        assert first.team.slug == "gh-aryan"

        # A second sign-in reuses the same user + team but mints a fresh token;
        # the previous token stays valid (we can't re-show a hashed token).
        second = store.provision_github_login(github_id="42", login="Aryan", email="a@e.com")
        assert second.user.id == first.user.id
        assert second.team.id == first.team.id
        assert second.token != first.token
        assert store.verify_token(second.token) is not None
        assert store.verify_token(first.token) is not None

        # No public email -> a noreply fallback is synthesised.
        third = store.provision_github_login(github_id="99", login="NoEmail")
        assert third.user.email.endswith("@users.noreply.github.com")
    finally:
        store.close()


def test_run_sync_pipeline_sets_ready_status(tmp_path: Path) -> None:
    store = HostedStore(tmp_path / "hosted.db")
    try:
        store.bootstrap_dev()
        repo = store.register_repo(
            RepoRegistration(
                team_slug="default",
                name="fixture",
                local_path=_repo(tmp_path / "repo"),
            )
        )
        assert store.get_repo(repo.id).last_sync_status == "never"

        result = store.run_sync_pipeline(repo.id)

        assert result.event.status == "success"
        assert store.get_repo(repo.id).last_sync_status == "ready"
        assert store.get_repo(repo.id).last_error is None
    finally:
        store.close()


def test_run_sync_pipeline_failure_sets_failed_status(tmp_path: Path) -> None:
    store = HostedStore(tmp_path / "hosted.db")
    try:
        store.bootstrap_dev()
        repo_root = _repo(tmp_path / "repo")
        repo = store.register_repo(
            RepoRegistration(team_slug="default", name="fixture", local_path=repo_root)
        )
        shutil.rmtree(repo_root)  # make the working tree disappear before indexing

        with pytest.raises(RuntimeError):
            store.run_sync_pipeline(repo.id)

        failed = store.get_repo(repo.id)
        assert failed.last_sync_status == "failed"
        assert failed.last_error
    finally:
        store.close()


def test_sync_worker_runs_job_off_thread_and_marks_ready(tmp_path: Path) -> None:
    db = tmp_path / "hosted.db"
    store = HostedStore(db)
    try:
        store.bootstrap_dev()
        repo = store.register_repo(
            RepoRegistration(
                team_slug="default",
                name="fixture",
                local_path=_repo(tmp_path / "repo"),
            )
        )
    finally:
        store.close()

    worker = SyncJobWorker(db)
    try:
        future = worker.enqueue(repo.id, delivery_id="delivery-async")
        result = future.result(timeout=30)
        assert result.event.status == "success"
        assert result.event.delivery_id == "delivery-async"
    finally:
        worker.shutdown()

    reopened = HostedStore(db)
    try:
        assert reopened.get_repo(repo.id).last_sync_status == "ready"
    finally:
        reopened.close()


def test_github_sync_clones_checkout_and_indexes(tmp_path: Path) -> None:
    store = HostedStore(tmp_path / "hosted.db")
    try:
        store.bootstrap_dev()
        source_repo = _git_repo(tmp_path / "source")
        installation = store.upsert_github_installation(
            team_slug="default",
            installation_id="42",
            account_login="AryanSaini26",
            account_type="User",
        )
        store.upsert_github_repository(
            installation_id=installation.installation_id,
            provider_repo_id="1002",
            full_name="AryanSaini26/CloneMe",
            name="CloneMe",
            owner="AryanSaini26",
            clone_url=str(source_repo),
        )

        result = store.sync_github_repository("1002")

        assert result.event.status == "success"
        assert Path(result.repo.local_path).parent.name == "checkouts"
        assert Path(result.repo.graph_db_path).exists()
        assert store.repo_stats(result.repo.id)["symbols"] >= 1
    finally:
        store.close()
