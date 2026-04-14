"""Tests for the SQL tree-sitter parser."""

from pathlib import Path

import pytest

from codeatlas.models import RelationshipKind, SymbolKind
from codeatlas.parsers.sql_parser import SqlParser


def test_parse_file_returns_parse_result(sql_parser: SqlParser, sample_sql_path: Path) -> None:
    result = sql_parser.parse_file(sample_sql_path)
    assert result.file_info.path == str(sample_sql_path)
    assert len(result.symbols) > 0


def test_parse_source_returns_parse_result(sql_parser: SqlParser, sample_sql_source: str) -> None:
    result = sql_parser.parse_source(sample_sql_source, "test.sql")
    assert result.file_info.path == "test.sql"
    assert len(result.symbols) > 0


def test_file_info_language(sql_parser: SqlParser, sample_sql_source: str) -> None:
    result = sql_parser.parse_source(sample_sql_source, "test.sql")
    assert result.file_info.language == "sql"


def test_content_hash_consistent(sql_parser: SqlParser, sample_sql_source: str) -> None:
    r1 = sql_parser.parse_source(sample_sql_source, "test.sql")
    r2 = sql_parser.parse_source(sample_sql_source, "test.sql")
    assert r1.file_info.content_hash == r2.file_info.content_hash


def test_extracts_tables(sql_parser: SqlParser, sample_sql_source: str) -> None:
    result = sql_parser.parse_source(sample_sql_source, "test.sql")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    names = [s.name for s in classes]
    assert "users" in names
    assert "orders" in names


def test_extracts_views(sql_parser: SqlParser, sample_sql_source: str) -> None:
    result = sql_parser.parse_source(sample_sql_source, "test.sql")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    names = [s.name for s in classes]
    assert "active_users" in names
    assert "user_order_summary" in names


def test_extracts_functions(sql_parser: SqlParser, sample_sql_source: str) -> None:
    result = sql_parser.parse_source(sample_sql_source, "test.sql")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    names = [s.name for s in funcs]
    assert "get_user_name" in names


def test_table_signature_includes_columns(sql_parser: SqlParser) -> None:
    source = "CREATE TABLE products (id INTEGER, price REAL, name TEXT);"
    result = sql_parser.parse_source(source, "test.sql")
    tables = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    assert len(tables) == 1
    assert tables[0].signature is not None
    assert "id" in tables[0].signature
    assert "price" in tables[0].signature


def test_function_signature_present(sql_parser: SqlParser, sample_sql_source: str) -> None:
    result = sql_parser.parse_source(sample_sql_source, "test.sql")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    fn = next((f for f in funcs if f.name == "get_user_name"), None)
    assert fn is not None
    assert fn.signature is not None
    assert "get_user_name" in fn.signature


def test_view_calls_table(sql_parser: SqlParser, sample_sql_source: str) -> None:
    result = sql_parser.parse_source(sample_sql_source, "test.sql")
    calls = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    targets = [r.target_id for r in calls]
    # active_users VIEW references users table
    assert any("users" in t for t in targets)


def test_view_with_join_calls_both_tables(sql_parser: SqlParser, sample_sql_source: str) -> None:
    result = sql_parser.parse_source(sample_sql_source, "test.sql")
    calls = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    # user_order_summary joins users and orders
    sources = [r.source_id for r in calls]
    assert any("user_order_summary" in s for s in sources)


def test_supported_extensions(sql_parser: SqlParser) -> None:
    assert ".sql" in sql_parser.supported_extensions


def test_language_property(sql_parser: SqlParser) -> None:
    assert sql_parser.language == "sql"


def test_empty_file(sql_parser: SqlParser) -> None:
    result = sql_parser.parse_source("", "empty.sql")
    assert result.file_info.language == "sql"
    assert result.symbols == []
    assert result.relationships == []


def test_symbol_count_in_file_info(sql_parser: SqlParser, sample_sql_source: str) -> None:
    result = sql_parser.parse_source(sample_sql_source, "test.sql")
    assert result.file_info.symbol_count == len(result.symbols)
    assert result.file_info.relationship_count == len(result.relationships)


@pytest.mark.parametrize(
    "source,expected_kind",
    [
        ("CREATE TABLE foo (id INT);", SymbolKind.CLASS),
        ("CREATE VIEW bar AS SELECT 1;", SymbolKind.CLASS),
        (
            "CREATE FUNCTION baz() RETURNS INT AS $$ BEGIN RETURN 1; END; $$ LANGUAGE plpgsql;",
            SymbolKind.FUNCTION,
        ),
    ],
)
def test_symbol_kinds(sql_parser: SqlParser, source: str, expected_kind: SymbolKind) -> None:
    result = sql_parser.parse_source(source, "test.sql")
    kinds = [s.kind for s in result.symbols]
    assert expected_kind in kinds


def test_builtins_not_captured_as_calls(sql_parser: SqlParser) -> None:
    source = "CREATE VIEW v AS SELECT * FROM dual;"
    result = sql_parser.parse_source(source, "test.sql")
    calls = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    targets = [r.target_id for r in calls]
    assert not any("dual" in t for t in targets)
