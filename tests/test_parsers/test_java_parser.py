"""Tests for the Java tree-sitter parser."""

from pathlib import Path

from codeatlas.parsers.java_parser import JavaParser


def test_parse_file_returns_parse_result(java_parser: JavaParser, sample_java_path: Path) -> None:
    result = java_parser.parse_file(sample_java_path)
    assert result.file_info.path == str(sample_java_path)
    assert len(result.symbols) > 0


def test_parse_source_returns_parse_result(
    java_parser: JavaParser, sample_java_source: str
) -> None:
    result = java_parser.parse_source(sample_java_source, "Test.java")
    assert result.file_info.path == "Test.java"
    assert len(result.symbols) > 0


def test_file_info_language(java_parser: JavaParser, sample_java_source: str) -> None:
    result = java_parser.parse_source(sample_java_source, "Test.java")
    assert result.file_info.language == "java"


def test_content_hash_consistent(java_parser: JavaParser, sample_java_source: str) -> None:
    r1 = java_parser.parse_source(sample_java_source, "Test.java")
    r2 = java_parser.parse_source(sample_java_source, "Test.java")
    assert r1.file_info.content_hash == r2.file_info.content_hash


def test_extracts_package(java_parser: JavaParser, sample_java_source: str) -> None:
    result = java_parser.parse_source(sample_java_source, "Test.java")
    packages = [s for s in result.symbols if s.kind.value == "module"]
    assert len(packages) == 1
    assert "com.example.app" in packages[0].qualified_name


def test_extracts_imports(java_parser: JavaParser, sample_java_source: str) -> None:
    result = java_parser.parse_source(sample_java_source, "Test.java")
    imports = [s for s in result.symbols if s.kind.value == "import"]
    assert len(imports) >= 2
    import_names = [s.name for s in imports]
    assert "List" in import_names
    assert "Optional" in import_names


def test_extracts_class(java_parser: JavaParser, sample_java_source: str) -> None:
    result = java_parser.parse_source(sample_java_source, "Test.java")
    classes = [s for s in result.symbols if s.kind.value == "class" and s.name == "User"]
    assert len(classes) == 1


def test_extracts_interface(java_parser: JavaParser, sample_java_source: str) -> None:
    result = java_parser.parse_source(sample_java_source, "Test.java")
    interfaces = [s for s in result.symbols if s.kind.value == "interface"]
    assert len(interfaces) == 1
    assert interfaces[0].name == "UserService"


def test_extracts_enum(java_parser: JavaParser, sample_java_source: str) -> None:
    result = java_parser.parse_source(sample_java_source, "Test.java")
    enums = [s for s in result.symbols if s.kind.value == "enum"]
    assert len(enums) == 1
    assert enums[0].name == "Role"


def test_extracts_record(java_parser: JavaParser, sample_java_source: str) -> None:
    result = java_parser.parse_source(sample_java_source, "Test.java")
    records = [s for s in result.symbols if s.name == "Point"]
    assert len(records) == 1
    assert records[0].signature is not None
    assert "record Point" in records[0].signature


def test_extracts_methods(java_parser: JavaParser, sample_java_source: str) -> None:
    result = java_parser.parse_source(sample_java_source, "Test.java")
    methods = [s for s in result.symbols if s.kind.value == "method"]
    method_names = [s.name for s in methods]
    assert "getName" in method_names
    assert "setName" in method_names
    assert "create" in method_names


def test_extracts_constructor(java_parser: JavaParser, sample_java_source: str) -> None:
    result = java_parser.parse_source(sample_java_source, "Test.java")
    methods = [s for s in result.symbols if s.kind.value == "method"]
    # Constructor appears as a method with the class name
    constructors = [s for s in methods if s.name == "User"]
    assert len(constructors) >= 1


def test_method_qualified_name(java_parser: JavaParser, sample_java_source: str) -> None:
    result = java_parser.parse_source(sample_java_source, "Test.java")
    methods = [s for s in result.symbols if s.kind.value == "method"]
    get_name = next(s for s in methods if s.name == "getName")
    assert get_name.qualified_name == "User.getName"


def test_extracts_fields(java_parser: JavaParser, sample_java_source: str) -> None:
    result = java_parser.parse_source(sample_java_source, "Test.java")
    fields = [s for s in result.symbols if s.kind.value == "variable"]
    field_names = [s.name for s in fields]
    assert "name" in field_names
    assert "age" in field_names


def test_extracts_constants(java_parser: JavaParser, sample_java_source: str) -> None:
    result = java_parser.parse_source(sample_java_source, "Test.java")
    consts = [s for s in result.symbols if s.kind.value == "constant"]
    assert any(s.name == "MAX_AGE" for s in consts)


def test_extracts_javadoc(java_parser: JavaParser, sample_java_source: str) -> None:
    result = java_parser.parse_source(sample_java_source, "Test.java")
    user = next(s for s in result.symbols if s.name == "User" and s.kind.value == "class")
    assert user.docstring is not None
    assert "user" in user.docstring.lower()


def test_method_has_signature(java_parser: JavaParser, sample_java_source: str) -> None:
    result = java_parser.parse_source(sample_java_source, "Test.java")
    methods = [s for s in result.symbols if s.kind.value == "method"]
    get_name = next(s for s in methods if s.name == "getName")
    assert get_name.signature is not None
    assert "String" in get_name.signature


def test_extracts_inheritance(java_parser: JavaParser, sample_java_source: str) -> None:
    result = java_parser.parse_source(sample_java_source, "Test.java")
    inherits = [r for r in result.relationships if r.kind.value == "inherits"]
    # User extends BaseEntity
    targets = [r.target_id for r in inherits]
    assert any("BaseEntity" in t for t in targets)


def test_extracts_implements(java_parser: JavaParser, sample_java_source: str) -> None:
    result = java_parser.parse_source(sample_java_source, "Test.java")
    impls = [r for r in result.relationships if r.kind.value == "implements"]
    targets = [r.target_id for r in impls]
    assert any("Serializable" in t for t in targets)


def test_extracts_import_relationships(java_parser: JavaParser, sample_java_source: str) -> None:
    result = java_parser.parse_source(sample_java_source, "Test.java")
    import_rels = [r for r in result.relationships if r.kind.value == "imports"]
    assert len(import_rels) >= 2


def test_extracts_calls_relationships(java_parser: JavaParser, sample_java_source: str) -> None:
    result = java_parser.parse_source(sample_java_source, "Test.java")
    call_rels = [r for r in result.relationships if r.kind.value == "calls"]
    assert len(call_rels) >= 1


def test_empty_source(java_parser: JavaParser) -> None:
    result = java_parser.parse_source("", "Empty.java")
    assert len(result.symbols) == 0
    assert len(result.relationships) == 0


def test_symbol_ids_unique(java_parser: JavaParser, sample_java_source: str) -> None:
    result = java_parser.parse_source(sample_java_source, "Test.java")
    ids = [s.id for s in result.symbols]
    assert len(ids) == len(set(ids))


def test_symbol_count_matches(java_parser: JavaParser, sample_java_source: str) -> None:
    result = java_parser.parse_source(sample_java_source, "Test.java")
    assert result.file_info.symbol_count == len(result.symbols)
