"""Tests for graph export to DOT and JSON formats."""

import json

import pytest

from codeatlas.graph.export import ExportOptions, export_dot, export_json
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


def _sym(name: str, kind: SymbolKind = SymbolKind.FUNCTION, fp: str = "app.py") -> Symbol:
    return Symbol(
        id=f"{fp}::{name}",
        name=name,
        qualified_name=name,
        kind=kind,
        file_path=fp,
        span=Span(start=Position(line=0, column=0), end=Position(line=5, column=0)),
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


@pytest.fixture
def populated_store() -> GraphStore:
    store = GraphStore(":memory:")
    s1 = _sym("main", SymbolKind.FUNCTION, "app.py")
    s2 = _sym("helper", SymbolKind.FUNCTION, "utils.py")
    rel = _rel("app.py::main", "utils.py::helper")
    store.upsert_parse_result(_result("app.py", [s1], [rel]))
    store.upsert_parse_result(_result("utils.py", [s2]))
    return store


def test_export_dot_produces_valid_output(populated_store: GraphStore) -> None:
    dot = export_dot(populated_store)
    assert dot.startswith("digraph codeatlas")
    assert "main" in dot
    assert "helper" in dot
    assert "}" in dot


def test_export_dot_includes_edges(populated_store: GraphStore) -> None:
    dot = export_dot(populated_store)
    assert "->" in dot
    assert "calls" in dot


def test_export_dot_excludes_externals_by_default(graph_store: GraphStore) -> None:
    sym = _sym("foo")
    rel = _rel("app.py::foo", "<unresolved>::bar")
    graph_store.upsert_parse_result(_result("app.py", [sym], [rel]))
    dot = export_dot(graph_store)
    assert "<unresolved>" not in dot


def test_export_dot_includes_externals_when_asked(graph_store: GraphStore) -> None:
    sym = _sym("foo")
    rel = _rel("app.py::foo", "<unresolved>::bar")
    graph_store.upsert_parse_result(_result("app.py", [sym], [rel]))
    dot = export_dot(graph_store, ExportOptions(include_externals=True))
    assert "bar" in dot


def test_export_dot_file_filter(populated_store: GraphStore) -> None:
    dot = export_dot(populated_store, ExportOptions(file_filter="app"))
    assert "main" in dot
    assert "helper" not in dot


def test_export_json_produces_valid_json(populated_store: GraphStore) -> None:
    output = export_json(populated_store)
    data = json.loads(output)
    assert "nodes" in data
    assert "links" in data
    assert len(data["nodes"]) == 2


def test_export_json_has_links(populated_store: GraphStore) -> None:
    output = export_json(populated_store)
    data = json.loads(output)
    assert len(data["links"]) == 1
    assert data["links"][0]["kind"] == "calls"


def test_export_json_file_filter(populated_store: GraphStore) -> None:
    output = export_json(populated_store, ExportOptions(file_filter="utils"))
    data = json.loads(output)
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["name"] == "helper"
