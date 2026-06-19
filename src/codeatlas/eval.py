"""Deterministic evaluation harness for CodeAtlas retrieval/context quality."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Literal, cast

from codeatlas.agent_context import VALID_CONTEXT_MODES, ContextMode, build_context_pack
from codeatlas.graph.store import GraphStore

EvalMode = Literal[
    "fts",
    "bm25",
    "pagerank",
    "semantic",
    "hybrid",
    "graph-neighborhood",
    "oracle-ablation",
    "context-pack",
]
DEFAULT_EVAL_MODES: tuple[EvalMode, ...] = (
    "fts",
    "bm25",
    "pagerank",
    "semantic",
    "hybrid",
    "graph-neighborhood",
    "context-pack",
)
VALID_TASK_TYPES = frozenset(
    {
        "symbol_lookup",
        "impact_analysis",
        "dependency_trace",
        "architecture_context",
        "test_location",
        "retrieval",
    }
)


def load_suite(path: str | Path) -> list[dict[str, Any]]:
    """Load a JSON eval suite.

    Accepted shapes keep backward compatibility with the original suite:
    - {"tasks": [{"query": "...", "expected_symbols": ["..."]}]}
    - [{"query": "...", "expected_symbols": ["..."]}]

    New real-repo task fields:
    id, repo, task_type, query, expected_symbols, expected_files, seed_symbol,
    hard_negatives, expected_edit_files, k, budget, notes.
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
        expected_files = task.get("expected_files", [])
        hard_negatives = task.get("hard_negatives", [])
        expected_edit_files = task.get("expected_edit_files", task.get("expected_patch", []))
        task_type = str(task.get("task_type", "retrieval"))
        if not query:
            raise ValueError(f"task {i} is missing a non-empty query")
        if task_type not in VALID_TASK_TYPES:
            raise ValueError(f"task {i} task_type must be one of {sorted(VALID_TASK_TYPES)}")
        if not isinstance(expected, list):
            raise ValueError(f"task {i} expected_symbols must be a list")
        if not isinstance(expected_files, list):
            raise ValueError(f"task {i} expected_files must be a list")
        if not isinstance(hard_negatives, list):
            raise ValueError(f"task {i} hard_negatives must be a list")
        if not isinstance(expected_edit_files, list):
            raise ValueError(f"task {i} expected_edit_files must be a list")
        if not expected and not expected_files:
            raise ValueError(f"task {i} must include expected_symbols or expected_files")
        normalized.append(
            {
                "id": task.get("id", f"task-{i}"),
                "category": task.get("category", "retrieval"),
                "repo": task.get("repo", "local"),
                "task_type": task_type,
                "query": query,
                "expected_symbols": [str(e) for e in expected],
                "expected_files": [str(e) for e in expected_files],
                "hard_negatives": [str(e) for e in hard_negatives],
                "expected_edit_files": [str(e) for e in expected_edit_files],
                "seed_symbol": task.get("seed_symbol"),
                "k": int(task.get("k", 5)),
                "budget": int(task.get("budget", 0)) if task.get("budget") is not None else None,
                "notes": task.get("notes"),
            }
        )
    return normalized


def _hit_matches(hit_name: str, expected: list[str]) -> bool:
    hit = hit_name.lower()
    return any(
        hit == exp.lower() or hit.endswith(f"::{exp.lower()}") or hit.endswith(f".{exp.lower()}")
        for exp in expected
    )


def _file_matches(hit_file: str, expected: list[str]) -> bool:
    hit = hit_file.lower()
    return any(hit == exp.lower() or hit.endswith(exp.lower()) for exp in expected)


def _recall(hits: list[str], expected: list[str], *, file_mode: bool = False) -> float:
    if not expected:
        return 0.0
    matcher = _file_matches if file_mode else _hit_matches
    matched = sum(1 for exp in expected if any(matcher(hit, [exp]) for hit in hits))
    return matched / len(expected)


def _first_match_rank(
    hits: list[str], expected: list[str], *, file_mode: bool = False
) -> int | None:
    if not expected:
        return None
    matcher = _file_matches if file_mode else _hit_matches
    return next((idx + 1 for idx, hit in enumerate(hits) if matcher(hit, expected)), None)


def _context_mode(mode: EvalMode) -> ContextMode:
    if mode in {"context-pack", "graph-neighborhood", "oracle-ablation"}:
        return "pagerank"
    if mode == "bm25":
        return "fts"
    return cast(ContextMode, mode)


def _precision(hits: list[str], expected: list[str], *, file_mode: bool = False) -> float:
    if not hits:
        return 0.0
    matcher = _file_matches if file_mode else _hit_matches
    matched = sum(1 for hit in hits if matcher(hit, expected))
    return matched / len(hits)


def _ndcg(hits: list[str], expected: list[str], *, file_mode: bool = False) -> float:
    if not hits or not expected:
        return 0.0
    matcher = _file_matches if file_mode else _hit_matches
    dcg = 0.0
    matched_expected: set[str] = set()
    for idx, hit in enumerate(hits, 1):
        matched = next((exp for exp in expected if matcher(hit, [exp])), None)
        if matched is not None and matched not in matched_expected:
            matched_expected.add(matched)
            dcg += 1.0 / math.log2(idx + 1)
    ideal_count = min(len(expected), len(hits))
    idcg = sum(1.0 / math.log2(idx + 1) for idx in range(1, ideal_count + 1))
    return 0.0 if idcg == 0 else dcg / idcg


def _likely_failure_reason(
    *,
    mode_effective: str,
    expected_symbols: list[str],
    expected_files: list[str],
    symbol_recall: float,
    file_recall: float,
) -> str:
    if mode_effective.endswith("-fallback"):
        return f"{mode_effective}; semantic index was unavailable"
    if expected_symbols and symbol_recall == 0.0:
        return "expected symbol did not appear in ranked context pack"
    if expected_files and file_recall == 0.0:
        return "expected file did not appear in ranked context pack"
    if expected_symbols and symbol_recall < 1.0:
        return "some expected symbols were outside top-k"
    if expected_files and file_recall < 1.0:
        return "some expected files were outside top-k"
    return "matched"


def _failure_class(reason: str) -> str:
    if "fallback" in reason or "semantic index" in reason:
        return "stale_or_missing_index"
    if "symbol" in reason:
        return "ranking_gap"
    if "file" in reason:
        return "edit_localization_gap"
    if "outside top-k" in reason:
        return "insufficient_budget"
    return "matched"


def run_eval_suite(
    store: GraphStore,
    suite_path: str | Path,
    *,
    budget_tokens: int = 2000,
    mode: EvalMode = "pagerank",
    semantic_index: Any | None = None,
    repo_filter: str | None = None,
) -> dict[str, Any]:
    valid_eval_modes = (
        *VALID_CONTEXT_MODES,
        "bm25",
        "graph-neighborhood",
        "oracle-ablation",
        "context-pack",
    )
    if mode not in valid_eval_modes:
        valid = ", ".join(valid_eval_modes)
        raise ValueError(f"mode must be one of: {valid}")

    tasks = load_suite(suite_path)
    if repo_filter is not None:
        tasks = [task for task in tasks if task["repo"] == repo_filter]
    task_results: list[dict[str, Any]] = []
    total_latency = 0.0
    total_symbol_recall = 0.0
    total_file_recall = 0.0
    total_rr = 0.0
    total_precision = 0.0
    total_ndcg = 0.0
    total_edit_recall = 0.0
    total_density = 0.0
    total_savings = 0.0
    effective_modes: set[str] = set()
    misses_by_category: dict[str, int] = {}
    misses: list[dict[str, Any]] = []

    for task in tasks:
        task_budget = int(task["budget"] or budget_tokens)
        task_k = max(1, int(task["k"]))
        started = time.perf_counter()
        pack = build_context_pack(
            store,
            task["query"],
            budget_tokens=task_budget,
            limit=task_k,
            mode=_context_mode(mode),
            semantic_index=semantic_index,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        mode_effective = "context-pack" if mode == "context-pack" else str(pack["mode_effective"])
        effective_modes.add(mode_effective)
        total_latency += latency_ms
        hits = [r["symbol"]["qualified_name"] for r in pack["results"]]
        hit_files = [r["symbol"]["file"] for r in pack["results"]]
        hit_files.extend(summary["file"] for summary in pack["file_summaries"])
        # Preserve order while deduplicating.
        hit_files = list(dict.fromkeys(hit_files))
        symbol_recall = _recall(hits, task["expected_symbols"])
        file_recall = _recall(hit_files, task["expected_files"], file_mode=True)
        precision = max(
            _precision(hits[:task_k], task["expected_symbols"]),
            _precision(hit_files[:task_k], task["expected_files"], file_mode=True),
        )
        ndcg = max(
            _ndcg(hits[:task_k], task["expected_symbols"]),
            _ndcg(hit_files[:task_k], task["expected_files"], file_mode=True),
        )
        edit_recall = _recall(hit_files, task["expected_edit_files"], file_mode=True)
        useful_context_density = precision
        first_match = _first_match_rank(hits, task["expected_symbols"])
        if first_match is None:
            first_match = _first_match_rank(hit_files, task["expected_files"], file_mode=True)
        reciprocal_rank = 0.0 if first_match is None else 1.0 / first_match
        total_symbol_recall += symbol_recall
        total_file_recall += file_recall
        total_rr += reciprocal_rank
        total_precision += precision
        total_ndcg += ndcg
        total_edit_recall += edit_recall
        total_density += useful_context_density
        total_savings += float(pack["context_savings"])
        reason = _likely_failure_reason(
            mode_effective=mode_effective,
            expected_symbols=task["expected_symbols"],
            expected_files=task["expected_files"],
            symbol_recall=symbol_recall,
            file_recall=file_recall,
        )
        is_miss = (
            (bool(task["expected_symbols"]) and symbol_recall < 1.0)
            or (bool(task["expected_files"]) and file_recall < 1.0)
            or mode_effective.endswith("-fallback")
        )
        if is_miss:
            misses_by_category[task["task_type"]] = misses_by_category.get(task["task_type"], 0) + 1
            misses.append(
                {
                    "id": task["id"],
                    "repo": task["repo"],
                    "task_type": task["task_type"],
                    "query": task["query"],
                    "mode": mode,
                    "mode_effective": mode_effective,
                    "expected_symbols": task["expected_symbols"],
                    "expected_files": task["expected_files"],
                    "hits": hits[:task_k],
                    "hit_files": hit_files[:task_k],
                    "reason": reason,
                    "failure_class": _failure_class(reason),
                }
            )
        task_results.append(
            {
                "id": task["id"],
                "category": task["category"],
                "repo": task["repo"],
                "task_type": task["task_type"],
                "query": task["query"],
                "seed_symbol": task["seed_symbol"],
                "mode_effective": mode_effective,
                "expected_symbols": task["expected_symbols"],
                "expected_files": task["expected_files"],
                "hard_negatives": task["hard_negatives"],
                "expected_edit_files": task["expected_edit_files"],
                "hits": hits,
                "hit_files": hit_files,
                "recall_at_k": symbol_recall,
                "symbol_recall_at_k": round(symbol_recall, 6),
                "file_recall_at_k": round(file_recall, 6),
                "precision_at_k": round(precision, 6),
                "ndcg_at_k": round(ndcg, 6),
                "edit_localization_recall": round(edit_recall, 6),
                "useful_context_density": round(useful_context_density, 6),
                "reciprocal_rank": round(reciprocal_rank, 6),
                "latency_ms": round(latency_ms, 3),
                "context_savings": pack["context_savings"],
                "failure_reason": reason,
                "failure_class": _failure_class(reason),
            }
        )

    n = len(tasks)
    stats = store.get_stats()
    return {
        "suite": str(suite_path),
        "repo_filter": repo_filter,
        "task_count": n,
        "mode": mode,
        "mode_effective": next(iter(effective_modes)) if len(effective_modes) == 1 else "mixed",
        "metrics": {
            "recall_at_k": round(total_symbol_recall / n, 6) if n else 0.0,
            "symbol_recall_at_k": round(total_symbol_recall / n, 6) if n else 0.0,
            "file_recall_at_k": round(total_file_recall / n, 6) if n else 0.0,
            "mrr": round(total_rr / n, 6) if n else 0.0,
            "precision_at_k": round(total_precision / n, 6) if n else 0.0,
            "ndcg_at_k": round(total_ndcg / n, 6) if n else 0.0,
            "edit_localization_recall": round(total_edit_recall / n, 6) if n else 0.0,
            "useful_context_density": round(total_density / n, 6) if n else 0.0,
            "avg_latency_ms": round(total_latency / n, 3) if n else 0.0,
            "avg_context_savings": round(total_savings / n, 4) if n else 0.0,
            "indexed_files": stats["files"],
            "indexed_symbols": stats["symbols"],
            "indexed_relationships": stats["relationships"],
            "miss_count": len(misses),
        },
        "misses_by_category": misses_by_category,
        "misses": misses,
        "tasks": task_results,
    }


def run_eval_comparison(
    store: GraphStore,
    suite_path: str | Path,
    *,
    budget_tokens: int = 2000,
    modes: list[EvalMode] | tuple[EvalMode, ...] = DEFAULT_EVAL_MODES,
    semantic_index: Any | None = None,
    repo_filter: str | None = None,
) -> dict[str, Any]:
    """Run the same suite across retrieval modes for apples-to-apples comparison."""
    reports = {
        mode: run_eval_suite(
            store,
            suite_path,
            budget_tokens=budget_tokens,
            mode=mode,
            semantic_index=semantic_index,
            repo_filter=repo_filter,
        )
        for mode in modes
    }
    comparison = [
        {
            "mode": mode,
            "mode_effective": reports[mode]["mode_effective"],
            **reports[mode]["metrics"],
        }
        for mode in modes
    ]
    first = next(iter(reports.values()), {"task_count": 0})
    return {
        "suite": str(suite_path),
        "repo_filter": repo_filter,
        "task_count": first["task_count"],
        "budget_tokens": budget_tokens,
        "comparison": comparison,
        "modes": reports,
    }


def render_eval_markdown(report: dict[str, Any]) -> str:
    if "comparison" in report:
        return _render_comparison_markdown(report)

    metrics = report["metrics"]
    lines = [
        "# CodeAtlas Eval Report",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Tasks | {report['task_count']} |",
        f"| Mode | `{report.get('mode', 'pagerank')}` |",
        f"| Effective mode | `{report.get('mode_effective', report.get('mode', 'pagerank'))}` |",
        f"| Recall@k | {metrics['recall_at_k']:.3f} |",
        f"| File recall@k | {metrics['file_recall_at_k']:.3f} |",
        f"| Precision@k | {metrics['precision_at_k']:.3f} |",
        f"| nDCG@k | {metrics['ndcg_at_k']:.3f} |",
        f"| Edit localization recall | {metrics['edit_localization_recall']:.3f} |",
        f"| Useful context density | {metrics['useful_context_density']:.3f} |",
        f"| MRR | {metrics['mrr']:.3f} |",
        f"| Avg latency | {metrics['avg_latency_ms']:.2f} ms |",
        f"| Avg context savings | {metrics['avg_context_savings']:.2%} |",
        f"| Indexed files | {metrics['indexed_files']} |",
        f"| Indexed symbols | {metrics['indexed_symbols']} |",
        "",
        "## Tasks",
        "",
        "| Query | Expected symbols | Expected files | Top hits | Top files | RR | Latency |",
        "|-------|------------------|----------------|----------|-----------|----|---------|",
    ]
    for task in report["tasks"]:
        expected = ", ".join(f"`{e}`" for e in task["expected_symbols"])
        expected_files = ", ".join(f"`{e}`" for e in task["expected_files"])
        hits = ", ".join(f"`{h}`" for h in task["hits"][:5]) or "_none_"
        hit_files = ", ".join(f"`{h}`" for h in task["hit_files"][:5]) or "_none_"
        lines.append(
            f"| `{task['query']}` | {expected or '_none_'} | {expected_files or '_none_'} | "
            f"{hits} | {hit_files} | "
            f"{task['reciprocal_rank']:.3f} | {task['latency_ms']:.2f} ms |"
        )
    lines.append("")
    return "\n".join(lines)


def _render_comparison_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# CodeAtlas Eval Report",
        "",
        "## Mode Comparison",
        "",
        "| Mode | Effective | Symbol recall@k | File recall@k | Precision@k | nDCG@k | Edit loc | Density | MRR | Avg latency | Context savings | Misses |",
        "|------|-----------|-----------------|---------------|-------------|--------|----------|---------|-----|-------------|-----------------|--------|",
    ]
    for row in report["comparison"]:
        lines.append(
            f"| `{row['mode']}` | `{row['mode_effective']}` | "
            f"{row['symbol_recall_at_k']:.3f} | {row['file_recall_at_k']:.3f} | "
            f"{row['precision_at_k']:.3f} | {row['ndcg_at_k']:.3f} | "
            f"{row['edit_localization_recall']:.3f} | {row['useful_context_density']:.3f} | "
            f"{row['mrr']:.3f} | {row['avg_latency_ms']:.2f} ms | "
            f"{row['avg_context_savings']:.2%} | {row['miss_count']} |"
        )

    best = max(
        report["comparison"],
        key=lambda row: (row["recall_at_k"], row["mrr"], -row["avg_latency_ms"]),
    )
    lines.extend(
        [
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Tasks | {report['task_count']} |",
            f"| Budget | {report['budget_tokens']:,} tokens |",
            f"| Best mode | `{best['mode']}` |",
            f"| Best recall@k | {best['recall_at_k']:.3f} |",
            f"| Best MRR | {best['mrr']:.3f} |",
            f"| Total misses | {best['miss_count']} |",
            "",
            "## Failure Analysis",
            "",
            "| Mode | Task | Repo | Type | Query | Reason |",
            "|------|------|------|------|-------|--------|",
        ]
    )
    any_misses = False
    for mode, mode_report in report["modes"].items():
        for miss in mode_report.get("misses", [])[:20]:
            any_misses = True
            lines.append(
                f"| `{mode}` | `{miss['id']}` | `{miss['repo']}` | `{miss['task_type']}` | "
                f"`{miss['query']}` | {miss['failure_class']}: {miss['reason']} |"
            )
    if not any_misses:
        lines.append("| _none_ | _none_ | _none_ | _none_ | _none_ | All tasks matched |")
    lines.extend(
        [
            "",
            "## Tasks",
            "",
        ]
    )
    for mode, mode_report in report["modes"].items():
        lines.extend(
            [
                f"### `{mode}`",
                "",
                "| Query | Expected symbols | Expected files | Top hits | Top files | RR | Latency |",
                "|-------|------------------|----------------|----------|-----------|----|---------|",
            ]
        )
        for task in mode_report["tasks"]:
            expected = ", ".join(f"`{e}`" for e in task["expected_symbols"])
            expected_files = ", ".join(f"`{e}`" for e in task["expected_files"])
            hits = ", ".join(f"`{h}`" for h in task["hits"][:5]) or "_none_"
            hit_files = ", ".join(f"`{h}`" for h in task["hit_files"][:5]) or "_none_"
            lines.append(
                f"| `{task['query']}` | {expected or '_none_'} | {expected_files or '_none_'} | "
                f"{hits} | {hit_files} | "
                f"{task['reciprocal_rank']:.3f} | {task['latency_ms']:.2f} ms |"
            )
        lines.append("")
    return "\n".join(lines)
