"""Tests for the MCP server tool functions."""

import json
from typing import Any
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
    find_by_decorator,
    find_dead_code,
    find_path_between_symbols,
    get_api_surface,
    get_change_impact,
    get_coverage_gaps,
    get_dependencies,
    get_file_content,
    get_file_coupling,
    get_file_dependencies,
    get_file_overview,
    get_graph_stats,
    get_hotspots,
    get_impact_analysis,
    get_module_overview,
    get_symbol_coverage,
    get_symbol_details,
    get_symbol_history,
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


# --- get_api_surface ---


def test_get_api_surface_returns_public_symbols() -> None:
    result = json.loads(get_api_surface())
    assert result["total"] >= 1
    all_names = [s["name"] for f in result["files"] for s in f["symbols"]]
    assert "main" in all_names
    assert "Widget" in all_names


def test_get_api_surface_excludes_private() -> None:
    from codeatlas.models import Position, Span, Symbol, SymbolKind

    store = GraphStore(":memory:")
    pub = Symbol(
        id="app2.py::public_fn",
        name="public_fn",
        qualified_name="public_fn",
        kind=SymbolKind.FUNCTION,
        file_path="app2.py",
        span=Span(start=Position(line=0, column=0), end=Position(line=5, column=0)),
        language="python",
    )
    priv = Symbol(
        id="app2.py::_private_fn",
        name="_private_fn",
        qualified_name="_private_fn",
        kind=SymbolKind.FUNCTION,
        file_path="app2.py",
        span=Span(start=Position(line=6, column=0), end=Position(line=10, column=0)),
        language="python",
    )
    from codeatlas.models import FileInfo, ParseResult

    store.upsert_parse_result(
        ParseResult(
            file_info=FileInfo(path="app2.py", language="python", content_hash="x"),
            symbols=[pub, priv],
            relationships=[],
        )
    )
    set_store(store)
    result = json.loads(get_api_surface())
    all_names = [s["name"] for f in result["files"] for s in f["symbols"]]
    assert "public_fn" in all_names
    assert "_private_fn" not in all_names


def test_get_api_surface_with_file_filter() -> None:
    result = json.loads(get_api_surface(file_filter="app"))
    for f in result["files"]:
        assert "app" in f["file"]


# --- get_symbol_coverage ---


def test_get_symbol_coverage_covered() -> None:
    from codeatlas.models import FileInfo, ParseResult, Position, Span, Symbol, SymbolKind

    store = GraphStore(":memory:")
    prod = Symbol(
        id="src/svc.py::process",
        name="process",
        qualified_name="process",
        kind=SymbolKind.FUNCTION,
        file_path="src/svc.py",
        span=Span(start=Position(line=0, column=0), end=Position(line=5, column=0)),
        language="python",
    )
    test_fn = Symbol(
        id="tests/test_svc.py::test_process",
        name="test_process",
        qualified_name="test_process",
        kind=SymbolKind.FUNCTION,
        file_path="tests/test_svc.py",
        span=Span(start=Position(line=0, column=0), end=Position(line=5, column=0)),
        language="python",
        is_test=True,
    )
    rel = Relationship(
        source_id="tests/test_svc.py::test_process",
        target_id="src/svc.py::process",
        kind=RelationshipKind.CALLS,
        file_path="tests/test_svc.py",
    )
    store.upsert_parse_result(
        ParseResult(
            file_info=FileInfo(path="src/svc.py", language="python", content_hash="a"),
            symbols=[prod],
            relationships=[],
        )
    )
    store.upsert_parse_result(
        ParseResult(
            file_info=FileInfo(path="tests/test_svc.py", language="python", content_hash="b"),
            symbols=[test_fn],
            relationships=[rel],
        )
    )
    set_store(store)
    result = json.loads(get_symbol_coverage("process"))
    assert "results" in result
    assert len(result["results"]) >= 1
    entry = result["results"][0]
    assert entry["covered"] is True
    assert any(r["name"] == "test_process" for r in entry["test_references"])


def test_get_symbol_coverage_not_covered() -> None:
    result = json.loads(get_symbol_coverage("helper"))
    assert "results" in result
    entry = result["results"][0]
    assert entry["covered"] is False
    assert entry["test_references"] == []


def test_get_symbol_coverage_not_found() -> None:
    result = json.loads(get_symbol_coverage("does_not_exist_xyz"))
    assert "error" in result


# --- get_hotspots ---


def test_get_hotspots_no_git(tmp_path: Any) -> None:
    # Non-git directory → empty hotspots list, not an error
    result = json.loads(get_hotspots(repo_path=str(tmp_path), limit=5))
    assert result["count"] == 0
    assert result["hotspots"] == []


def test_get_hotspots_with_mocked_churn(tmp_path: Any) -> None:
    # Mock git churn so we can exercise the join logic without a real repo
    with patch("codeatlas.git_integration.get_git_churn") as mock_churn:
        mock_churn.return_value = [
            {"file": "app.py", "commits": 5},
            {"file": "utils.py", "commits": 3},
        ]
        result = json.loads(get_hotspots(repo_path=str(tmp_path), limit=10))
        assert result["count"] == 2
        scores = {h["file"]: h["hotspot_score"] for h in result["hotspots"]}
        # app.py has main with 0 in_degree → score = 5 * (1 + 0) = 5
        # utils.py has helper with in_degree 1 → score = 3 * (1 + 1) = 6
        assert scores["utils.py"] > scores["app.py"]


# --- find_by_decorator ---


def test_find_by_decorator_finds_match() -> None:
    from codeatlas.models import FileInfo, ParseResult, Position, Span, Symbol, SymbolKind

    store = GraphStore(":memory:")
    decorated = Symbol(
        id="api.py::route_handler",
        name="route_handler",
        qualified_name="route_handler",
        kind=SymbolKind.FUNCTION,
        file_path="api.py",
        span=Span(start=Position(line=0, column=0), end=Position(line=5, column=0)),
        language="python",
        decorators=["app.route", "login_required"],
    )
    store.upsert_parse_result(
        ParseResult(
            file_info=FileInfo(path="api.py", language="python", content_hash="x"),
            symbols=[decorated],
            relationships=[],
        )
    )
    set_store(store)
    result = json.loads(find_by_decorator("route"))
    assert result["count"] == 1
    assert result["symbols"][0]["name"] == "route_handler"
    assert "app.route" in result["symbols"][0]["decorators"]


def test_find_by_decorator_no_match() -> None:
    result = json.loads(find_by_decorator("nonexistent_decorator_xyz"))
    assert result["count"] == 0
    assert result["symbols"] == []


# --- get_symbol_history ---


def test_get_symbol_history_symbol_not_found() -> None:
    result = json.loads(get_symbol_history("nonexistent_xyz_123"))
    assert "error" in result


def test_get_symbol_history_no_git(tmp_path: Any) -> None:
    # main exists in fixture but tmp_path has no git → 0 commits, no error
    result = json.loads(get_symbol_history("main", repo_path=str(tmp_path)))
    assert result["symbol"] == "main"
    assert result["commit_count"] == 0


def test_get_symbol_history_parses_commits(tmp_path: Any) -> None:
    fake_output = (
        "abc12345\x1fAlice\x1falice@example.com\x1f2026-01-01\x1fInitial commit\n"
        "def67890\x1fBob\x1fbob@example.com\x1f2026-01-02\x1fFix bug"
    )
    mock_result = type("MockResult", (), {"stdout": fake_output})()
    with patch("subprocess.run", return_value=mock_result):
        result = json.loads(get_symbol_history("main", repo_path="."))
    assert result["commit_count"] == 2
    assert result["commits"][0]["author"] == "Alice"
    assert result["commits"][0]["hash"] == "abc12345"
    assert result["commits"][1]["message"] == "Fix bug"


# --- export_graph mermaid format ---


def test_export_graph_mermaid_format() -> None:
    out = export_graph(format="mermaid")
    assert out.startswith("classDiagram")


def test_export_graph_dot_format() -> None:
    out = export_graph(format="dot")
    assert out.startswith("digraph")


def test_export_graph_default_is_json() -> None:
    out = export_graph()
    data = json.loads(out)
    assert "nodes" in data
    assert "links" in data


# --- get_coverage_gaps ---


def test_get_coverage_gaps_empty() -> None:
    """With no test-file symbols, all public symbols are gaps."""
    result = json.loads(get_coverage_gaps())
    assert "total_uncovered" in result
    assert "files" in result
    assert isinstance(result["total_uncovered"], int)


def test_get_coverage_gaps_with_file_filter() -> None:
    result = json.loads(get_coverage_gaps(file_filter="app.py"))
    assert result["file_filter"] == "app.py"
    assert "files" in result


def test_get_coverage_gaps_limit() -> None:
    result = json.loads(get_coverage_gaps(limit=1))
    total = result["total_uncovered"]
    returned = sum(len(f["symbols"]) for f in result["files"])
    assert returned <= min(total, 1)


# --- get_file_content ---


def test_get_file_content_not_found() -> None:
    result = json.loads(get_file_content("/nonexistent/path/file.py"))
    assert "error" in result


def test_get_file_content_full_file(tmp_path: Any) -> None:
    f = tmp_path / "hello.py"
    f.write_text("def foo():\n    return 1\n")
    result = json.loads(get_file_content(str(f)))
    assert result["content"] == "def foo():\n    return 1\n"
    assert result["total_lines"] == 2
    assert result["start_line"] == 1
    assert result["end_line"] == 2


def test_get_file_content_line_range(tmp_path: Any) -> None:
    f = tmp_path / "multi.py"
    f.write_text("line1\nline2\nline3\nline4\nline5\n")
    result = json.loads(get_file_content(str(f), start_line=2, end_line=4))
    assert result["content"] == "line2\nline3\nline4"
    assert result["start_line"] == 2
    assert result["end_line"] == 4


def test_get_file_content_start_only(tmp_path: Any) -> None:
    f = tmp_path / "code.py"
    f.write_text("a\nb\nc\n")
    result = json.loads(get_file_content(str(f), start_line=2))
    assert "b" in result["content"]
    assert "c" in result["content"]


def test_get_file_content_file_path_in_result(tmp_path: Any) -> None:
    f = tmp_path / "src.py"
    f.write_text("x = 1\n")
    result = json.loads(get_file_content(str(f)))
    assert str(f) in result["file_path"]
