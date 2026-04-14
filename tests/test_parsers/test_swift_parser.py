"""Tests for the Swift tree-sitter parser."""

from pathlib import Path

import pytest

from codeatlas.models import RelationshipKind, SymbolKind
from codeatlas.parsers.swift_parser import SwiftParser


def test_parse_file_returns_parse_result(
    swift_parser: SwiftParser, sample_swift_path: Path
) -> None:
    result = swift_parser.parse_file(sample_swift_path)
    assert result.file_info.path == str(sample_swift_path)
    assert len(result.symbols) > 0


def test_parse_source_returns_parse_result(
    swift_parser: SwiftParser, sample_swift_source: str
) -> None:
    result = swift_parser.parse_source(sample_swift_source, "test.swift")
    assert result.file_info.path == "test.swift"
    assert len(result.symbols) > 0


def test_file_info_language(swift_parser: SwiftParser, sample_swift_source: str) -> None:
    result = swift_parser.parse_source(sample_swift_source, "test.swift")
    assert result.file_info.language == "swift"


def test_content_hash_consistent(swift_parser: SwiftParser, sample_swift_source: str) -> None:
    r1 = swift_parser.parse_source(sample_swift_source, "test.swift")
    r2 = swift_parser.parse_source(sample_swift_source, "test.swift")
    assert r1.file_info.content_hash == r2.file_info.content_hash


def test_extracts_import(swift_parser: SwiftParser, sample_swift_source: str) -> None:
    result = swift_parser.parse_source(sample_swift_source, "test.swift")
    imports = [s for s in result.symbols if s.kind == SymbolKind.IMPORT]
    assert len(imports) >= 1
    names = [s.name for s in imports]
    assert "Foundation" in names


def test_extracts_protocol_as_interface(
    swift_parser: SwiftParser, sample_swift_source: str
) -> None:
    result = swift_parser.parse_source(sample_swift_source, "test.swift")
    interfaces = [s for s in result.symbols if s.kind == SymbolKind.INTERFACE]
    assert len(interfaces) >= 1
    names = [s.name for s in interfaces]
    assert "Drawable" in names


def test_extracts_classes(swift_parser: SwiftParser, sample_swift_source: str) -> None:
    result = swift_parser.parse_source(sample_swift_source, "test.swift")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    assert len(classes) >= 2
    names = [s.name for s in classes]
    assert "Shape" in names
    assert "Circle" in names


def test_extracts_methods(swift_parser: SwiftParser, sample_swift_source: str) -> None:
    result = swift_parser.parse_source(sample_swift_source, "test.swift")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    assert len(methods) >= 2
    names = [s.name for s in methods]
    assert "draw" in names


def test_extracts_top_level_functions(swift_parser: SwiftParser, sample_swift_source: str) -> None:
    result = swift_parser.parse_source(sample_swift_source, "test.swift")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    names = [s.name for s in funcs]
    assert "greet" in names
    assert "add" in names


def test_extracts_typealias(swift_parser: SwiftParser, sample_swift_source: str) -> None:
    result = swift_parser.parse_source(sample_swift_source, "test.swift")
    aliases = [s for s in result.symbols if s.kind == SymbolKind.TYPE_ALIAS]
    assert len(aliases) >= 1
    assert any(s.name == "Completion" for s in aliases)


def test_method_qualified_name_includes_class(
    swift_parser: SwiftParser, sample_swift_source: str
) -> None:
    result = swift_parser.parse_source(sample_swift_source, "test.swift")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    qnames = [s.qualified_name for s in methods]
    assert any("Shape." in qn for qn in qnames)


def test_method_signature(swift_parser: SwiftParser) -> None:
    source = "func greet(name: String, age: Int) -> String { return name }\n"
    result = swift_parser.parse_source(source, "test.swift")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert len(funcs) == 1
    assert funcs[0].signature is not None
    assert "greet" in funcs[0].signature
    assert "name" in funcs[0].signature


def test_docstring_extraction(swift_parser: SwiftParser, sample_swift_source: str) -> None:
    result = swift_parser.parse_source(sample_swift_source, "test.swift")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    shape = next((c for c in classes if c.name == "Shape"), None)
    assert shape is not None
    assert shape.docstring is not None


def test_inherits_relationship(swift_parser: SwiftParser, sample_swift_source: str) -> None:
    result = swift_parser.parse_source(sample_swift_source, "test.swift")
    inherits = [r for r in result.relationships if r.kind == RelationshipKind.INHERITS]
    assert len(inherits) >= 1
    sources = [r.source_id for r in inherits]
    assert any("Circle" in s for s in sources)


def test_imports_relationship(swift_parser: SwiftParser, sample_swift_source: str) -> None:
    result = swift_parser.parse_source(sample_swift_source, "test.swift")
    import_rels = [r for r in result.relationships if r.kind == RelationshipKind.IMPORTS]
    assert len(import_rels) >= 1
    targets = [r.target_id for r in import_rels]
    assert any("Foundation" in t for t in targets)


def test_calls_relationship(swift_parser: SwiftParser, sample_swift_source: str) -> None:
    result = swift_parser.parse_source(sample_swift_source, "test.swift")
    calls = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    assert len(calls) >= 1


def test_supported_extensions(swift_parser: SwiftParser) -> None:
    assert ".swift" in swift_parser.supported_extensions


def test_language_property(swift_parser: SwiftParser) -> None:
    assert swift_parser.language == "swift"


def test_empty_file(swift_parser: SwiftParser) -> None:
    result = swift_parser.parse_source("", "empty.swift")
    assert result.file_info.language == "swift"
    assert result.symbols == []
    assert result.relationships == []


def test_symbol_count_in_file_info(swift_parser: SwiftParser, sample_swift_source: str) -> None:
    result = swift_parser.parse_source(sample_swift_source, "test.swift")
    assert result.file_info.symbol_count == len(result.symbols)
    assert result.file_info.relationship_count == len(result.relationships)


@pytest.mark.parametrize(
    "source,expected_kind",
    [
        ("class Foo {}\n", SymbolKind.CLASS),
        ("protocol Bar {}\n", SymbolKind.INTERFACE),
        ("func baz() {}\n", SymbolKind.FUNCTION),
        ("typealias MyInt = Int\n", SymbolKind.TYPE_ALIAS),
        ("import Foundation\n", SymbolKind.IMPORT),
    ],
)
def test_symbol_kinds(swift_parser: SwiftParser, source: str, expected_kind: SymbolKind) -> None:
    result = swift_parser.parse_source(source, "test.swift")
    kinds = [s.kind for s in result.symbols]
    assert expected_kind in kinds
