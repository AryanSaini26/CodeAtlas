"""Tests for the Svelte component parser."""

from pathlib import Path

import pytest

from codeatlas.models import RelationshipKind, SymbolKind
from codeatlas.parsers.svelte_parser import SvelteParser


@pytest.fixture
def svelte_parser() -> SvelteParser:
    return SvelteParser()


@pytest.fixture
def sample_svelte_path() -> Path:
    return Path(__file__).parent.parent / "fixtures" / "sample_svelte" / "App.svelte"


@pytest.fixture
def sample_svelte_source(sample_svelte_path: Path) -> str:
    return sample_svelte_path.read_text()


# --- basic parse ---


def test_parse_file_returns_parse_result(
    svelte_parser: SvelteParser, sample_svelte_path: Path
) -> None:
    result = svelte_parser.parse_file(sample_svelte_path)
    assert result.file_info.path == str(sample_svelte_path)
    assert len(result.symbols) > 0


def test_parse_source_returns_parse_result(
    svelte_parser: SvelteParser, sample_svelte_source: str
) -> None:
    result = svelte_parser.parse_source(sample_svelte_source, "App.svelte")
    assert result.file_info.path == "App.svelte"
    assert len(result.symbols) > 0


def test_file_info_language(svelte_parser: SvelteParser, sample_svelte_source: str) -> None:
    result = svelte_parser.parse_source(sample_svelte_source, "App.svelte")
    assert result.file_info.language == "svelte"


def test_content_hash_consistent(svelte_parser: SvelteParser, sample_svelte_source: str) -> None:
    r1 = svelte_parser.parse_source(sample_svelte_source, "App.svelte")
    r2 = svelte_parser.parse_source(sample_svelte_source, "App.svelte")
    assert r1.file_info.content_hash == r2.file_info.content_hash


def test_size_bytes_populated(svelte_parser: SvelteParser, sample_svelte_source: str) -> None:
    result = svelte_parser.parse_source(sample_svelte_source, "App.svelte")
    assert result.file_info.size_bytes > 0


# --- component symbol ---


def test_emits_component_symbol(svelte_parser: SvelteParser, sample_svelte_source: str) -> None:
    result = svelte_parser.parse_source(sample_svelte_source, "App.svelte")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    assert len(classes) >= 1
    assert any(s.name == "App" for s in classes)


def test_component_name_from_filename(svelte_parser: SvelteParser) -> None:
    result = svelte_parser.parse_source("<script>\nlet x = 1;\n</script>\n", "MyWidget.svelte")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    assert any(s.name == "MyWidget" for s in classes)


# --- imports ---


def test_extracts_imports(svelte_parser: SvelteParser, sample_svelte_source: str) -> None:
    result = svelte_parser.parse_source(sample_svelte_source, "App.svelte")
    imports = [s for s in result.symbols if s.kind == SymbolKind.IMPORT]
    assert len(imports) >= 2


def test_extracts_svelte_import(svelte_parser: SvelteParser, sample_svelte_source: str) -> None:
    result = svelte_parser.parse_source(sample_svelte_source, "App.svelte")
    imports = [s for s in result.symbols if s.kind == SymbolKind.IMPORT]
    names = [s.name for s in imports]
    assert "svelte" in names


def test_import_creates_relationship(
    svelte_parser: SvelteParser, sample_svelte_source: str
) -> None:
    result = svelte_parser.parse_source(sample_svelte_source, "App.svelte")
    import_rels = [r for r in result.relationships if r.kind == RelationshipKind.IMPORTS]
    assert len(import_rels) >= 1


# --- functions ---


def test_extracts_functions(svelte_parser: SvelteParser, sample_svelte_source: str) -> None:
    result = svelte_parser.parse_source(sample_svelte_source, "App.svelte")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert len(funcs) >= 2
    names = [s.name for s in funcs]
    assert "increment" in names
    assert "fetchData" in names


def test_function_has_signature(svelte_parser: SvelteParser) -> None:
    result = svelte_parser.parse_source(
        "<script>\nfunction greet(name) { return 'hello'; }\n</script>\n",
        "Greet.svelte",
    )
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert len(funcs) == 1
    assert funcs[0].signature is not None
    assert "greet" in funcs[0].signature


def test_async_function_detected(svelte_parser: SvelteParser, sample_svelte_source: str) -> None:
    result = svelte_parser.parse_source(sample_svelte_source, "App.svelte")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    fetch_fn = next((f for f in funcs if f.name == "fetchData"), None)
    assert fetch_fn is not None
    assert fetch_fn.signature is not None
    assert "async" in fetch_fn.signature


# --- no script block ---


def test_no_script_block(svelte_parser: SvelteParser) -> None:
    result = svelte_parser.parse_source("<div>Hello World</div>\n", "Static.svelte")
    # Should still have the component symbol
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    assert any(s.name == "Static" for s in classes)


# --- call relationships ---


def test_extracts_call_relationships(svelte_parser: SvelteParser) -> None:
    result = svelte_parser.parse_source(
        "<script>\nfunction main() { helper(); }\nfunction helper() {}\n</script>\n",
        "Comp.svelte",
    )
    calls = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    assert len(calls) >= 1


# --- misc ---


def test_symbol_count_matches_symbols(
    svelte_parser: SvelteParser, sample_svelte_source: str
) -> None:
    result = svelte_parser.parse_source(sample_svelte_source, "App.svelte")
    assert result.file_info.symbol_count == len(result.symbols)


def test_supported_extensions(svelte_parser: SvelteParser) -> None:
    assert ".svelte" in svelte_parser.supported_extensions
