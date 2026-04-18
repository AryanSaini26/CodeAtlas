# Example: use CodeAtlas as an MCP tool from Claude Code / Cursor

CodeAtlas ships a FastMCP server with 29 tools. Once configured, agents can call `search_symbols`, `get_pagerank`, `find_path`, `get_symbol_coverage`, etc. directly inside a chat.

## 1. Index the repo once

```bash
cd /path/to/your/repo
codeatlas init
codeatlas index --workers 4
```

## 2. Register CodeAtlas with Claude Code

Add to `~/.claude/claude_desktop_config.json`:

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

For Cursor, use the equivalent MCP config block in its settings.

## 3. Restart Claude Code / Cursor

The 29 CodeAtlas tools will appear in the tool list. Try prompts like:

- *"Find every caller of `parse_file` using the CodeAtlas graph."*
- *"Rank the most central symbols in this repo by PageRank."*
- *"Which classes have no tests covering them?"* (uses `get_coverage_gaps`)
- *"Show me the shortest path from `main` to `write_to_db`."*
- *"What symbols were added or modified between `HEAD` and `main`?"*

The agent will chain several tools automatically — for example, `search_symbols` → `get_symbol_details` → `get_dependencies` to answer a single question. This is where CodeAtlas differs from filesystem-only tools: the agent queries a *graph*, not a pile of text.

## Incremental sync

Leave a background watcher running so the graph stays fresh:

```bash
codeatlas index --watch &
```

Or install the pre-commit hook:

```bash
codeatlas pre-commit install
```
