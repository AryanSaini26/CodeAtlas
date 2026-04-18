"""Tests for the TypeScript AST parser."""

from pathlib import Path

from codeatlas.models import ParseResult, RelationshipKind, SymbolKind
from codeatlas.parsers.typescript_parser import TypeScriptParser


def _names(result: ParseResult) -> set[str]:
    return {s.name for s in result.symbols}


def _kinds(result: ParseResult, kind: SymbolKind) -> list[str]:
    return [s.name for s in result.symbols if s.kind == kind]


# --- File-level tests ---


def test_parse_file_returns_parse_result(
    typescript_parser: TypeScriptParser, sample_typescript_path: Path
) -> None:
    result = typescript_parser.parse_file(sample_typescript_path)
    assert isinstance(result, ParseResult)


def test_parse_source_returns_parse_result(
    typescript_parser: TypeScriptParser, sample_typescript_source: str
) -> None:
    result = typescript_parser.parse_source(sample_typescript_source, "test.ts")
    assert isinstance(result, ParseResult)


def test_file_info_language(
    typescript_parser: TypeScriptParser, sample_typescript_source: str
) -> None:
    result = typescript_parser.parse_source(sample_typescript_source, "test.ts")
    assert result.file_info.language == "typescript"


def test_file_info_content_hash_consistent(
    typescript_parser: TypeScriptParser, sample_typescript_source: str
) -> None:
    r1 = typescript_parser.parse_source(sample_typescript_source, "test.ts")
    r2 = typescript_parser.parse_source(sample_typescript_source, "test.ts")
    assert r1.file_info.content_hash == r2.file_info.content_hash


# --- Symbol extraction ---


def test_extracts_function_declaration(
    typescript_parser: TypeScriptParser, sample_typescript_source: str
) -> None:
    result = typescript_parser.parse_source(sample_typescript_source, "test.ts")
    assert "greet" in _names(result)


def test_extracts_arrow_function(
    typescript_parser: TypeScriptParser, sample_typescript_source: str
) -> None:
    result = typescript_parser.parse_source(sample_typescript_source, "test.ts")
    assert "formatUser" in _names(result)


def test_extracts_generic_function(
    typescript_parser: TypeScriptParser, sample_typescript_source: str
) -> None:
    result = typescript_parser.parse_source(sample_typescript_source, "test.ts")
    assert "identity" in _names(result)


def test_extracts_class(typescript_parser: TypeScriptParser, sample_typescript_source: str) -> None:
    result = typescript_parser.parse_source(sample_typescript_source, "test.ts")
    assert "BaseService" in _names(result)
    assert "UserService" in _names(result)


def test_extracts_interface(
    typescript_parser: TypeScriptParser, sample_typescript_source: str
) -> None:
    result = typescript_parser.parse_source(sample_typescript_source, "test.ts")
    assert "User" in _names(result)
    assert "Describable" in _names(result)


def test_extracts_enum(typescript_parser: TypeScriptParser, sample_typescript_source: str) -> None:
    result = typescript_parser.parse_source(sample_typescript_source, "test.ts")
    assert "TaskStatus" in _names(result)


def test_extracts_type_alias(
    typescript_parser: TypeScriptParser, sample_typescript_source: str
) -> None:
    result = typescript_parser.parse_source(sample_typescript_source, "test.ts")
    assert "Result" in _names(result)
    assert "UserCallback" in _names(result)


def test_extracts_class_methods(
    typescript_parser: TypeScriptParser, sample_typescript_source: str
) -> None:
    result = typescript_parser.parse_source(sample_typescript_source, "test.ts")
    assert "getName" in _names(result)
    assert "addUser" in _names(result)
    assert "findById" in _names(result)
    assert "describe" in _names(result)


def test_extracts_namespace(
    typescript_parser: TypeScriptParser, sample_typescript_source: str
) -> None:
    result = typescript_parser.parse_source(sample_typescript_source, "test.ts")
    assert "Utils" in _names(result)


def test_extracts_namespace_member(
    typescript_parser: TypeScriptParser, sample_typescript_source: str
) -> None:
    result = typescript_parser.parse_source(sample_typescript_source, "test.ts")
    assert "slugify" in _names(result)


def test_symbol_kinds_correct(
    typescript_parser: TypeScriptParser, sample_typescript_source: str
) -> None:
    result = typescript_parser.parse_source(sample_typescript_source, "test.ts")
    classes = _kinds(result, SymbolKind.CLASS)
    interfaces = _kinds(result, SymbolKind.INTERFACE)
    enums = _kinds(result, SymbolKind.ENUM)
    type_aliases = _kinds(result, SymbolKind.TYPE_ALIAS)
    assert "BaseService" in classes
    assert "User" in interfaces
    assert "TaskStatus" in enums
    assert "Result" in type_aliases


# --- Relationship extraction ---


def test_extracts_import_relationships(
    typescript_parser: TypeScriptParser, sample_typescript_source: str
) -> None:
    result = typescript_parser.parse_source(sample_typescript_source, "test.ts")
    rels = [r for r in result.relationships if r.kind == RelationshipKind.IMPORTS]
    assert len(rels) > 0


def test_extracts_inheritance_relationship(
    typescript_parser: TypeScriptParser, sample_typescript_source: str
) -> None:
    result = typescript_parser.parse_source(sample_typescript_source, "test.ts")
    rels = [r for r in result.relationships if r.kind == RelationshipKind.INHERITS]
    targets = {r.target_id for r in rels}
    assert any("BaseService" in t for t in targets)


def test_extracts_implements_relationship(
    typescript_parser: TypeScriptParser, sample_typescript_source: str
) -> None:
    result = typescript_parser.parse_source(sample_typescript_source, "test.ts")
    rels = [r for r in result.relationships if r.kind == RelationshipKind.IMPLEMENTS]
    targets = {r.target_id for r in rels}
    assert any("Describable" in t for t in targets)


def test_extracts_calls_relationships(
    typescript_parser: TypeScriptParser, sample_typescript_source: str
) -> None:
    result = typescript_parser.parse_source(sample_typescript_source, "test.ts")
    rels = [r for r in result.relationships if r.kind == RelationshipKind.CALLS]
    assert len(rels) > 0


# --- Edge cases ---


def test_empty_source(typescript_parser: TypeScriptParser) -> None:
    result = typescript_parser.parse_source("", "empty.ts")
    assert result.file_info.language == "typescript"
    assert result.symbols == []
    assert result.relationships == []


def test_symbol_ids_unique(
    typescript_parser: TypeScriptParser, sample_typescript_source: str
) -> None:
    result = typescript_parser.parse_source(sample_typescript_source, "test.ts")
    ids = [s.id for s in result.symbols]
    assert len(ids) == len(set(ids))


def test_tsx_extension(typescript_parser: TypeScriptParser) -> None:
    source = "const App = () => <div>Hello</div>;\nexport default App;"
    result = typescript_parser.parse_source(source, "app.tsx")
    assert result.file_info.language == "typescript"


def test_type_alias_detected(typescript_parser: TypeScriptParser) -> None:
    source = "export type UserId = string;\nexport type Maybe<T> = T | null;\n"
    result = typescript_parser.parse_source(source, "types.ts")
    type_aliases = [s.name for s in result.symbols if s.kind == SymbolKind.TYPE_ALIAS]
    assert "UserId" in type_aliases
    assert "Maybe" in type_aliases


def test_interface_inheritance(typescript_parser: TypeScriptParser) -> None:
    source = "interface Animal { name: string; }\ninterface Dog extends Animal { bark(): void; }\n"
    result = typescript_parser.parse_source(source, "animals.ts")
    inherit_rels = [r for r in result.relationships if r.kind == RelationshipKind.INHERITS]
    assert any(r.target_id.endswith("Animal") for r in inherit_rels)
