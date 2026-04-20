# CodeAtlas — code knowledge graphs for AI agents

> Tree-sitter parsers, a persistent SQLite + FTS5 graph, FAISS semantic search, PageRank centrality, and a 29-tool MCP surface. Installs in one `pip install`. Ships with a React web UI.

<!-- hero screencast -->
![hero](../assets/hero.gif)

## Why it exists

AI coding agents waste most of their context window orienting themselves in a codebase. CodeAtlas gives them a pre-built structural and semantic index so they can navigate intelligently from the first token — no repeated greps, no hallucinated call chains.

## What makes it different

| | CodeAtlas | Typical alternatives |
|---|---|---|
| Storage | Persistent SQLite + FTS5 (1M+ symbols) | Flat `graph.json` re-serialized every run |
| Semantic search | FAISS + MiniLM embeddings | Keyword grep only |
| Centrality | PageRank (caller-weighted) | Degree-based "god nodes" |
| MCP surface | 29 tools | 3–5 tools |
| CLI surface | 27 subcommands | <10 |
| Interactive UI | React SPA + FastAPI | Static HTML export |
| Incremental sync | watchdog + webhook + pre-commit | Full reindex each run |

## 30-second tour

```bash
pip install codeatlas
codeatlas index /path/to/repo
codeatlas ui                       # API + web UI on :8080
```

Point Claude Code at `codeatlas serve` to hand agents 29 MCP tools over the same graph:

```json
{
  "mcpServers": {
    "codeatlas": { "command": "codeatlas", "args": ["serve"] }
  }
}
```

## Screens

<!-- screenshot placeholders — replace with real PNGs post-launch -->
| Overview | Graph | Diff |
|:---:|:---:|:---:|
| ![overview](../assets/ui-overview.png) | ![graph](../assets/ui-graph.png) | ![diff](../assets/ui-diff.png) |

## What's in the box

- **26 languages** via tree-sitter — Python, TypeScript/TSX, Go, Rust, Java, C, C++, C#, Ruby, JavaScript, Kotlin, PHP, Scala, Bash, Lua, Elixir, Swift, Haskell, SQL, Zig, OCaml, Julia, PowerShell, Svelte.
- **Graph analysis** — PageRank, label-propagation communities, cycle detection, dead code, hotspots, coverage gaps, shortest path, file coupling.
- **Exports** — DOT, JSON, Mermaid, GraphML, CSV, Cypher.
- **Sync** — file watcher, GitHub webhook, `pre-commit install` hook.
- **Visibility** — CLI, HTTP/JSON API, React web UI, VS Code extension.

## Links

- GitHub: <https://github.com/AryanSaini26/CodeAtlas>
- PyPI: <https://pypi.org/project/codeatlas/>
- Docs: <https://aryansaini26.github.io/CodeAtlas/>
- VS Code extension: *(pending marketplace publish)*
