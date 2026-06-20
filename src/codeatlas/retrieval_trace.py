"""Retrieval trace — observability for *why* a result ranked.

Runs each retrieval stage (FTS, semantic, PageRank, and the final ordering used
by the chosen mode incl. cross-encoder rerank) and records each candidate's
per-stage signals so you can explain the ranking, not just trust it.
"""

from __future__ import annotations

from typing import Any, cast

from codeatlas.graph.store import GraphStore


def _explain(top: dict[str, Any], effective_mode: str) -> str:
    reasons: list[str] = []
    if top.get("fts_rank") is not None:
        reasons.append(f"FTS match (rank {top['fts_rank']})")
    if top.get("semantic_rank") is not None:
        reasons.append(f"semantic match (rank {top['semantic_rank']})")
    if top.get("pagerank", 0.0) > 0:
        reasons.append(f"PageRank centrality {top['pagerank']}")
    if effective_mode == "rerank":
        reasons.append("selected by cross-encoder rerank")
    why = ", ".join(reasons) if reasons else "name/text match"
    return f"`{top['qualified_name']}` ranked #1: {why}."


def build_query_trace(
    store: GraphStore,
    query: str,
    *,
    mode: str = "pagerank",
    semantic_index: Any | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Return a per-candidate, per-stage trace of how ``query`` was ranked."""
    fts_rank = {sym.id: i + 1 for i, sym in enumerate(store.search(query, limit=50))}
    semantic_rank: dict[str, int] = {}
    if semantic_index is not None:
        try:
            semantic_rank = {
                sym.id: i + 1
                for i, (sym, _) in enumerate(semantic_index.search(query, store, limit=50))
            }
        except Exception:
            semantic_rank = {}
    pagerank = store.compute_pagerank()

    # Final ordering is produced by the same path build_context_pack uses.
    from codeatlas.agent_context import ContextMode, _rank_candidates

    ranked, effective_mode = _rank_candidates(
        store, query, mode=cast(ContextMode, mode), limit=limit, semantic_index=semantic_index
    )

    candidates: list[dict[str, Any]] = []
    for i, sym in enumerate(ranked[: max(limit, 20)]):
        candidates.append(
            {
                "qualified_name": sym.qualified_name,
                "file": sym.file_path,
                "fts_rank": fts_rank.get(sym.id),
                "semantic_rank": semantic_rank.get(sym.id),
                "pagerank": round(pagerank.get(sym.id, 0.0), 4),
                "final_rank": i + 1,
                "included": i < limit,
            }
        )

    return {
        "query": query,
        "mode": mode,
        "mode_effective": effective_mode,
        "candidates": candidates,
        "explanation": _explain(candidates[0], effective_mode) if candidates else "no candidates",
    }
