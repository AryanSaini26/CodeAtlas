"""Tests for graph analysis methods: cycle detection, unused symbols, centrality."""

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


def _sym(
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


def _rel(
    source: str,
    target: str,
    kind: RelationshipKind = RelationshipKind.CALLS,
    file_path: str = "test.py",
) -> Relationship:
    return Relationship(source_id=source, target_id=target, kind=kind, file_path=file_path)


def _result(
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
            size_bytes=100,
        ),
        symbols=syms,
        relationships=rels,
    )


# --- Cycle detection ---


class TestDetectCycles:
    def test_no_cycles_in_empty_graph(self) -> None:
        store = GraphStore(":memory:")
        assert store.detect_cycles() == []

    def test_no_cycles_in_linear_chain(self) -> None:
        store = GraphStore(":memory:")
        a, b, c = _sym("a", line=0), _sym("b", line=10), _sym("c", line=20)
        store.upsert_parse_result(
            _result(
                symbols=[a, b, c],
                relationships=[
                    _rel(a.id, b.id),
                    _rel(b.id, c.id),
                ],
            )
        )
        assert store.detect_cycles() == []

    def test_detects_simple_cycle(self) -> None:
        store = GraphStore(":memory:")
        a, b = _sym("a", line=0), _sym("b", line=10)
        store.upsert_parse_result(
            _result(
                symbols=[a, b],
                relationships=[
                    _rel(a.id, b.id),
                    _rel(b.id, a.id),
                ],
            )
        )
        cycles = store.detect_cycles()
        assert len(cycles) == 1
        assert set(cycles[0]) == {a.id, b.id}

    def test_detects_three_node_cycle(self) -> None:
        store = GraphStore(":memory:")
        a, b, c = _sym("a", line=0), _sym("b", line=10), _sym("c", line=20)
        store.upsert_parse_result(
            _result(
                symbols=[a, b, c],
                relationships=[
                    _rel(a.id, b.id),
                    _rel(b.id, c.id),
                    _rel(c.id, a.id),
                ],
            )
        )
        cycles = store.detect_cycles()
        assert len(cycles) == 1
        assert set(cycles[0]) == {a.id, b.id, c.id}

    def test_ignores_external_references(self) -> None:
        store = GraphStore(":memory:")
        a = _sym("a", line=0)
        store.upsert_parse_result(
            _result(
                symbols=[a],
                relationships=[
                    _rel(a.id, "<external>::os"),
                    _rel("<external>::os", a.id),
                ],
            )
        )
        assert store.detect_cycles() == []

    def test_filters_by_relationship_kind(self) -> None:
        store = GraphStore(":memory:")
        a, b = _sym("a", line=0), _sym("b", line=10)
        store.upsert_parse_result(
            _result(
                symbols=[a, b],
                relationships=[
                    _rel(a.id, b.id, kind=RelationshipKind.INHERITS),
                    _rel(b.id, a.id, kind=RelationshipKind.INHERITS),
                ],
            )
        )
        # Default kinds are calls + imports, so inherits cycle should not appear
        assert store.detect_cycles() == []
        # But explicitly asking for inherits should find it
        cycles = store.detect_cycles(relationship_kinds=["inherits"])
        assert len(cycles) == 1


# --- Unused symbols ---


class TestFindUnusedSymbols:
    def test_empty_graph(self) -> None:
        store = GraphStore(":memory:")
        assert store.find_unused_symbols() == []

    def test_all_symbols_referenced(self) -> None:
        store = GraphStore(":memory:")
        a, b = _sym("a", line=0), _sym("b", line=10)
        store.upsert_parse_result(
            _result(
                symbols=[a, b],
                relationships=[
                    _rel(a.id, b.id),
                    _rel(b.id, a.id),
                ],
            )
        )
        assert store.find_unused_symbols() == []

    def test_finds_unreferenced_symbol(self) -> None:
        store = GraphStore(":memory:")
        a = _sym("a", line=0)
        b = _sym("b", line=10)
        orphan = _sym("orphan", line=20)
        store.upsert_parse_result(
            _result(
                symbols=[a, b, orphan],
                relationships=[_rel(a.id, b.id)],
            )
        )
        unused = store.find_unused_symbols()
        unused_names = [s.name for s in unused]
        assert "orphan" in unused_names
        # 'a' has no incoming either, but it's still in unused
        assert "a" in unused_names
        # 'b' is referenced by 'a', so it should NOT be unused
        assert "b" not in unused_names

    def test_excludes_modules_and_imports(self) -> None:
        store = GraphStore(":memory:")
        mod = _sym("mymodule", kind=SymbolKind.MODULE)
        imp = _sym("os_import", kind=SymbolKind.IMPORT, line=5)
        func = _sym("helper", kind=SymbolKind.FUNCTION, line=10)
        store.upsert_parse_result(_result(symbols=[mod, imp, func]))
        unused = store.find_unused_symbols()
        unused_names = [s.name for s in unused]
        assert "mymodule" not in unused_names
        assert "os_import" not in unused_names
        assert "helper" in unused_names

    def test_excludes_entry_points(self) -> None:
        store = GraphStore(":memory:")
        main = _sym("main", line=0)
        init = _sym("__init__", line=5)
        helper = _sym("helper", line=10)
        store.upsert_parse_result(_result(symbols=[main, init, helper]))
        unused = store.find_unused_symbols()
        unused_names = [s.name for s in unused]
        assert "main" not in unused_names
        assert "__init__" not in unused_names
        assert "helper" in unused_names


# --- Symbol centrality ---


class TestSymbolCentrality:
    def test_empty_graph(self) -> None:
        store = GraphStore(":memory:")
        assert store.get_symbol_centrality() == []

    def test_centrality_values(self) -> None:
        store = GraphStore(":memory:")
        hub = _sym("hub", line=0)
        a = _sym("a", line=10)
        b = _sym("b", line=20)
        c = _sym("c", line=30)
        store.upsert_parse_result(
            _result(
                symbols=[hub, a, b, c],
                relationships=[
                    _rel(hub.id, a.id),
                    _rel(hub.id, b.id),
                    _rel(hub.id, c.id),
                    _rel(a.id, hub.id),
                ],
            )
        )
        centrality = store.get_symbol_centrality()
        # hub should be first (out=3, in=1, total=4)
        assert centrality[0]["name"] == "hub"
        assert centrality[0]["out_degree"] == 3
        assert centrality[0]["in_degree"] == 1
        assert centrality[0]["total_degree"] == 4

    def test_respects_limit(self) -> None:
        store = GraphStore(":memory:")
        symbols = [_sym(f"s{i}", line=i * 10) for i in range(10)]
        rels = [_rel(symbols[0].id, symbols[i].id) for i in range(1, 10)]
        store.upsert_parse_result(_result(symbols=symbols, relationships=rels))
        result = store.get_symbol_centrality(limit=3)
        assert len(result) == 3

    def test_excludes_zero_degree(self) -> None:
        store = GraphStore(":memory:")
        connected = _sym("connected", line=0)
        isolated = _sym("isolated", line=10)
        target = _sym("target", line=20)
        store.upsert_parse_result(
            _result(
                symbols=[connected, isolated, target],
                relationships=[_rel(connected.id, target.id)],
            )
        )
        centrality = store.get_symbol_centrality()
        names = [c["name"] for c in centrality]
        assert "isolated" not in names
        assert "connected" in names
        assert "target" in names
