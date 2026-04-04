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
            raise RuntimeError("No graph database found. Run 'codeatlas index' first.")
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
        results.append(
            {
                "symbol": sym.qualified_name,
                "file": sym.file_path,
                "depends_on": [{"target": r.target_id, "kind": r.kind.value} for r in outgoing],
                "depended_by": [{"source": r.source_id, "kind": r.kind.value} for r in incoming],
            }
        )
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
    return json.dumps(
        {
            "symbol": sym.qualified_name,
            "file": sym.file_path,
            "call_chain": chain,
        },
        indent=2,
    )


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
    return json.dumps(
        {
            "symbol": sym.qualified_name,
            "file": sym.file_path,
            "affected": impact,
        },
        indent=2,
    )


@mcp.tool()
def search_symbols(query: str, limit: int = 20) -> str:
    """Search for symbols by name, docstring, or signature using full-text search."""
    store = get_store()
    results = store.search(query, limit=limit)
    return json.dumps(
        {
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
        },
        indent=2,
    )


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
    """Get summary statistics of the indexed knowledge graph.

    Returns file/symbol/relationship counts plus breakdowns by language and symbol kind.
    """
    store = get_store()
    stats = store.get_stats()
    stats["languages"] = store.get_language_breakdown()
    stats["kinds"] = store.get_kind_breakdown()
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
def detect_circular_dependencies() -> str:
    """Detect circular dependencies (import/call cycles) in the codebase.

    Returns cycles where A depends on B depends on C depends on A.
    Useful for identifying architectural issues.
    """
    store = get_store()
    cycles = store.detect_cycles()
    return json.dumps(
        {
            "cycle_count": len(cycles),
            "cycles": [{"symbols": cycle, "length": len(cycle)} for cycle in cycles],
        },
        indent=2,
    )


@mcp.tool()
def find_dead_code() -> str:
    """Find symbols that are never referenced by anything else (potential dead code).

    Returns functions, classes, and methods with zero incoming relationships.
    Excludes entry points like main, __init__, and module-level imports.
    """
    store = get_store()
    unused = store.find_unused_symbols()
    return json.dumps(
        {
            "count": len(unused),
            "unused_symbols": [
                {
                    "name": s.qualified_name,
                    "kind": s.kind.value,
                    "file": s.file_path,
                    "line": s.span.start.line + 1,
                }
                for s in unused
            ],
        },
        indent=2,
    )


@mcp.tool()
def analyze_complexity(limit: int = 20) -> str:
    """Analyze symbol coupling by computing degree centrality.

    Returns the most connected symbols (highest in-degree + out-degree),
    which are the most critical and potentially most complex parts of the codebase.
    """
    store = get_store()
    centrality = store.get_symbol_centrality(limit=limit)
    return json.dumps(
        {
            "count": len(centrality),
            "symbols": centrality,
        },
        indent=2,
    )


@mcp.tool()
def find_path_between_symbols(source: str, target: str, max_depth: int = 10) -> str:
    """Find the shortest dependency path between two symbols.

    Args:
        source: Name of the starting symbol
        target: Name of the destination symbol
        max_depth: Maximum path length to search
    """
    store = get_store()
    src_matches = store.find_symbols_by_name(source)
    tgt_matches = store.find_symbols_by_name(target)

    if not src_matches:
        return json.dumps({"error": f"Source symbol '{source}' not found"})
    if not tgt_matches:
        return json.dumps({"error": f"Target symbol '{target}' not found"})

    src_sym = src_matches[0]
    tgt_sym = tgt_matches[0]
    path = store.find_path(src_sym.id, tgt_sym.id, max_depth=max_depth)

    if path is None:
        return json.dumps(
            {
                "source": src_sym.qualified_name,
                "target": tgt_sym.qualified_name,
                "path": None,
                "message": "No path found between these symbols",
            }
        )

    return json.dumps(
        {
            "source": src_sym.qualified_name,
            "target": tgt_sym.qualified_name,
            "path": path,
            "length": len(path) - 1,
        },
        indent=2,
    )


@mcp.tool()
def get_file_coupling(limit: int = 20) -> str:
    """Analyze coupling between files based on cross-file relationships.

    Returns file pairs ranked by how many relationships exist between them.
    High coupling between files may indicate they should be merged or refactored.
    """
    store = get_store()
    coupling = store.get_file_coupling(limit=limit)
    return json.dumps(
        {
            "count": len(coupling),
            "file_pairs": coupling,
        },
        indent=2,
    )


@mcp.tool()
def get_change_impact(repo_path: str = ".", ref: str = "HEAD", max_depth: int = 3) -> str:
    """Analyze the impact of current git changes on the codebase.

    Detects which files/symbols changed in the current git diff, then traces
    reverse dependencies to find all affected symbols and files.

    Args:
        repo_path: Path to the git repository
        ref: Git ref to diff against (default: HEAD for uncommitted changes)
        max_depth: How deep to trace reverse dependencies
    """
    from pathlib import Path

    from codeatlas.git_integration import analyze_change_impact

    store = get_store()
    result = analyze_change_impact(store, Path(repo_path), ref=ref, max_depth=max_depth)

    return json.dumps(
        {
            "changed_files": result.changed_files,
            "changed_symbols": [
                {
                    "name": cs.symbol.qualified_name,
                    "kind": cs.symbol.kind.value,
                    "file": cs.symbol.file_path,
                    "line": cs.symbol.span.start.line + 1,
                    "change_type": cs.change_type,
                }
                for cs in result.changed_symbols
            ],
            "affected_symbols": [
                {
                    "name": s.qualified_name,
                    "kind": s.kind.value,
                    "file": s.file_path,
                    "line": s.span.start.line + 1,
                }
                for s in result.affected_symbols
            ],
            "affected_files": result.affected_files,
        },
        indent=2,
    )


@mcp.tool()
def find_similar_code(query: str, limit: int = 10) -> str:
    """Natural language search across the codebase using semantic similarity.

    Examples: "find all places where we handle authentication errors",
    "show me the database connection setup"
    """
    store = get_store()
    sem = get_semantic_index()
    results = sem.search(query, store, limit=limit)
    return json.dumps(
        {
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
        },
        indent=2,
    )
