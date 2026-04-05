"""
CodeAtlas benchmark suite.

Measures indexing throughput, query latency, and memory usage on real repos.
Clones small well-known open-source repos into a temp dir and profiles:
  - Full index time and files/s
  - Incremental index time
  - FTS search latency (p50 / p95)
  - Semantic search latency (if sentence-transformers available)
  - Peak RSS memory during indexing
  - Estimated token savings vs naive full-file context

Run:
    python benchmarks/bench.py
    python benchmarks/bench.py --repo https://github.com/pallets/flask --name flask
    python benchmarks/bench.py --json   # machine-readable output
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from statistics import median, quantiles
from typing import Any

# Add src to path so we can import codeatlas without installing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    import platform
    import resource  # Unix only

    def _peak_rss_mb() -> float:
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS reports bytes, Linux reports KB
        if platform.system() == "Darwin":
            return rss / (1024 * 1024)
        return rss / 1024
except ImportError:

    def _peak_rss_mb() -> float:  # type: ignore[misc]
        return 0.0


def _clone(url: str, dest: Path) -> bool:
    """Shallow-clone a repo. Returns True on success."""
    result = subprocess.run(
        ["git", "clone", "--depth=1", "--quiet", url, str(dest)],
        capture_output=True,
        timeout=120,
    )
    return result.returncode == 0


def _count_tokens_naive(store: Any) -> int:
    """Estimate tokens consumed by naively dumping all source files."""
    total_bytes = 0
    for fi in store.list_files():
        p = Path(fi.path)
        try:
            total_bytes += p.stat().st_size
        except OSError:
            pass
    # ~4 bytes per token is a rough estimate
    return total_bytes // 4


def _count_tokens_atlas(store: Any) -> int:
    """Estimate tokens for structured CodeAtlas graph output.

    An AI agent querying the graph gets structured JSON instead of raw source.
    Estimate ~30 tokens per symbol (name, kind, file:line, signature).
    Relationships add ~10 tokens each (source -> target, kind).
    """
    stats = store.get_stats()
    return stats["symbols"] * 30 + stats["relationships"] * 10


def bench_repo(
    name: str,
    repo_path: Path,
    runs: int = 3,
) -> dict[str, Any]:
    from codeatlas.config import CodeAtlasConfig, GraphConfig
    from codeatlas.graph.store import GraphStore
    from codeatlas.indexer import RepoIndexer

    results: dict[str, Any] = {"name": name, "repo": str(repo_path)}

    config = CodeAtlasConfig(
        repo_root=repo_path,
        graph=GraphConfig(db_path=Path(":memory:")),
    )

    # ── Full index — time across N fresh stores ───────────────────────────────
    index_times: list[float] = []
    last_stats: dict[str, int] = {}
    rss_before = _peak_rss_mb()
    for _ in range(runs):
        s = GraphStore(":memory:")
        ix = RepoIndexer(config, s)
        t0 = time.perf_counter()
        last_stats = ix.index_full(resolve=True)
        index_times.append(time.perf_counter() - t0)

    rss_after = _peak_rss_mb()

    # One clean store for all queries (avoids FTS5 content sync issues)
    store = GraphStore(":memory:")
    indexer = RepoIndexer(config, store)
    indexer.index_full(resolve=True)
    graph_stats = store.get_stats()

    results["index"] = {
        "files": graph_stats["files"],
        "symbols": graph_stats["symbols"],
        "relationships": graph_stats["relationships"],
        "parsed": last_stats["parsed"],
        "errors": last_stats["errors"],
        "time_s": round(median(index_times), 3),
        "files_per_s": round(graph_stats["files"] / median(index_times), 1),
        "symbols_per_s": round(graph_stats["symbols"] / median(index_times), 1),
        "peak_rss_mb": round(rss_after - rss_before, 1),
    }

    # ── Incremental index (no changes → should be fast) ─────────────────────
    inc_times: list[float] = []
    for _ in range(runs):
        t0 = time.perf_counter()
        indexer.index_incremental(resolve=False)
        inc_times.append(time.perf_counter() - t0)

    results["incremental"] = {
        "time_s": round(median(inc_times), 3),
        "speedup_vs_full": round(median(index_times) / median(inc_times), 1),
    }

    # ── FTS search latency ───────────────────────────────────────────────────
    search_terms = ["error", "init", "parse", "handle", "config", "get", "set", "run"]
    fts_times: list[float] = []
    for term in search_terms:
        for _ in range(5):
            t0 = time.perf_counter()
            store.search(term, limit=10)
            fts_times.append((time.perf_counter() - t0) * 1000)

    qs = quantiles(fts_times, n=20)
    results["fts_search_ms"] = {
        "p50": round(median(fts_times), 2),
        "p95": round(qs[18], 2),
        "min": round(min(fts_times), 2),
        "max": round(max(fts_times), 2),
    }

    # ── Graph traversal latency ──────────────────────────────────────────────
    all_symbols = store.find_symbols_by_name("init") or store.find_symbols_by_name("run")
    traversal_times: list[float] = []
    if all_symbols:
        sym = all_symbols[0]
        for _ in range(20):
            t0 = time.perf_counter()
            store.trace_call_chain(sym.id, max_depth=5)
            traversal_times.append((time.perf_counter() - t0) * 1000)
        results["graph_traversal_ms"] = {
            "p50": round(median(traversal_times), 2),
            "p95": round(quantiles(traversal_times, n=20)[18], 2),
        }

    # ── Token savings estimate ───────────────────────────────────────────────
    naive_tokens = _count_tokens_naive(store)
    atlas_tokens = _count_tokens_atlas(store)
    savings_pct = round((1 - atlas_tokens / naive_tokens) * 100, 1) if naive_tokens > 0 else 0

    results["token_savings"] = {
        "naive_full_context_tokens": naive_tokens,
        "atlas_graph_tokens": atlas_tokens,
        "savings_pct": savings_pct,
        "note": "Estimate: ~4 bytes/token for source, ~30 tokens/symbol + ~10 tokens/relationship for graph",
    }

    return results


def _print_results(r: dict[str, Any]) -> None:
    sep = "─" * 60
    print(f"\n{sep}")
    print(f"  Repo: {r['name']}  ({r['repo']})")
    print(sep)

    idx = r["index"]
    print("\n  Full Index")
    print(f"    Files:           {idx['files']:>8,}")
    print(f"    Symbols:         {idx['symbols']:>8,}")
    print(f"    Relationships:   {idx['relationships']:>8,}")
    print(f"    Parse errors:    {idx['errors']:>8}")
    print(f"    Time (median):   {idx['time_s']:>8.3f}s")
    print(f"    Files/s:         {idx['files_per_s']:>8.1f}")
    print(f"    Symbols/s:       {idx['symbols_per_s']:>8.1f}")
    print(f"    Peak RSS delta:  {idx['peak_rss_mb']:>8.1f} MB")

    inc = r["incremental"]
    print("\n  Incremental Index (no changes)")
    print(f"    Time (median):   {inc['time_s']:>8.3f}s")
    print(f"    Speedup vs full: {inc['speedup_vs_full']:>8.1f}x")

    fts = r["fts_search_ms"]
    print("\n  FTS Search Latency")
    print(f"    p50:             {fts['p50']:>8.2f} ms")
    print(f"    p95:             {fts['p95']:>8.2f} ms")

    if "graph_traversal_ms" in r:
        gt = r["graph_traversal_ms"]
        print("\n  Graph Traversal Latency (call chain, depth=5)")
        print(f"    p50:             {gt['p50']:>8.2f} ms")
        print(f"    p95:             {gt['p95']:>8.2f} ms")

    tok = r["token_savings"]
    print("\n  Token Savings vs Naive Full-File Context")
    print(f"    Naive (all files): {tok['naive_full_context_tokens']:>10,} tokens")
    print(f"    Atlas (graph):     {tok['atlas_graph_tokens']:>10,} tokens")
    print(f"    Savings:           {tok['savings_pct']:>9.1f}%")
    print(f"    Note: {tok['note']}")
    print()


# Default benchmark targets — small, fast-to-clone repos
DEFAULT_TARGETS = [
    ("requests", "https://github.com/psf/requests"),
    ("click", "https://github.com/pallets/click"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="CodeAtlas benchmark suite")
    parser.add_argument("--repo", help="URL of a git repo to benchmark")
    parser.add_argument("--name", default="custom", help="Name for the repo")
    parser.add_argument("--runs", type=int, default=3, help="Measurement runs per benchmark")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--output", help="Write JSON results to this file")
    args = parser.parse_args()

    targets = [(args.name, args.repo)] if args.repo else DEFAULT_TARGETS

    all_results = []

    with tempfile.TemporaryDirectory() as tmpdir:
        for name, url in targets:
            dest = Path(tmpdir) / name
            print(f"Cloning {url} ...", flush=True)
            if not _clone(url, dest):
                print(f"  Failed to clone {url}, skipping.")
                continue
            print(f"Running benchmarks for '{name}' ({args.runs} runs each)...", flush=True)
            result = bench_repo(name, dest, runs=args.runs)
            all_results.append(result)
            if not args.json:
                _print_results(result)

    if args.json or args.output:
        output = json.dumps(all_results, indent=2)
        if args.output:
            Path(args.output).write_text(output)
            print(f"Results written to {args.output}")
        else:
            print(output)


if __name__ == "__main__":
    main()
