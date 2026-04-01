"""Hybrid search combining FTS5 keyword search with FAISS vector search."""

from __future__ import annotations

from codeatlas.graph.store import GraphStore
from codeatlas.models import Symbol
from codeatlas.search.embeddings import SemanticIndex


def _reciprocal_rank_fusion(
    ranked_lists: list[list[str]],
    k: int = 60,
) -> list[str]:
    """Merge multiple ranked lists using reciprocal rank fusion.

    RRF score = sum(1 / (k + rank)) across all lists.
    """
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, item_id in enumerate(ranked):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank + 1)

    return sorted(scores, key=lambda x: scores[x], reverse=True)


class HybridSearch:
    """Combines FTS5 keyword search with FAISS semantic search."""

    def __init__(self, store: GraphStore, semantic_index: SemanticIndex) -> None:
        self._store = store
        self._semantic = semantic_index

    def search(self, query: str, limit: int = 20) -> list[Symbol]:
        """Run hybrid search: FTS5 + FAISS, merged with reciprocal rank fusion."""
        # FTS5 keyword results
        fts_results = self._store.search(query, limit=limit * 2)
        fts_ids = [s.id for s in fts_results]

        # FAISS semantic results
        semantic_results = self._semantic.search(query, self._store, limit=limit * 2)
        semantic_ids = [s.id for s, _ in semantic_results]

        # Merge using RRF
        merged_ids = _reciprocal_rank_fusion([fts_ids, semantic_ids])

        # Build a lookup from both result sets
        symbol_map: dict[str, Symbol] = {}
        for sym in fts_results:
            symbol_map[sym.id] = sym
        for sym, _ in semantic_results:
            symbol_map[sym.id] = sym

        results: list[Symbol] = []
        for sid in merged_ids[:limit]:
            if sid in symbol_map:
                results.append(symbol_map[sid])

        return results
