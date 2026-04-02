# CodeAtlas

An open-source MCP server that constructs real-time code knowledge graphs of any repository and exposes them to AI coding agents like Claude Code and Cursor.

## The Problem

AI coding agents waste 60-80% of their context window orienting themselves in a codebase before doing real work. CodeAtlas gives them pre-built structural and semantic knowledge so they can navigate intelligently from the first token.

## Features

- **Multi-language parsing** - Tree-sitter AST parsing for Python, TypeScript/TSX, and Go
- **Knowledge graph** - SQLite + FTS5 with recursive CTE graph traversals (zero infrastructure)
- **Semantic search** - FAISS vector search with sentence-transformers for natural language code queries
- **Hybrid search** - Reciprocal rank fusion merging keyword (FTS5) and vector (FAISS) results
- **Real-time sync** - Watchdog file watcher and GitHub webhook handler for incremental updates
- **MCP server** - 10 tools exposed via the Model Context Protocol for AI agent consumption
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
include_extensions = [".py", ".ts", ".tsx", ".go"]

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
| `codeatlas stats` | Show graph statistics (files, symbols, relationships) |
| `codeatlas query <term>` | Full-text search across the codebase |
| `codeatlas query <term> --semantic` | Natural language semantic search |
| `codeatlas query <term> --hybrid` | Combined FTS + semantic search |
| `codeatlas show <symbol>` | Inspect a symbol's signature, docs, deps, and call chain |
| `codeatlas export` | Export graph in DOT or JSON format |
| `codeatlas watch [path]` | Watch for file changes and update graph in real-time |
| `codeatlas webhook [path]` | Start a GitHub webhook server for push-triggered updates |
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

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `get_file_overview` | Structural summary of a source file |
| `get_dependencies` | What a symbol depends on and what depends on it |
| `trace_call_chain` | Full call graph traversal from a symbol |
| `get_impact_analysis` | What breaks if a symbol changes |
| `search_symbols` | Full-text search across the codebase |
| `find_similar_code` | Natural language semantic search |
| `get_module_overview` | Directory/module summary |
| `get_file_dependencies` | File-level dependency graph |
| `get_graph_stats` | Summary statistics of the indexed graph |
| `export_graph` | Export graph in DOT or JSON format |

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
                                                              +-----+-----+
                                                              |           |
                                                          FTS5 Search  FAISS Vectors
                                                              |           |
                                                              +-----+-----+
                                                                    |
                                                              Hybrid Search
                                                                    |
                                                              MCP Server --> AI Agents
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

# Run tests
.venv/bin/pytest -v

# Lint
.venv/bin/ruff check src tests

# Format
.venv/bin/ruff format src tests
```

## License

MIT
