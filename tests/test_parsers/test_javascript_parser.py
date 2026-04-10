"""Tests for the JavaScript tree-sitter parser."""

from pathlib import Path

import pytest

from codeatlas.models import SymbolKind
from codeatlas.parsers.javascript_parser import JavaScriptParser


def test_parse_file_returns_parse_result(
    javascript_parser: JavaScriptParser, sample_javascript_path: Path
) -> None:
    result = javascript_parser.parse_file(sample_javascript_path)
    assert result.file_info.path == str(sample_javascript_path)
    assert len(result.symbols) > 0


def test_parse_source_returns_parse_result(
    javascript_parser: JavaScriptParser, sample_javascript_source: str
) -> None:
    result = javascript_parser.parse_source(sample_javascript_source, "test.js")
    assert result.file_info.path == "test.js"
    assert len(result.symbols) > 0


def test_file_info_language(
    javascript_parser: JavaScriptParser, sample_javascript_source: str
) -> None:
    result = javascript_parser.parse_source(sample_javascript_source, "test.js")
    assert result.file_info.language == "javascript"


def test_content_hash_consistent(
    javascript_parser: JavaScriptParser, sample_javascript_source: str
) -> None:
    r1 = javascript_parser.parse_source(sample_javascript_source, "test.js")
    r2 = javascript_parser.parse_source(sample_javascript_source, "test.js")
    assert r1.file_info.content_hash == r2.file_info.content_hash


def test_extracts_import(
    javascript_parser: JavaScriptParser, sample_javascript_source: str
) -> None:
    result = javascript_parser.parse_source(sample_javascript_source, "test.js")
    imports = [s for s in result.symbols if s.kind == SymbolKind.IMPORT]
    assert len(imports) >= 1
    import_names = [s.name for s in imports]
    assert "fs" in import_names or "path" in import_names


def test_extracts_constant(
    javascript_parser: JavaScriptParser, sample_javascript_source: str
) -> None:
    result = javascript_parser.parse_source(sample_javascript_source, "test.js")
    consts = [s for s in result.symbols if s.kind == SymbolKind.CONSTANT]
    assert any(s.name == "MAX_RETRIES" for s in consts)


def test_extracts_class(javascript_parser: JavaScriptParser, sample_javascript_source: str) -> None:
    result = javascript_parser.parse_source(sample_javascript_source, "test.js")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    class_names = [s.name for s in classes]
    assert "UserService" in class_names
    assert "AdminService" in class_names


def test_extracts_methods(
    javascript_parser: JavaScriptParser, sample_javascript_source: str
) -> None:
    result = javascript_parser.parse_source(sample_javascript_source, "test.js")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    method_names = [s.name for s in methods]
    assert "getUser" in method_names
    assert "create" in method_names


def test_extracts_function(
    javascript_parser: JavaScriptParser, sample_javascript_source: str
) -> None:
    result = javascript_parser.parse_source(sample_javascript_source, "test.js")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    names = [s.name for s in funcs]
    assert "processItems" in names


def test_extracts_arrow_function(
    javascript_parser: JavaScriptParser, sample_javascript_source: str
) -> None:
    result = javascript_parser.parse_source(sample_javascript_source, "test.js")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    names = [s.name for s in funcs]
    assert "helper" in names


def test_extracts_function_expression(
    javascript_parser: JavaScriptParser, sample_javascript_source: str
) -> None:
    result = javascript_parser.parse_source(sample_javascript_source, "test.js")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    names = [s.name for s in funcs]
    assert "greet" in names


def test_method_qualified_name_includes_class(
    javascript_parser: JavaScriptParser, sample_javascript_source: str
) -> None:
    result = javascript_parser.parse_source(sample_javascript_source, "test.js")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    qnames = [s.qualified_name for s in methods]
    assert any("UserService." in qn for qn in qnames)


def test_method_signature_present(javascript_parser: JavaScriptParser) -> None:
    source = "class Foo { async getUser(id, opts) {} }"
    result = javascript_parser.parse_source(source, "test.js")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    assert len(methods) == 1
    assert methods[0].signature is not None
    assert "getUser" in methods[0].signature


def test_jsdoc_extraction(javascript_parser: JavaScriptParser) -> None:
    source = "/** Fetches a user */\nfunction getUser(id) { return id; }"
    result = javascript_parser.parse_source(source, "test.js")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert len(funcs) == 1
    assert funcs[0].docstring is not None
    assert "Fetches a user" in funcs[0].docstring


def test_line_comment_as_docstring(javascript_parser: JavaScriptParser) -> None:
    source = "// Process all items\nfunction process() {}"
    result = javascript_parser.parse_source(source, "test.js")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert len(funcs) == 1
    assert funcs[0].docstring is not None
    assert "Process all items" in funcs[0].docstring


def test_extracts_call_relationships(
    javascript_parser: JavaScriptParser, sample_javascript_source: str
) -> None:
    result = javascript_parser.parse_source(sample_javascript_source, "test.js")
    calls = [r for r in result.relationships if r.kind.value == "calls"]
    assert len(calls) >= 1


def test_extracts_import_relationships(
    javascript_parser: JavaScriptParser, sample_javascript_source: str
) -> None:
    result = javascript_parser.parse_source(sample_javascript_source, "test.js")
    imports = [r for r in result.relationships if r.kind.value == "imports"]
    assert len(imports) >= 1


def test_export_function_is_extracted(javascript_parser: JavaScriptParser) -> None:
    source = "export function doWork(x) { helper(x); }"
    result = javascript_parser.parse_source(source, "test.js")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert any(s.name == "doWork" for s in funcs)


def test_export_class_is_extracted(javascript_parser: JavaScriptParser) -> None:
    source = "export class Config { setup() {} }"
    result = javascript_parser.parse_source(source, "test.js")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    assert any(s.name == "Config" for s in classes)


def test_export_const_is_extracted(javascript_parser: JavaScriptParser) -> None:
    source = "export const VERSION = '1.0';"
    result = javascript_parser.parse_source(source, "test.js")
    consts = [s for s in result.symbols if s.kind == SymbolKind.CONSTANT]
    assert any(s.name == "VERSION" for s in consts)


def test_supported_extensions(javascript_parser: JavaScriptParser) -> None:
    assert ".js" in javascript_parser.supported_extensions
    assert ".mjs" in javascript_parser.supported_extensions


def test_language_property(javascript_parser: JavaScriptParser) -> None:
    assert javascript_parser.language == "javascript"


def test_empty_file(javascript_parser: JavaScriptParser) -> None:
    result = javascript_parser.parse_source("", "empty.js")
    assert result.file_info.language == "javascript"
    assert result.symbols == []
    assert result.relationships == []


def test_symbol_count_in_file_info(
    javascript_parser: JavaScriptParser, sample_javascript_source: str
) -> None:
    result = javascript_parser.parse_source(sample_javascript_source, "test.js")
    assert result.file_info.symbol_count == len(result.symbols)
    assert result.file_info.relationship_count == len(result.relationships)


@pytest.mark.parametrize(
    "source,expected_kind",
    [
        ("class Foo {}", SymbolKind.CLASS),
        ("function bar() {}", SymbolKind.FUNCTION),
        ("const MAX = 42;", SymbolKind.CONSTANT),
        ("import x from 'mod';", SymbolKind.IMPORT),
    ],
)
def test_symbol_kinds(
    javascript_parser: JavaScriptParser, source: str, expected_kind: SymbolKind
) -> None:
    result = javascript_parser.parse_source(source, "test.js")
    kinds = [s.kind for s in result.symbols]
    assert expected_kind in kinds
