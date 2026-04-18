# MCP tools

CodeAtlas exposes 29 tools over the Model Context Protocol. Agents call them the same way they call filesystem or web-fetch tools.

## Search + lookup

| Tool | Purpose |
|---|---|
| `search_symbols(query, kind_filter?, file_filter?, limit?)` | FTS5 search with optional kind/file scoping |
| `find_similar_code(query, limit?)` | FAISS semantic search (requires `codeatlas[search]`) |
| `get_symbol_details(symbol_name)` | Full metadata for one symbol |
| `get_symbol_context(symbol_name, context_lines?)` | Metadata + surrounding source |
| `list_symbols_by_kind(kind, file_filter?, limit?, offset?)` | Paginated by kind |
| `find_by_decorator(decorator, file_filter?)` | All symbols tagged with a decorator |
| `find_usages(symbol_name, limit?)` | All incoming edges |
| `get_file_content(path, start?, end?)` | Raw source (useful when the agent needs context the graph doesn't carry) |

## Graph traversal

| Tool | Purpose |
|---|---|
| `get_dependencies(symbol_name)` | Outgoing edges |
| `trace_call_chain(symbol_name, max_depth?)` | BFS outgoing |
| `find_path_between_symbols(source, target, max_depth?)` | Shortest path |
| `get_impact_analysis(symbol_name, max_depth?)` | Transitive reverse BFS |
| `get_file_dependencies(path)` | Per-file edge list |
| `get_file_overview(path)` | Everything a file defines + imports |
| `get_module_overview(directory)` | Roll-up for a subdirectory |

## Analysis

| Tool | Purpose |
|---|---|
| `get_pagerank(limit?, kind_filter?)` | PageRank ranking |
| `get_hotspots(repo_path?, limit?)` | churn × in-degree |
| `get_file_coupling(limit?)` | Coupled file pairs |
| `get_coverage_gaps(file_filter?, limit?, offset?)` | Paginated untested public symbols |
| `get_symbol_coverage(symbol_name)` | Test functions that reference one symbol |
| `get_api_surface(file_filter?, limit?)` | All public non-test symbols |
| `detect_circular_dependencies()` | Cycles in the import graph |
| `find_dead_code()` | Symbols with no incoming edges (excluding tests) |
| `analyze_complexity(limit?)` | Degree + cyclomatic complexity ranking |

## Change-aware

| Tool | Purpose |
|---|---|
| `get_change_impact(repo_path?, ref?, max_depth?)` | What's affected by recent changes |
| `get_symbol_history(symbol_name, ...)` | Git blame/log for a symbol |
| `get_symbol_diff(since_ref, repo_path?)` | Added/removed/modified symbols between refs |

## Meta

| Tool | Purpose |
|---|---|
| `get_graph_stats()` | Node + edge counts per kind |
| `export_graph(format?, file_filter?)` | Serialize to dot/json/mermaid/graphml/csv/cypher |

## Input validation

Tool inputs are validated against a canonical kind set and clamped limits. Bad inputs return structured JSON errors:

```json
{"error": "unknown kind: \"foo\"", "field": "kind_filter", "value": "foo"}
```

Paginated tools (`list_symbols_by_kind`, `get_coverage_gaps`) follow a consistent contract:

```json
{
  "offset": 0,
  "has_more": true,
  "next_offset": 100,
  "symbols": [...]
}
```

Iterate by passing `next_offset` back as the next `offset`.
