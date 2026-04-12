"""Tests for the Bash tree-sitter parser."""

from pathlib import Path

import pytest

from codeatlas.models import RelationshipKind, SymbolKind
from codeatlas.parsers.bash_parser import BashParser


def test_parse_file_returns_parse_result(bash_parser: BashParser, sample_bash_path: Path) -> None:
    result = bash_parser.parse_file(sample_bash_path)
    assert result.file_info.path == str(sample_bash_path)
    assert len(result.symbols) > 0


def test_parse_source_returns_parse_result(
    bash_parser: BashParser, sample_bash_source: str
) -> None:
    result = bash_parser.parse_source(sample_bash_source, "test.sh")
    assert result.file_info.path == "test.sh"
    assert len(result.symbols) > 0


def test_file_info_language(bash_parser: BashParser, sample_bash_source: str) -> None:
    result = bash_parser.parse_source(sample_bash_source, "test.sh")
    assert result.file_info.language == "bash"


def test_content_hash_consistent(bash_parser: BashParser, sample_bash_source: str) -> None:
    r1 = bash_parser.parse_source(sample_bash_source, "test.sh")
    r2 = bash_parser.parse_source(sample_bash_source, "test.sh")
    assert r1.file_info.content_hash == r2.file_info.content_hash


def test_extracts_constants(bash_parser: BashParser, sample_bash_source: str) -> None:
    result = bash_parser.parse_source(sample_bash_source, "test.sh")
    constants = [s for s in result.symbols if s.kind == SymbolKind.CONSTANT]
    assert len(constants) >= 1
    names = [s.name for s in constants]
    assert "MAX_RETRIES" in names


def test_constants_are_uppercase_only(bash_parser: BashParser) -> None:
    source = "MAX_COUNT=10\nlower_var=5\nMIXEDCase=3\n"
    result = bash_parser.parse_source(source, "test.sh")
    constants = [s for s in result.symbols if s.kind == SymbolKind.CONSTANT]
    names = [s.name for s in constants]
    assert "MAX_COUNT" in names
    assert "lower_var" not in names
    assert "MIXEDCase" not in names


def test_extracts_functions(bash_parser: BashParser, sample_bash_source: str) -> None:
    result = bash_parser.parse_source(sample_bash_source, "test.sh")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert len(funcs) >= 3
    names = [s.name for s in funcs]
    assert "greet" in names
    assert "add" in names
    assert "deploy" in names


def test_function_signature(bash_parser: BashParser) -> None:
    source = "hello() {\n  echo hi\n}"
    result = bash_parser.parse_source(source, "test.sh")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert len(funcs) == 1
    assert funcs[0].signature == "function hello()"


def test_function_docstring(bash_parser: BashParser, sample_bash_source: str) -> None:
    result = bash_parser.parse_source(sample_bash_source, "test.sh")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    greet = next((f for f in funcs if f.name == "greet"), None)
    assert greet is not None
    assert greet.docstring is not None
    assert "Greet" in greet.docstring


def test_extracts_call_relationships(bash_parser: BashParser, sample_bash_source: str) -> None:
    result = bash_parser.parse_source(sample_bash_source, "test.sh")
    call_rels = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    assert len(call_rels) >= 1


def test_deploy_calls_greet(bash_parser: BashParser, sample_bash_source: str) -> None:
    result = bash_parser.parse_source(sample_bash_source, "test.sh")
    call_rels = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    sources = [r.source_id for r in call_rels]
    targets = [r.target_id for r in call_rels]
    assert any("deploy" in s for s in sources)
    assert any("greet" in t for t in targets)


def test_builtins_not_captured(bash_parser: BashParser) -> None:
    source = "foo() {\n  echo hello\n  printf '%s' world\n  cd /tmp\n}"
    result = bash_parser.parse_source(source, "test.sh")
    targets = [r.target_id for r in result.relationships]
    assert not any("echo" in t for t in targets)
    assert not any("printf" in t for t in targets)
    assert not any("cd" in t for t in targets)


def test_function_span(bash_parser: BashParser) -> None:
    source = "greet() {\n  echo hello\n}"
    result = bash_parser.parse_source(source, "test.sh")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert len(funcs) == 1
    assert funcs[0].span.start.line == 0


def test_supported_extensions(bash_parser: BashParser) -> None:
    assert ".sh" in bash_parser.supported_extensions
    assert ".bash" in bash_parser.supported_extensions


def test_language_property(bash_parser: BashParser) -> None:
    assert bash_parser.language == "bash"


def test_empty_file(bash_parser: BashParser) -> None:
    result = bash_parser.parse_source("", "empty.sh")
    assert result.file_info.language == "bash"
    assert result.symbols == []
    assert result.relationships == []


def test_symbol_count_in_file_info(bash_parser: BashParser, sample_bash_source: str) -> None:
    result = bash_parser.parse_source(sample_bash_source, "test.sh")
    assert result.file_info.symbol_count == len(result.symbols)
    assert result.file_info.relationship_count == len(result.relationships)


@pytest.mark.parametrize(
    "source,expected_kind",
    [
        ("MY_CONST=42\n", SymbolKind.CONSTANT),
        ("my_func() {\n  echo hi\n}\n", SymbolKind.FUNCTION),
    ],
)
def test_symbol_kinds(bash_parser: BashParser, source: str, expected_kind: SymbolKind) -> None:
    result = bash_parser.parse_source(source, "test.sh")
    kinds = [s.kind for s in result.symbols]
    assert expected_kind in kinds
