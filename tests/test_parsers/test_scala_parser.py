"""Tests for the Scala tree-sitter parser."""

from pathlib import Path

import pytest

from codeatlas.models import SymbolKind
from codeatlas.parsers.scala_parser import ScalaParser


def test_parse_file_returns_parse_result(
    scala_parser: ScalaParser, sample_scala_path: Path
) -> None:
    result = scala_parser.parse_file(sample_scala_path)
    assert result.file_info.path == str(sample_scala_path)
    assert len(result.symbols) > 0


def test_parse_source_returns_parse_result(
    scala_parser: ScalaParser, sample_scala_source: str
) -> None:
    result = scala_parser.parse_source(sample_scala_source, "test.scala")
    assert result.file_info.path == "test.scala"
    assert len(result.symbols) > 0


def test_file_info_language(scala_parser: ScalaParser, sample_scala_source: str) -> None:
    result = scala_parser.parse_source(sample_scala_source, "test.scala")
    assert result.file_info.language == "scala"


def test_content_hash_consistent(scala_parser: ScalaParser, sample_scala_source: str) -> None:
    r1 = scala_parser.parse_source(sample_scala_source, "test.scala")
    r2 = scala_parser.parse_source(sample_scala_source, "test.scala")
    assert r1.file_info.content_hash == r2.file_info.content_hash


def test_extracts_import(scala_parser: ScalaParser, sample_scala_source: str) -> None:
    result = scala_parser.parse_source(sample_scala_source, "test.scala")
    imports = [s for s in result.symbols if s.kind == SymbolKind.IMPORT]
    assert len(imports) >= 1
    names = [s.qualified_name for s in imports]
    assert any("scala" in n for n in names)


def test_extracts_val_as_variable(scala_parser: ScalaParser, sample_scala_source: str) -> None:
    result = scala_parser.parse_source(sample_scala_source, "test.scala")
    variables = [s for s in result.symbols if s.kind == SymbolKind.VARIABLE]
    names = [s.name for s in variables]
    assert "MAX_SIZE" in names


def test_extracts_trait_as_interface(scala_parser: ScalaParser, sample_scala_source: str) -> None:
    result = scala_parser.parse_source(sample_scala_source, "test.scala")
    interfaces = [s for s in result.symbols if s.kind == SymbolKind.INTERFACE]
    assert len(interfaces) >= 1
    names = [s.name for s in interfaces]
    assert "Greeter" in names


def test_extracts_class(scala_parser: ScalaParser, sample_scala_source: str) -> None:
    result = scala_parser.parse_source(sample_scala_source, "test.scala")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    names = [s.name for s in classes]
    assert "UserService" in names
    assert "AdminService" in names


def test_extracts_object_as_class(scala_parser: ScalaParser, sample_scala_source: str) -> None:
    result = scala_parser.parse_source(sample_scala_source, "test.scala")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    names = [s.name for s in classes]
    assert "Config" in names


def test_extracts_methods(scala_parser: ScalaParser, sample_scala_source: str) -> None:
    result = scala_parser.parse_source(sample_scala_source, "test.scala")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    names = [s.name for s in methods]
    assert "createUser" in names
    assert "greet" in names


def test_extracts_toplevel_function(scala_parser: ScalaParser, sample_scala_source: str) -> None:
    result = scala_parser.parse_source(sample_scala_source, "test.scala")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert any(s.name == "processAll" for s in funcs)


def test_method_qualified_name_includes_class(
    scala_parser: ScalaParser, sample_scala_source: str
) -> None:
    result = scala_parser.parse_source(sample_scala_source, "test.scala")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    qnames = [s.qualified_name for s in methods]
    assert any("UserService." in qn for qn in qnames)


def test_function_signature_present(scala_parser: ScalaParser) -> None:
    source = "def greet(name: String): String = name"
    result = scala_parser.parse_source(source, "test.scala")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert len(funcs) == 1
    assert funcs[0].signature is not None
    assert "greet" in funcs[0].signature
    assert "String" in funcs[0].signature


def test_docstring_extraction(scala_parser: ScalaParser) -> None:
    source = '// Creates a user\ndef createUser(): String = ""'
    result = scala_parser.parse_source(source, "test.scala")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert len(funcs) == 1
    assert funcs[0].docstring is not None
    assert "Creates a user" in funcs[0].docstring


def test_class_docstring(scala_parser: ScalaParser, sample_scala_source: str) -> None:
    result = scala_parser.parse_source(sample_scala_source, "test.scala")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    svc = next((c for c in classes if c.name == "UserService"), None)
    assert svc is not None
    assert svc.docstring is not None


def test_inheritance_relationship(scala_parser: ScalaParser, sample_scala_source: str) -> None:
    result = scala_parser.parse_source(sample_scala_source, "test.scala")
    inherits = [r for r in result.relationships if r.kind.value == "inherits"]
    assert len(inherits) >= 1
    sources = [r.source_id for r in inherits]
    assert any("UserService" in s for s in sources)


def test_extracts_call_relationships(scala_parser: ScalaParser, sample_scala_source: str) -> None:
    result = scala_parser.parse_source(sample_scala_source, "test.scala")
    calls = [r for r in result.relationships if r.kind.value == "calls"]
    assert len(calls) >= 1


def test_extracts_import_relationships(scala_parser: ScalaParser, sample_scala_source: str) -> None:
    result = scala_parser.parse_source(sample_scala_source, "test.scala")
    imports = [r for r in result.relationships if r.kind.value == "imports"]
    assert len(imports) >= 1


def test_supported_extensions(scala_parser: ScalaParser) -> None:
    assert ".scala" in scala_parser.supported_extensions
    assert ".sc" in scala_parser.supported_extensions


def test_language_property(scala_parser: ScalaParser) -> None:
    assert scala_parser.language == "scala"


def test_empty_file(scala_parser: ScalaParser) -> None:
    result = scala_parser.parse_source("", "empty.scala")
    assert result.file_info.language == "scala"
    assert result.symbols == []
    assert result.relationships == []


def test_symbol_count_in_file_info(scala_parser: ScalaParser, sample_scala_source: str) -> None:
    result = scala_parser.parse_source(sample_scala_source, "test.scala")
    assert result.file_info.symbol_count == len(result.symbols)
    assert result.file_info.relationship_count == len(result.relationships)


@pytest.mark.parametrize(
    "source,expected_kind",
    [
        ("class Foo {}", SymbolKind.CLASS),
        ("trait Bar {}", SymbolKind.INTERFACE),
        ("val x = 1", SymbolKind.VARIABLE),
        ("def doIt(): Unit = {}", SymbolKind.FUNCTION),
        ("object Singleton {}", SymbolKind.CLASS),
    ],
)
def test_symbol_kinds(scala_parser: ScalaParser, source: str, expected_kind: SymbolKind) -> None:
    result = scala_parser.parse_source(source, "test.scala")
    kinds = [s.kind for s in result.symbols]
    assert expected_kind in kinds
