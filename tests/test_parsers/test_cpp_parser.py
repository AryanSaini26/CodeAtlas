"""Tests for the C++ tree-sitter parser."""

from pathlib import Path

from codeatlas.parsers.cpp_parser import CppParser


def test_parse_file_returns_parse_result(cpp_parser: CppParser, sample_cpp_path: Path) -> None:
    result = cpp_parser.parse_file(sample_cpp_path)
    assert result.file_info.path == str(sample_cpp_path)
    assert len(result.symbols) > 0


def test_parse_source_returns_parse_result(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    assert result.file_info.path == "test.cpp"
    assert len(result.symbols) > 0


def test_file_info_language(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    assert result.file_info.language == "cpp"


def test_content_hash_consistent(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    r1 = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    r2 = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    assert r1.file_info.content_hash == r2.file_info.content_hash


def test_extracts_includes(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    imports = [s for s in result.symbols if s.kind.value == "import"]
    import_names = [s.name for s in imports]
    assert "iostream" in import_names
    assert "vector" in import_names
    assert "utils.h" in import_names


def test_extracts_namespace(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    namespaces = [s for s in result.symbols if s.kind.value == "namespace"]
    ns_names = [s.name for s in namespaces]
    assert "myapp" in ns_names
    assert "utils" in ns_names


def test_nested_namespace_qualified_name(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    namespaces = [s for s in result.symbols if s.kind.value == "namespace"]
    utils_ns = [s for s in namespaces if s.name == "utils"]
    assert len(utils_ns) == 1
    assert utils_ns[0].qualified_name == "myapp::utils"


def test_extracts_class(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    classes = [s for s in result.symbols if s.kind.value == "class" and s.name == "User"]
    assert len(classes) == 1
    assert classes[0].qualified_name == "myapp::User"


def test_extracts_struct(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    structs = [s for s in result.symbols if s.kind.value == "class" and s.name == "Point"]
    assert len(structs) == 1
    assert structs[0].qualified_name == "myapp::Point"


def test_extracts_enum(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    enums = [s for s in result.symbols if s.kind.value == "enum"]
    assert len(enums) == 1
    assert enums[0].name == "Color"
    assert enums[0].qualified_name == "myapp::Color"


def test_extracts_class_methods(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    methods = [s for s in result.symbols if s.kind.value == "method"]
    method_names = [s.name for s in methods]
    assert "get_name" in method_names
    assert "set_name" in method_names
    assert "get_age" in method_names
    assert "create" in method_names


def test_extracts_constructor_destructor(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    methods = [s for s in result.symbols if s.kind.value == "method"]
    method_names = [s.name for s in methods]
    assert "User" in method_names  # constructor
    assert "~User" in method_names  # destructor


def test_method_qualified_name(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    methods = [s for s in result.symbols if s.kind.value == "method" and s.name == "get_name"]
    assert len(methods) >= 1
    assert "User" in methods[0].qualified_name


def test_extracts_inheritance(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    inherits = [r for r in result.relationships if r.kind.value == "inherits"]
    targets = [r.target_id for r in inherits]
    assert any("Entity" in t for t in targets)
    assert any("Serializable" in t for t in targets)


def test_extracts_iprocessor_inheritance(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    inherits = [r for r in result.relationships if r.kind.value == "inherits"]
    # UserProcessor inherits from IProcessor
    user_proc_inherits = [r for r in inherits if "UserProcessor" in r.source_id]
    assert len(user_proc_inherits) == 1
    assert "IProcessor" in user_proc_inherits[0].target_id


def test_extracts_template_class(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    classes = [s for s in result.symbols if s.kind.value == "class" and s.name == "Container"]
    assert len(classes) == 1
    assert classes[0].qualified_name == "myapp::Container"


def test_extracts_constant(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    constants = [s for s in result.symbols if s.kind.value == "constant"]
    assert any(s.name == "MAX_USERS" for s in constants)


def test_extracts_type_alias(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    aliases = [s for s in result.symbols if s.kind.value == "type_alias"]
    assert any(s.name == "StringVec" for s in aliases)


def test_extracts_free_function(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    functions = [s for s in result.symbols if s.kind.value == "function"]
    func_names = [s.name for s in functions]
    assert "free_function" in func_names
    assert "implemented_function" in func_names


def test_free_function_signature(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    func = next(s for s in result.symbols if s.name == "free_function")
    assert "int x" in func.signature
    assert "double y" in func.signature


def test_extracts_doc_comment_triple_slash(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    user = next(s for s in result.symbols if s.kind.value == "class" and s.name == "User")
    assert user.docstring is not None
    assert "user entity" in user.docstring.lower()


def test_extracts_doc_comment_block(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    proc = next(s for s in result.symbols if s.name == "IProcessor")
    assert proc.docstring is not None
    assert "processor" in proc.docstring.lower()


def test_extracts_method_doc_comment(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    get_name = [s for s in result.symbols if s.name == "get_name"]
    assert len(get_name) >= 1
    assert get_name[0].docstring is not None
    assert "name" in get_name[0].docstring.lower()


def test_extracts_call_relationships(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    calls = [r for r in result.relationships if r.kind.value == "calls"]
    call_targets = [r.target_id for r in calls]
    assert any("create" in t for t in call_targets)
    assert any("set_name" in t for t in call_targets)


def test_extracts_import_relationships(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    imports = [r for r in result.relationships if r.kind.value == "imports"]
    assert len(imports) >= 3


def test_struct_members(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    # Point struct should have fields x, y and method distance_to
    point_syms = [s for s in result.symbols if "Point" in s.qualified_name and s.name != "Point"]
    names = [s.name for s in point_syms]
    assert "x" in names
    assert "y" in names
    assert "distance_to" in names


def test_nested_namespace_function(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    func = [s for s in result.symbols if s.name == "helper_func"]
    assert len(func) == 1
    assert func[0].qualified_name == "myapp::utils::helper_func"


def test_empty_source(cpp_parser: CppParser) -> None:
    result = cpp_parser.parse_source("", "empty.cpp")
    assert result.file_info.symbol_count == 0
    assert result.symbols == []


def test_unique_symbol_ids(cpp_parser: CppParser, sample_cpp_source: str) -> None:
    result = cpp_parser.parse_source(sample_cpp_source, "test.cpp")
    ids = [s.id for s in result.symbols]
    assert len(ids) == len(set(ids)), f"Duplicate IDs found: {[x for x in ids if ids.count(x) > 1]}"


def test_supported_extensions(cpp_parser: CppParser) -> None:
    exts = cpp_parser.supported_extensions
    assert ".cpp" in exts
    assert ".hpp" in exts
    assert ".h" in exts
    assert ".cc" in exts
