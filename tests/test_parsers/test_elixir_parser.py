"""Tests for the Elixir tree-sitter parser."""

from pathlib import Path

import pytest

from codeatlas.models import RelationshipKind, SymbolKind
from codeatlas.parsers.elixir_parser import ElixirParser


def test_parse_file_returns_parse_result(
    elixir_parser: ElixirParser, sample_elixir_path: Path
) -> None:
    result = elixir_parser.parse_file(sample_elixir_path)
    assert result.file_info.path == str(sample_elixir_path)
    assert len(result.symbols) > 0


def test_parse_source_returns_parse_result(
    elixir_parser: ElixirParser, sample_elixir_source: str
) -> None:
    result = elixir_parser.parse_source(sample_elixir_source, "test.ex")
    assert result.file_info.path == "test.ex"
    assert len(result.symbols) > 0


def test_file_info_language(elixir_parser: ElixirParser, sample_elixir_source: str) -> None:
    result = elixir_parser.parse_source(sample_elixir_source, "test.ex")
    assert result.file_info.language == "elixir"


def test_content_hash_consistent(elixir_parser: ElixirParser, sample_elixir_source: str) -> None:
    r1 = elixir_parser.parse_source(sample_elixir_source, "test.ex")
    r2 = elixir_parser.parse_source(sample_elixir_source, "test.ex")
    assert r1.file_info.content_hash == r2.file_info.content_hash


def test_extracts_module(elixir_parser: ElixirParser, sample_elixir_source: str) -> None:
    result = elixir_parser.parse_source(sample_elixir_source, "test.ex")
    modules = [s for s in result.symbols if s.kind == SymbolKind.MODULE]
    assert len(modules) >= 2
    names = [s.name for s in modules]
    assert "Utils" in names
    assert "Worker" in names


def test_extracts_protocol_as_interface(
    elixir_parser: ElixirParser, sample_elixir_source: str
) -> None:
    result = elixir_parser.parse_source(sample_elixir_source, "test.ex")
    interfaces = [s for s in result.symbols if s.kind == SymbolKind.INTERFACE]
    assert len(interfaces) >= 1
    names = [s.name for s in interfaces]
    assert "Serializable" in names


def test_extracts_functions_as_methods(
    elixir_parser: ElixirParser, sample_elixir_source: str
) -> None:
    result = elixir_parser.parse_source(sample_elixir_source, "test.ex")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    assert len(methods) >= 2
    names = [s.name for s in methods]
    assert "greet" in names
    assert "add" in names


def test_extracts_private_function(elixir_parser: ElixirParser, sample_elixir_source: str) -> None:
    result = elixir_parser.parse_source(sample_elixir_source, "test.ex")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    names = [s.name for s in methods]
    assert "private_helper" in names


def test_method_qualified_name_includes_module(
    elixir_parser: ElixirParser, sample_elixir_source: str
) -> None:
    result = elixir_parser.parse_source(sample_elixir_source, "test.ex")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    qnames = [s.qualified_name for s in methods]
    assert any("SampleApp.Utils.greet" == qn for qn in qnames)


def test_function_signature(elixir_parser: ElixirParser) -> None:
    source = "defmodule M do\n  def hello(name, age) do\n    name\n  end\nend\n"
    result = elixir_parser.parse_source(source, "test.ex")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    assert len(methods) == 1
    assert methods[0].signature is not None
    assert "hello" in methods[0].signature


def test_function_docstring(elixir_parser: ElixirParser, sample_elixir_source: str) -> None:
    result = elixir_parser.parse_source(sample_elixir_source, "test.ex")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    greet = next((m for m in methods if m.name == "greet"), None)
    assert greet is not None
    assert greet.docstring is not None
    assert "greeting" in greet.docstring.lower() or "greet" in greet.docstring.lower()


def test_extracts_call_relationships(
    elixir_parser: ElixirParser, sample_elixir_source: str
) -> None:
    result = elixir_parser.parse_source(sample_elixir_source, "test.ex")
    call_rels = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    assert len(call_rels) >= 1


def test_run_calls_greet(elixir_parser: ElixirParser, sample_elixir_source: str) -> None:
    result = elixir_parser.parse_source(sample_elixir_source, "test.ex")
    call_rels = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    sources = [r.source_id for r in call_rels]
    targets = [r.target_id for r in call_rels]
    assert any("run" in s for s in sources)
    assert any("greet" in t for t in targets)


def test_function_span(elixir_parser: ElixirParser) -> None:
    source = "defmodule M do\n  def hello do\n    :ok\n  end\nend\n"
    result = elixir_parser.parse_source(source, "test.ex")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    assert len(methods) == 1
    assert methods[0].span.start.line >= 0


def test_supported_extensions(elixir_parser: ElixirParser) -> None:
    assert ".ex" in elixir_parser.supported_extensions
    assert ".exs" in elixir_parser.supported_extensions


def test_language_property(elixir_parser: ElixirParser) -> None:
    assert elixir_parser.language == "elixir"


def test_empty_file(elixir_parser: ElixirParser) -> None:
    result = elixir_parser.parse_source("", "empty.ex")
    assert result.file_info.language == "elixir"
    assert result.symbols == []
    assert result.relationships == []


def test_symbol_count_in_file_info(elixir_parser: ElixirParser, sample_elixir_source: str) -> None:
    result = elixir_parser.parse_source(sample_elixir_source, "test.ex")
    assert result.file_info.symbol_count == len(result.symbols)
    assert result.file_info.relationship_count == len(result.relationships)


def test_defp_parsed_as_method(elixir_parser: ElixirParser) -> None:
    source = "defmodule M do\n  defp secret do\n    :ok\n  end\nend\n"
    result = elixir_parser.parse_source(source, "test.ex")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    assert any(m.name == "secret" for m in methods)


@pytest.mark.parametrize(
    "source,expected_kind",
    [
        ("defmodule Foo do\nend\n", SymbolKind.MODULE),
        ("defprotocol Bar do\nend\n", SymbolKind.INTERFACE),
    ],
)
def test_symbol_kinds(elixir_parser: ElixirParser, source: str, expected_kind: SymbolKind) -> None:
    result = elixir_parser.parse_source(source, "test.ex")
    kinds = [s.kind for s in result.symbols]
    assert expected_kind in kinds
