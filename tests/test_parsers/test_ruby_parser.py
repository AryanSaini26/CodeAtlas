"""Tests for the Ruby tree-sitter parser."""

from pathlib import Path

import pytest

from codeatlas.models import SymbolKind
from codeatlas.parsers.ruby_parser import RubyParser


def test_parse_file_returns_parse_result(ruby_parser: RubyParser, sample_ruby_path: Path) -> None:
    result = ruby_parser.parse_file(sample_ruby_path)
    assert result.file_info.path == str(sample_ruby_path)
    assert len(result.symbols) > 0


def test_parse_source_returns_parse_result(
    ruby_parser: RubyParser, sample_ruby_source: str
) -> None:
    result = ruby_parser.parse_source(sample_ruby_source, "test.rb")
    assert result.file_info.path == "test.rb"
    assert len(result.symbols) > 0


def test_file_info_language(ruby_parser: RubyParser, sample_ruby_source: str) -> None:
    result = ruby_parser.parse_source(sample_ruby_source, "test.rb")
    assert result.file_info.language == "ruby"


def test_content_hash_consistent(ruby_parser: RubyParser, sample_ruby_source: str) -> None:
    r1 = ruby_parser.parse_source(sample_ruby_source, "test.rb")
    r2 = ruby_parser.parse_source(sample_ruby_source, "test.rb")
    assert r1.file_info.content_hash == r2.file_info.content_hash


def test_extracts_require_as_import(ruby_parser: RubyParser, sample_ruby_source: str) -> None:
    result = ruby_parser.parse_source(sample_ruby_source, "test.rb")
    imports = [s for s in result.symbols if s.kind == SymbolKind.IMPORT]
    assert len(imports) >= 1
    import_names = [s.name for s in imports]
    assert "json" in import_names


def test_extracts_require_relative(ruby_parser: RubyParser, sample_ruby_source: str) -> None:
    result = ruby_parser.parse_source(sample_ruby_source, "test.rb")
    imports = [s for s in result.symbols if s.kind == SymbolKind.IMPORT]
    import_names = [s.name for s in imports]
    assert any("models" in n for n in import_names)


def test_extracts_constant(ruby_parser: RubyParser, sample_ruby_source: str) -> None:
    result = ruby_parser.parse_source(sample_ruby_source, "test.rb")
    constants = [s for s in result.symbols if s.kind == SymbolKind.CONSTANT]
    assert len(constants) >= 1
    assert any(s.name == "MAX_RETRIES" for s in constants)


def test_extracts_module(ruby_parser: RubyParser, sample_ruby_source: str) -> None:
    result = ruby_parser.parse_source(sample_ruby_source, "test.rb")
    modules = [s for s in result.symbols if s.kind == SymbolKind.MODULE]
    assert len(modules) >= 1
    assert any(s.name == "Utils" for s in modules)


def test_extracts_class(ruby_parser: RubyParser, sample_ruby_source: str) -> None:
    result = ruby_parser.parse_source(sample_ruby_source, "test.rb")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    assert len(classes) >= 2
    class_names = [s.name for s in classes]
    assert "Animal" in class_names
    assert "Dog" in class_names


def test_extracts_instance_methods(ruby_parser: RubyParser, sample_ruby_source: str) -> None:
    result = ruby_parser.parse_source(sample_ruby_source, "test.rb")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    method_names = [s.name for s in methods]
    assert "initialize" in method_names
    assert "speak" in method_names


def test_extracts_singleton_method(ruby_parser: RubyParser, sample_ruby_source: str) -> None:
    result = ruby_parser.parse_source(sample_ruby_source, "test.rb")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    # self.create should appear as a singleton method
    names = [s.name for s in methods]
    assert "create" in names


def test_extracts_toplevel_function(ruby_parser: RubyParser, sample_ruby_source: str) -> None:
    result = ruby_parser.parse_source(sample_ruby_source, "test.rb")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert any(s.name == "process_animals" for s in funcs)


def test_method_qualified_name_includes_class(
    ruby_parser: RubyParser, sample_ruby_source: str
) -> None:
    result = ruby_parser.parse_source(sample_ruby_source, "test.rb")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    qualified_names = [s.qualified_name for s in methods]
    assert any("Animal." in qn for qn in qualified_names)


def test_method_signature_present(ruby_parser: RubyParser) -> None:
    source = "def greet(name, age)\n  puts name\nend"
    result = ruby_parser.parse_source(source, "test.rb")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert len(funcs) == 1
    assert funcs[0].signature is not None
    assert "greet" in funcs[0].signature
    assert "name" in funcs[0].signature


def test_docstring_extraction(ruby_parser: RubyParser) -> None:
    source = "# Creates a new user\n# with given params\ndef create_user\nend"
    result = ruby_parser.parse_source(source, "test.rb")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert len(funcs) == 1
    assert funcs[0].docstring is not None
    assert "Creates a new user" in funcs[0].docstring


def test_class_docstring_extraction(ruby_parser: RubyParser, sample_ruby_source: str) -> None:
    result = ruby_parser.parse_source(sample_ruby_source, "test.rb")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    animal = next((c for c in classes if c.name == "Animal"), None)
    assert animal is not None
    assert animal.docstring is not None


def test_extracts_call_relationships(ruby_parser: RubyParser, sample_ruby_source: str) -> None:
    result = ruby_parser.parse_source(sample_ruby_source, "test.rb")
    assert len(result.relationships) > 0
    call_rels = [r for r in result.relationships if r.kind.value == "calls"]
    assert len(call_rels) >= 1


def test_require_creates_import_relationship(
    ruby_parser: RubyParser, sample_ruby_source: str
) -> None:
    result = ruby_parser.parse_source(sample_ruby_source, "test.rb")
    import_rels = [r for r in result.relationships if r.kind.value == "imports"]
    assert len(import_rels) >= 1
    targets = [r.target_id for r in import_rels]
    assert any("json" in t for t in targets)


def test_inheritance_relationship(ruby_parser: RubyParser, sample_ruby_source: str) -> None:
    result = ruby_parser.parse_source(sample_ruby_source, "test.rb")
    inherits_rels = [r for r in result.relationships if r.kind.value == "inherits"]
    assert len(inherits_rels) >= 1
    # Dog < Animal
    sources = [r.source_id for r in inherits_rels]
    assert any("Dog" in s for s in sources)


def test_supported_extensions(ruby_parser: RubyParser) -> None:
    assert ".rb" in ruby_parser.supported_extensions


def test_language_property(ruby_parser: RubyParser) -> None:
    assert ruby_parser.language == "ruby"


def test_empty_file(ruby_parser: RubyParser) -> None:
    result = ruby_parser.parse_source("", "empty.rb")
    assert result.file_info.language == "ruby"
    assert result.symbols == []
    assert result.relationships == []


def test_symbol_count_in_file_info(ruby_parser: RubyParser, sample_ruby_source: str) -> None:
    result = ruby_parser.parse_source(sample_ruby_source, "test.rb")
    assert result.file_info.symbol_count == len(result.symbols)
    assert result.file_info.relationship_count == len(result.relationships)


def test_module_method_qualified_name(ruby_parser: RubyParser) -> None:
    source = "module Helpers\n  def self.format(x)\n    x.to_s\n  end\nend"
    result = ruby_parser.parse_source(source, "test.rb")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    assert len(methods) == 1
    assert "Helpers" in methods[0].qualified_name
    assert "format" in methods[0].qualified_name


@pytest.mark.parametrize(
    "source,expected_kind",
    [
        ("class Foo\nend", SymbolKind.CLASS),
        ("module Bar\nend", SymbolKind.MODULE),
        ("MAX = 42", SymbolKind.CONSTANT),
        ("def top_fn\nend", SymbolKind.FUNCTION),
    ],
)
def test_symbol_kinds(ruby_parser: RubyParser, source: str, expected_kind: SymbolKind) -> None:
    result = ruby_parser.parse_source(source, "test.rb")
    kinds = [s.kind for s in result.symbols]
    assert expected_kind in kinds
