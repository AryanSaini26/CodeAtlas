"""Tests for graph-based PR analysis."""

from __future__ import annotations

import subprocess
from pathlib import Path

from codeatlas.config import CodeAtlasConfig
from codeatlas.graph.store import GraphStore
from codeatlas.indexer import RepoIndexer
from codeatlas.pr_analysis import analyze_changed_files, analyze_pr, render_pr_markdown


def _git(args: list[str], cwd: Path) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@e.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _index(repo: Path, db: Path) -> GraphStore:
    config = CodeAtlasConfig.find_and_load(repo)
    config.graph.db_path = db
    store = GraphStore(db)
    RepoIndexer(config, store).index_full(resolve=True)
    return store


def test_analyze_changed_files_reports_symbols_and_render(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "util.py").write_text("def helper(x: int) -> int:\n    return x + 1\n")
    (repo / "app.py").write_text(
        "from util import helper\n\n\ndef main() -> int:\n    return helper(1)\n"
    )
    store = _index(repo, tmp_path / "graph.db")
    try:
        analysis = analyze_changed_files(store, repo, ["util.py"], base="main", head="HEAD")
    finally:
        store.close()

    names = {s["qualified_name"] for s in analysis.changed_symbols}
    assert "helper" in names
    assert 0.0 <= analysis.risk_score <= 10.0
    md = render_pr_markdown(analysis)
    assert "PR intelligence" in md
    assert "Changed symbols" in md


def test_analyze_pr_uses_git_range(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init"], repo)
    (repo / "auth.py").write_text("def login(u: str) -> str:\n    return u\n")
    _git(["add", "."], repo)
    _git(["commit", "-m", "base"], repo)
    base = _git(["rev-parse", "HEAD"], repo)

    (repo / "auth.py").write_text("def login(u: str) -> str:\n    return u.strip()\n")
    _git(["add", "."], repo)
    _git(["commit", "-m", "change"], repo)

    db = tmp_path / "graph.db"
    _index(repo, db).close()
    analysis = analyze_pr(db, repo, base=base, head="HEAD")
    assert "auth.py" in analysis.changed_files
