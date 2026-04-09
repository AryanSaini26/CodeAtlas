"""Semantic and hybrid search layer.

These modules require the 'search' extra: pip install codeatlas[search]
"""

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "SemanticIndex":
        from codeatlas.search.embeddings import SemanticIndex

        return SemanticIndex
    if name == "HybridSearch":
        from codeatlas.search.hybrid import HybridSearch

        return HybridSearch
    raise AttributeError(f"module 'codeatlas.search' has no attribute {name!r}")


__all__ = ["HybridSearch", "SemanticIndex"]
