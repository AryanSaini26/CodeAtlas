"""Tests for the Go AST parser."""

from pathlib import Path

from codeatlas.models import ParseResult, RelationshipKind, SymbolKind
from codeatlas.parsers.go_parser import GoParser


def _names(result: ParseResult) -> set[str]:
    return {s.name for s in result.symbols}


def _kinds(result: ParseResult, kind: SymbolKind) -> list[str]:
    return [s.name for s in result.symbols if s.kind == kind]


# --- File-level tests ---


def test_parse_file_returns_parse_result(go_parser: GoParser, sample_go_path: Path) -> None:
    result = go_parser.parse_file(sample_go_path)
    assert isinstance(result, ParseResult)


def test_parse_source_returns_parse_result(go_parser: GoParser, sample_go_source: str) -> None:
    result = go_parser.parse_source(sample_go_source, "test.go")
    assert isinstance(result, ParseResult)


def test_file_info_language(go_parser: GoParser, sample_go_source: str) -> None:
    result = go_parser.parse_source(sample_go_source, "test.go")
    assert result.file_info.language == "go"


def test_content_hash_consistent(go_parser: GoParser, sample_go_source: str) -> None:
    r1 = go_parser.parse_source(sample_go_source, "test.go")
    r2 = go_parser.parse_source(sample_go_source, "test.go")
    assert r1.file_info.content_hash == r2.file_info.content_hash


# --- Symbol extraction ---


def test_extracts_package(go_parser: GoParser, sample_go_source: str) -> None:
    result = go_parser.parse_source(sample_go_source, "test.go")
    assert "animals" in _names(result)


def test_extracts_imports(go_parser: GoParser, sample_go_source: str) -> None:
    result = go_parser.parse_source(sample_go_source, "test.go")
    imports = _kinds(result, SymbolKind.IMPORT)
    assert "fmt" in imports
    assert "strings" in imports


def test_extracts_functions(go_parser: GoParser, sample_go_source: str) -> None:
    result = go_parser.parse_source(sample_go_source, "test.go")
    functions = _kinds(result, SymbolKind.FUNCTION)
    assert "NewDog" in functions
    assert "Greet" in functions


def test_extracts_methods(go_parser: GoParser, sample_go_source: str) -> None:
    result = go_parser.parse_source(sample_go_source, "test.go")
    methods = _kinds(result, SymbolKind.METHOD)
    assert "Speak" in methods
    assert "Fetch" in methods
    assert "Start" in methods


def test_method_qualified_name_includes_receiver(
    go_parser: GoParser, sample_go_source: str
) -> None:
    result = go_parser.parse_source(sample_go_source, "test.go")
    speak = next(s for s in result.symbols if s.name == "Speak")
    assert speak.qualified_name == "Dog.Speak"


def test_extracts_struct(go_parser: GoParser, sample_go_source: str) -> None:
    result = go_parser.parse_source(sample_go_source, "test.go")
    classes = _kinds(result, SymbolKind.CLASS)
    assert "Dog" in classes
    assert "Server" in classes


def test_extracts_interface(go_parser: GoParser, sample_go_source: str) -> None:
    result = go_parser.parse_source(sample_go_source, "test.go")
    interfaces = _kinds(result, SymbolKind.INTERFACE)
    assert "Animal" in interfaces


def test_extracts_type_alias(go_parser: GoParser, sample_go_source: str) -> None:
    result = go_parser.parse_source(sample_go_source, "test.go")
    assert "StringAlias" in _names(result)


def test_extracts_const(go_parser: GoParser, sample_go_source: str) -> None:
    result = go_parser.parse_source(sample_go_source, "test.go")
    constants = _kinds(result, SymbolKind.CONSTANT)
    assert "MaxAge" in constants


def test_extracts_var(go_parser: GoParser, sample_go_source: str) -> None:
    result = go_parser.parse_source(sample_go_source, "test.go")
    variables = _kinds(result, SymbolKind.VARIABLE)
    assert "DefaultName" in variables


def test_function_has_signature(go_parser: GoParser, sample_go_source: str) -> None:
    result = go_parser.parse_source(sample_go_source, "test.go")
    func = next(s for s in result.symbols if s.name == "NewDog")
    assert func.signature is not None
    assert "NewDog" in func.signature


def test_extracts_docstring(go_parser: GoParser, sample_go_source: str) -> None:
    result = go_parser.parse_source(sample_go_source, "test.go")
    func = next(s for s in result.symbols if s.name == "Greet")
    assert func.docstring is not None
    assert "greeting" in func.docstring.lower()


# --- Relationship extraction ---


def test_extracts_import_relationships(go_parser: GoParser, sample_go_source: str) -> None:
    result = go_parser.parse_source(sample_go_source, "test.go")
    rels = [r for r in result.relationships if r.kind == RelationshipKind.IMPORTS]
    targets = {r.target_id for r in rels}
    assert any("fmt" in t for t in targets)


def test_extracts_calls_relationships(go_parser: GoParser, sample_go_source: str) -> None:
    result = go_parser.parse_source(sample_go_source, "test.go")
    rels = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    assert len(rels) > 0
    targets = {r.target_id for r in rels}
    assert any("fmt.Sprintf" in t for t in targets)


# --- Edge cases ---


def test_empty_source(go_parser: GoParser) -> None:
    result = go_parser.parse_source("", "empty.go")
    assert result.file_info.language == "go"
    assert result.symbols == []


def test_symbol_ids_unique(go_parser: GoParser, sample_go_source: str) -> None:
    result = go_parser.parse_source(sample_go_source, "test.go")
    ids = [s.id for s in result.symbols]
    assert len(ids) == len(set(ids))


def test_symbol_count_matches(go_parser: GoParser, sample_go_source: str) -> None:
    result = go_parser.parse_source(sample_go_source, "test.go")
    assert result.file_info.symbol_count == len(result.symbols)
