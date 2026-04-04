"""Tests for the Rust tree-sitter parser."""

from pathlib import Path

from codeatlas.parsers.rust_parser import RustParser


def test_parse_file_returns_parse_result(rust_parser: RustParser, sample_rust_path: Path) -> None:
    result = rust_parser.parse_file(sample_rust_path)
    assert result.file_info.path == str(sample_rust_path)
    assert len(result.symbols) > 0


def test_parse_source_returns_parse_result(
    rust_parser: RustParser, sample_rust_source: str
) -> None:
    result = rust_parser.parse_source(sample_rust_source, "test.rs")
    assert result.file_info.path == "test.rs"
    assert len(result.symbols) > 0


def test_file_info_language(rust_parser: RustParser, sample_rust_source: str) -> None:
    result = rust_parser.parse_source(sample_rust_source, "test.rs")
    assert result.file_info.language == "rust"


def test_content_hash_consistent(rust_parser: RustParser, sample_rust_source: str) -> None:
    r1 = rust_parser.parse_source(sample_rust_source, "test.rs")
    r2 = rust_parser.parse_source(sample_rust_source, "test.rs")
    assert r1.file_info.content_hash == r2.file_info.content_hash


def test_extracts_use_declarations(rust_parser: RustParser, sample_rust_source: str) -> None:
    result = rust_parser.parse_source(sample_rust_source, "test.rs")
    imports = [s for s in result.symbols if s.kind.value == "import"]
    assert len(imports) >= 2
    import_names = [s.name for s in imports]
    assert "fmt" in import_names or "HashMap" in import_names


def test_extracts_struct(rust_parser: RustParser, sample_rust_source: str) -> None:
    result = rust_parser.parse_source(sample_rust_source, "test.rs")
    structs = [s for s in result.symbols if s.kind.value == "class" and s.name == "User"]
    assert len(structs) == 1


def test_extracts_trait(rust_parser: RustParser, sample_rust_source: str) -> None:
    result = rust_parser.parse_source(sample_rust_source, "test.rs")
    traits = [s for s in result.symbols if s.kind.value == "interface"]
    assert len(traits) == 1
    assert traits[0].name == "Greeter"


def test_extracts_enum(rust_parser: RustParser, sample_rust_source: str) -> None:
    result = rust_parser.parse_source(sample_rust_source, "test.rs")
    enums = [s for s in result.symbols if s.kind.value == "enum"]
    assert len(enums) == 1
    assert enums[0].name == "Color"


def test_extracts_functions(rust_parser: RustParser, sample_rust_source: str) -> None:
    result = rust_parser.parse_source(sample_rust_source, "test.rs")
    functions = [s for s in result.symbols if s.kind.value == "function"]
    assert any(s.name == "create_user" for s in functions)


def test_extracts_impl_methods(rust_parser: RustParser, sample_rust_source: str) -> None:
    result = rust_parser.parse_source(sample_rust_source, "test.rs")
    methods = [s for s in result.symbols if s.kind.value == "method"]
    method_names = [s.name for s in methods]
    assert "new" in method_names
    assert "display" in method_names
    assert "greet" in method_names


def test_method_qualified_name_includes_type(
    rust_parser: RustParser, sample_rust_source: str
) -> None:
    result = rust_parser.parse_source(sample_rust_source, "test.rs")
    methods = [s for s in result.symbols if s.kind.value == "method"]
    # Methods on User should be qualified as User.method
    user_methods = [s for s in methods if s.qualified_name.startswith("User.")]
    assert len(user_methods) >= 2


def test_extracts_type_alias(rust_parser: RustParser, sample_rust_source: str) -> None:
    result = rust_parser.parse_source(sample_rust_source, "test.rs")
    aliases = [s for s in result.symbols if s.kind.value == "type_alias"]
    assert len(aliases) == 1
    assert aliases[0].name == "UserId"


def test_extracts_const(rust_parser: RustParser, sample_rust_source: str) -> None:
    result = rust_parser.parse_source(sample_rust_source, "test.rs")
    consts = [s for s in result.symbols if s.kind.value == "constant"]
    assert any(s.name == "MAX_USERS" for s in consts)


def test_extracts_static(rust_parser: RustParser, sample_rust_source: str) -> None:
    result = rust_parser.parse_source(sample_rust_source, "test.rs")
    statics = [s for s in result.symbols if s.kind.value == "variable"]
    assert any(s.name == "APP_NAME" for s in statics)


def test_extracts_mod(rust_parser: RustParser, sample_rust_source: str) -> None:
    result = rust_parser.parse_source(sample_rust_source, "test.rs")
    mods = [s for s in result.symbols if s.kind.value == "module"]
    assert any(s.name == "utils" for s in mods)


def test_extracts_doc_comment(rust_parser: RustParser, sample_rust_source: str) -> None:
    result = rust_parser.parse_source(sample_rust_source, "test.rs")
    user = next(s for s in result.symbols if s.name == "User" and s.kind.value == "class")
    assert user.docstring is not None
    assert "user" in user.docstring.lower()


def test_function_has_signature(rust_parser: RustParser, sample_rust_source: str) -> None:
    result = rust_parser.parse_source(sample_rust_source, "test.rs")
    func = next(s for s in result.symbols if s.name == "create_user")
    assert func.signature is not None
    assert "fn create_user" in func.signature


def test_extracts_import_relationships(rust_parser: RustParser, sample_rust_source: str) -> None:
    result = rust_parser.parse_source(sample_rust_source, "test.rs")
    import_rels = [r for r in result.relationships if r.kind.value == "imports"]
    assert len(import_rels) >= 2


def test_extracts_implements_relationships(
    rust_parser: RustParser, sample_rust_source: str
) -> None:
    result = rust_parser.parse_source(sample_rust_source, "test.rs")
    impl_rels = [r for r in result.relationships if r.kind.value == "implements"]
    # User implements Greeter and fmt::Display
    assert len(impl_rels) >= 1


def test_extracts_calls_relationships(rust_parser: RustParser, sample_rust_source: str) -> None:
    result = rust_parser.parse_source(sample_rust_source, "test.rs")
    call_rels = [r for r in result.relationships if r.kind.value == "calls"]
    assert len(call_rels) >= 1


def test_empty_source(rust_parser: RustParser) -> None:
    result = rust_parser.parse_source("", "empty.rs")
    assert len(result.symbols) == 0
    assert len(result.relationships) == 0


def test_symbol_ids_unique(rust_parser: RustParser, sample_rust_source: str) -> None:
    result = rust_parser.parse_source(sample_rust_source, "test.rs")
    ids = [s.id for s in result.symbols]
    assert len(ids) == len(set(ids))


def test_symbol_count_matches(rust_parser: RustParser, sample_rust_source: str) -> None:
    result = rust_parser.parse_source(sample_rust_source, "test.rs")
    assert result.file_info.symbol_count == len(result.symbols)
