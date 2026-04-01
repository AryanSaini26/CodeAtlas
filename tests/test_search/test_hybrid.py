"""Tests for hybrid search."""

import pytest

from codeatlas.graph.store import GraphStore
from codeatlas.models import (
    FileInfo,
    ParseResult,
    Position,
    Span,
    Symbol,
    SymbolKind,
)
from codeatlas.search.embeddings import SemanticIndex
from codeatlas.search.hybrid import HybridSearch


def _sym(
    name: str,
    docstring: str | None = None,
    fp: str = "app.py",
) -> Symbol:
    return Symbol(
        id=f"{fp}::{name}",
        name=name,
        qualified_name=name,
        kind=SymbolKind.FUNCTION,
        file_path=fp,
        span=Span(start=Position(line=0, column=0), end=Position(line=5, column=0)),
        docstring=docstring,
        signature=f"def {name}()",
        language="python",
    )


def _result(fp: str, syms: list[Symbol]) -> ParseResult:
    return ParseResult(
        file_info=FileInfo(path=fp, language="python", content_hash="abc", symbol_count=len(syms)),
        symbols=syms,
    )


@pytest.fixture
def hybrid_setup() -> tuple[HybridSearch, GraphStore]:
    store = GraphStore(":memory:")
    store.upsert_parse_result(_result("app.py", [
        _sym("create_user", docstring="Create a new user in the system"),
        _sym("delete_user", docstring="Remove a user from the database"),
        _sym("validate_email", docstring="Check if an email address is valid"),
        _sym("send_notification", docstring="Send a push notification to the user"),
    ]))

    sem = SemanticIndex()
    sem.build_from_store(store)

    return HybridSearch(store, sem), store


def test_hybrid_returns_results(hybrid_setup: tuple[HybridSearch, GraphStore]) -> None:
    searcher, _ = hybrid_setup
    results = searcher.search("user creation")
    assert len(results) > 0


def test_hybrid_ranks_relevant_first(hybrid_setup: tuple[HybridSearch, GraphStore]) -> None:
    searcher, _ = hybrid_setup
    results = searcher.search("create_user")
    assert len(results) > 0
    assert results[0].name == "create_user"


def test_hybrid_respects_limit(hybrid_setup: tuple[HybridSearch, GraphStore]) -> None:
    searcher, _ = hybrid_setup
    results = searcher.search("user", limit=2)
    assert len(results) <= 2
