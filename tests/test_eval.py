"""Tests for retrieval evaluation metrics and suite schema."""

from pathlib import Path

from codeatlas.config import CodeAtlasConfig
from codeatlas.eval import load_suite, run_eval_suite
from codeatlas.graph.store import GraphStore
from codeatlas.indexer import RepoIndexer


def _index_repo(repo: Path, db: Path) -> GraphStore:
    config = CodeAtlasConfig.find_and_load(repo)
    config.graph.db_path = db
    store = GraphStore(db)
    RepoIndexer(config, store).index_full()
    return store


def test_load_suite_accepts_extended_task_shape(tmp_path: Path) -> None:
    suite = tmp_path / "suite.json"
    suite.write_text(
        """
        {
          "tasks": [
            {
              "id": "task-1",
              "repo": "fixture",
              "task_type": "test_location",
              "query": "where is greet tested",
              "expected_files": ["tests/test_app.py"],
              "seed_symbol": "greet",
              "budget": 512,
              "k": 3,
              "notes": "file-only task"
            }
          ]
        }
        """
    )
    tasks = load_suite(suite)
    assert tasks[0]["task_type"] == "test_location"
    assert tasks[0]["expected_symbols"] == []
    assert tasks[0]["expected_files"] == ["tests/test_app.py"]
    assert tasks[0]["budget"] == 512


def test_run_eval_suite_reports_file_recall_and_misses(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def greet(name: str) -> str:\n    return name\n")
    (repo / "test_app.py").write_text("def test_greet():\n    assert True\n")
    suite = tmp_path / "suite.json"
    suite.write_text(
        """
        {
          "tasks": [
            {
              "id": "hit",
              "repo": "fixture",
              "task_type": "symbol_lookup",
              "query": "greet",
              "expected_symbols": ["greet"],
              "expected_files": ["app.py"]
            },
            {
              "id": "miss",
              "repo": "fixture",
              "task_type": "test_location",
              "query": "greet",
              "expected_files": ["does_not_exist.py"]
            }
          ]
        }
        """
    )
    store = _index_repo(repo, tmp_path / "graph.db")
    try:
        report = run_eval_suite(store, suite, mode="fts")
    finally:
        store.close()

    assert report["metrics"]["symbol_recall_at_k"] == 0.5
    assert report["metrics"]["file_recall_at_k"] == 0.5
    assert report["metrics"]["miss_count"] == 1
    assert report["misses_by_category"] == {"test_location": 1}
