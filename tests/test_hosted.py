"""Tests for the hosted-MVP metadata store."""

from __future__ import annotations

from pathlib import Path

from codeatlas.hosted import HostedStore, RepoRegistration


def _repo(root: Path) -> Path:
    root.mkdir()
    (root / "app.py").write_text("def hello(name: str) -> str:\n    return f'hi {name}'\n")
    return root


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
