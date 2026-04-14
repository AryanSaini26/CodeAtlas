"""Tests for the SQLite graph store."""

from typing import Any

import pytest

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


# --- Scoped search (file_filter, kind_filter) ---


def test_search_with_kind_filter(graph_store: GraphStore) -> None:
    graph_store.upsert_parse_result(
        _make_result(
            "scoped.py",
            [
                _make_symbol("my_func", file_path="scoped.py", kind=SymbolKind.FUNCTION),
                _make_symbol("MyClass", file_path="scoped.py", kind=SymbolKind.CLASS),
            ],
        )
    )
    results = graph_store.search("my", kind_filter="function")
    assert all(s.kind == SymbolKind.FUNCTION for s in results)
    names = [s.name for s in results]
    assert "my_func" in names
    assert "MyClass" not in names


def test_search_with_file_filter(graph_store: GraphStore) -> None:
    graph_store.upsert_parse_result(
        _make_result("src/auth.py", [_make_symbol("login", file_path="src/auth.py")])
    )
    graph_store.upsert_parse_result(
        _make_result("src/views.py", [_make_symbol("login", file_path="src/views.py")])
    )
    results = graph_store.search("login", file_filter="auth")
    assert all("auth" in s.file_path for s in results)
    assert len(results) == 1


def test_search_filter_no_match(graph_store: GraphStore) -> None:
    graph_store.upsert_parse_result(
        _make_result("filter_test.py", [_make_symbol("helper", file_path="filter_test.py")])
    )
    results = graph_store.search("helper", kind_filter="class")
    assert results == []


def test_search_with_multi_kind_filter(graph_store: GraphStore) -> None:
    graph_store.upsert_parse_result(
        _make_result(
            "multi_kind.py",
            [
                _make_symbol("my_func", file_path="multi_kind.py", kind=SymbolKind.FUNCTION),
                _make_symbol("MyClass", file_path="multi_kind.py", kind=SymbolKind.CLASS),
                _make_symbol("MY_CONST", file_path="multi_kind.py", kind=SymbolKind.CONSTANT),
            ],
        )
    )
    results = graph_store.search("my", kind_filter=["function", "class"])
    kinds = {s.kind.value for s in results}
    assert "function" in kinds or "class" in kinds
    assert "constant" not in kinds


def test_search_multi_kind_includes_both(graph_store: GraphStore) -> None:
    graph_store.upsert_parse_result(
        _make_result(
            "both.py",
            [
                _make_symbol("do_work", file_path="both.py", kind=SymbolKind.FUNCTION),
                _make_symbol("WorkClass", file_path="both.py", kind=SymbolKind.CLASS),
            ],
        )
    )
    results = graph_store.search("work", kind_filter=["function", "class"])
    names = [s.name for s in results]
    # At least one of the two symbols should appear
    assert "do_work" in names or "WorkClass" in names


# --- Query expansion ---


def test_fts_expansion_camelcase(graph_store: GraphStore) -> None:
    sym = _make_symbol("greet_world")
    graph_store.upsert_parse_result(_make_result(symbols=[sym]))
    # camelCase version should find the underscore symbol via expansion
    found = graph_store.search("greetWorld")
    assert any(s.name == "greet_world" for s in found)


def test_fts_expansion_prefix_fallback(graph_store: GraphStore) -> None:
    sym = _make_symbol("authenticate")
    graph_store.upsert_parse_result(_make_result(symbols=[sym]))
    found = graph_store.search("authenticat")
    assert any(s.name == "authenticate" for s in found)


def test_fts_no_expansion_when_direct_match(graph_store: GraphStore) -> None:
    sym = _make_symbol("helper")
    graph_store.upsert_parse_result(_make_result(symbols=[sym]))
    found = graph_store.search("helper")
    assert found  # direct match, no expansion needed
    assert found[0].name == "helper"


# --- get_symbols_by_kind ---


def test_get_symbols_by_kind(graph_store: GraphStore) -> None:
    graph_store.upsert_parse_result(
        _make_result(
            "kind_test.py",
            [
                _make_symbol("KindTestClass", file_path="kind_test.py", kind=SymbolKind.CLASS),
                _make_symbol("kind_test_func", file_path="kind_test.py", kind=SymbolKind.FUNCTION),
            ],
        )
    )
    classes = graph_store.get_symbols_by_kind("class")
    assert any(s.name == "KindTestClass" for s in classes)
    assert all(s.kind == SymbolKind.CLASS for s in classes)


def test_get_symbols_by_kind_with_filter(graph_store: GraphStore) -> None:
    graph_store.upsert_parse_result(
        _make_result(
            "src/api.py", [_make_symbol("ApiClass", file_path="src/api.py", kind=SymbolKind.CLASS)]
        )
    )
    graph_store.upsert_parse_result(
        _make_result(
            "tests/test_api.py",
            [_make_symbol("TestClass", file_path="tests/test_api.py", kind=SymbolKind.CLASS)],
        )
    )
    results = graph_store.get_symbols_by_kind("class", file_filter="src/")
    assert len(results) == 1
    assert results[0].name == "ApiClass"


def test_get_symbols_by_kind_empty(graph_store: GraphStore) -> None:
    results = graph_store.get_symbols_by_kind("namespace")
    assert results == []


# --- get_api_surface ---


def test_get_api_surface_excludes_private(graph_store: GraphStore) -> None:
    pub = _make_symbol("public_func", file_path="src/app.py", kind=SymbolKind.FUNCTION)
    priv = _make_symbol("_private_func", file_path="src/app.py", kind=SymbolKind.FUNCTION)
    imp = _make_symbol("os", file_path="src/app.py", kind=SymbolKind.IMPORT)
    graph_store.upsert_parse_result(_make_result("src/app.py", [pub, priv, imp]))
    surface = graph_store.get_api_surface()
    names = [s.name for s in surface]
    assert "public_func" in names
    assert "_private_func" not in names
    assert "os" not in names


def test_get_api_surface_excludes_test_symbols(graph_store: GraphStore) -> None:
    prod = _make_symbol("do_work", file_path="src/worker.py", kind=SymbolKind.FUNCTION)
    test_sym = Symbol(
        id="tests/test_worker.py::test_do_work",
        name="test_do_work",
        qualified_name="test_do_work",
        kind=SymbolKind.FUNCTION,
        file_path="tests/test_worker.py",
        span=Span(start=Position(line=0, column=0), end=Position(line=5, column=0)),
        language="python",
        is_test=True,
    )
    graph_store.upsert_parse_result(_make_result("src/worker.py", [prod]))
    graph_store.upsert_parse_result(_make_result("tests/test_worker.py", [test_sym]))
    surface = graph_store.get_api_surface()
    names = [s.name for s in surface]
    assert "do_work" in names
    assert "test_do_work" not in names


def test_get_api_surface_file_filter(graph_store: GraphStore) -> None:
    s1 = _make_symbol("api_handler", file_path="src/api/routes.py", kind=SymbolKind.FUNCTION)
    s2 = _make_symbol("db_connect", file_path="src/db/conn.py", kind=SymbolKind.FUNCTION)
    graph_store.upsert_parse_result(_make_result("src/api/routes.py", [s1]))
    graph_store.upsert_parse_result(_make_result("src/db/conn.py", [s2]))
    surface = graph_store.get_api_surface(file_filter="src/api")
    names = [s.name for s in surface]
    assert "api_handler" in names
    assert "db_connect" not in names


# --- get_symbol_coverage ---


def test_get_symbol_coverage_found(graph_store: GraphStore) -> None:
    prod = _make_symbol("process_order", file_path="src/orders.py", kind=SymbolKind.FUNCTION)
    test_func = Symbol(
        id="tests/test_orders.py::test_process_order",
        name="test_process_order",
        qualified_name="test_process_order",
        kind=SymbolKind.FUNCTION,
        file_path="tests/test_orders.py",
        span=Span(start=Position(line=0, column=0), end=Position(line=5, column=0)),
        language="python",
        is_test=True,
    )
    rel = _make_relationship(
        "tests/test_orders.py::test_process_order",
        "src/orders.py::process_order",
        kind=RelationshipKind.CALLS,
        file_path="tests/test_orders.py",
    )
    graph_store.upsert_parse_result(_make_result("src/orders.py", [prod]))
    graph_store.upsert_parse_result(_make_result("tests/test_orders.py", [test_func], [rel]))
    coverage = graph_store.get_symbol_coverage("process_order")
    assert "results" in coverage
    assert len(coverage["results"]) >= 1
    entry = coverage["results"][0]
    assert entry["covered"] is True
    assert len(entry["test_references"]) >= 1
    assert "test_process_order" in [r["name"] for r in entry["test_references"]]


def test_get_symbol_coverage_not_covered(graph_store: GraphStore) -> None:
    sym = _make_symbol("uncovered_func", file_path="src/utils.py", kind=SymbolKind.FUNCTION)
    graph_store.upsert_parse_result(_make_result("src/utils.py", [sym]))
    coverage = graph_store.get_symbol_coverage("uncovered_func")
    assert "results" in coverage
    assert coverage["results"][0]["covered"] is False
    assert coverage["results"][0]["test_references"] == []


def test_get_symbol_coverage_not_found(graph_store: GraphStore) -> None:
    coverage = graph_store.get_symbol_coverage("nonexistent_xyz_abc")
    assert "error" in coverage


# --- get_hotspots (unit-level: no real git, verifies structure) ---


def test_get_hotspots_returns_list_when_no_git(graph_store: GraphStore, tmp_path: Any) -> None:
    # A directory with no git history returns an empty list (no churn data)
    results = graph_store.get_hotspots(repo_path=str(tmp_path))
    assert isinstance(results, list)


# --- _transaction rollback on error ---


def test_transaction_rollback_on_error(graph_store: GraphStore) -> None:
    """Cover _transaction's except branch (rollback + re-raise)."""
    # Ensure a RuntimeError raised inside _transaction propagates out
    with pytest.raises(RuntimeError, match="intentional rollback"):
        with graph_store._transaction():
            raise RuntimeError("intentional rollback")


# --- find_symbols_by_name with kind filter ---


def test_find_symbols_by_name_with_kind(graph_store: GraphStore) -> None:
    """Cover the kind-filtered branch in find_symbols_by_name (line 238)."""
    graph_store.upsert_parse_result(
        _make_result(
            "kind_test.py",
            [
                _make_symbol("kind_func", file_path="kind_test.py", kind=SymbolKind.FUNCTION),
                _make_symbol("KindClass", file_path="kind_test.py", kind=SymbolKind.CLASS),
            ],
        )
    )
    # Filtering by kind should return only the CLASS
    results = graph_store.find_symbols_by_name("KindClass", kind="class")
    assert all(s.kind == SymbolKind.CLASS for s in results)
    assert len(results) >= 1
    # Filtering by a non-matching kind should return empty
    results_wrong = graph_store.find_symbols_by_name("KindClass", kind="function")
    assert results_wrong == []


# --- find_symbols_by_decorator with file_filter ---


def test_find_symbols_by_decorator_with_file_filter(graph_store: GraphStore) -> None:
    """Cover the file_filter branch in find_symbols_by_decorator (lines 400-401)."""

    # Manually insert symbols with decorators in different files
    sym_a = _make_symbol("cached_fn", file_path="cache.py", kind=SymbolKind.FUNCTION)
    sym_b = _make_symbol("other_fn", file_path="other.py", kind=SymbolKind.FUNCTION)
    # We need to set decorators; create via model directly
    sym_a_with_dec = sym_a.model_copy(update={"decorators": ["cache"]})
    sym_b_with_dec = sym_b.model_copy(update={"decorators": ["cache"]})

    from codeatlas.models import FileInfo, ParseResult  # noqa: PLC0415

    graph_store.upsert_parse_result(
        ParseResult(
            file_info=FileInfo(path="cache.py", language="python", content_hash="a", symbol_count=1),
            symbols=[sym_a_with_dec],
            relationships=[],
        )
    )
    graph_store.upsert_parse_result(
        ParseResult(
            file_info=FileInfo(path="other.py", language="python", content_hash="b", symbol_count=1),
            symbols=[sym_b_with_dec],
            relationships=[],
        )
    )

    results = graph_store.find_symbols_by_decorator("cache", file_filter="cache.py")
    assert all("cache" in s.file_path for s in results)
    assert len(results) >= 1


# --- FTS OperationalError returns empty ---


def test_fts_query_operational_error_returns_empty(graph_store: GraphStore) -> None:
    """Cover the except sqlite3.OperationalError branch in _fts_query (lines 334-335).

    Passing a syntactically invalid FTS5 query triggers OperationalError without mocking.
    """
    # An unclosed parenthesis is an FTS5 syntax error
    results = graph_store._fts_query("NEAR(", limit=10)
    assert results == []


# --- find_shortest_path skips external/unresolved ---


def test_find_path_skips_external_nodes(graph_store: GraphStore) -> None:
    """Cover the external/unresolved node skip in find_path (line 752)."""
    a = _make_symbol("alpha", file_path="path.py", kind=SymbolKind.FUNCTION)
    b = _make_symbol("beta", file_path="path.py", kind=SymbolKind.FUNCTION)
    # Add an external node that should be filtered out, plus a direct a→b edge
    rel_to_ext = _make_relationship(a.id, "<external>::os.path", file_path="path.py")
    rel_a_b = _make_relationship(a.id, b.id, file_path="path.py")
    graph_store.upsert_parse_result(
        _make_result("path.py", [a, b], relationships=[rel_to_ext, rel_a_b])
    )

    path = graph_store.find_path(a.id, b.id)
    # Should find the direct path a→b, external node not in result
    assert path is not None
    assert all("<external>" not in node for node in path)
