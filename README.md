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

## Quick Start

```bash
pip install codeatlas

# Index a repository
codeatlas index /path/to/repo

# View graph statistics
codeatlas stats

# Search by keyword
codeatlas query "authentication"

# Search by natural language (requires sentence-transformers)
codeatlas query "where do we handle login errors" --semantic

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
```

## License

MIT
