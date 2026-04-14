"""MCP server exposing CodeAtlas knowledge graph tools."""

import json
from pathlib import Path
from typing import Any

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
def search_symbols(
    query: str,
    limit: int = 20,
    file_filter: str | None = None,
    kind_filter: str | None = None,
) -> str:
    """Search for symbols by name, docstring, or signature using full-text search.

    Args:
        query: Search terms (supports camelCase and underscore expansion automatically)
        limit: Maximum results to return
        file_filter: Restrict to files whose path contains this substring (e.g. 'src/auth/')
        kind_filter: Restrict to a symbol kind: function, method, class, interface,
                     constant, variable, import, module, type_alias, enum, namespace
    """
    store = get_store()
    results = store.search(query, limit=limit, file_filter=file_filter, kind_filter=kind_filter)
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
def get_symbol_details(symbol_name: str) -> str:
    """Get full metadata and relationship summary for a named symbol in one call.

    Returns signature, docstring, decorators, location, and all incoming/outgoing
    relationships — eliminating the need to chain get_file_overview + get_dependencies.

    Args:
        symbol_name: Exact or partial symbol name (e.g. 'UserService', 'parse_file')
    """
    store = get_store()
    matches = store.find_symbols_by_name(symbol_name)
    if not matches:
        return json.dumps({"error": f"Symbol '{symbol_name}' not found"})

    results = []
    for sym in matches:
        deps = store.get_dependencies(sym.id)
        dependents = store.get_dependents(sym.id)
        results.append(
            {
                "id": sym.id,
                "name": sym.name,
                "qualified_name": sym.qualified_name,
                "kind": sym.kind.value,
                "file": sym.file_path,
                "line": sym.span.start.line + 1,
                "language": sym.language,
                "signature": sym.signature,
                "docstring": sym.docstring,
                "decorators": sym.decorators,
                "relationships": {
                    "outgoing_count": len(deps),
                    "incoming_count": len(dependents),
                    "depends_on": [{"target_id": r.target_id, "kind": r.kind.value} for r in deps],
                    "depended_by": [
                        {"source_id": r.source_id, "kind": r.kind.value} for r in dependents
                    ],
                },
            }
        )
    return json.dumps({"query": symbol_name, "count": len(results), "symbols": results}, indent=2)


@mcp.tool()
def list_symbols_by_kind(
    kind: str,
    file_filter: str | None = None,
    limit: int = 100,
) -> str:
    """List all symbols of a specific kind across the codebase.

    Useful for getting a complete inventory: 'show me all classes',
    'show me all interfaces', 'show me all functions in src/api/'.

    Args:
        kind: One of: function, method, class, interface, constant, variable,
              import, module, type_alias, enum, namespace
        file_filter: Optional path substring to restrict results (e.g. 'src/api/')
        limit: Maximum number of results (default 100)
    """
    store = get_store()
    results = store.get_symbols_by_kind(kind, file_filter=file_filter, limit=limit)
    return json.dumps(
        {
            "kind": kind,
            "file_filter": file_filter,
            "count": len(results),
            "symbols": [
                {
                    "name": s.qualified_name,
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
    stats: dict[str, Any] = dict(store.get_stats())
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


@mcp.tool()
def find_by_decorator(
    decorator_name: str,
    file_filter: str | None = None,
    limit: int = 50,
) -> str:
    """Find all symbols that have a specific decorator or annotation.

    Useful for questions like "which functions are cached?", "find all route handlers",
    or "show me all abstract methods".

    Args:
        decorator_name: Partial or full decorator name (e.g. 'cached_property', 'route', 'Override')
        file_filter: Optional path substring to restrict results (e.g. 'src/api/')
        limit: Maximum number of results to return
    """
    store = get_store()
    results = store.find_symbols_by_decorator(decorator_name, file_filter=file_filter, limit=limit)
    return json.dumps(
        {
            "decorator": decorator_name,
            "file_filter": file_filter,
            "count": len(results),
            "symbols": [
                {
                    "name": s.qualified_name,
                    "kind": s.kind.value,
                    "file": s.file_path,
                    "line": s.span.start.line + 1,
                    "decorators": s.decorators,
                    "signature": s.signature,
                }
                for s in results
            ],
        },
        indent=2,
    )


@mcp.tool()
def get_symbol_history(
    symbol_name: str,
    repo_path: str = ".",
    max_commits: int = 10,
) -> str:
    """Get the git commit history for a symbol — who changed it, when, and why.

    Shows commits that touched the file containing the symbol, filtered to the
    symbol's line range. Useful for understanding why code evolved and who to ask.

    Args:
        symbol_name: Name of the symbol to look up
        repo_path: Path to the git repository (default: current directory)
        max_commits: Maximum number of commits to return
    """
    import subprocess

    store = get_store()
    matches = store.find_symbols_by_name(symbol_name)
    if not matches:
        return json.dumps({"error": f"Symbol '{symbol_name}' not found"})

    sym = matches[0]
    start_line = sym.span.start.line + 1
    end_line = sym.span.end.line + 1

    try:
        result = subprocess.run(
            [
                "git",
                "log",
                f"-{max_commits}",
                "--pretty=format:%H%x1f%an%x1f%ae%x1f%ad%x1f%s",
                "--date=short",
                f"-L{start_line},{end_line}:{sym.file_path}",
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=15,
        )
        raw = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        raw = ""

    commits: list[dict[str, Any]] = []
    if raw:
        for line in raw.splitlines():
            if not line or "\x1f" not in line:
                continue
            parts = line.split("\x1f", 4)
            if len(parts) == 5:
                commits.append(
                    {
                        "hash": parts[0][:8],
                        "author": parts[1],
                        "email": parts[2],
                        "date": parts[3],
                        "message": parts[4],
                    }
                )

    return json.dumps(
        {
            "symbol": sym.qualified_name,
            "kind": sym.kind.value,
            "file": sym.file_path,
            "lines": f"{start_line}-{end_line}",
            "commit_count": len(commits),
            "commits": commits,
        },
        indent=2,
    )
