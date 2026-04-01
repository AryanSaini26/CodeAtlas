"""Embedding pipeline using sentence-transformers and FAISS for semantic search."""

from __future__ import annotations

from pathlib import Path

import faiss
import numpy as np
from numpy.typing import NDArray

from codeatlas.graph.store import GraphStore
from codeatlas.models import Symbol

DEFAULT_MODEL = "all-MiniLM-L6-v2"


def _symbol_text(sym: Symbol) -> str:
    """Build a searchable text representation of a symbol."""
    parts = [sym.qualified_name.replace(".", " "), sym.kind.value]
    if sym.signature:
        parts.append(sym.signature)
    if sym.docstring:
        parts.append(sym.docstring)
    return " ".join(parts)


class SemanticIndex:
    """FAISS-backed semantic search over code symbols."""

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self._model_name = model_name
        self._model: object | None = None
        self._index: faiss.IndexFlatIP | None = None
        self._symbol_ids: list[str] = []
        self._dimension: int = 0

    def _get_model(self) -> object:
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def _encode(self, texts: list[str]) -> NDArray[np.float32]:
        model = self._get_model()
        embeddings: NDArray[np.float32] = model.encode(  # type: ignore[union-attr]
            texts, normalize_embeddings=True, show_progress_bar=False
        )
        return embeddings.astype(np.float32)

    def build_from_store(self, store: GraphStore) -> int:
        """Build the FAISS index from all symbols in the graph store."""
        conn = store._conn
        rows = conn.execute(
            "SELECT id, name, qualified_name, kind, file_path, "
            "start_line, start_col, end_line, end_col, "
            "docstring, signature, decorators, language FROM symbols"
        ).fetchall()

        if not rows:
            return 0

        symbols = [store._row_to_symbol(r) for r in rows]
        texts = [_symbol_text(s) for s in symbols]
        self._symbol_ids = [s.id for s in symbols]

        embeddings = self._encode(texts)
        self._dimension = embeddings.shape[1]

        self._index = faiss.IndexFlatIP(self._dimension)
        self._index.add(embeddings)

        return len(self._symbol_ids)

    def search(
        self, query: str, store: GraphStore, limit: int = 20
    ) -> list[tuple[Symbol, float]]:
        """Search for symbols similar to the query text.

        Returns list of (symbol, similarity_score) tuples.
        """
        if self._index is None or self._index.ntotal == 0:
            return []

        query_embedding = self._encode([query])
        scores, indices = self._index.search(query_embedding, min(limit, self._index.ntotal))

        results: list[tuple[Symbol, float]] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            symbol_id = self._symbol_ids[idx]
            symbols = store.find_symbols_by_name(
                symbol_id.split("::")[-1] if "::" in symbol_id else symbol_id
            )
            # Find exact match by ID
            for sym in symbols:
                if sym.id == symbol_id:
                    results.append((sym, float(score)))
                    break

        return results

    def save(self, path: Path) -> None:
        """Save the FAISS index and metadata to disk."""
        if self._index is None:
            return
        faiss.write_index(self._index, str(path / "codeatlas.faiss"))
        ids_path = path / "codeatlas_ids.txt"
        ids_path.write_text("\n".join(self._symbol_ids))

    def load(self, path: Path) -> bool:
        """Load a previously saved FAISS index."""
        index_path = path / "codeatlas.faiss"
        ids_path = path / "codeatlas_ids.txt"
        if not index_path.exists() or not ids_path.exists():
            return False

        self._index = faiss.read_index(str(index_path))
        self._symbol_ids = ids_path.read_text().strip().split("\n")
        self._dimension = self._index.d
        return True

    @property
    def size(self) -> int:
        return self._index.ntotal if self._index else 0
