# CodeAtlas

[![CI](https://github.com/AryanSaini26/CodeAtlas/actions/workflows/ci.yml/badge.svg)](https://github.com/AryanSaini26/CodeAtlas/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/AryanSaini26/CodeAtlas/branch/main/graph/badge.svg)](https://codecov.io/gh/AryanSaini26/CodeAtlas)
[![PyPI](https://img.shields.io/pypi/v/codeatlas.svg)](https://pypi.org/project/codeatlas/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

An open-source MCP server that constructs real-time code knowledge graphs of any repository and exposes them to AI coding agents like Claude Code and Cursor.

## The Problem

AI coding agents waste 60-80% of their context window orienting themselves in a codebase before doing real work. CodeAtlas gives them pre-built structural and semantic knowledge so they can navigate intelligently from the first token.

## Features

- **Multi-language parsing** - Tree-sitter AST parsing for 17 languages: Python, TypeScript/TSX, Go, Rust, Java, C/C++, C#, Ruby, JavaScript, Kotlin, PHP, Scala, Bash, Lua, Elixir, Swift, and Haskell
- **Knowledge graph** - SQLite + FTS5 with recursive CTE graph traversals (zero infrastructure)
- **Semantic search** - FAISS vector search with sentence-transformers for natural language code queries
- **Hybrid search** - Reciprocal rank fusion merging keyword (FTS5) and vector (FAISS) results
- **Graph analysis** - Cycle detection, dead code finder, symbol centrality, shortest path, file coupling
- **Interactive visualization** - D3.js force-directed graph with search, zoom, and hover inspection
- **Real-time sync** - Watchdog file watcher and GitHub webhook handler for incremental updates
- **Change impact analysis** - Git-aware diff analysis showing which symbols and files are affected
- **MCP server** - 18 tools exposed via the Model Context Protocol for AI agent consumption
- **Graph export** - DOT (Graphviz) and JSON (D3.js) visualization formats
- **Config files** - Optional `codeatlas.toml` for per-repo settings

## Quick Start

```bash
pip install codeatlas

# Initialize a config file (optional)
codeatlas init

# Index a repository
codeatlas index /path/to/repo

# View graph statistics
codeatlas stats

# Search by keyword
codeatlas query "authentication"

# Search by natural language (requires sentence-transformers)
codeatlas query "where do we handle login errors" --semantic

# Inspect a specific symbol
codeatlas show UserService

# Run code quality audit (cycles, dead code, complexity)
codeatlas audit

# Visualize the graph in your browser
codeatlas viz --open

# Watch for file changes
codeatlas watch /path/to/repo

# Export the graph
codeatlas export --format dot -o graph.dot
codeatlas export --format json -o graph.json
```

## Installation

```bash
# Core (parsing + graph + CLI)
pip install codeatlas

# With MCP server
pip install codeatlas[mcp]

# With semantic search
pip install codeatlas[search]

# Everything
pip install codeatlas[all]
```

## Supported Languages

| Language | Extensions | Extractions |
|----------|-----------|-------------|
| **Python** | `.py` | Classes, functions, methods, decorators, docstrings, imports, inheritance |
| **TypeScript/TSX** | `.ts`, `.tsx` | Functions, classes, interfaces, type aliases, exports, generics, JSDoc |
| **JavaScript** | `.js`, `.mjs`, `.cjs` | Classes, functions, arrow functions, imports, exports, JSDoc |
| **Go** | `.go` | Functions, methods, structs, interfaces, packages, type aliases |
| **Rust** | `.rs` | Structs, traits, enums, impl blocks, type aliases, `///` doc comments |
| **Java** | `.java` | Classes, interfaces, enums, records, constructors, Javadoc, annotations |
| **Kotlin** | `.kt`, `.kts` | Classes, interfaces, objects, companion objects, functions, KDoc |
| **C/C++** | `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hxx`, `.h` | Classes, structs, enums, namespaces, templates, inheritance, `///`/`/** */` docs |
| **C#** | `.cs` | Classes, interfaces, structs, enums, records, properties, XML doc comments, inheritance |
| **Ruby** | `.rb` | Classes, modules, methods, constants, require imports, `#` doc comments |
| **PHP** | `.php` | Classes, interfaces, traits, functions, use imports, PHPDoc |
| **Scala** | `.scala`, `.sc` | Classes, traits, objects, functions, val/var, Scaladoc |
| **Bash** | `.sh`, `.bash` | Functions, UPPER_CASE constants, `#` doc comments, call relationships |
| **Lua** | `.lua` | Functions, local functions, function expressions, variables, `--` doc comments |
| **Elixir** | `.ex`, `.exs` | Modules, protocols (interfaces), def/defp functions, `@doc` docstrings |
| **Swift** | `.swift` | Classes, structs, protocols (interfaces), functions, methods, typealiases, `///`/`/** */` docs |
| **Haskell** | `.hs`, `.lhs` | Functions, data types, type aliases, newtypes, typeclasses (interfaces), imports, call relationships |

## Configuration

CodeAtlas can be configured with a `codeatlas.toml` file in your repository root. Generate one with:

```bash
codeatlas init
```

Example `codeatlas.toml`:

```toml
[codeatlas]
exclude_dirs = [".git", ".venv", "node_modules", "__pycache__", "dist", "build"]

[codeatlas.parser]
max_file_size_kb = 500
include_extensions = [".py", ".ts", ".tsx", ".js", ".mjs", ".go", ".rs", ".java", ".kt", ".kts", ".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".h", ".cs", ".rb", ".php", ".scala", ".sc", ".sh", ".bash", ".lua", ".ex", ".exs", ".swift", ".hs", ".lhs"]

[codeatlas.graph]
db_path = ".codeatlas/graph.db"
```

If no config file is found, sensible defaults are used.

## CLI Commands

| Command | Description |
|---------|-------------|
| `codeatlas init` | Generate a `codeatlas.toml` config file |
| `codeatlas index [path]` | Index a repository into the knowledge graph |
| `codeatlas index [path] --incremental` | Only re-index files that changed |
| `codeatlas index [path] --watch` | Index then keep watching for file changes |
| `codeatlas diff [path]` | Show files that changed since the last index |
| `codeatlas stats` | Show graph statistics (files, symbols, relationships) |
| `codeatlas list-files` | List all indexed files with language and symbol counts |
| `codeatlas query <term>` | Full-text search across the codebase |
| `codeatlas query <term> --semantic` | Natural language semantic search |
| `codeatlas query <term> --hybrid` | Combined FTS + semantic search |
| `codeatlas query <term> --json` | Output results as a JSON array |
| `codeatlas show <symbol>` | Inspect a symbol's signature, docs, deps, and call chain |
| `codeatlas show <symbol> --json` | Output symbol details as JSON |
| `codeatlas audit` | Run code quality analysis (cycles, dead code, complexity) |
| `codeatlas audit --json` | Output audit results as JSON |
| `codeatlas audit --include-tests` | Include test-file symbols in dead code analysis |
| `codeatlas find-path <src> <tgt>` | Find shortest dependency path between two symbols |
| `codeatlas coupling` | Show file coupling analysis |
| `codeatlas impact [path]` | Analyze impact of current git changes on the graph |
| `codeatlas export` | Export graph in DOT or JSON format |
| `codeatlas viz` | Generate interactive D3.js graph visualization |
| `codeatlas watch [path]` | Watch for file changes and update graph in real-time |
| `codeatlas webhook [path]` | Start a GitHub webhook server for push-triggered updates |
| `codeatlas languages` | List all supported languages and file extensions |
| `codeatlas clean` | Remove the `.codeatlas` directory |
| `codeatlas serve` | Start the MCP server |

## MCP Server

Start the MCP server for use with Claude Code, Cursor, or any MCP-compatible agent:

```bash
codeatlas serve
```

### Claude Code Configuration

Add to your Claude Code MCP settings:

```json
{
  "mcpServers": {
    "codeatlas": {
      "command": "codeatlas",
      "args": ["serve"]
    }
  }
}
```

### Available MCP Tools (20)

| Tool | Description |
|------|-------------|
| `get_file_overview` | Structural summary of a source file |
| `get_dependencies` | What a symbol depends on and what depends on it |
| `get_symbol_details` | Full metadata + relationships for a symbol in one call |
| `list_symbols_by_kind` | List all symbols of a kind (e.g. "show me all classes") |
| `trace_call_chain` | Full call graph traversal from a symbol |
| `get_impact_analysis` | What breaks if a symbol changes |
| `search_symbols` | Full-text search with optional kind/file filters and query expansion |
| `find_similar_code` | Natural language semantic search |
| `get_module_overview` | Directory/module summary |
| `get_file_dependencies` | File-level dependency graph |
| `get_graph_stats` | Summary statistics of the indexed graph |
| `export_graph` | Export graph in DOT or JSON format |
| `detect_circular_dependencies` | Find import/call cycles in the codebase |
| `find_dead_code` | Find symbols with zero incoming references |
| `analyze_complexity` | Symbol centrality (most coupled/critical code) |
| `find_path_between_symbols` | Shortest dependency path between two symbols |
| `get_file_coupling` | Cross-file relationship density analysis |
| `get_change_impact` | Git-aware change impact analysis |
| `find_by_decorator` | Find all symbols tagged with a given decorator/annotation |
| `get_symbol_history` | Git blame/log history for a symbol (commits that touched it) |

## Graph Visualization

Generate an interactive force-directed graph of your codebase:

```bash
# Generate and open in browser
codeatlas viz --open

# Save to a specific file
codeatlas viz -o my-graph.html

# Filter to specific directory
codeatlas viz --file-filter src/core/
```

The visualization features:
- Force-directed layout with D3.js
- Color-coded nodes by symbol kind (class, function, interface, etc.)
- Hover to highlight a symbol's direct connections
- Search bar to filter symbols by name
- Zoom and pan with mouse
- Drag nodes to rearrange

## GitHub Webhook

For automatic graph updates on push:

```bash
codeatlas webhook /path/to/repo --port 9000 --secret YOUR_WEBHOOK_SECRET
```

Then configure your GitHub repo webhook to POST to `http://your-server:9000/webhook`.

## Architecture

```
Source Files --> Tree-sitter AST --> Symbols + Relationships --> SQLite Graph
                                                                    |
                                                 +--------+---------+--------+
                                                 |        |         |        |
                                              FTS5     FAISS     Graph    D3.js
                                             Search   Vectors   Analysis   Viz
                                                 |        |         |        |
                                                 +--------+---------+--------+
                                                              |
                                                   CLI + MCP Server --> AI Agents
```

**Design decisions:**
- SQLite over Neo4j: zero infrastructure, ships with Python, FTS5 for keyword search, recursive CTEs for graph traversals
- FAISS over pgvector: runs locally without a database server
- Tree-sitter over regex: incremental parsing, handles all edge cases, cross-language consistency

## Development

```bash
# Clone and set up
git clone https://github.com/AryanSaini26/CodeAtlas.git
cd CodeAtlas
python3.12 -m venv .venv
.venv/bin/pip install -e ".[all,dev]"

# Run tests with coverage (643 tests, ~90%)
.venv/bin/pytest -v --cov=codeatlas --cov-report=term-missing

# Lint / format
.venv/bin/ruff check src tests
.venv/bin/ruff format src tests

# Benchmarks (clones requests + click, runs timing/memory/token-savings)
python benchmarks/bench.py
```

## Releasing

Releases are fully automated via GitHub Actions. To cut a new release:

```bash
# Bump version, tag, and push — CI will build and publish to PyPI
make release VERSION=0.2.0
```

Requires:
1. PyPI Trusted Publishing configured at pypi.org for this repo (no API tokens needed)
2. `GITHUB_TOKEN` is automatic — no extra secrets required

## License

MIT
