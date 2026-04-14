"""Tests for the C tree-sitter parser."""

from pathlib import Path

import pytest

from codeatlas.models import RelationshipKind, SymbolKind
from codeatlas.parsers.c_parser import CParser


def test_parse_file_returns_parse_result(c_parser: CParser, sample_c_path: Path) -> None:
    result = c_parser.parse_file(sample_c_path)
    assert result.file_info.path == str(sample_c_path)
    assert len(result.symbols) > 0


def test_parse_source_returns_parse_result(c_parser: CParser, sample_c_source: str) -> None:
    result = c_parser.parse_source(sample_c_source, "test.c")
    assert result.file_info.path == "test.c"
    assert len(result.symbols) > 0


def test_file_info_language(c_parser: CParser, sample_c_source: str) -> None:
    result = c_parser.parse_source(sample_c_source, "test.c")
    assert result.file_info.language == "c"


def test_content_hash_consistent(c_parser: CParser, sample_c_source: str) -> None:
    r1 = c_parser.parse_source(sample_c_source, "test.c")
    r2 = c_parser.parse_source(sample_c_source, "test.c")
    assert r1.file_info.content_hash == r2.file_info.content_hash


def test_extracts_functions(c_parser: CParser, sample_c_source: str) -> None:
    result = c_parser.parse_source(sample_c_source, "test.c")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    names = [s.name for s in funcs]
    assert "add" in names
    assert "multiply" in names
    assert "compute" in names


def test_extracts_structs(c_parser: CParser, sample_c_source: str) -> None:
    result = c_parser.parse_source(sample_c_source, "test.c")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    names = [s.name for s in classes]
    assert "Point" in names


def test_extracts_enums(c_parser: CParser, sample_c_source: str) -> None:
    result = c_parser.parse_source(sample_c_source, "test.c")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    names = [s.name for s in classes]
    assert "Color" in names


def test_extracts_type_alias(c_parser: CParser, sample_c_source: str) -> None:
    result = c_parser.parse_source(sample_c_source, "test.c")
    aliases = [s for s in result.symbols if s.kind == SymbolKind.TYPE_ALIAS]
    names = [s.name for s in aliases]
    assert "BinaryOp" in names


def test_extracts_includes(c_parser: CParser, sample_c_source: str) -> None:
    result = c_parser.parse_source(sample_c_source, "test.c")
    imports = [s for s in result.symbols if s.kind == SymbolKind.IMPORT]
    names = [s.name for s in imports]
    assert "stdio.h" in names
    assert "stdlib.h" in names
    assert "utils.h" in names


def test_include_relationship(c_parser: CParser, sample_c_source: str) -> None:
    result = c_parser.parse_source(sample_c_source, "test.c")
    imports = [r for r in result.relationships if r.kind == RelationshipKind.IMPORTS]
    assert len(imports) >= 3


def test_calls_relationship(c_parser: CParser, sample_c_source: str) -> None:
    result = c_parser.parse_source(sample_c_source, "test.c")
    calls = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    sources = [r.source_id for r in calls]
    assert any("compute" in s for s in sources)


def test_stdlib_calls_excluded(c_parser: CParser, sample_c_source: str) -> None:
    result = c_parser.parse_source(sample_c_source, "test.c")
    calls = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    targets = [r.target_id for r in calls]
    assert not any("printf" in t for t in targets)


def test_function_signature(c_parser: CParser, sample_c_source: str) -> None:
    result = c_parser.parse_source(sample_c_source, "test.c")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    add_fn = next((f for f in funcs if f.name == "add"), None)
    assert add_fn is not None
    assert add_fn.signature is not None
    assert "add" in add_fn.signature


def test_supported_extensions(c_parser: CParser) -> None:
    assert ".c" in c_parser.supported_extensions


def test_language_property(c_parser: CParser) -> None:
    assert c_parser.language == "c"


def test_empty_file(c_parser: CParser) -> None:
    result = c_parser.parse_source("", "empty.c")
    assert result.file_info.language == "c"
    assert result.symbols == []
    assert result.relationships == []


def test_symbol_count_in_file_info(c_parser: CParser, sample_c_source: str) -> None:
    result = c_parser.parse_source(sample_c_source, "test.c")
    assert result.file_info.symbol_count == len(result.symbols)
    assert result.file_info.relationship_count == len(result.relationships)


@pytest.mark.parametrize(
    "source,expected_kind",
    [
        ("int foo(int x) { return x; }", SymbolKind.FUNCTION),
        ("typedef struct { int a; } MyStruct;", SymbolKind.CLASS),
        ("typedef enum { A, B } MyEnum;", SymbolKind.CLASS),
        ("typedef int (*FnPtr)(int);", SymbolKind.TYPE_ALIAS),
    ],
)
def test_symbol_kinds(c_parser: CParser, source: str, expected_kind: SymbolKind) -> None:
    result = c_parser.parse_source(source, "test.c")
    kinds = [s.kind for s in result.symbols]
    assert expected_kind in kinds
