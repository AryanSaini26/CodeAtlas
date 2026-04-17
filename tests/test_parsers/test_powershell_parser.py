"""Tests for the PowerShell tree-sitter parser."""

from pathlib import Path

import pytest

from codeatlas.models import RelationshipKind, SymbolKind
from codeatlas.parsers.powershell_parser import PowerShellParser


@pytest.fixture
def ps_parser() -> PowerShellParser:
    return PowerShellParser()


@pytest.fixture
def sample_ps_path() -> Path:
    return Path(__file__).parent.parent / "fixtures" / "sample_powershell" / "sample.ps1"


@pytest.fixture
def sample_ps_source(sample_ps_path: Path) -> str:
    return sample_ps_path.read_text()


# --- basic parse ---


def test_parse_file_returns_parse_result(ps_parser: PowerShellParser, sample_ps_path: Path) -> None:
    result = ps_parser.parse_file(sample_ps_path)
    assert result.file_info.path == str(sample_ps_path)
    assert len(result.symbols) > 0


def test_parse_source_returns_parse_result(
    ps_parser: PowerShellParser, sample_ps_source: str
) -> None:
    result = ps_parser.parse_source(sample_ps_source, "test.ps1")
    assert result.file_info.path == "test.ps1"
    assert len(result.symbols) > 0


def test_file_info_language(ps_parser: PowerShellParser, sample_ps_source: str) -> None:
    result = ps_parser.parse_source(sample_ps_source, "test.ps1")
    assert result.file_info.language == "powershell"


def test_content_hash_consistent(ps_parser: PowerShellParser, sample_ps_source: str) -> None:
    r1 = ps_parser.parse_source(sample_ps_source, "test.ps1")
    r2 = ps_parser.parse_source(sample_ps_source, "test.ps1")
    assert r1.file_info.content_hash == r2.file_info.content_hash


def test_size_bytes_populated(ps_parser: PowerShellParser, sample_ps_source: str) -> None:
    result = ps_parser.parse_source(sample_ps_source, "test.ps1")
    assert result.file_info.size_bytes > 0


# --- functions ---


def test_extracts_functions(ps_parser: PowerShellParser, sample_ps_source: str) -> None:
    result = ps_parser.parse_source(sample_ps_source, "test.ps1")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert len(funcs) >= 2
    names = [s.name for s in funcs]
    assert "Get-Greeting" in names
    assert "Set-UserConfig" in names


def test_function_has_signature(ps_parser: PowerShellParser) -> None:
    result = ps_parser.parse_source(
        "function Get-Item {\n    param([string]$Name)\n    Write-Host $Name\n}\n",
        "test.ps1",
    )
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert len(funcs) == 1
    assert funcs[0].signature is not None
    assert "Get-Item" in funcs[0].signature


def test_function_with_doc_comment(ps_parser: PowerShellParser) -> None:
    result = ps_parser.parse_source(
        "# Greet a user\nfunction Greet { Write-Host 'hi' }\n", "test.ps1"
    )
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert len(funcs) == 1
    assert funcs[0].docstring is not None


# --- classes ---


def test_extracts_classes(ps_parser: PowerShellParser, sample_ps_source: str) -> None:
    result = ps_parser.parse_source(sample_ps_source, "test.ps1")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    assert len(classes) >= 2
    names = [s.name for s in classes]
    assert "UserService" in names
    assert "ConfigManager" in names


def test_class_has_methods(ps_parser: PowerShellParser, sample_ps_source: str) -> None:
    result = ps_parser.parse_source(sample_ps_source, "test.ps1")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    assert len(methods) >= 2
    method_names = [s.name for s in methods]
    assert "GetUser" in method_names
    assert "DeleteUser" in method_names


def test_method_qualified_name(ps_parser: PowerShellParser) -> None:
    result = ps_parser.parse_source(
        "class Foo {\n    [void] Bar() { Write-Host 'x' }\n}\n", "test.ps1"
    )
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    assert len(methods) == 1
    assert methods[0].qualified_name == "Foo.Bar"


def test_constructor_as_method(ps_parser: PowerShellParser) -> None:
    result = ps_parser.parse_source(
        "class MyClass {\n    MyClass([string]$v) { $this.V = $v }\n}\n", "test.ps1"
    )
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    names = [s.name for s in methods]
    assert "MyClass" in names


# --- call relationships ---


def test_extracts_call_relationships(ps_parser: PowerShellParser) -> None:
    result = ps_parser.parse_source(
        "function Caller {\n    Invoke-Custom -Name test\n}\nfunction Invoke-Custom {\n    Write-Host 'x'\n}\n",
        "test.ps1",
    )
    calls = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    assert len(calls) >= 1
    target_names = [r.target_id for r in calls]
    assert any("Invoke-Custom" in t for t in target_names)


def test_builtin_calls_skipped(ps_parser: PowerShellParser) -> None:
    result = ps_parser.parse_source(
        "function MyFunc {\n    Write-Host 'test'\n    Write-Output 'out'\n}\n",
        "test.ps1",
    )
    calls = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    assert len(calls) == 0


# --- misc ---


def test_symbol_count_matches_symbols(ps_parser: PowerShellParser, sample_ps_source: str) -> None:
    result = ps_parser.parse_source(sample_ps_source, "test.ps1")
    assert result.file_info.symbol_count == len(result.symbols)


def test_supported_extensions(ps_parser: PowerShellParser) -> None:
    exts = ps_parser.supported_extensions
    assert ".ps1" in exts
    assert ".psm1" in exts
    assert ".psd1" in exts


def test_parse_psm1_extension(ps_parser: PowerShellParser) -> None:
    result = ps_parser.parse_source("function Export-Data { Write-Host 'x' }\n", "module.psm1")
    assert result.file_info.language == "powershell"
    assert len(result.symbols) >= 1
