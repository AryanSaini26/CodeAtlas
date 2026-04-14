"""Tests for the Haskell tree-sitter parser."""

from pathlib import Path

import pytest

from codeatlas.models import RelationshipKind, SymbolKind
from codeatlas.parsers.haskell_parser import HaskellParser


def test_parse_file_returns_parse_result(
    haskell_parser: HaskellParser, sample_haskell_path: Path
) -> None:
    result = haskell_parser.parse_file(sample_haskell_path)
    assert result.file_info.path == str(sample_haskell_path)
    assert len(result.symbols) > 0


def test_parse_source_returns_parse_result(
    haskell_parser: HaskellParser, sample_haskell_source: str
) -> None:
    result = haskell_parser.parse_source(sample_haskell_source, "test.hs")
    assert result.file_info.path == "test.hs"
    assert len(result.symbols) > 0


def test_file_info_language(haskell_parser: HaskellParser, sample_haskell_source: str) -> None:
    result = haskell_parser.parse_source(sample_haskell_source, "test.hs")
    assert result.file_info.language == "haskell"


def test_content_hash_consistent(haskell_parser: HaskellParser, sample_haskell_source: str) -> None:
    r1 = haskell_parser.parse_source(sample_haskell_source, "test.hs")
    r2 = haskell_parser.parse_source(sample_haskell_source, "test.hs")
    assert r1.file_info.content_hash == r2.file_info.content_hash


def test_extracts_imports(haskell_parser: HaskellParser, sample_haskell_source: str) -> None:
    result = haskell_parser.parse_source(sample_haskell_source, "test.hs")
    imports = [s for s in result.symbols if s.kind == SymbolKind.IMPORT]
    assert len(imports) >= 1
    names = [s.name for s in imports]
    assert any("Data.List" in n for n in names)


def test_extracts_data_type_as_class(
    haskell_parser: HaskellParser, sample_haskell_source: str
) -> None:
    result = haskell_parser.parse_source(sample_haskell_source, "test.hs")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    assert len(classes) >= 1
    names = [s.name for s in classes]
    assert "Animal" in names


def test_extracts_type_alias(haskell_parser: HaskellParser, sample_haskell_source: str) -> None:
    result = haskell_parser.parse_source(sample_haskell_source, "test.hs")
    aliases = [s for s in result.symbols if s.kind == SymbolKind.TYPE_ALIAS]
    assert len(aliases) >= 1
    assert any(s.name == "Name" for s in aliases)


def test_extracts_newtype_as_class(
    haskell_parser: HaskellParser, sample_haskell_source: str
) -> None:
    result = haskell_parser.parse_source(sample_haskell_source, "test.hs")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    names = [s.name for s in classes]
    assert "UserId" in names


def test_extracts_typeclass_as_interface(
    haskell_parser: HaskellParser, sample_haskell_source: str
) -> None:
    result = haskell_parser.parse_source(sample_haskell_source, "test.hs")
    interfaces = [s for s in result.symbols if s.kind == SymbolKind.INTERFACE]
    assert len(interfaces) >= 1
    assert any(s.name == "Speakable" for s in interfaces)


def test_extracts_functions(haskell_parser: HaskellParser, sample_haskell_source: str) -> None:
    result = haskell_parser.parse_source(sample_haskell_source, "test.hs")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    names = [s.name for s in funcs]
    assert "greet" in names
    assert "add" in names
    assert "main" in names


def test_function_qualified_name_includes_module(
    haskell_parser: HaskellParser, sample_haskell_source: str
) -> None:
    result = haskell_parser.parse_source(sample_haskell_source, "test.hs")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    qnames = [s.qualified_name for s in funcs]
    assert any("SampleModule.greet" == qn for qn in qnames)


def test_function_signature(haskell_parser: HaskellParser, sample_haskell_source: str) -> None:
    result = haskell_parser.parse_source(sample_haskell_source, "test.hs")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    greet = next((f for f in funcs if f.name == "greet"), None)
    assert greet is not None
    assert greet.signature is not None
    assert "greet" in greet.signature


def test_extracts_imports_relationship(
    haskell_parser: HaskellParser, sample_haskell_source: str
) -> None:
    result = haskell_parser.parse_source(sample_haskell_source, "test.hs")
    import_rels = [r for r in result.relationships if r.kind == RelationshipKind.IMPORTS]
    assert len(import_rels) >= 1
    targets = [r.target_id for r in import_rels]
    assert any("Data.List" in t for t in targets)


def test_extracts_call_relationships(
    haskell_parser: HaskellParser, sample_haskell_source: str
) -> None:
    result = haskell_parser.parse_source(sample_haskell_source, "test.hs")
    calls = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    assert len(calls) >= 1


def test_main_calls_greet(haskell_parser: HaskellParser, sample_haskell_source: str) -> None:
    result = haskell_parser.parse_source(sample_haskell_source, "test.hs")
    calls = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    sources = [r.source_id for r in calls]
    targets = [r.target_id for r in calls]
    assert any("main" in s for s in sources)
    assert any("greet" in t for t in targets)


def test_prelude_not_captured(haskell_parser: HaskellParser) -> None:
    source = 'module M where\nfoo = putStrLn "hello"\n'
    result = haskell_parser.parse_source(source, "test.hs")
    targets = [r.target_id for r in result.relationships if r.kind == RelationshipKind.CALLS]
    assert not any("putStrLn" in t for t in targets)


def test_supported_extensions(haskell_parser: HaskellParser) -> None:
    assert ".hs" in haskell_parser.supported_extensions
    assert ".lhs" in haskell_parser.supported_extensions


def test_language_property(haskell_parser: HaskellParser) -> None:
    assert haskell_parser.language == "haskell"


def test_empty_file(haskell_parser: HaskellParser) -> None:
    result = haskell_parser.parse_source("", "empty.hs")
    assert result.file_info.language == "haskell"
    assert result.symbols == []
    assert result.relationships == []


def test_symbol_count_in_file_info(
    haskell_parser: HaskellParser, sample_haskell_source: str
) -> None:
    result = haskell_parser.parse_source(sample_haskell_source, "test.hs")
    assert result.file_info.symbol_count == len(result.symbols)
    assert result.file_info.relationship_count == len(result.relationships)


@pytest.mark.parametrize(
    "source,expected_kind",
    [
        ("module M where\ndata Color = Red | Green\n", SymbolKind.CLASS),
        ("module M where\ntype Name = String\n", SymbolKind.TYPE_ALIAS),
        ("module M where\nclass Eq a where\n  eq :: a -> a -> Bool\n", SymbolKind.INTERFACE),
        ("module M where\nfoo :: Int\nfoo = 42\n", SymbolKind.FUNCTION),
    ],
)
def test_symbol_kinds(
    haskell_parser: HaskellParser, source: str, expected_kind: SymbolKind
) -> None:
    result = haskell_parser.parse_source(source, "test.hs")
    kinds = [s.kind for s in result.symbols]
    assert expected_kind in kinds
