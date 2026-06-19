# CLI reference

Every CodeAtlas CLI subcommand. Run `codeatlas <cmd> --help` for option details.

## Setup

| Command | Purpose |
|---|---|
| `codeatlas init` | Write `codeatlas.toml` and create `.codeatlas/` |
| `codeatlas install-completion [bash\|zsh\|fish]` | Print shell completion script (autodetects shell) |
| `codeatlas languages` | List all 24 supported parsers |
| `codeatlas clean` | Remove `.codeatlas/` state |

## Indexing

| Command | Purpose |
|---|---|
| `codeatlas index [PATH] [--workers N] [--watch]` | Parse + ingest into graph |
| `codeatlas bench [PATH] [--workers N] [--json] [--eval-suite SUITE] [--build-semantic]` | Benchmark indexing throughput and optional eval quality |
| `codeatlas bench-suite --repos REPOS --suite SUITE --out DIR` | Run pinned multi-repo benchmark/eval suite |
| `codeatlas agent-eval --suite SUITE --repos REPOS --out DIR [--dry-run]` | Validate or run agent outcome A/B tasks |
| `codeatlas doctor [--json]` | Diagnose install: Python, SQLite/FTS5, parsers, optional deps |
| `codeatlas list-files` | Enumerate files that would be indexed |

## Querying

| Command | Purpose |
|---|---|
| `codeatlas query <text> [--kind K] [--file F] [--semantic] [--hybrid]` | Search symbols (FTS / semantic / hybrid) |
| `codeatlas context <text> [--mode MODE] [--budget N] [--json]` | Build a token-budgeted context pack |
| `codeatlas eval --suite SUITE [--compare] [--build-semantic]` | Run deterministic retrieval/context evals |
| `codeatlas show <symbol>` | Print full details for a symbol |
| `codeatlas find-path <src> <dst>` | Shortest path between two symbols |
| `codeatlas find-usages <symbol>` | Incoming edges (callers, importers) |
| `codeatlas stats [--json]` | Repository stats |

## Analysis

| Command | Purpose |
|---|---|
| `codeatlas audit [--cycles] [--unused] [--centrality]` | Dead code + cycles + centrality |
| `codeatlas rank [--kind K] [--limit N]` | PageRank centrality |
| `codeatlas communities [--min-size N]` | Label-propagation clusters |
| `codeatlas hotspots [--limit N]` | git_churn × in_degree ranking |
| `codeatlas coupling [--limit N]` | Tightly-coupled file pairs |
| `codeatlas coverage-gaps [--file-filter F]` | Public symbols with no test references |
| `codeatlas impact <symbol>` | Transitive change-impact set |
| `codeatlas diff --since <ref>` | Symbol-level git diff |

## Export

| Command | Purpose |
|---|---|
| `codeatlas export --format {dot,json,mermaid,graphml,csv,cypher} [-o FILE]` | Export the graph |
| `codeatlas viz --out FILE.html` | Interactive D3 force graph |

## MCP + sync

| Command | Purpose |
|---|---|
| `codeatlas serve` | Start the MCP server on stdio |
| `codeatlas watch` | Foreground file watcher |
| `codeatlas webhook --port 8000` | GitHub webhook endpoint |
| `codeatlas pre-commit install` | Install the git pre-commit hook |
