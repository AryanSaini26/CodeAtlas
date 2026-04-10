"""Tests for the Kotlin tree-sitter parser."""

from pathlib import Path

import pytest

from codeatlas.models import SymbolKind
from codeatlas.parsers.kotlin_parser import KotlinParser


def test_parse_file_returns_parse_result(
    kotlin_parser: KotlinParser, sample_kotlin_path: Path
) -> None:
    result = kotlin_parser.parse_file(sample_kotlin_path)
    assert result.file_info.path == str(sample_kotlin_path)
    assert len(result.symbols) > 0


def test_parse_source_returns_parse_result(
    kotlin_parser: KotlinParser, sample_kotlin_source: str
) -> None:
    result = kotlin_parser.parse_source(sample_kotlin_source, "test.kt")
    assert result.file_info.path == "test.kt"
    assert len(result.symbols) > 0


def test_file_info_language(kotlin_parser: KotlinParser, sample_kotlin_source: str) -> None:
    result = kotlin_parser.parse_source(sample_kotlin_source, "test.kt")
    assert result.file_info.language == "kotlin"


def test_content_hash_consistent(kotlin_parser: KotlinParser, sample_kotlin_source: str) -> None:
    r1 = kotlin_parser.parse_source(sample_kotlin_source, "test.kt")
    r2 = kotlin_parser.parse_source(sample_kotlin_source, "test.kt")
    assert r1.file_info.content_hash == r2.file_info.content_hash


def test_extracts_import(kotlin_parser: KotlinParser, sample_kotlin_source: str) -> None:
    result = kotlin_parser.parse_source(sample_kotlin_source, "test.kt")
    imports = [s for s in result.symbols if s.kind == SymbolKind.IMPORT]
    assert len(imports) >= 1
    names = [s.qualified_name for s in imports]
    assert any("kotlin" in n for n in names)


def test_extracts_const_as_constant(kotlin_parser: KotlinParser, sample_kotlin_source: str) -> None:
    result = kotlin_parser.parse_source(sample_kotlin_source, "test.kt")
    consts = [s for s in result.symbols if s.kind == SymbolKind.CONSTANT]
    assert any(s.name == "MAX_SIZE" for s in consts)


def test_extracts_val_as_variable(kotlin_parser: KotlinParser, sample_kotlin_source: str) -> None:
    result = kotlin_parser.parse_source(sample_kotlin_source, "test.kt")
    variables = [s for s in result.symbols if s.kind == SymbolKind.VARIABLE]
    assert any(s.name == "APP_NAME" for s in variables)


def test_extracts_interface(kotlin_parser: KotlinParser, sample_kotlin_source: str) -> None:
    result = kotlin_parser.parse_source(sample_kotlin_source, "test.kt")
    interfaces = [s for s in result.symbols if s.kind == SymbolKind.INTERFACE]
    assert len(interfaces) >= 1
    assert any(s.name == "Greeter" for s in interfaces)


def test_extracts_class(kotlin_parser: KotlinParser, sample_kotlin_source: str) -> None:
    result = kotlin_parser.parse_source(sample_kotlin_source, "test.kt")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    class_names = [s.name for s in classes]
    assert "UserService" in class_names


def test_extracts_object_as_class(kotlin_parser: KotlinParser, sample_kotlin_source: str) -> None:
    result = kotlin_parser.parse_source(sample_kotlin_source, "test.kt")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    names = [s.name for s in classes]
    assert "Config" in names


def test_extracts_methods(kotlin_parser: KotlinParser, sample_kotlin_source: str) -> None:
    result = kotlin_parser.parse_source(sample_kotlin_source, "test.kt")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    names = [s.name for s in methods]
    assert "createUser" in names


def test_extracts_companion_method(kotlin_parser: KotlinParser, sample_kotlin_source: str) -> None:
    result = kotlin_parser.parse_source(sample_kotlin_source, "test.kt")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    names = [s.name for s in methods]
    assert "create" in names


def test_extracts_toplevel_function(kotlin_parser: KotlinParser, sample_kotlin_source: str) -> None:
    result = kotlin_parser.parse_source(sample_kotlin_source, "test.kt")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert any(s.name == "processAll" for s in funcs)


def test_method_qualified_name_includes_class(
    kotlin_parser: KotlinParser, sample_kotlin_source: str
) -> None:
    result = kotlin_parser.parse_source(sample_kotlin_source, "test.kt")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    qnames = [s.qualified_name for s in methods]
    assert any("UserService." in qn for qn in qnames)


def test_function_signature_present(kotlin_parser: KotlinParser) -> None:
    source = "fun greet(name: String): String { return name }"
    result = kotlin_parser.parse_source(source, "test.kt")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert len(funcs) == 1
    assert funcs[0].signature is not None
    assert "greet" in funcs[0].signature
    assert "String" in funcs[0].signature


def test_doc_comment_extraction(kotlin_parser: KotlinParser) -> None:
    source = '// Creates a user\nfun createUser(): String { return "" }'
    result = kotlin_parser.parse_source(source, "test.kt")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert len(funcs) == 1
    assert funcs[0].docstring is not None
    assert "Creates a user" in funcs[0].docstring


def test_class_docstring(kotlin_parser: KotlinParser, sample_kotlin_source: str) -> None:
    result = kotlin_parser.parse_source(sample_kotlin_source, "test.kt")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    svc = next((c for c in classes if c.name == "UserService"), None)
    assert svc is not None
    assert svc.docstring is not None


def test_extracts_call_relationships(
    kotlin_parser: KotlinParser, sample_kotlin_source: str
) -> None:
    result = kotlin_parser.parse_source(sample_kotlin_source, "test.kt")
    calls = [r for r in result.relationships if r.kind.value == "calls"]
    assert len(calls) >= 1


def test_extracts_import_relationships(
    kotlin_parser: KotlinParser, sample_kotlin_source: str
) -> None:
    result = kotlin_parser.parse_source(sample_kotlin_source, "test.kt")
    imports = [r for r in result.relationships if r.kind.value == "imports"]
    assert len(imports) >= 1


def test_inheritance_relationship(kotlin_parser: KotlinParser, sample_kotlin_source: str) -> None:
    result = kotlin_parser.parse_source(sample_kotlin_source, "test.kt")
    inherits = [r for r in result.relationships if r.kind.value == "inherits"]
    assert len(inherits) >= 1
    sources = [r.source_id for r in inherits]
    assert any("UserService" in s for s in sources)


def test_supported_extensions(kotlin_parser: KotlinParser) -> None:
    assert ".kt" in kotlin_parser.supported_extensions
    assert ".kts" in kotlin_parser.supported_extensions


def test_language_property(kotlin_parser: KotlinParser) -> None:
    assert kotlin_parser.language == "kotlin"


def test_empty_file(kotlin_parser: KotlinParser) -> None:
    result = kotlin_parser.parse_source("", "empty.kt")
    assert result.file_info.language == "kotlin"
    assert result.symbols == []
    assert result.relationships == []


def test_symbol_count_in_file_info(kotlin_parser: KotlinParser, sample_kotlin_source: str) -> None:
    result = kotlin_parser.parse_source(sample_kotlin_source, "test.kt")
    assert result.file_info.symbol_count == len(result.symbols)
    assert result.file_info.relationship_count == len(result.relationships)


@pytest.mark.parametrize(
    "source,expected_kind",
    [
        ("class Foo {}", SymbolKind.CLASS),
        ("interface Bar {}", SymbolKind.INTERFACE),
        ("const val X = 1", SymbolKind.CONSTANT),
        ("val y = 2", SymbolKind.VARIABLE),
        ("fun doIt() {}", SymbolKind.FUNCTION),
    ],
)
def test_symbol_kinds(kotlin_parser: KotlinParser, source: str, expected_kind: SymbolKind) -> None:
    result = kotlin_parser.parse_source(source, "test.kt")
    kinds = [s.kind for s in result.symbols]
    assert expected_kind in kinds
