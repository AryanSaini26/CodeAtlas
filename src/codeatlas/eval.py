"""Deterministic evaluation harness for CodeAtlas retrieval/context quality."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from codeatlas.agent_context import build_context_pack
from codeatlas.graph.store import GraphStore


def load_suite(path: str | Path) -> list[dict[str, Any]]:
    """Load a JSON eval suite.

    Accepted shapes:
    - {"tasks": [{"query": "...", "expected_symbols": ["..."]}]}
    - [{"query": "...", "expected_symbols": ["..."]}]
    """
    raw = json.loads(Path(path).read_text())
    tasks = raw.get("tasks", raw) if isinstance(raw, dict) else raw
    if not isinstance(tasks, list):
        raise ValueError("eval suite must be a list or an object with a 'tasks' list")
    normalized: list[dict[str, Any]] = []
    for i, task in enumerate(tasks, 1):
        if not isinstance(task, dict):
            raise ValueError(f"task {i} must be an object")
        query = str(task.get("query", "")).strip()
        expected = task.get("expected_symbols", task.get("expected", []))
        if not query:
            raise ValueError(f"task {i} is missing a non-empty query")
        if not isinstance(expected, list) or not expected:
            raise ValueError(f"task {i} must include expected_symbols")
        normalized.append(
            {
                "id": task.get("id", f"task-{i}"),
                "query": query,
                "expected_symbols": [str(e) for e in expected],
                "k": int(task.get("k", 5)),
            }
        )
    return normalized


def _hit_matches(hit_name: str, expected: list[str]) -> bool:
    hit = hit_name.lower()
    return any(hit == exp.lower() or hit.endswith(f"::{exp.lower()}") for exp in expected)


def run_eval_suite(
    store: GraphStore,
    suite_path: str | Path,
    *,
    budget_tokens: int = 2000,
) -> dict[str, Any]:
    tasks = load_suite(suite_path)
    task_results: list[dict[str, Any]] = []
    total_latency = 0.0
    total_recall = 0.0
    total_rr = 0.0
    total_savings = 0.0

    for task in tasks:
        started = time.perf_counter()
        pack = build_context_pack(
            store,
            task["query"],
            budget_tokens=budget_tokens,
            limit=max(1, int(task["k"])),
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        total_latency += latency_ms
        hits = [r["symbol"]["qualified_name"] for r in pack["results"]]
        matched = [_hit_matches(hit, task["expected_symbols"]) for hit in hits]
        first_match = next((idx + 1 for idx, ok in enumerate(matched) if ok), None)
        recall = 1.0 if first_match is not None else 0.0
        reciprocal_rank = 0.0 if first_match is None else 1.0 / first_match
        total_recall += recall
        total_rr += reciprocal_rank
        total_savings += float(pack["context_savings"])
        task_results.append(
            {
                "id": task["id"],
                "query": task["query"],
                "expected_symbols": task["expected_symbols"],
                "hits": hits,
                "recall_at_k": recall,
                "reciprocal_rank": round(reciprocal_rank, 6),
                "latency_ms": round(latency_ms, 3),
                "context_savings": pack["context_savings"],
            }
        )

    n = len(tasks)
    stats = store.get_stats()
    return {
        "suite": str(suite_path),
        "task_count": n,
        "metrics": {
            "recall_at_k": round(total_recall / n, 6) if n else 0.0,
            "mrr": round(total_rr / n, 6) if n else 0.0,
            "avg_latency_ms": round(total_latency / n, 3) if n else 0.0,
            "avg_context_savings": round(total_savings / n, 4) if n else 0.0,
            "indexed_files": stats["files"],
            "indexed_symbols": stats["symbols"],
            "indexed_relationships": stats["relationships"],
        },
        "tasks": task_results,
    }


def render_eval_markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    lines = [
        "# CodeAtlas Eval Report",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Tasks | {report['task_count']} |",
        f"| Recall@k | {metrics['recall_at_k']:.3f} |",
        f"| MRR | {metrics['mrr']:.3f} |",
        f"| Avg latency | {metrics['avg_latency_ms']:.2f} ms |",
        f"| Avg context savings | {metrics['avg_context_savings']:.2%} |",
        f"| Indexed files | {metrics['indexed_files']} |",
        f"| Indexed symbols | {metrics['indexed_symbols']} |",
        "",
        "## Tasks",
        "",
        "| Query | Expected | Top hits | RR | Latency |",
        "|-------|----------|----------|----|---------|",
    ]
    for task in report["tasks"]:
        expected = ", ".join(f"`{e}`" for e in task["expected_symbols"])
        hits = ", ".join(f"`{h}`" for h in task["hits"][:5]) or "_none_"
        lines.append(
            f"| `{task['query']}` | {expected} | {hits} | "
            f"{task['reciprocal_rank']:.3f} | {task['latency_ms']:.2f} ms |"
        )
    lines.append("")
    return "\n".join(lines)
