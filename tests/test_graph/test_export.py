"""Tests for graph export to DOT and JSON formats."""

import json

import pytest

from codeatlas.graph.export import ExportOptions, export_dot, export_json, export_mermaid
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


# --- Mermaid export ---


@pytest.fixture
def class_store() -> GraphStore:
    """Store with a class hierarchy for testing the Mermaid classDiagram output."""
    store = GraphStore(":memory:")
    base = Symbol(
        id="src/shapes.py::Shape",
        name="Shape",
        qualified_name="Shape",
        kind=SymbolKind.CLASS,
        file_path="src/shapes.py",
        span=Span(start=Position(line=0, column=0), end=Position(line=10, column=0)),
        language="python",
    )
    circle = Symbol(
        id="src/shapes.py::Circle",
        name="Circle",
        qualified_name="Circle",
        kind=SymbolKind.CLASS,
        file_path="src/shapes.py",
        span=Span(start=Position(line=12, column=0), end=Position(line=20, column=0)),
        language="python",
    )
    drawable = Symbol(
        id="src/shapes.py::Drawable",
        name="Drawable",
        qualified_name="Drawable",
        kind=SymbolKind.INTERFACE,
        file_path="src/shapes.py",
        span=Span(start=Position(line=22, column=0), end=Position(line=25, column=0)),
        language="python",
    )
    draw = Symbol(
        id="src/shapes.py::Shape.draw",
        name="draw",
        qualified_name="Shape.draw",
        kind=SymbolKind.METHOD,
        file_path="src/shapes.py",
        span=Span(start=Position(line=2, column=4), end=Position(line=4, column=0)),
        language="python",
        signature="def draw(self) -> None",
    )
    rel_inherits = Relationship(
        source_id="src/shapes.py::Circle",
        target_id="src/shapes.py::Shape",
        kind=RelationshipKind.INHERITS,
        file_path="src/shapes.py",
    )
    rel_implements = Relationship(
        source_id="src/shapes.py::Shape",
        target_id="src/shapes.py::Drawable",
        kind=RelationshipKind.IMPLEMENTS,
        file_path="src/shapes.py",
    )
    store.upsert_parse_result(
        _result(
            "src/shapes.py",
            [base, circle, drawable, draw],
            [rel_inherits, rel_implements],
        )
    )
    return store


def test_export_mermaid_starts_with_class_diagram(class_store: GraphStore) -> None:
    out = export_mermaid(class_store)
    assert out.startswith("classDiagram")


def test_export_mermaid_includes_classes(class_store: GraphStore) -> None:
    out = export_mermaid(class_store)
    assert "class Shape" in out
    assert "class Circle" in out


def test_export_mermaid_includes_interface_marker(class_store: GraphStore) -> None:
    out = export_mermaid(class_store)
    assert "class Drawable" in out
    assert "<<interface>>" in out


def test_export_mermaid_includes_methods(class_store: GraphStore) -> None:
    out = export_mermaid(class_store)
    assert "+def draw(self) -> None" in out


def test_export_mermaid_includes_inheritance_arrow(class_store: GraphStore) -> None:
    out = export_mermaid(class_store)
    assert "Shape <|-- Circle" in out


def test_export_mermaid_includes_implements_arrow(class_store: GraphStore) -> None:
    out = export_mermaid(class_store)
    assert "Drawable <|.. Shape" in out


def test_export_mermaid_with_file_filter(class_store: GraphStore) -> None:
    out = export_mermaid(class_store, ExportOptions(file_filter="src/"))
    assert "Shape" in out
    out_no_match = export_mermaid(class_store, ExportOptions(file_filter="other/"))
    assert "Shape" not in out_no_match


def test_export_mermaid_handles_unresolved_target() -> None:
    store = GraphStore(":memory:")
    sym = Symbol(
        id="app.py::MyClass",
        name="MyClass",
        qualified_name="MyClass",
        kind=SymbolKind.CLASS,
        file_path="app.py",
        span=Span(start=Position(line=0, column=0), end=Position(line=5, column=0)),
        language="python",
    )
    rel = Relationship(
        source_id="app.py::MyClass",
        target_id="<unresolved>::ExternalBase",
        kind=RelationshipKind.INHERITS,
        file_path="app.py",
    )
    store.upsert_parse_result(_result("app.py", [sym], [rel]))
    out = export_mermaid(store)
    assert "ExternalBase <|-- MyClass" in out


def test_export_mermaid_truncates_long_signatures() -> None:
    store = GraphStore(":memory:")
    cls = Symbol(
        id="app.py::Big",
        name="Big",
        qualified_name="Big",
        kind=SymbolKind.CLASS,
        file_path="app.py",
        span=Span(start=Position(line=0, column=0), end=Position(line=5, column=0)),
        language="python",
    )
    long_sig = "def very_long_method_name(" + ", ".join(f"arg{i}: int" for i in range(15)) + ")"
    method = Symbol(
        id="app.py::Big.huge_method",
        name="huge_method",
        qualified_name="Big.huge_method",
        kind=SymbolKind.METHOD,
        file_path="app.py",
        span=Span(start=Position(line=2, column=4), end=Position(line=4, column=0)),
        language="python",
        signature=long_sig,
    )
    store.upsert_parse_result(_result("app.py", [cls, method]))
    out = export_mermaid(store)
    assert "..." in out  # truncated
