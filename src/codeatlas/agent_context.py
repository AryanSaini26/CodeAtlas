"""Agent-ready context packs over the CodeAtlas graph.

The goal of a context pack is not to dump the whole graph. It is a compact,
ranked bundle an AI coding agent can use immediately: matching symbols,
nearby dependency context, and file-level summaries with a token budget.
"""

from __future__ import annotations

from typing import Any

from codeatlas.graph.store import GraphStore
from codeatlas.models import Relationship, Symbol


def estimate_tokens(text: str) -> int:
    """Cheap deterministic token estimate used for budget trimming."""
    return max(1, (len(text) + 3) // 4)


def _symbol_payload(sym: Symbol) -> dict[str, Any]:
    return {
        "id": sym.id,
        "name": sym.name,
        "qualified_name": sym.qualified_name,
        "kind": sym.kind.value,
        "file": sym.file_path,
        "line": sym.span.start.line + 1,
        "end_line": sym.span.end.line + 1,
        "language": sym.language,
        "signature": sym.signature,
        "docstring": sym.docstring,
        "is_test": sym.is_test,
    }


def _relationship_refs(
    store: GraphStore, rels: list[Relationship], *, attr: str
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for rel in rels:
        other_id = getattr(rel, attr)
        other = store.get_symbol_by_id(other_id)
        refs.append(
            {
                "symbol_id": other_id,
                "qualified_name": other.qualified_name if other else other_id,
                "kind": other.kind.value if other else "external",
                "file": other.file_path if other else rel.file_path,
                "line": other.span.start.line + 1 if other else None,
                "relationship": rel.kind.value,
                "confidence": rel.confidence.value,
            }
        )
    return refs


def _score_symbol(sym: Symbol, query: str, pagerank: dict[str, float]) -> float:
    q = query.lower().strip()
    haystacks = [sym.name.lower(), sym.qualified_name.lower(), sym.file_path.lower()]
    score = 0.0
    if any(h == q for h in haystacks):
        score += 100.0
    elif any(h.startswith(q) for h in haystacks):
        score += 70.0
    elif any(q in h for h in haystacks):
        score += 45.0
    if sym.docstring and q in sym.docstring.lower():
        score += 12.0
    if sym.signature and q in sym.signature.lower():
        score += 8.0
    score += pagerank.get(sym.id, 0.0) * 100.0
    return round(score, 6)


def build_context_pack(
    store: GraphStore,
    query: str,
    *,
    budget_tokens: int = 2000,
    limit: int = 10,
    relation_limit: int = 6,
) -> dict[str, Any]:
    """Build a deterministic, token-budgeted context pack for an agent."""
    if budget_tokens < 128:
        raise ValueError("budget_tokens must be at least 128")
    if limit < 1:
        raise ValueError("limit must be at least 1")

    candidates = store.search(query, limit=max(limit * 3, 20))
    seen = {sym.id for sym in candidates}
    for sym in store.find_symbols_by_name(query):
        if sym.id not in seen:
            candidates.append(sym)
            seen.add(sym.id)

    pagerank = store.compute_pagerank()
    ranked = sorted(
        candidates,
        key=lambda sym: (-_score_symbol(sym, query, pagerank), sym.file_path, sym.span.start.line),
    )

    selected: list[dict[str, Any]] = []
    selected_files: set[str] = set()
    estimated_tokens = estimate_tokens(query)
    baseline_tokens = 0

    for sym in ranked:
        outgoing = store.get_dependencies(sym.id)[:relation_limit]
        incoming = store.get_dependents(sym.id)[:relation_limit]
        entry = {
            "score": _score_symbol(sym, query, pagerank),
            "symbol": _symbol_payload(sym),
            "relationships": {
                "outgoing": _relationship_refs(store, outgoing, attr="target_id"),
                "incoming": _relationship_refs(store, incoming, attr="source_id"),
                "outgoing_count": len(store.get_dependencies(sym.id)),
                "incoming_count": len(store.get_dependents(sym.id)),
            },
        }
        entry_tokens = estimate_tokens(str(entry))
        baseline_tokens += entry_tokens
        if selected and estimated_tokens + entry_tokens > budget_tokens:
            continue
        selected.append(entry)
        selected_files.add(sym.file_path)
        estimated_tokens += entry_tokens
        if len(selected) >= limit:
            break

    file_summaries = []
    for file_path in sorted(selected_files):
        symbols = store.get_symbols_in_file(file_path)
        payload = {
            "file": file_path,
            "symbol_count": len(symbols),
            "symbols": [
                {
                    "name": sym.name,
                    "qualified_name": sym.qualified_name,
                    "kind": sym.kind.value,
                    "line": sym.span.start.line + 1,
                }
                for sym in symbols[:25]
            ],
        }
        tokens = estimate_tokens(str(payload))
        if estimated_tokens + tokens <= budget_tokens:
            file_summaries.append(payload)
            estimated_tokens += tokens

    baseline_tokens = max(baseline_tokens, estimated_tokens)
    savings = 0.0 if baseline_tokens == 0 else 1.0 - (estimated_tokens / baseline_tokens)
    return {
        "query": query,
        "budget_tokens": budget_tokens,
        "estimated_tokens": estimated_tokens,
        "context_savings": round(max(0.0, savings), 4),
        "result_count": len(selected),
        "results": selected,
        "file_summaries": file_summaries,
    }
