"""Keeps the demo asset valid: the auth->billing->admin chain must resolve."""

from __future__ import annotations

from pathlib import Path

from codeatlas.config import CodeAtlasConfig
from codeatlas.graph.store import GraphStore
from codeatlas.indexer import RepoIndexer
from codeatlas.pr_analysis import analyze_changed_files

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo-monorepo"


def test_demo_monorepo_blast_radius(tmp_path: Path) -> None:
    db = tmp_path / "demo.db"
    config = CodeAtlasConfig.find_and_load(DEMO)
    config.graph.db_path = db
    store = GraphStore(db)
    RepoIndexer(config, store).index_full(resolve=True)
    try:
        analysis = analyze_changed_files(store, DEMO, ["auth/session.py"], base="main", head="HEAD")
    finally:
        store.close()

    changed = {s["qualified_name"] for s in analysis.changed_symbols}
    impacted = {i["qualified_name"] for i in analysis.impacted}
    assert "verify_token" in changed
    assert "create_invoice" in impacted  # billing depends on auth
    assert "tests/test_auth.py" in analysis.suggested_tests
