"""On-demand retrieval-quality eval for a hosted repo's graph.

This is the wedge codeatlas.live doesn't have: instead of just drawing a graph,
prove the index can actually retrieve. We can't assume a hand-authored task
suite for an arbitrary user repo, so we auto-generate a *self-retrieval* suite
from the repo's own symbols (query a symbol's name, expect that symbol back) and
score it across non-semantic modes (no embeddings needed server-side).

The metric is honest about what it measures — "can the index surface a symbol you
name" — and is labelled as a self-retrieval check in the UI, not overclaimed.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any

from codeatlas.eval import EvalMode, run_eval_comparison
from codeatlas.graph.store import GraphStore

# Text/graph modes only — no FAISS/embedding index is built for hosted repos.
EVAL_MODES: tuple[EvalMode, ...] = ("fts", "bm25", "pagerank")
_SAMPLE_KINDS = ("function", "method", "class")


def build_self_retrieval_suite(store: GraphStore, *, limit: int = 15) -> list[dict[str, Any]]:
    """Sample distinctive symbols and turn each into a self-retrieval task."""
    seen: set[str] = set()
    tasks: list[dict[str, Any]] = []
    for kind in _SAMPLE_KINDS:
        for symbol in store.get_symbols_by_kind(kind, limit=200):
            name = symbol.name
            # Skip private/dunder and short names — they make weak, ambiguous queries.
            if len(name) < 4 or name.startswith("_") or name in seen:
                continue
            seen.add(name)
            tasks.append(
                {
                    "id": f"self-{len(tasks) + 1}",
                    "query": name,
                    "expected_symbols": [name],
                    "expected_files": [symbol.file_path],
                    "k": 5,
                }
            )
            if len(tasks) >= limit:
                return tasks
    return tasks


def run_repo_retrieval_eval(graph_db_path: Path | str, *, limit: int = 15) -> dict[str, Any]:
    """Run a self-retrieval comparison across modes for a synced repo's graph."""
    store = GraphStore(Path(graph_db_path))
    try:
        tasks = build_self_retrieval_suite(store, limit=limit)
        if not tasks:
            return {
                "kind": "self_retrieval",
                "task_count": 0,
                "comparison": [],
                "generated_at": int(time.time() * 1000),
                "note": "no indexable symbols found; sync the repo first",
            }
        with tempfile.TemporaryDirectory() as tmp:
            suite_path = Path(tmp) / "suite.json"
            suite_path.write_text(json.dumps({"tasks": tasks}))
            report = run_eval_comparison(store, suite_path, modes=EVAL_MODES)
        return {
            "kind": "self_retrieval",
            "task_count": int(report.get("task_count", len(tasks))),
            "comparison": report.get("comparison", []),
            "generated_at": int(time.time() * 1000),
            "note": "auto-generated self-retrieval suite (query a symbol, expect it back)",
        }
    finally:
        store.close()
