"""MCP server exposing CodeAtlas knowledge graph tools."""

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from codeatlas.graph.export import ExportOptions, export_dot, export_json
from codeatlas.graph.store import GraphStore
from codeatlas.search.embeddings import SemanticIndex

mcp = FastMCP("codeatlas")

_store: GraphStore | None = None
_semantic: SemanticIndex | None = None


def get_store() -> GraphStore:
    global _store
    if _store is None:
        db_path = Path(".codeatlas/graph.db")
        if not db_path.exists():
            raise RuntimeError(
                "No graph database found. Run 'codeatlas index' first."
            )
        _store = GraphStore(db_path)
    return _store


def set_store(store: GraphStore) -> None:
    """Inject a store instance (used by CLI and tests)."""
    global _store
    _store = store


def get_semantic_index() -> SemanticIndex:
    global _semantic
    if _semantic is None:
        _semantic = SemanticIndex()
        store = get_store()
        db_path = Path(".codeatlas")
        if not _semantic.load(db_path):
            _semantic.build_from_store(store)
            db_path.mkdir(parents=True, exist_ok=True)
            _semantic.save(db_path)
    return _semantic


@mcp.tool()
def get_file_overview(path: str) -> str:
    """Get a structural summary of a source file: all symbols, their kinds, and line numbers."""
    store = get_store()
    symbols = store.get_symbols_in_file(path)
    if not symbols:
        return json.dumps({"error": f"No symbols found for {path}"})

    result = {
        "file": path,
        "symbol_count": len(symbols),
        "symbols": [
            {
                "name": s.qualified_name,
                "kind": s.kind.value,
                "line": s.span.start.line + 1,
                "signature": s.signature,
                "docstring": s.docstring,
            }
            for s in symbols
        ],
    }
    return json.dumps(result, indent=2)


@mcp.tool()
def get_dependencies(symbol_name: str) -> str:
    """Find what a symbol depends on and what depends on it.

    Accepts a symbol name (e.g. 'UserService') and returns incoming/outgoing relationships.
    """
    store = get_store()
    matches = store.find_symbols_by_name(symbol_name)
    if not matches:
        return json.dumps({"error": f"Symbol '{symbol_name}' not found"})

    results = []
    for sym in matches:
        outgoing = store.get_dependencies(sym.id)
        incoming = store.get_dependents(sym.id)
        results.append({
            "symbol": sym.qualified_name,
            "file": sym.file_path,
            "depends_on": [
                {"target": r.target_id, "kind": r.kind.value} for r in outgoing
            ],
            "depended_by": [
                {"source": r.source_id, "kind": r.kind.value} for r in incoming
            ],
        })
    return json.dumps(results, indent=2)


@mcp.tool()
def trace_call_chain(symbol_name: str, max_depth: int = 5) -> str:
    """Trace the full call graph starting from a symbol.

    Shows what functions/methods are called transitively.
    """
    store = get_store()
    matches = store.find_symbols_by_name(symbol_name)
    if not matches:
        return json.dumps({"error": f"Symbol '{symbol_name}' not found"})

    sym = matches[0]
    chain = store.trace_call_chain(sym.id, max_depth=max_depth)
    return json.dumps({
        "symbol": sym.qualified_name,
        "file": sym.file_path,
        "call_chain": chain,
    }, indent=2)


@mcp.tool()
def get_impact_analysis(symbol_name: str, max_depth: int = 5) -> str:
    """Analyze what would be affected if a symbol changes.

    Traces reverse dependencies to find all callers/importers.
    """
    store = get_store()
    matches = store.find_symbols_by_name(symbol_name)
    if not matches:
        return json.dumps({"error": f"Symbol '{symbol_name}' not found"})

    sym = matches[0]
    impact = store.get_impact_analysis(sym.id, max_depth=max_depth)
    return json.dumps({
        "symbol": sym.qualified_name,
        "file": sym.file_path,
        "affected": impact,
    }, indent=2)


@mcp.tool()
def search_symbols(query: str, limit: int = 20) -> str:
    """Search for symbols by name, docstring, or signature using full-text search."""
    store = get_store()
    results = store.search(query, limit=limit)
    return json.dumps({
        "query": query,
        "count": len(results),
        "results": [
            {
                "name": s.qualified_name,
                "kind": s.kind.value,
                "file": s.file_path,
                "line": s.span.start.line + 1,
                "signature": s.signature,
                "docstring": s.docstring,
            }
            for s in results
        ],
    }, indent=2)


@mcp.tool()
def get_module_overview(directory: str) -> str:
    """Get a summary of all symbols in a directory/module.

    Shows file structure and public API at a glance.
    """
    store = get_store()
    overview = store.get_module_overview(directory)
    return json.dumps(overview, indent=2)


@mcp.tool()
def get_file_dependencies(path: str) -> str:
    """Show what files a given file depends on and what files depend on it."""
    store = get_store()
    deps = store.get_file_dependencies(path)
    return json.dumps({"file": path, **deps}, indent=2)


@mcp.tool()
def get_graph_stats() -> str:
    """Get summary statistics of the indexed knowledge graph."""
    store = get_store()
    stats = store.get_stats()
    return json.dumps(stats, indent=2)


@mcp.tool()
def export_graph(format: str = "json", file_filter: str | None = None) -> str:
    """Export the knowledge graph in DOT (Graphviz) or JSON (D3.js) format.

    Args:
        format: 'dot' or 'json'
        file_filter: Only include symbols from files matching this prefix
    """
    store = get_store()
    opts = ExportOptions(file_filter=file_filter)
    if format == "dot":
        return export_dot(store, opts)
    return export_json(store, opts)


@mcp.tool()
def find_similar_code(query: str, limit: int = 10) -> str:
    """Natural language search across the codebase using semantic similarity.

    Examples: "find all places where we handle authentication errors",
    "show me the database connection setup"
    """
    store = get_store()
    sem = get_semantic_index()
    results = sem.search(query, store, limit=limit)
    return json.dumps({
        "query": query,
        "count": len(results),
        "results": [
            {
                "name": sym.qualified_name,
                "kind": sym.kind.value,
                "file": sym.file_path,
                "line": sym.span.start.line + 1,
                "signature": sym.signature,
                "docstring": sym.docstring,
                "score": round(score, 4),
            }
            for sym, score in results
        ],
    }, indent=2)
