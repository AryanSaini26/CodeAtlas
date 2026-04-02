"""Tests for the semantic embedding search."""

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


def _sym(
    name: str,
    kind: SymbolKind = SymbolKind.FUNCTION,
    fp: str = "app.py",
    docstring: str | None = None,
    signature: str | None = None,
) -> Symbol:
    return Symbol(
        id=f"{fp}::{name}",
        name=name,
        qualified_name=name,
        kind=kind,
        file_path=fp,
        span=Span(start=Position(line=0, column=0), end=Position(line=5, column=0)),
        docstring=docstring,
        signature=signature,
        language="python",
    )


def _result(fp: str, syms: list[Symbol]) -> ParseResult:
    return ParseResult(
        file_info=FileInfo(path=fp, language="python", content_hash="abc", symbol_count=len(syms)),
        symbols=syms,
    )


@pytest.fixture
def store_with_symbols() -> GraphStore:
    store = GraphStore(":memory:")
    store.upsert_parse_result(
        _result(
            "auth.py",
            [
                _sym(
                    "authenticate_user",
                    fp="auth.py",
                    docstring="Verify user credentials against the database",
                    signature="def authenticate_user(username, password)",
                ),
                _sym(
                    "hash_password",
                    fp="auth.py",
                    docstring="Hash a password using bcrypt",
                    signature="def hash_password(raw_password)",
                ),
            ],
        )
    )
    store.upsert_parse_result(
        _result(
            "db.py",
            [
                _sym(
                    "connect_database",
                    fp="db.py",
                    docstring="Open a connection to the PostgreSQL database",
                    signature="def connect_database(url)",
                ),
                _sym(
                    "run_migration",
                    fp="db.py",
                    docstring="Run database schema migrations",
                    signature="def run_migration(version)",
                ),
            ],
        )
    )
    store.upsert_parse_result(
        _result(
            "api.py",
            [
                _sym(
                    "handle_request",
                    fp="api.py",
                    docstring="Process an incoming HTTP request",
                    signature="def handle_request(req)",
                ),
                _sym(
                    "format_response",
                    fp="api.py",
                    docstring="Format the API response as JSON",
                    signature="def format_response(data)",
                ),
            ],
        )
    )
    return store


def test_build_from_store(store_with_symbols: GraphStore) -> None:
    index = SemanticIndex()
    count = index.build_from_store(store_with_symbols)
    assert count == 6
    assert index.size == 6


def test_search_returns_results(store_with_symbols: GraphStore) -> None:
    index = SemanticIndex()
    index.build_from_store(store_with_symbols)

    results = index.search("authentication login", store_with_symbols, limit=3)
    assert len(results) > 0
    names = [s.name for s, _ in results]
    assert "authenticate_user" in names


def test_search_database_query(store_with_symbols: GraphStore) -> None:
    index = SemanticIndex()
    index.build_from_store(store_with_symbols)

    results = index.search("database connection setup", store_with_symbols, limit=3)
    assert len(results) > 0
    names = [s.name for s, _ in results]
    assert "connect_database" in names


def test_search_returns_scores(store_with_symbols: GraphStore) -> None:
    index = SemanticIndex()
    index.build_from_store(store_with_symbols)

    results = index.search("password hashing", store_with_symbols, limit=3)
    for sym, score in results:
        assert isinstance(score, float)
        assert score > 0


def test_search_empty_index(store_with_symbols: GraphStore) -> None:
    index = SemanticIndex()
    results = index.search("anything", store_with_symbols)
    assert results == []


def test_save_and_load(store_with_symbols: GraphStore, tmp_path: object) -> None:
    from pathlib import Path

    save_dir = Path(str(tmp_path))

    index = SemanticIndex()
    index.build_from_store(store_with_symbols)
    index.save(save_dir)

    loaded = SemanticIndex()
    assert loaded.load(save_dir)
    assert loaded.size == 6

    # Verify search still works after load
    results = loaded.search("authentication", store_with_symbols, limit=3)
    assert len(results) > 0


def test_build_empty_store() -> None:
    store = GraphStore(":memory:")
    index = SemanticIndex()
    count = index.build_from_store(store)
    assert count == 0
    assert index.size == 0
