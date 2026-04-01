"""Tests for the MCP server tool functions."""

import json

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
    get_dependencies,
    get_file_dependencies,
    get_file_overview,
    get_graph_stats,
    get_impact_analysis,
    get_module_overview,
    search_symbols,
    set_store,
    trace_call_chain,
)


def _sym(name: str, kind: SymbolKind = SymbolKind.FUNCTION, fp: str = "app.py", line: int = 0) -> Symbol:
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


def _rel(src: str, tgt: str, kind: RelationshipKind = RelationshipKind.CALLS, fp: str = "app.py") -> Relationship:
    return Relationship(source_id=src, target_id=tgt, kind=kind, file_path=fp)


def _result(fp: str, syms: list[Symbol], rels: list[Relationship] | None = None) -> ParseResult:
    r = rels or []
    return ParseResult(
        file_info=FileInfo(path=fp, language="python", content_hash="abc", symbol_count=len(syms), relationship_count=len(r)),
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
