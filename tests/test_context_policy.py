"""Tests for secret-safe / policy-aware context packs."""

from __future__ import annotations

from pathlib import Path

from codeatlas.agent_context import build_context_pack
from codeatlas.config import CodeAtlasConfig
from codeatlas.context_policy import ContextPolicy, is_denied, redact, safety_report
from codeatlas.graph.store import GraphStore
from codeatlas.indexer import RepoIndexer


def test_is_denied_and_redact() -> None:
    pol = ContextPolicy()
    assert is_denied(".env", pol)
    assert is_denied("config/secrets/keys.py", pol)
    assert is_denied("frontend/node_modules/x/index.js", pol)
    assert not is_denied("src/app.py", pol)

    cleaned, n = redact("AWS=AKIA1234567890ABCDEF rest", pol)
    assert n == 1
    assert "AKIA1234567890ABCDEF" not in cleaned


def _index(tmp_path: Path) -> tuple[GraphStore, Path]:
    repo = tmp_path / "repo"
    (repo / "secrets").mkdir(parents=True)
    (repo / "app.py").write_text("def main() -> int:\n    return 1\n")
    (repo / "secrets" / "keys.py").write_text("def load_key() -> str:\n    return 'x'\n")
    config = CodeAtlasConfig.find_and_load(repo)
    config.graph.db_path = tmp_path / "graph.db"
    store = GraphStore(config.graph.db_path)
    RepoIndexer(config, store).index_full(resolve=True)
    return store, repo


def test_policy_excludes_denied_files_from_pack(tmp_path: Path) -> None:
    store, _ = _index(tmp_path)
    try:
        with_policy = build_context_pack(store, "load key", policy=ContextPolicy())
        without = build_context_pack(store, "load key")
    finally:
        store.close()

    def files(pack: dict) -> set[str]:
        return {r["symbol"]["file"] for r in pack["results"]}

    assert any("secrets" in f for f in files(without))  # baseline would surface it
    assert not any("secrets" in f for f in files(with_policy))  # policy excludes it
    assert with_policy["policy"]["excluded_files"] >= 1


def test_safety_report_counts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".env").write_text("API_TOKEN=abcdef\n")
    (repo / "ok.py").write_text("def f() -> int:\n    return 1\n")
    report = safety_report(str(repo), ContextPolicy())
    assert ".env" in report["excluded"]
    assert report["excluded_count"] >= 1
