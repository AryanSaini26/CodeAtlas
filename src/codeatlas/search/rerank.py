"""Cross-encoder reranking — the precise second stage of two-stage retrieval.

Stage 1 (recall) is hybrid FTS5 + FAISS fusion; stage 2 (precision) re-scores the
top candidates with a cross-encoder that reads the (query, symbol) pair jointly,
which is more accurate than the bi-encoder cosine used for recall. This is the
2026 production-RAG pattern. sentence-transformers is imported lazily so the core
package stays importable without the ``search`` extra.
"""

from __future__ import annotations

from typing import Any

from codeatlas.models import Symbol

DEFAULT_CROSS_ENCODER = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def _symbol_text(sym: Symbol) -> str:
    """Compact text used as the document side of the (query, doc) pair."""
    parts = [sym.qualified_name.replace(".", " "), sym.kind.value]
    if sym.signature:
        parts.append(sym.signature)
    if sym.docstring:
        parts.append(sym.docstring)
    return " ".join(parts)


class CrossEncoderReranker:
    """Re-orders recall candidates by joint (query, symbol) relevance."""

    def __init__(self, model_name: str = DEFAULT_CROSS_ENCODER) -> None:
        self._model_name = model_name
        self._model: Any = None

    def _get_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self._model_name)
        return self._model

    def rerank(
        self,
        query: str,
        symbols: list[Symbol],
        *,
        limit: int | None = None,
    ) -> list[Symbol]:
        """Return ``symbols`` reordered by descending cross-encoder score."""
        if not symbols:
            return []
        model = self._get_model()
        scores = model.predict([(query, _symbol_text(sym)) for sym in symbols])
        ranked = [
            sym
            for sym, _ in sorted(
                zip(symbols, scores, strict=False),
                key=lambda pair: float(pair[1]),
                reverse=True,
            )
        ]
        return ranked[:limit] if limit is not None else ranked
