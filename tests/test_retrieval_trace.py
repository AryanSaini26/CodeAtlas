"""Tests for the retrieval trace (explain-query)."""

from __future__ import annotations

from pathlib import Path

from codeatlas.config import CodeAtlasConfig
from codeatlas.graph.store import GraphStore
from codeatlas.indexer import RepoIndexer
from codeatlas.retrieval_trace import build_query_trace


def _index(tmp_path: Path) -> GraphStore:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text(
        "def authenticate(user: str) -> str:\n    return user\n\n\n"
        "def logout() -> None:\n    return None\n"
    )
    config = CodeAtlasConfig.find_and_load(repo)
    config.graph.db_path = tmp_path / "graph.db"
    store = GraphStore(config.graph.db_path)
    RepoIndexer(config, store).index_full(resolve=True)
    return store


def test_build_query_trace_stages_and_explanation(tmp_path: Path) -> None:
    store = _index(tmp_path)
    try:
        trace = build_query_trace(store, "authenticate", mode="pagerank")
    finally:
        store.close()

    assert trace["query"] == "authenticate"
    assert trace["mode_effective"] == "pagerank"
    assert trace["candidates"], "expected at least one candidate"
    top = trace["candidates"][0]
    # Every candidate carries the per-stage signals.
    for c in trace["candidates"]:
        assert "fts_rank" in c and "pagerank" in c and "final_rank" in c
    assert "authenticate" in top["qualified_name"]
    assert "ranked #1" in trace["explanation"]
