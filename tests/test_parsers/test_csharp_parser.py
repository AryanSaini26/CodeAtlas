"""Tests for the C# tree-sitter parser."""

from pathlib import Path

from codeatlas.parsers.csharp_parser import CSharpParser


def test_parse_file_returns_parse_result(
    csharp_parser: CSharpParser, sample_csharp_path: Path
) -> None:
    result = csharp_parser.parse_file(sample_csharp_path)
    assert result.file_info.path == str(sample_csharp_path)
    assert len(result.symbols) > 0


def test_parse_source_returns_parse_result(
    csharp_parser: CSharpParser, sample_csharp_source: str
) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    assert result.file_info.path == "test.cs"
    assert len(result.symbols) > 0


def test_file_info_language(csharp_parser: CSharpParser, sample_csharp_source: str) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    assert result.file_info.language == "csharp"


def test_content_hash_consistent(csharp_parser: CSharpParser, sample_csharp_source: str) -> None:
    r1 = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    r2 = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    assert r1.file_info.content_hash == r2.file_info.content_hash


def test_extracts_using_directives(csharp_parser: CSharpParser, sample_csharp_source: str) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    imports = [s for s in result.symbols if s.kind.value == "import"]
    import_names = [s.name for s in imports]
    assert "System" in import_names
    assert "Generic" in import_names
    assert "Linq" in import_names


def test_extracts_namespace(csharp_parser: CSharpParser, sample_csharp_source: str) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    namespaces = [s for s in result.symbols if s.kind.value == "namespace"]
    assert len(namespaces) == 1
    assert namespaces[0].name == "MyApp.Models"


def test_extracts_class(csharp_parser: CSharpParser, sample_csharp_source: str) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    classes = [s for s in result.symbols if s.kind.value == "class" and s.name == "User"]
    assert len(classes) == 1
    assert classes[0].qualified_name == "MyApp.Models.User"


def test_extracts_interface(csharp_parser: CSharpParser, sample_csharp_source: str) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    interfaces = [s for s in result.symbols if s.kind.value == "interface"]
    assert len(interfaces) == 1
    assert interfaces[0].name == "IProcessor"


def test_extracts_enum(csharp_parser: CSharpParser, sample_csharp_source: str) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    enums = [s for s in result.symbols if s.kind.value == "enum"]
    assert len(enums) == 1
    assert enums[0].name == "UserRole"


def test_extracts_struct(csharp_parser: CSharpParser, sample_csharp_source: str) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    structs = [s for s in result.symbols if s.kind.value == "class" and s.name == "Point"]
    assert len(structs) == 1


def test_extracts_record(csharp_parser: CSharpParser, sample_csharp_source: str) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    records = [s for s in result.symbols if s.kind.value == "class" and s.name == "UserDto"]
    assert len(records) == 1


def test_extracts_methods(csharp_parser: CSharpParser, sample_csharp_source: str) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    methods = [s for s in result.symbols if s.kind.value == "method"]
    method_names = [s.name for s in methods]
    assert "Validate" in method_names
    assert "Create" in method_names
    assert "LogAction" in method_names


def test_extracts_constructor(csharp_parser: CSharpParser, sample_csharp_source: str) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    methods = [s for s in result.symbols if s.kind.value == "method"]
    method_names = [s.name for s in methods]
    assert "User" in method_names


def test_method_qualified_name(csharp_parser: CSharpParser, sample_csharp_source: str) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    validate = next(s for s in result.symbols if s.name == "Validate")
    assert validate.qualified_name == "MyApp.Models.User.Validate"


def test_method_signature(csharp_parser: CSharpParser, sample_csharp_source: str) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    validate = next(s for s in result.symbols if s.name == "Validate")
    assert "bool" in validate.signature
    assert "Validate" in validate.signature


def test_extracts_properties(csharp_parser: CSharpParser, sample_csharp_source: str) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    props = [s for s in result.symbols if s.kind.value == "variable" and "User" in s.qualified_name]
    prop_names = [s.name for s in props]
    assert "Name" in prop_names
    assert "Age" in prop_names


def test_extracts_struct_fields(csharp_parser: CSharpParser, sample_csharp_source: str) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    fields = [
        s for s in result.symbols if s.kind.value == "variable" and "Point" in s.qualified_name
    ]
    field_names = [s.name for s in fields]
    assert "X" in field_names
    assert "Y" in field_names


def test_extracts_inheritance(csharp_parser: CSharpParser, sample_csharp_source: str) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    inherits = [r for r in result.relationships if r.kind.value == "inherits"]
    targets = [r.target_id for r in inherits]
    assert any("BaseEntity" in t for t in targets)


def test_extracts_implements(csharp_parser: CSharpParser, sample_csharp_source: str) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    implements = [r for r in result.relationships if r.kind.value == "implements"]
    targets = [r.target_id for r in implements]
    assert any("ISerializable" in t for t in targets)


def test_user_processor_implements(csharp_parser: CSharpParser, sample_csharp_source: str) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    # UserProcessor implements IProcessor<User>
    implements = [
        r
        for r in result.relationships
        if r.kind.value == "implements" and "UserProcessor" in r.source_id
    ]
    assert len(implements) == 1
    assert "IProcessor" in implements[0].target_id


def test_extracts_xml_doc_comment(csharp_parser: CSharpParser, sample_csharp_source: str) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    user = next(s for s in result.symbols if s.kind.value == "class" and s.name == "User")
    assert user.docstring is not None
    assert "user" in user.docstring.lower()


def test_extracts_method_doc_comment(
    csharp_parser: CSharpParser, sample_csharp_source: str
) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    validate = next(s for s in result.symbols if s.name == "Validate")
    assert validate.docstring is not None
    assert "validates" in validate.docstring.lower()


def test_extracts_call_relationships(
    csharp_parser: CSharpParser, sample_csharp_source: str
) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    calls = [r for r in result.relationships if r.kind.value == "calls"]
    call_targets = [r.target_id for r in calls]
    assert any("Validate" in t for t in call_targets)
    assert any("WriteLine" in t for t in call_targets)


def test_extracts_import_relationships(
    csharp_parser: CSharpParser, sample_csharp_source: str
) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    imports = [r for r in result.relationships if r.kind.value == "imports"]
    assert len(imports) >= 3


def test_abstract_class(csharp_parser: CSharpParser, sample_csharp_source: str) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    repo = next(s for s in result.symbols if s.name == "Repository")
    assert repo.kind.value == "class"
    assert repo.qualified_name == "MyApp.Models.Repository"


def test_static_class_methods(csharp_parser: CSharpParser, sample_csharp_source: str) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    ext_method = next(s for s in result.symbols if s.name == "ToUpperCase")
    assert ext_method.kind.value == "method"
    assert "Extensions" in ext_method.qualified_name


def test_interface_methods(csharp_parser: CSharpParser, sample_csharp_source: str) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    methods = [
        s for s in result.symbols if s.kind.value == "method" and "IProcessor" in s.qualified_name
    ]
    method_names = [s.name for s in methods]
    assert "Process" in method_names
    assert "CanProcess" in method_names


def test_struct_method(csharp_parser: CSharpParser, sample_csharp_source: str) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    dist = next(s for s in result.symbols if s.name == "DistanceTo")
    assert dist.kind.value == "method"
    assert "Point" in dist.qualified_name


def test_empty_source(csharp_parser: CSharpParser) -> None:
    result = csharp_parser.parse_source("", "empty.cs")
    assert result.file_info.symbol_count == 0
    assert result.symbols == []


def test_unique_symbol_ids(csharp_parser: CSharpParser, sample_csharp_source: str) -> None:
    result = csharp_parser.parse_source(sample_csharp_source, "test.cs")
    ids = [s.id for s in result.symbols]
    assert len(ids) == len(set(ids)), f"Duplicate IDs: {[x for x in ids if ids.count(x) > 1]}"


def test_supported_extensions(csharp_parser: CSharpParser) -> None:
    assert csharp_parser.supported_extensions == [".cs"]
