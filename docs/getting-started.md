# Getting started

## Prerequisites

- Python 3.11+
- A git-managed codebase

## Install

```bash
pip install "codeatlas[all]"
```

The `[all]` extra pulls in `mcp`, `search` (FAISS + sentence-transformers for semantic search), and `webhook` (starlette + uvicorn for the GitHub webhook endpoint). Drop extras you don't need:

```bash
pip install codeatlas            # core (parsers + store + CLI)
pip install "codeatlas[mcp]"     # + MCP server
pip install "codeatlas[search]"  # + FAISS embeddings
```

## Initialize a repo

```bash
cd your-repo
codeatlas init
```

This writes `codeatlas.toml` with default settings and creates `.codeatlas/` for the SQLite database. `codeatlas init` is idempotent — safe to re-run.

## Index the repo

```bash
codeatlas index --workers 4 .
```

`--workers 4` parallelizes file parsing with a per-process `ParserRegistry`. On repos larger than ~10k files this is typically 3–5× faster than serial.

The indexer respects `.codeatlas-ignore` if present, otherwise falls back to `.gitignore`. Re-running `codeatlas index` is incremental: only files whose mtime/hash changed are re-parsed.

## Explore the graph

```bash
codeatlas stats                                  # overall stats
codeatlas query "parse_file"                     # full-text search
codeatlas query "parse_file" --semantic          # embedding search
codeatlas query "parse_file" --hybrid            # RRF fusion
codeatlas show parse_file                        # details for one symbol
codeatlas find-path main write_to_db             # shortest path in graph
codeatlas find-usages parse_file                 # incoming edges
codeatlas audit --unused                         # dead code
codeatlas audit --cycles                         # circular imports
codeatlas rank --limit 20                        # PageRank centrality
codeatlas hotspots --limit 10                    # churn × in-degree
codeatlas coupling --limit 10                    # tightly-coupled files
codeatlas communities --min-size 3               # module clusters
codeatlas coverage-gaps --limit 20               # untested public symbols
codeatlas diff --since HEAD~10                   # symbol-level git diff
codeatlas export --format mermaid > graph.mmd    # Mermaid class diagram
codeatlas viz --out graph.html                   # interactive HTML
```

See [CLI reference](cli.md) for every subcommand.

## Wire into Claude Code / Cursor

Add to `~/.claude/claude_desktop_config.json` (Claude Code) or the equivalent MCP block in Cursor's settings:

```json
{
  "mcpServers": {
    "codeatlas": {
      "command": "codeatlas",
      "args": ["serve", "--db", "/path/to/your/repo/.codeatlas/graph.db"]
    }
  }
}
```

Restart the client. The 29 CodeAtlas tools (listed in [MCP tools](mcp-tools.md)) will appear.

## Keep the graph fresh

Pick one:

```bash
codeatlas index --watch                  # foreground watcher
codeatlas pre-commit install             # update on each commit
codeatlas webhook --port 8000            # GitHub webhook endpoint
```
