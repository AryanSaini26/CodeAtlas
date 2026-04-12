"""Tests for the PHP tree-sitter parser."""

from pathlib import Path

import pytest

from codeatlas.models import SymbolKind
from codeatlas.parsers.php_parser import PhpParser


def test_parse_file_returns_parse_result(php_parser: PhpParser, sample_php_path: Path) -> None:
    result = php_parser.parse_file(sample_php_path)
    assert result.file_info.path == str(sample_php_path)
    assert len(result.symbols) > 0


def test_parse_source_returns_parse_result(php_parser: PhpParser, sample_php_source: str) -> None:
    result = php_parser.parse_source(sample_php_source, "test.php")
    assert result.file_info.path == "test.php"
    assert len(result.symbols) > 0


def test_file_info_language(php_parser: PhpParser, sample_php_source: str) -> None:
    result = php_parser.parse_source(sample_php_source, "test.php")
    assert result.file_info.language == "php"


def test_content_hash_consistent(php_parser: PhpParser, sample_php_source: str) -> None:
    r1 = php_parser.parse_source(sample_php_source, "test.php")
    r2 = php_parser.parse_source(sample_php_source, "test.php")
    assert r1.file_info.content_hash == r2.file_info.content_hash


def test_extracts_use_as_import(php_parser: PhpParser, sample_php_source: str) -> None:
    result = php_parser.parse_source(sample_php_source, "test.php")
    imports = [s for s in result.symbols if s.kind == SymbolKind.IMPORT]
    assert len(imports) >= 1
    names = [s.name for s in imports]
    assert "User" in names


def test_extracts_constant(php_parser: PhpParser, sample_php_source: str) -> None:
    result = php_parser.parse_source(sample_php_source, "test.php")
    consts = [s for s in result.symbols if s.kind == SymbolKind.CONSTANT]
    assert any(s.name == "MAX_RETRIES" for s in consts)


def test_extracts_interface(php_parser: PhpParser, sample_php_source: str) -> None:
    result = php_parser.parse_source(sample_php_source, "test.php")
    interfaces = [s for s in result.symbols if s.kind == SymbolKind.INTERFACE]
    assert len(interfaces) >= 1
    assert any(s.name == "Greeter" for s in interfaces)


def test_extracts_class(php_parser: PhpParser, sample_php_source: str) -> None:
    result = php_parser.parse_source(sample_php_source, "test.php")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    names = [s.name for s in classes]
    assert "UserService" in names
    assert "AdminService" in names


def test_extracts_methods(php_parser: PhpParser, sample_php_source: str) -> None:
    result = php_parser.parse_source(sample_php_source, "test.php")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    names = [s.name for s in methods]
    assert "createUser" in names
    assert "create" in names


def test_extracts_toplevel_function(php_parser: PhpParser, sample_php_source: str) -> None:
    result = php_parser.parse_source(sample_php_source, "test.php")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert any(s.name == "processAll" for s in funcs)


def test_method_qualified_name_includes_class(
    php_parser: PhpParser, sample_php_source: str
) -> None:
    result = php_parser.parse_source(sample_php_source, "test.php")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    qnames = [s.qualified_name for s in methods]
    assert any("UserService." in qn for qn in qnames)


def test_method_signature_present(php_parser: PhpParser) -> None:
    src = "<?php\nclass Foo {\n    public function bar(string $x): int { return 0; }\n}"
    result = php_parser.parse_source(src, "test.php")
    methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
    assert len(methods) == 1
    assert methods[0].signature is not None
    assert "bar" in methods[0].signature


def test_docstring_extraction(php_parser: PhpParser) -> None:
    src = "<?php\n// Creates a user\nfunction createUser(): void {}"
    result = php_parser.parse_source(src, "test.php")
    funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
    assert len(funcs) == 1
    assert funcs[0].docstring is not None
    assert "Creates a user" in funcs[0].docstring


def test_class_docstring(php_parser: PhpParser, sample_php_source: str) -> None:
    result = php_parser.parse_source(sample_php_source, "test.php")
    classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
    svc = next((c for c in classes if c.name == "UserService"), None)
    assert svc is not None
    assert svc.docstring is not None


def test_inheritance_relationship(php_parser: PhpParser, sample_php_source: str) -> None:
    result = php_parser.parse_source(sample_php_source, "test.php")
    inherits = [r for r in result.relationships if r.kind.value == "inherits"]
    assert len(inherits) >= 1
    sources = [r.source_id for r in inherits]
    assert any("UserService" in s for s in sources)


def test_implements_relationship(php_parser: PhpParser, sample_php_source: str) -> None:
    result = php_parser.parse_source(sample_php_source, "test.php")
    impls = [r for r in result.relationships if r.kind.value == "implements"]
    assert len(impls) >= 1
    assert any("Greeter" in r.target_id for r in impls)


def test_extracts_call_relationships(php_parser: PhpParser, sample_php_source: str) -> None:
    result = php_parser.parse_source(sample_php_source, "test.php")
    calls = [r for r in result.relationships if r.kind.value == "calls"]
    assert len(calls) >= 1


def test_extracts_import_relationships(php_parser: PhpParser, sample_php_source: str) -> None:
    result = php_parser.parse_source(sample_php_source, "test.php")
    imports = [r for r in result.relationships if r.kind.value == "imports"]
    assert len(imports) >= 1


def test_supported_extensions(php_parser: PhpParser) -> None:
    assert ".php" in php_parser.supported_extensions


def test_language_property(php_parser: PhpParser) -> None:
    assert php_parser.language == "php"


def test_empty_file(php_parser: PhpParser) -> None:
    result = php_parser.parse_source("<?php\n", "empty.php")
    assert result.file_info.language == "php"
    assert result.symbols == []


def test_symbol_count_in_file_info(php_parser: PhpParser, sample_php_source: str) -> None:
    result = php_parser.parse_source(sample_php_source, "test.php")
    assert result.file_info.symbol_count == len(result.symbols)
    assert result.file_info.relationship_count == len(result.relationships)


@pytest.mark.parametrize(
    "source,expected_kind",
    [
        ("<?php\nclass Foo {}", SymbolKind.CLASS),
        ("<?php\ninterface Bar { public function doIt(): void; }", SymbolKind.INTERFACE),
        ("<?php\nconst MAX = 42;", SymbolKind.CONSTANT),
        ("<?php\nfunction doIt(): void {}", SymbolKind.FUNCTION),
        ("<?php\nuse App\\Models\\User;", SymbolKind.IMPORT),
    ],
)
def test_symbol_kinds(php_parser: PhpParser, source: str, expected_kind: SymbolKind) -> None:
    result = php_parser.parse_source(source, "test.php")
    kinds = [s.kind for s in result.symbols]
    assert expected_kind in kinds
