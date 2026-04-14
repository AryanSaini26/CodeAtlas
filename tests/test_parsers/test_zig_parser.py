"""Tests for the Zig tree-sitter parser."""

from pathlib import Path

import pytest

from codeatlas.models import RelationshipKind, SymbolKind
from codeatlas.parsers.zig_parser import ZigParser


def test_parse_file_returns_parse_result(zig_parser: ZigParser, sample_zig_path: Path) -> None:
    result = zig_parser.parse_file(sample_zig_path)
    assert result.file_info.path == str(sample_zig_path)
    assert len(result.symbols) > 0


def test_parse_source_returns_parse_result(zig_parser: ZigParser, sample_zig_source: str) -> None:
    result = zig_parser.parse_source(sample_zig_source, "test.zig")
    assert result.file_info.path == "test.zig"
    assert len(result.symbols) > 0


def test_file_info_language(zig_parser: ZigParser, sample_zig_source: str) -> None:
    result = zig_parser.parse_source(sample_zig_source, "test.zig")
    assert result.file_info.language == "zig"


def test_content_hash_consistent(zig_parser: ZigParser, sample_zig_source: str) -> None:
    r1 = zig_parser.parse_source(sample_zig_source, "test.zig")
    r2 = zig_parser.parse_source(sample_zig_source, "test.zig")
    assert r1.file_info.content_hash == r2.file_info.content_hash


def test_extracts_functions(zig_parser: ZigParser, sample_zig_source: str) -> None:
    result = zig_parser.parse_source(sample_zig_source, "test.zig")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    names = [s.name for s in funcs]
    assert "add" in names
    assert "multiply" in names
    assert "compute" in names


def test_extracts_structs(zig_parser: ZigParser, sample_zig_source: str) -> None:
    result = zig_parser.parse_source(sample_zig_source, "test.zig")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    names = [s.name for s in classes]
    assert "Point" in names


def test_extracts_enums(zig_parser: ZigParser, sample_zig_source: str) -> None:
    result = zig_parser.parse_source(sample_zig_source, "test.zig")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    names = [s.name for s in classes]
    assert "Color" in names


def test_extracts_unions(zig_parser: ZigParser, sample_zig_source: str) -> None:
    result = zig_parser.parse_source(sample_zig_source, "test.zig")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    names = [s.name for s in classes]
    assert "Shape" in names


def test_extracts_imports(zig_parser: ZigParser, sample_zig_source: str) -> None:
    result = zig_parser.parse_source(sample_zig_source, "test.zig")
    imports = [s for s in result.symbols if s.kind == SymbolKind.IMPORT]
    names = [s.name for s in imports]
    assert "std" in names
    assert "math.zig" in names


def test_extracts_constants(zig_parser: ZigParser, sample_zig_source: str) -> None:
    result = zig_parser.parse_source(sample_zig_source, "test.zig")
    constants = [s for s in result.symbols if s.kind == SymbolKind.CONSTANT]
    names = [s.name for s in constants]
    assert "MAX_SIZE" in names


def test_calls_relationship(zig_parser: ZigParser, sample_zig_source: str) -> None:
    result = zig_parser.parse_source(sample_zig_source, "test.zig")
    calls = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    sources = [r.source_id for r in calls]
    assert any("compute" in s for s in sources)


def test_stdlib_not_in_calls(zig_parser: ZigParser) -> None:
    source = 'fn foo() void { std.debug.print("hi"); }'
    result = zig_parser.parse_source(source, "test.zig")
    calls = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    targets = [r.target_id for r in calls]
    assert not any("std" in t for t in targets)


def test_function_signature(zig_parser: ZigParser, sample_zig_source: str) -> None:
    result = zig_parser.parse_source(sample_zig_source, "test.zig")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    add_fn = next((f for f in funcs if f.name == "add"), None)
    assert add_fn is not None
    assert add_fn.signature is not None
    assert "add" in add_fn.signature


def test_supported_extensions(zig_parser: ZigParser) -> None:
    assert ".zig" in zig_parser.supported_extensions


def test_language_property(zig_parser: ZigParser) -> None:
    assert zig_parser.language == "zig"


def test_empty_file(zig_parser: ZigParser) -> None:
    result = zig_parser.parse_source("", "empty.zig")
    assert result.file_info.language == "zig"
    assert result.symbols == []
    assert result.relationships == []


def test_symbol_count_in_file_info(zig_parser: ZigParser, sample_zig_source: str) -> None:
    result = zig_parser.parse_source(sample_zig_source, "test.zig")
    assert result.file_info.symbol_count == len(result.symbols)
    assert result.file_info.relationship_count == len(result.relationships)


@pytest.mark.parametrize(
    "source,expected_kind",
    [
        ("pub fn foo(x: i32) i32 { return x; }", SymbolKind.FUNCTION),
        ("const MyStruct = struct { x: i32 };", SymbolKind.CLASS),
        ("const MyEnum = enum { A, B };", SymbolKind.CLASS),
        ('const std = @import("std");', SymbolKind.IMPORT),
    ],
)
def test_symbol_kinds(zig_parser: ZigParser, source: str, expected_kind: SymbolKind) -> None:
    result = zig_parser.parse_source(source, "test.zig")
    kinds = [s.kind for s in result.symbols]
    assert expected_kind in kinds
