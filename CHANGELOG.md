# Changelog

All notable changes to CodeAtlas are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-04-18

### Added

- **Parallel parsing** — `codeatlas index --workers N` uses `ProcessPoolExecutor` with a per-process `ParserRegistry` for 3–5× speedup on large repos.
- **Shell completion installer** — `codeatlas install-completion [bash|zsh|fish]` prints a source-able completion script; auto-detects shell from `$SHELL`.
- **MCP input validation** — all tool inputs for `search_symbols`, `list_symbols_by_kind`, and `get_pagerank` are validated against a canonical kind set and clamped limits, returning structured JSON errors on bad input.
- **Pagination on list-returning MCP tools** — `list_symbols_by_kind` accepts `offset` + `limit`, returns `has_more` and `next_offset` for cursor-style iteration.
- **Symbol-level diff** — `codeatlas diff --since <ref>` surfaces added/removed/modified symbols between two git refs (not just file-level diffs).
- **PageRank centrality** — `codeatlas pagerank` + `get_pagerank` MCP tool rank symbols by true graph centrality rather than naive degree counting.
- **Community detection** — Label-propagation clustering exposes cohesive subgraphs; `--color-by community` in force-graph export.
- **GraphML, CSV, Cypher exports** — `codeatlas export --format {graphml,csv,cypher}` for Gephi/yEd/Cytoscape and Neo4j ingest.
- **Julia, PowerShell, Svelte parsers** — bringing the supported language count to 26.
- **Auto-respect `.gitignore`** — indexer falls back to `.gitignore` when `.codeatlas-ignore` is absent.
- **`get_hotspots` MCP tool + `codeatlas hotspots` CLI** — ranks files by `git_churn × graph_in_degree` to surface the highest-risk code for review.
- **`get_symbol_coverage` MCP tool** — given a symbol name, returns all test functions that reference it via `CALLS`/`IMPORTS` relationships (uses the `is_test` flag).
- **`get_api_surface` MCP tool** — returns all public non-test symbols (excludes leading-underscore names, imports, variables) grouped by file. Useful for documentation generation.
- **Mermaid `classDiagram` export** — `codeatlas export --format mermaid` and `export_graph(format="mermaid")` produce a Mermaid class diagram with classes, interfaces, enums, methods, and inheritance/implements edges.
- **Swift parser** (`tree-sitter-swift`) — classes, structs, protocols, functions, methods, typealiases, doc comments, call relationships.
- **Haskell parser** (`tree-sitter-haskell`) — data types, newtypes, typeclasses, functions with type signatures, call relationships.
- **`find_by_decorator` MCP tool** — find all symbols tagged with a given decorator/annotation, with optional file filter.
- **`get_symbol_history` MCP tool** — git blame/log for a symbol showing which commits touched it.
- **`get_symbol_details` MCP tool** — full metadata + relationships for a symbol in a single call.
- **`list_symbols_by_kind` MCP tool** — list all symbols of a given kind (e.g. all classes), with optional file filter.
- **Cross-file import resolution** — 4-pass strategy (exact qname → import-scoped same-dir → last-segment → global with same-dir preference) replaces the old global-name-only matching.
- **Test file tagging** — new `is_test` column on `symbols`/`files`; dead-code analysis excludes test symbols by default. New `--include-tests` flag on `codeatlas audit` to opt back in.
- **`--json` flags** on `query`, `show`, `audit`, and `hotspots` for machine-readable output.
- **`codeatlas index --watch`** — combined index + watch mode that indexes once then keeps watching for file changes.
- **Scoped FTS search** — `search_symbols` (and `store.search`) now accept `kind_filter` and `file_filter` parameters.
- **Query expansion fallback** — FTS now retries with camelCase/underscore expansion and prefix wildcards when initial query returns 0 hits.
- **Graceful degradation for optional deps** — CLI and MCP server now show a clear install message when `--semantic`/`--hybrid` is requested without `codeatlas[search]` installed, instead of crashing with `ImportError`.

### Changed

- MCP tool count: 18 → 29.
- Supported languages: 15 → 26 (added Swift, Haskell, SQL, Zig, OCaml, Julia, PowerShell, Svelte, and more).
- CLI subcommand count: 18 → 27.
- Export formats: 2 → 6 (added Mermaid, GraphML, CSV, Cypher).
- Development Status classifier: Beta → Production/Stable.
- Total tests: 532 → 1001+; coverage held at 92%+.

### Fixed

- 16 strict-mypy errors across `cpp_parser`, `git_integration`, `viz`, `sync/watcher`, `sync/webhook`, `search/embeddings`, `server`, `cli`, `search/__init__`. Mypy now runs in CI and is required for green.

## [0.1.0] — Initial release

### Added

- Tree-sitter parsers for 15 languages: Python, TypeScript/TSX, JavaScript, Go, Rust, Java, Kotlin, C/C++, C#, Ruby, PHP, Scala, Bash, Lua, Elixir.
- SQLite + FTS5 knowledge graph store with WAL mode and recursive CTE traversals.
- FAISS + sentence-transformers semantic search; reciprocal-rank-fusion hybrid search.
- Graph analysis: cycle detection, dead code finder, symbol centrality, shortest path, file coupling.
- Git-aware change impact analysis.
- D3.js force-directed graph visualization.
- Watchdog file watcher and GitHub webhook handler for incremental updates.
- DOT (Graphviz) and JSON (D3.js) graph export.
- 18-tool MCP server (FastMCP).
- Click CLI: `init`, `index`, `diff`, `stats`, `query`, `show`, `audit`, `find-path`, `coupling`, `impact`, `export`, `viz`, `watch`, `webhook`, `languages`, `clean`, `serve`, `list-files`.
- Optional `codeatlas.toml` configuration.
