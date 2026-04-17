"""Tests for the Julia tree-sitter parser."""

from pathlib import Path

import pytest

from codeatlas.models import RelationshipKind, SymbolKind
from codeatlas.parsers.julia_parser import JuliaParser


@pytest.fixture
def julia_parser() -> JuliaParser:
    return JuliaParser()


@pytest.fixture
def sample_julia_path() -> Path:
    return Path(__file__).parent.parent / "fixtures" / "sample_julia" / "sample.jl"


@pytest.fixture
def sample_julia_source(sample_julia_path: Path) -> str:
    return sample_julia_path.read_text()


# --- basic parse ---


def test_parse_file_returns_parse_result(
    julia_parser: JuliaParser, sample_julia_path: Path
) -> None:
    result = julia_parser.parse_file(sample_julia_path)
    assert result.file_info.path == str(sample_julia_path)
    assert len(result.symbols) > 0


def test_parse_source_returns_parse_result(
    julia_parser: JuliaParser, sample_julia_source: str
) -> None:
    result = julia_parser.parse_source(sample_julia_source, "test.jl")
    assert result.file_info.path == "test.jl"
    assert len(result.symbols) > 0


def test_file_info_language(julia_parser: JuliaParser, sample_julia_source: str) -> None:
    result = julia_parser.parse_source(sample_julia_source, "test.jl")
    assert result.file_info.language == "julia"


def test_content_hash_consistent(julia_parser: JuliaParser, sample_julia_source: str) -> None:
    r1 = julia_parser.parse_source(sample_julia_source, "test.jl")
    r2 = julia_parser.parse_source(sample_julia_source, "test.jl")
    assert r1.file_info.content_hash == r2.file_info.content_hash


def test_size_bytes_populated(julia_parser: JuliaParser, sample_julia_source: str) -> None:
    result = julia_parser.parse_source(sample_julia_source, "test.jl")
    assert result.file_info.size_bytes > 0


# --- modules ---


def test_extracts_module(julia_parser: JuliaParser, sample_julia_source: str) -> None:
    result = julia_parser.parse_source(sample_julia_source, "test.jl")
    modules = [s for s in result.symbols if s.kind == SymbolKind.MODULE]
    assert len(modules) >= 1
    assert any(s.name == "SampleModule" for s in modules)


# --- imports ---


def test_extracts_import(julia_parser: JuliaParser, sample_julia_source: str) -> None:
    result = julia_parser.parse_source(sample_julia_source, "test.jl")
    imports = [s for s in result.symbols if s.kind == SymbolKind.IMPORT]
    assert len(imports) >= 1
    names = [s.name for s in imports]
    assert "LinearAlgebra" in names


def test_extracts_using_as_import(julia_parser: JuliaParser, sample_julia_source: str) -> None:
    result = julia_parser.parse_source(sample_julia_source, "test.jl")
    imports = [s for s in result.symbols if s.kind == SymbolKind.IMPORT]
    names = [s.name for s in imports]
    assert "Statistics" in names


def test_import_creates_relationship(julia_parser: JuliaParser, sample_julia_source: str) -> None:
    result = julia_parser.parse_source(sample_julia_source, "test.jl")
    import_rels = [r for r in result.relationships if r.kind == RelationshipKind.IMPORTS]
    assert len(import_rels) >= 1


# --- constants ---


def test_extracts_constant(julia_parser: JuliaParser, sample_julia_source: str) -> None:
    result = julia_parser.parse_source(sample_julia_source, "test.jl")
    constants = [s for s in result.symbols if s.kind == SymbolKind.CONSTANT]
    assert len(constants) >= 1
    names = [s.name for s in constants]
    assert "MAX_SIZE" in names


# --- abstract types ---


def test_extracts_abstract_type(julia_parser: JuliaParser, sample_julia_source: str) -> None:
    result = julia_parser.parse_source(sample_julia_source, "test.jl")
    interfaces = [s for s in result.symbols if s.kind == SymbolKind.INTERFACE]
    assert len(interfaces) >= 1
    assert any(s.name == "Shape" for s in interfaces)


# --- structs ---


def test_extracts_struct(julia_parser: JuliaParser, sample_julia_source: str) -> None:
    result = julia_parser.parse_source(sample_julia_source, "test.jl")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    assert len(classes) >= 2
    names = [s.name for s in classes]
    assert "Circle" in names
    assert "Rectangle" in names


def test_struct_with_inheritance(julia_parser: JuliaParser) -> None:
    result = julia_parser.parse_source("struct Dog <: Animal\n    name::String\nend\n", "test.jl")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    assert len(classes) == 1
    assert classes[0].name == "Dog"


def test_struct_without_inheritance(julia_parser: JuliaParser) -> None:
    result = julia_parser.parse_source(
        "struct Point\n    x::Float64\n    y::Float64\nend\n", "test.jl"
    )
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    assert len(classes) == 1
    assert classes[0].name == "Point"


# --- functions ---


def test_extracts_functions(julia_parser: JuliaParser, sample_julia_source: str) -> None:
    result = julia_parser.parse_source(sample_julia_source, "test.jl")
    funcs = [s for s in result.symbols if s.kind in (SymbolKind.FUNCTION, SymbolKind.METHOD)]
    assert len(funcs) >= 2


def test_function_has_signature(julia_parser: JuliaParser) -> None:
    result = julia_parser.parse_source(
        "function add(a::Int, b::Int)\n    return a + b\nend\n", "test.jl"
    )
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert len(funcs) == 1
    assert funcs[0].signature is not None
    assert "add" in funcs[0].signature


def test_function_inside_module_is_method(julia_parser: JuliaParser) -> None:
    result = julia_parser.parse_source("module M\nfunction foo()\nend\nend\n", "test.jl")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    assert len(methods) >= 1
    assert any(s.name == "foo" for s in methods)


def test_function_outside_module_is_function(julia_parser: JuliaParser) -> None:
    result = julia_parser.parse_source("function standalone(x)\n    return x\nend\n", "test.jl")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert len(funcs) == 1
    assert funcs[0].name == "standalone"


# --- macros ---


def test_extracts_macro(julia_parser: JuliaParser, sample_julia_source: str) -> None:
    result = julia_parser.parse_source(sample_julia_source, "test.jl")
    macros = [s for s in result.symbols if s.name.startswith("@")]
    assert len(macros) >= 1
    assert any("assert_positive" in s.name for s in macros)


# --- relationships ---


def test_extracts_call_relationships(julia_parser: JuliaParser) -> None:
    result = julia_parser.parse_source(
        "function caller()\n    callee()\nend\nfunction callee()\nend\n", "test.jl"
    )
    calls = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    assert len(calls) >= 1


def test_symbol_count_matches_symbols(julia_parser: JuliaParser, sample_julia_source: str) -> None:
    result = julia_parser.parse_source(sample_julia_source, "test.jl")
    assert result.file_info.symbol_count == len(result.symbols)


def test_supported_extensions(julia_parser: JuliaParser) -> None:
    assert ".jl" in julia_parser.supported_extensions
