"""Tests for the MCP server tool functions."""

import json
from unittest.mock import patch

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
from codeatlas.server import (
    analyze_complexity,
    detect_circular_dependencies,
    export_graph,
    find_dead_code,
    find_path_between_symbols,
    get_change_impact,
    get_dependencies,
    get_file_coupling,
    get_file_dependencies,
    get_file_overview,
    get_graph_stats,
    get_impact_analysis,
    get_module_overview,
    get_symbol_details,
    list_symbols_by_kind,
    search_symbols,
    set_store,
    trace_call_chain,
)


def _sym(
    name: str, kind: SymbolKind = SymbolKind.FUNCTION, fp: str = "app.py", line: int = 0
) -> Symbol:
    return Symbol(
        id=f"{fp}::{name}",
        name=name,
        qualified_name=name,
        kind=kind,
        file_path=fp,
        span=Span(start=Position(line=line, column=0), end=Position(line=line + 5, column=0)),
        signature=f"def {name}()" if kind == SymbolKind.FUNCTION else None,
        docstring=f"Docstring for {name}",
        language="python",
    )


def _rel(
    src: str, tgt: str, kind: RelationshipKind = RelationshipKind.CALLS, fp: str = "app.py"
) -> Relationship:
    return Relationship(source_id=src, target_id=tgt, kind=kind, file_path=fp)


def _result(fp: str, syms: list[Symbol], rels: list[Relationship] | None = None) -> ParseResult:
    r = rels or []
    return ParseResult(
        file_info=FileInfo(
            path=fp,
            language="python",
            content_hash="abc",
            symbol_count=len(syms),
            relationship_count=len(r),
        ),
        symbols=syms,
        relationships=r,
    )


@pytest.fixture(autouse=True)
def _setup_store() -> None:
    store = GraphStore(":memory:")
    s1 = _sym("main", SymbolKind.FUNCTION, "app.py", 0)
    s2 = _sym("helper", SymbolKind.FUNCTION, "utils.py", 0)
    s3 = _sym("Widget", SymbolKind.CLASS, "models.py", 0)
    rel1 = _rel("app.py::main", "utils.py::helper")
    rel2 = _rel("app.py::main", "models.py::Widget", RelationshipKind.IMPORTS)
    store.upsert_parse_result(_result("app.py", [s1], [rel1, rel2]))
    store.upsert_parse_result(_result("utils.py", [s2]))
    store.upsert_parse_result(_result("models.py", [s3]))
    set_store(store)


def test_get_file_overview() -> None:
    result = json.loads(get_file_overview("app.py"))
    assert result["file"] == "app.py"
    assert result["symbol_count"] == 1
    assert result["symbols"][0]["name"] == "main"


def test_get_file_overview_not_found() -> None:
    result = json.loads(get_file_overview("nonexistent.py"))
    assert "error" in result


def test_get_dependencies_found() -> None:
    result = json.loads(get_dependencies("main"))
    assert len(result) == 1
    assert len(result[0]["depends_on"]) == 2


def test_get_dependencies_not_found() -> None:
    result = json.loads(get_dependencies("nonexistent"))
    assert "error" in result


def test_trace_call_chain_result() -> None:
    result = json.loads(trace_call_chain("main"))
    assert result["symbol"] == "main"
    assert isinstance(result["call_chain"], list)


def test_get_impact_analysis_result() -> None:
    result = json.loads(get_impact_analysis("helper"))
    assert result["symbol"] == "helper"
    affected_sources = {a["source_id"] for a in result["affected"]}
    assert "app.py::main" in affected_sources


def test_search_symbols() -> None:
    result = json.loads(search_symbols("helper"))
    assert result["count"] >= 1
    assert result["results"][0]["name"] == "helper"


def test_get_module_overview_tool() -> None:
    result = json.loads(get_module_overview("app"))
    assert result["symbol_count"] == 1


def test_get_file_dependencies_tool() -> None:
    result = json.loads(get_file_dependencies("app.py"))
    assert "utils.py" in result["depends_on"]


def test_get_graph_stats_tool() -> None:
    result = json.loads(get_graph_stats())
    assert result["files"] == 3
    assert result["symbols"] == 3


def test_detect_circular_dependencies_no_cycles() -> None:
    result = json.loads(detect_circular_dependencies())
    assert result["cycle_count"] == 0
    assert result["cycles"] == []


def test_detect_circular_dependencies_with_cycle() -> None:
    store = GraphStore(":memory:")
    s1 = _sym("foo", SymbolKind.FUNCTION, "a.py", 0)
    s2 = _sym("bar", SymbolKind.FUNCTION, "b.py", 0)
    r1 = _rel("a.py::foo", "b.py::bar", fp="a.py")
    r2 = _rel("b.py::bar", "a.py::foo", fp="b.py")
    store.upsert_parse_result(_result("a.py", [s1], [r1]))
    store.upsert_parse_result(_result("b.py", [s2], [r2]))
    set_store(store)
    result = json.loads(detect_circular_dependencies())
    assert result["cycle_count"] == 1
    assert len(result["cycles"][0]["symbols"]) == 2


def test_find_dead_code_tool() -> None:
    result = json.loads(find_dead_code())
    # main has no incoming deps, helper does (main calls it), Widget does (main imports it)
    unused_names = [s["name"] for s in result["unused_symbols"]]
    assert "helper" not in unused_names
    assert "Widget" not in unused_names


def test_analyze_complexity_tool() -> None:
    result = json.loads(analyze_complexity(limit=10))
    assert result["count"] > 0
    # main has 2 outgoing rels so should appear
    names = [s["name"] for s in result["symbols"]]
    assert "main" in names


def test_find_path_between_symbols_found() -> None:
    result = json.loads(find_path_between_symbols("main", "helper"))
    assert result["path"] is not None
    assert result["length"] == 1


def test_find_path_between_symbols_not_found() -> None:
    result = json.loads(find_path_between_symbols("helper", "main"))
    # helper -> main has no edge (only main -> helper exists)
    assert result["path"] is None


def test_find_path_source_missing() -> None:
    result = json.loads(find_path_between_symbols("nonexistent", "main"))
    assert "error" in result


def test_get_file_coupling_tool() -> None:
    result = json.loads(get_file_coupling(limit=10))
    assert result["count"] > 0
    files = [(p["source_file"], p["target_file"]) for p in result["file_pairs"]]
    assert ("app.py", "utils.py") in files or ("app.py", "models.py") in files


def test_trace_call_chain_not_found() -> None:
    result = json.loads(trace_call_chain("nonexistent"))
    assert "error" in result


def test_get_impact_analysis_not_found() -> None:
    result = json.loads(get_impact_analysis("nonexistent"))
    assert "error" in result


def test_export_graph_json() -> None:
    result = export_graph(format="json")
    data = json.loads(result)
    assert "nodes" in data
    assert "links" in data


def test_export_graph_dot() -> None:
    result = export_graph(format="dot")
    assert "digraph" in result


def test_export_graph_with_filter() -> None:
    result = export_graph(format="json", file_filter="app")
    data = json.loads(result)
    assert "nodes" in data


def test_find_path_target_not_found() -> None:
    result = json.loads(find_path_between_symbols("main", "nonexistent"))
    assert "error" in result


@patch("codeatlas.git_integration.analyze_change_impact")
def test_get_change_impact_tool(mock_impact) -> None:
    from codeatlas.git_integration import ChangedSymbol, ChangeImpact
    from codeatlas.models import Position, Span, Symbol, SymbolKind

    sym = Symbol(
        id="app.py::main",
        name="main",
        qualified_name="main",
        kind=SymbolKind.FUNCTION,
        file_path="app.py",
        span=Span(start=Position(line=0, column=0), end=Position(line=5, column=0)),
        language="python",
    )
    mock_impact.return_value = ChangeImpact(
        changed_files=["app.py"],
        changed_symbols=[ChangedSymbol(symbol=sym, change_type="modified")],
        affected_symbols=[],
        affected_files=[],
    )
    result = json.loads(get_change_impact(repo_path="/tmp/fake"))
    assert result["changed_files"] == ["app.py"]
    assert len(result["changed_symbols"]) == 1
    assert result["changed_symbols"][0]["name"] == "main"


# --- search_symbols with filters ---


def test_search_symbols_with_kind_filter() -> None:
    result = json.loads(search_symbols("main", kind_filter="function"))
    assert result["count"] >= 1
    for r in result["results"]:
        assert r["kind"] == "function"


def test_search_symbols_with_file_filter() -> None:
    result = json.loads(search_symbols("main", file_filter="app"))
    assert result["count"] >= 1
    for r in result["results"]:
        assert "app" in r["file"]


# --- get_symbol_details ---


def test_get_symbol_details_found() -> None:
    result = json.loads(get_symbol_details("main"))
    assert result["count"] == 1
    sym = result["symbols"][0]
    assert sym["kind"] == "function"
    assert sym["file"] == "app.py"
    assert "relationships" in sym
    assert "signature" in sym
    assert "docstring" in sym


def test_get_symbol_details_outgoing_count() -> None:
    result = json.loads(get_symbol_details("main"))
    sym = result["symbols"][0]
    # main has 2 outgoing relationships (calls helper + imports Widget)
    assert sym["relationships"]["outgoing_count"] == 2
    assert sym["relationships"]["incoming_count"] == 0


def test_get_symbol_details_not_found() -> None:
    result = json.loads(get_symbol_details("nonexistent_xyz"))
    assert "error" in result


# --- list_symbols_by_kind ---


def test_list_symbols_by_kind_class() -> None:
    result = json.loads(list_symbols_by_kind("class"))
    assert result["kind"] == "class"
    assert result["count"] >= 1
    names = [s["name"] for s in result["symbols"]]
    assert "Widget" in names


def test_list_symbols_by_kind_function() -> None:
    result = json.loads(list_symbols_by_kind("function"))
    names = [s["name"] for s in result["symbols"]]
    assert "main" in names


def test_list_symbols_by_kind_invalid() -> None:
    result = json.loads(list_symbols_by_kind("nonexistentkind"))
    assert result["count"] == 0
    assert result["symbols"] == []


def test_list_symbols_by_kind_with_filter() -> None:
    result = json.loads(list_symbols_by_kind("function", file_filter="app"))
    assert result["count"] >= 1
    for s in result["symbols"]:
        assert "app" in s["file"]
