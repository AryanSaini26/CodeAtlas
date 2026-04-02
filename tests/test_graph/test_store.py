"""Tests for the SQLite graph store."""

from codeatlas.graph.store import GraphStore
from codeatlas.models import (
    FileInfo,
    ParseResult,
    Position,
    Relationship,
    RelationshipKind,
    Span,
    Symbol,
    SymbolKind,
)


def _make_symbol(
    name: str,
    file_path: str = "test.py",
    kind: SymbolKind = SymbolKind.FUNCTION,
    line: int = 0,
) -> Symbol:
    return Symbol(
        id=f"{file_path}::{name}",
        name=name,
        qualified_name=name,
        kind=kind,
        file_path=file_path,
        span=Span(
            start=Position(line=line, column=0),
            end=Position(line=line + 5, column=0),
        ),
        language="python",
    )


def _make_relationship(
    source: str,
    target: str,
    kind: RelationshipKind = RelationshipKind.CALLS,
    file_path: str = "test.py",
) -> Relationship:
    return Relationship(
        source_id=source,
        target_id=target,
        kind=kind,
        file_path=file_path,
    )


def _make_result(
    file_path: str = "test.py",
    symbols: list[Symbol] | None = None,
    relationships: list[Relationship] | None = None,
) -> ParseResult:
    syms = symbols or []
    rels = relationships or []
    return ParseResult(
        file_info=FileInfo(
            path=file_path,
            language="python",
            content_hash="abc123",
            symbol_count=len(syms),
            relationship_count=len(rels),
        ),
        symbols=syms,
        relationships=rels,
    )


# --- Basic CRUD ---


def test_upsert_and_retrieve_symbols(graph_store: GraphStore) -> None:
    sym = _make_symbol("my_func")
    result = _make_result(symbols=[sym])
    graph_store.upsert_parse_result(result)

    found = graph_store.get_symbols_in_file("test.py")
    assert len(found) == 1
    assert found[0].name == "my_func"


def test_upsert_idempotent(graph_store: GraphStore) -> None:
    sym = _make_symbol("my_func")
    result = _make_result(symbols=[sym])
    graph_store.upsert_parse_result(result)
    graph_store.upsert_parse_result(result)

    found = graph_store.get_symbols_in_file("test.py")
    assert len(found) == 1


def test_delete_file(graph_store: GraphStore) -> None:
    sym = _make_symbol("my_func")
    result = _make_result(symbols=[sym])
    graph_store.upsert_parse_result(result)

    graph_store.delete_file("test.py")
    found = graph_store.get_symbols_in_file("test.py")
    assert found == []


def test_find_symbols_by_name(graph_store: GraphStore) -> None:
    sym1 = _make_symbol("foo", file_path="a.py")
    sym2 = _make_symbol("bar", file_path="b.py")
    graph_store.upsert_parse_result(_make_result("a.py", [sym1]))
    graph_store.upsert_parse_result(_make_result("b.py", [sym2]))

    found = graph_store.find_symbols_by_name("foo")
    assert len(found) == 1
    assert found[0].file_path == "a.py"


def test_get_stats(graph_store: GraphStore) -> None:
    sym = _make_symbol("my_func")
    rel = _make_relationship("test.py::my_func", "<unresolved>::helper")
    result = _make_result(symbols=[sym], relationships=[rel])
    graph_store.upsert_parse_result(result)

    s = graph_store.get_stats()
    assert s["files"] == 1
    assert s["symbols"] == 1
    assert s["relationships"] == 1


# --- FTS search ---


def test_fts_search_by_name(graph_store: GraphStore) -> None:
    sym = _make_symbol("authenticate_user")
    result = _make_result(symbols=[sym])
    graph_store.upsert_parse_result(result)

    found = graph_store.search("authenticate")
    assert len(found) >= 1
    assert any(s.name == "authenticate_user" for s in found)


def test_fts_search_no_results(graph_store: GraphStore) -> None:
    sym = _make_symbol("my_func")
    graph_store.upsert_parse_result(_make_result(symbols=[sym]))
    found = graph_store.search("zzznomatch")
    assert found == []


# --- Graph traversals ---


def test_trace_call_chain(graph_store: GraphStore) -> None:
    # a -> b -> c
    sym_a = _make_symbol("a")
    sym_b = _make_symbol("b", line=10)
    sym_c = _make_symbol("c", line=20)
    rel_ab = _make_relationship("test.py::a", "test.py::b")
    rel_bc = _make_relationship("test.py::b", "test.py::c")
    result = _make_result(symbols=[sym_a, sym_b, sym_c], relationships=[rel_ab, rel_bc])
    graph_store.upsert_parse_result(result)

    chain = graph_store.trace_call_chain("test.py::a")
    targets = {row["target_id"] for row in chain}
    assert "test.py::b" in targets
    assert "test.py::c" in targets


def test_get_impact_analysis(graph_store: GraphStore) -> None:
    # x <- y <- z (z calls y, y calls x)
    sym_x = _make_symbol("x")
    sym_y = _make_symbol("y", line=10)
    sym_z = _make_symbol("z", line=20)
    rel_yx = _make_relationship("test.py::y", "test.py::x")
    rel_zy = _make_relationship("test.py::z", "test.py::y")
    result = _make_result(symbols=[sym_x, sym_y, sym_z], relationships=[rel_yx, rel_zy])
    graph_store.upsert_parse_result(result)

    impact = graph_store.get_impact_analysis("test.py::x")
    sources = {row["source_id"] for row in impact}
    assert "test.py::y" in sources
    assert "test.py::z" in sources


# --- Import resolution ---


def test_resolve_imports_resolves_unresolved(graph_store: GraphStore) -> None:
    sym_a = _make_symbol("helper", file_path="a.py")
    sym_b = _make_symbol("caller", file_path="b.py", line=10)
    rel = _make_relationship("b.py::caller", "<unresolved>::helper", RelationshipKind.CALLS, "b.py")
    graph_store.upsert_parse_result(_make_result("a.py", [sym_a]))
    graph_store.upsert_parse_result(_make_result("b.py", [sym_b], [rel]))

    stats = graph_store.resolve_imports()
    assert stats["resolved"] == 1
    assert stats["unresolved"] == 0

    # The relationship target should now point to the actual symbol
    deps = graph_store.get_dependencies("b.py::caller")
    assert any(d.target_id == "a.py::helper" for d in deps)


def test_resolve_imports_handles_external_prefix(graph_store: GraphStore) -> None:
    sym = _make_symbol("Widget", file_path="lib.py")
    rel = _make_relationship(
        "app.py::main", "<external>::lib.Widget", RelationshipKind.IMPORTS, "app.py"
    )
    sym_main = _make_symbol("main", file_path="app.py", line=10)
    graph_store.upsert_parse_result(_make_result("lib.py", [sym]))
    graph_store.upsert_parse_result(_make_result("app.py", [sym_main], [rel]))

    stats = graph_store.resolve_imports()
    assert stats["resolved"] == 1


def test_resolve_imports_leaves_truly_external(graph_store: GraphStore) -> None:
    sym = _make_symbol("my_func", file_path="app.py")
    rel = _make_relationship(
        "app.py::my_func", "<external>::numpy.array", RelationshipKind.IMPORTS, "app.py"
    )
    graph_store.upsert_parse_result(_make_result("app.py", [sym], [rel]))

    stats = graph_store.resolve_imports()
    assert stats["unresolved"] == 1


# --- Module-level queries ---


def test_get_module_overview(graph_store: GraphStore) -> None:
    sym1 = _make_symbol("foo", file_path="src/models.py")
    sym2 = _make_symbol("bar", file_path="src/models.py", line=10)
    sym3 = _make_symbol("baz", file_path="src/views.py")
    graph_store.upsert_parse_result(_make_result("src/models.py", [sym1, sym2]))
    graph_store.upsert_parse_result(_make_result("src/views.py", [sym3]))

    overview = graph_store.get_module_overview("src/")
    assert overview["file_count"] == 2
    assert overview["symbol_count"] == 3


def test_get_file_dependencies(graph_store: GraphStore) -> None:
    sym_a = _make_symbol("helper", file_path="a.py")
    sym_b = _make_symbol("caller", file_path="b.py", line=10)
    rel = _make_relationship("b.py::caller", "a.py::helper", RelationshipKind.CALLS, "b.py")
    graph_store.upsert_parse_result(_make_result("a.py", [sym_a]))
    graph_store.upsert_parse_result(_make_result("b.py", [sym_b], [rel]))

    deps = graph_store.get_file_dependencies("b.py")
    assert "a.py" in deps["depends_on"]

    deps_a = graph_store.get_file_dependencies("a.py")
    assert "b.py" in deps_a["depended_by"]


def test_get_affected_files(graph_store: GraphStore) -> None:
    sym_a = _make_symbol("helper", file_path="a.py")
    sym_b = _make_symbol("caller", file_path="b.py", line=10)
    rel = _make_relationship("b.py::caller", "a.py::helper", RelationshipKind.CALLS, "b.py")
    graph_store.upsert_parse_result(_make_result("a.py", [sym_a]))
    graph_store.upsert_parse_result(_make_result("b.py", [sym_b], [rel]))

    affected = graph_store.get_affected_files("a.py")
    assert "b.py" in affected
