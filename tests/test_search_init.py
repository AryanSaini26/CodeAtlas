"""Tests for codeatlas.search lazy-import __init__."""

import pytest


def test_semantic_index_lazy_import() -> None:
    """SemanticIndex is accessible via the search package."""
    import codeatlas.search as search_pkg

    cls = search_pkg.SemanticIndex  # triggers __getattr__
    from codeatlas.search.embeddings import SemanticIndex

    assert cls is SemanticIndex


def test_hybrid_search_lazy_import() -> None:
    """HybridSearch is accessible via the search package."""
    import codeatlas.search as search_pkg

    cls = search_pkg.HybridSearch  # triggers __getattr__
    from codeatlas.search.hybrid import HybridSearch

    assert cls is HybridSearch


def test_unknown_attribute_raises() -> None:
    """Accessing an unknown attribute raises AttributeError."""
    import codeatlas.search as search_pkg

    with pytest.raises(AttributeError, match="no attribute"):
        _ = search_pkg.NonExistent  # type: ignore[attr-defined]


def test_all_exports() -> None:
    """__all__ lists the expected names."""
    import codeatlas.search as search_pkg

    assert "SemanticIndex" in search_pkg.__all__
    assert "HybridSearch" in search_pkg.__all__


def test_getattr_returns_correct_type_for_semantic() -> None:
    """__getattr__ for SemanticIndex returns a class."""
    import codeatlas.search as search_pkg

    cls = search_pkg.__getattr__("SemanticIndex")
    assert isinstance(cls, type)


def test_getattr_returns_correct_type_for_hybrid() -> None:
    """__getattr__ for HybridSearch returns a class."""
    import codeatlas.search as search_pkg

    cls = search_pkg.__getattr__("HybridSearch")
    assert isinstance(cls, type)


def test_getattr_raises_for_unknown() -> None:
    """__getattr__ with unknown name raises AttributeError."""
    import codeatlas.search as search_pkg

    with pytest.raises(AttributeError):
        search_pkg.__getattr__("UnknownClass")
