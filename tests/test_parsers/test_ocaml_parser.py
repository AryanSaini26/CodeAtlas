"""Tests for the OCaml tree-sitter parser."""

from pathlib import Path

import pytest

from codeatlas.models import RelationshipKind, SymbolKind
from codeatlas.parsers.ocaml_parser import OCamlParser


def test_parse_file_returns_parse_result(
    ocaml_parser: OCamlParser, sample_ocaml_path: Path
) -> None:
    result = ocaml_parser.parse_file(sample_ocaml_path)
    assert result.file_info.path == str(sample_ocaml_path)
    assert len(result.symbols) > 0


def test_parse_source_returns_parse_result(
    ocaml_parser: OCamlParser, sample_ocaml_source: str
) -> None:
    result = ocaml_parser.parse_source(sample_ocaml_source, "test.ml")
    assert result.file_info.path == "test.ml"
    assert len(result.symbols) > 0


def test_file_info_language(ocaml_parser: OCamlParser, sample_ocaml_source: str) -> None:
    result = ocaml_parser.parse_source(sample_ocaml_source, "test.ml")
    assert result.file_info.language == "ocaml"


def test_content_hash_consistent(ocaml_parser: OCamlParser, sample_ocaml_source: str) -> None:
    r1 = ocaml_parser.parse_source(sample_ocaml_source, "test.ml")
    r2 = ocaml_parser.parse_source(sample_ocaml_source, "test.ml")
    assert r1.file_info.content_hash == r2.file_info.content_hash


def test_extracts_functions(ocaml_parser: OCamlParser, sample_ocaml_source: str) -> None:
    result = ocaml_parser.parse_source(sample_ocaml_source, "test.ml")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    names = [s.name for s in funcs]
    assert "add" in names
    assert "factorial" in names
    assert "greet" in names


def test_extracts_types(ocaml_parser: OCamlParser, sample_ocaml_source: str) -> None:
    result = ocaml_parser.parse_source(sample_ocaml_source, "test.ml")
    types = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    names = [s.name for s in types]
    assert "color" in names
    assert "point" in names


def test_extracts_module(ocaml_parser: OCamlParser, sample_ocaml_source: str) -> None:
    result = ocaml_parser.parse_source(sample_ocaml_source, "test.ml")
    modules = [s for s in result.symbols if s.kind == SymbolKind.MODULE]
    names = [s.name for s in modules]
    assert "Math" in names


def test_module_methods_extracted(ocaml_parser: OCamlParser, sample_ocaml_source: str) -> None:
    result = ocaml_parser.parse_source(sample_ocaml_source, "test.ml")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    qualified = [s.qualified_name for s in methods]
    assert any("Math.add" in q for q in qualified)
    assert any("Math.multiply" in q for q in qualified)


def test_extracts_open_imports(ocaml_parser: OCamlParser, sample_ocaml_source: str) -> None:
    result = ocaml_parser.parse_source(sample_ocaml_source, "test.ml")
    imports = [s for s in result.symbols if s.kind == SymbolKind.IMPORT]
    names = [s.name for s in imports]
    assert "Printf" in names


def test_calls_relationship(ocaml_parser: OCamlParser, sample_ocaml_source: str) -> None:
    result = ocaml_parser.parse_source(sample_ocaml_source, "test.ml")
    calls = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    assert len(calls) > 0


def test_recursive_call_captured(ocaml_parser: OCamlParser, sample_ocaml_source: str) -> None:
    result = ocaml_parser.parse_source(sample_ocaml_source, "test.ml")
    calls = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    targets = [r.target_id for r in calls]
    assert any("factorial" in t for t in targets)


def test_function_signature(ocaml_parser: OCamlParser, sample_ocaml_source: str) -> None:
    result = ocaml_parser.parse_source(sample_ocaml_source, "test.ml")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    add_fn = next((f for f in funcs if f.name == "add"), None)
    assert add_fn is not None
    assert add_fn.signature is not None
    assert "add" in add_fn.signature


def test_supported_extensions(ocaml_parser: OCamlParser) -> None:
    assert ".ml" in ocaml_parser.supported_extensions
    assert ".mli" in ocaml_parser.supported_extensions


def test_language_property(ocaml_parser: OCamlParser) -> None:
    assert ocaml_parser.language == "ocaml"


def test_empty_file(ocaml_parser: OCamlParser) -> None:
    result = ocaml_parser.parse_source("", "empty.ml")
    assert result.file_info.language == "ocaml"
    assert result.symbols == []
    assert result.relationships == []


def test_symbol_count_in_file_info(ocaml_parser: OCamlParser, sample_ocaml_source: str) -> None:
    result = ocaml_parser.parse_source(sample_ocaml_source, "test.ml")
    assert result.file_info.symbol_count == len(result.symbols)
    assert result.file_info.relationship_count == len(result.relationships)


@pytest.mark.parametrize(
    "source,expected_kind",
    [
        ("let foo x = x + 1", SymbolKind.FUNCTION),
        ("type color = Red | Green", SymbolKind.CLASS),
        ("open Printf", SymbolKind.IMPORT),
    ],
)
def test_symbol_kinds(ocaml_parser: OCamlParser, source: str, expected_kind: SymbolKind) -> None:
    result = ocaml_parser.parse_source(source, "test.ml")
    kinds = [s.kind for s in result.symbols]
    assert expected_kind in kinds
