"""Tests for the Lua tree-sitter parser."""

from pathlib import Path

import pytest

from codeatlas.models import RelationshipKind, SymbolKind
from codeatlas.parsers.lua_parser import LuaParser


def test_parse_file_returns_parse_result(lua_parser: LuaParser, sample_lua_path: Path) -> None:
    result = lua_parser.parse_file(sample_lua_path)
    assert result.file_info.path == str(sample_lua_path)
    assert len(result.symbols) > 0


def test_parse_source_returns_parse_result(lua_parser: LuaParser, sample_lua_source: str) -> None:
    result = lua_parser.parse_source(sample_lua_source, "test.lua")
    assert result.file_info.path == "test.lua"
    assert len(result.symbols) > 0


def test_file_info_language(lua_parser: LuaParser, sample_lua_source: str) -> None:
    result = lua_parser.parse_source(sample_lua_source, "test.lua")
    assert result.file_info.language == "lua"


def test_content_hash_consistent(lua_parser: LuaParser, sample_lua_source: str) -> None:
    r1 = lua_parser.parse_source(sample_lua_source, "test.lua")
    r2 = lua_parser.parse_source(sample_lua_source, "test.lua")
    assert r1.file_info.content_hash == r2.file_info.content_hash


def test_extracts_module_function(lua_parser: LuaParser, sample_lua_source: str) -> None:
    result = lua_parser.parse_source(sample_lua_source, "test.lua")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    names = [s.name for s in funcs]
    assert "greet" in names
    assert "add" in names


def test_module_function_qualified_name(lua_parser: LuaParser, sample_lua_source: str) -> None:
    result = lua_parser.parse_source(sample_lua_source, "test.lua")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    qnames = [s.qualified_name for s in funcs]
    assert "M.greet" in qnames
    assert "M.add" in qnames


def test_extracts_top_level_function(lua_parser: LuaParser, sample_lua_source: str) -> None:
    result = lua_parser.parse_source(sample_lua_source, "test.lua")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    names = [s.name for s in funcs]
    assert "process" in names


def test_extracts_local_function(lua_parser: LuaParser, sample_lua_source: str) -> None:
    result = lua_parser.parse_source(sample_lua_source, "test.lua")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    names = [s.name for s in funcs]
    assert "helper" in names


def test_extracts_function_expression(lua_parser: LuaParser, sample_lua_source: str) -> None:
    result = lua_parser.parse_source(sample_lua_source, "test.lua")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    names = [s.name for s in funcs]
    assert "transform" in names


def test_extracts_variable(lua_parser: LuaParser, sample_lua_source: str) -> None:
    result = lua_parser.parse_source(sample_lua_source, "test.lua")
    variables = [s for s in result.symbols if s.kind == SymbolKind.VARIABLE]
    # M = {} is captured as a variable (table, not function)
    names = [s.name for s in variables]
    assert "M" in names


def test_function_signature(lua_parser: LuaParser) -> None:
    source = "function greet(name, age)\n  return name\nend\n"
    result = lua_parser.parse_source(source, "test.lua")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert len(funcs) == 1
    assert funcs[0].signature is not None
    assert "greet" in funcs[0].signature
    assert "name" in funcs[0].signature


def test_function_docstring(lua_parser: LuaParser, sample_lua_source: str) -> None:
    result = lua_parser.parse_source(sample_lua_source, "test.lua")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    greet = next((f for f in funcs if f.name == "greet"), None)
    assert greet is not None
    assert greet.docstring is not None
    assert "greeting" in greet.docstring.lower() or "greet" in greet.docstring.lower()


def test_extracts_call_relationships(lua_parser: LuaParser, sample_lua_source: str) -> None:
    result = lua_parser.parse_source(sample_lua_source, "test.lua")
    call_rels = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    assert len(call_rels) >= 1


def test_process_calls_greet(lua_parser: LuaParser, sample_lua_source: str) -> None:
    result = lua_parser.parse_source(sample_lua_source, "test.lua")
    call_rels = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    sources = [r.source_id for r in call_rels]
    targets = [r.target_id for r in call_rels]
    assert any("process" in s for s in sources)
    assert any("greet" in t for t in targets)


def test_function_span(lua_parser: LuaParser) -> None:
    source = "function hello()\n  return 1\nend\n"
    result = lua_parser.parse_source(source, "test.lua")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert len(funcs) == 1
    assert funcs[0].span.start.line == 0


def test_supported_extensions(lua_parser: LuaParser) -> None:
    assert ".lua" in lua_parser.supported_extensions


def test_language_property(lua_parser: LuaParser) -> None:
    assert lua_parser.language == "lua"


def test_empty_file(lua_parser: LuaParser) -> None:
    result = lua_parser.parse_source("", "empty.lua")
    assert result.file_info.language == "lua"
    assert result.symbols == []
    assert result.relationships == []


def test_symbol_count_in_file_info(lua_parser: LuaParser, sample_lua_source: str) -> None:
    result = lua_parser.parse_source(sample_lua_source, "test.lua")
    assert result.file_info.symbol_count == len(result.symbols)
    assert result.file_info.relationship_count == len(result.relationships)


@pytest.mark.parametrize(
    "source,expected_kind",
    [
        ("function foo()\nend\n", SymbolKind.FUNCTION),
        ("local function bar()\nend\n", SymbolKind.FUNCTION),
        ("local x = 1\n", SymbolKind.VARIABLE),
    ],
)
def test_symbol_kinds(lua_parser: LuaParser, source: str, expected_kind: SymbolKind) -> None:
    result = lua_parser.parse_source(source, "test.lua")
    kinds = [s.kind for s in result.symbols]
    assert expected_kind in kinds
