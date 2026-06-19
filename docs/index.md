# Stratum / CodeAtlas

> **Hosted team context for AI coding agents, powered by real-time CodeAtlas knowledge graphs.**

Stratum is the hosted gateway product; CodeAtlas is the open-source engine and compatible CLI/package. CodeAtlas parses your codebase with tree-sitter, materializes it into a persistent SQLite graph, and exposes it to agents via the Model Context Protocol. Agents stop reading files by name and start querying a real graph — call chains, PageRank centrality, test coverage gaps, dependency cycles, hotspots, and more.

## Why Stratum / CodeAtlas

- **Hosted control plane foundation** — users, teams, repo tokens, GitHub App metadata, webhook replay/sync, and a `/hosted` dashboard.
- **24 tree-sitter parsers** — Python, TypeScript/JavaScript, Go, Rust, Java, Kotlin, C/C++, C#, Ruby, PHP, Scala, Swift, Haskell, Bash, Lua, Elixir, SQL, Zig, OCaml, Julia, PowerShell, Svelte, and more.
- **30 MCP tools** — broad agent surface area including search, graph traversal, context packs, centrality, coverage, and impact.
- **39 CLI commands** — everything the MCP server does is also scriptable.
- **Persistent SQLite + FTS5 store** — scales past 1M symbols, survives restarts, incrementally updatable.
- **True PageRank centrality** — not just degree counting.
- **Embedding-based semantic search** — FAISS + MiniLM for "find similar" queries, with reciprocal-rank-fusion hybrid over FTS5.
- **Symbol-level diff** — *which functions* changed between two refs, not just which files.
- **6 export formats** — DOT, JSON, Mermaid, GraphML, CSV, Cypher.
- **Live sync** — watchdog file watcher, GitHub webhook, pre-commit hook.

## Install

```bash
pip install "codeatlas[all]"
```

Or via Homebrew (after `1.0.0` lands on PyPI):

```bash
brew install AryanSaini26/tap/codeatlas
```

Or Docker:

```bash
docker run --rm -v $PWD:/repo codeatlas:latest index /repo
```

## Quick start

```bash
cd your-repo
codeatlas init                 # write codeatlas.toml + .codeatlas/
codeatlas index --workers 4    # parallel parse + graph build
codeatlas stats                # node/edge counts
codeatlas rank --limit 10      # top-10 PageRank
codeatlas hotspots --limit 10  # high-risk churn × in-degree
codeatlas serve                # start MCP server on stdio
```

See [Getting Started](getting-started.md) for the full walkthrough.
