"""Tests for the Python AST parser."""

from pathlib import Path

import pytest

from codeatlas.models import ParseResult, RelationshipKind, SymbolKind
from codeatlas.parsers.python_parser import PythonParser


def _names(result: ParseResult) -> set[str]:
    return {s.name for s in result.symbols}


def _kinds(result: ParseResult, kind: SymbolKind) -> list[str]:
    return [s.name for s in result.symbols if s.kind == kind]


# --- File-level tests ---


def test_parse_file_returns_parse_result(python_parser: PythonParser, sample_python_path: Path) -> None:
    result = python_parser.parse_file(sample_python_path)
    assert isinstance(result, ParseResult)


def test_parse_source_returns_parse_result(python_parser: PythonParser, sample_python_source: str) -> None:
    result = python_parser.parse_source(sample_python_source, "test.py")
    assert isinstance(result, ParseResult)


def test_file_info_language(python_parser: PythonParser, sample_python_source: str) -> None:
    result = python_parser.parse_source(sample_python_source, "test.py")
    assert result.file_info.language == "python"


def test_file_info_content_hash_is_consistent(python_parser: PythonParser, sample_python_source: str) -> None:
    r1 = python_parser.parse_source(sample_python_source, "test.py")
    r2 = python_parser.parse_source(sample_python_source, "test.py")
    assert r1.file_info.content_hash == r2.file_info.content_hash


# --- Symbol extraction ---


def test_extracts_standalone_function(python_parser: PythonParser, sample_python_source: str) -> None:
    result = python_parser.parse_source(sample_python_source, "test.py")
    assert "standalone_function" in _names(result)


def test_extracts_class(python_parser: PythonParser, sample_python_source: str) -> None:
    result = python_parser.parse_source(sample_python_source, "test.py")
    assert "BaseModel" in _names(result)


def test_extracts_child_class(python_parser: PythonParser, sample_python_source: str) -> None:
    result = python_parser.parse_source(sample_python_source, "test.py")
    assert "ChildModel" in _names(result)


def test_extracts_methods(python_parser: PythonParser, sample_python_source: str) -> None:
    result = python_parser.parse_source(sample_python_source, "test.py")
    assert "get_name" in _names(result)
    assert "compute" in _names(result)


def test_extracts_module_level_constants(python_parser: PythonParser, sample_python_source: str) -> None:
    result = python_parser.parse_source(sample_python_source, "test.py")
    constants = _kinds(result, SymbolKind.CONSTANT)
    assert "MAX_RETRIES" in constants
    assert "DEFAULT_TIMEOUT" in constants


def test_extracts_imports(python_parser: PythonParser, sample_python_source: str) -> None:
    result = python_parser.parse_source(sample_python_source, "test.py")
    import_names = _kinds(result, SymbolKind.IMPORT)
    assert len(import_names) > 0


def test_extracts_decorated_function(python_parser: PythonParser, sample_python_source: str) -> None:
    result = python_parser.parse_source(sample_python_source, "test.py")
    assert "decorated_function" in _names(result)


def test_decorated_function_has_decorator(python_parser: PythonParser, sample_python_source: str) -> None:
    result = python_parser.parse_source(sample_python_source, "test.py")
    sym = next(s for s in result.symbols if s.name == "decorated_function")
    assert len(sym.decorators) > 0


def test_extracts_docstrings(python_parser: PythonParser, sample_python_source: str) -> None:
    result = python_parser.parse_source(sample_python_source, "test.py")
    func = next((s for s in result.symbols if s.name == "standalone_function"), None)
    assert func is not None
    assert func.docstring and "Add two integers" in func.docstring


def test_function_has_signature(python_parser: PythonParser, sample_python_source: str) -> None:
    result = python_parser.parse_source(sample_python_source, "test.py")
    func = next(s for s in result.symbols if s.name == "standalone_function")
    assert func.signature and "standalone_function" in func.signature


# --- Relationship extraction ---


def test_extracts_inheritance_relationship(python_parser: PythonParser, sample_python_source: str) -> None:
    result = python_parser.parse_source(sample_python_source, "test.py")
    rels = [r for r in result.relationships if r.kind == RelationshipKind.INHERITS]
    targets = {r.target_id for r in rels}
    assert any("BaseModel" in t for t in targets)


def test_extracts_import_relationships(python_parser: PythonParser, sample_python_source: str) -> None:
    result = python_parser.parse_source(sample_python_source, "test.py")
    rels = [r for r in result.relationships if r.kind == RelationshipKind.IMPORTS]
    assert len(rels) > 0


def test_extracts_calls_relationships(python_parser: PythonParser, sample_python_source: str) -> None:
    result = python_parser.parse_source(sample_python_source, "test.py")
    rels = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    assert len(rels) > 0


def test_extracts_decorator_relationships(python_parser: PythonParser, sample_python_source: str) -> None:
    result = python_parser.parse_source(sample_python_source, "test.py")
    rels = [r for r in result.relationships if r.kind == RelationshipKind.DECORATES]
    assert len(rels) > 0


# --- Edge cases ---


def test_empty_source(python_parser: PythonParser) -> None:
    result = python_parser.parse_source("", "empty.py")
    assert result.file_info.language == "python"
    assert result.symbols == []
    assert result.relationships == []


def test_symbol_ids_are_unique(python_parser: PythonParser, sample_python_source: str) -> None:
    result = python_parser.parse_source(sample_python_source, "test.py")
    ids = [s.id for s in result.symbols]
    assert len(ids) == len(set(ids))


def test_symbol_count_matches(python_parser: PythonParser, sample_python_source: str) -> None:
    result = python_parser.parse_source(sample_python_source, "test.py")
    assert result.file_info.symbol_count == len(result.symbols)
