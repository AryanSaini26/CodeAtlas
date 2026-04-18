# Architecture

```
┌──────────────┐    ┌─────────────────┐    ┌──────────────────┐
│  Source      │───▶│  ParserRegistry │───▶│  ParseResult     │
│  (tree-sitter│    │  (26 languages) │    │  (Symbol, Edge)  │
│   grammars)  │    └─────────────────┘    └────────┬─────────┘
└──────────────┘                                    │
                                                    ▼
┌──────────────┐    ┌─────────────────┐    ┌──────────────────┐
│  Watcher     │───▶│  RepoIndexer    │───▶│  GraphStore      │
│  / webhook   │    │  (ProcessPool)  │    │  (SQLite+FTS5)   │
│  / pre-commit│    └─────────────────┘    └────────┬─────────┘
└──────────────┘                                    │
                                                    ▼
                           ┌────────────────────────┴────────────────────────┐
                           ▼                                                 ▼
                   ┌───────────────┐                               ┌────────────────┐
                   │  FastMCP      │                               │  Click CLI     │
                   │  server.py    │                               │  cli.py        │
                   │  (29 tools)   │                               │  (27 commands) │
                   └───────┬───────┘                               └────────┬───────┘
                           ▼                                                ▼
                   ┌───────────────┐                               ┌────────────────┐
                   │  Claude Code, │                               │  Terminal user │
                   │  Cursor, etc. │                               │                │
                   └───────────────┘                               └────────────────┘
```

## Components

### Parsers (`src/codeatlas/parsers/`)

Each parser wraps a tree-sitter grammar and emits a `ParseResult` (list of `Symbol` + list of `RelationshipEdge`). The base `LanguageParser` handles file I/O, UTF-8 byte offsets, test-file detection, and doc-comment extraction so each language parser can focus on its grammar. `ParserRegistry` dispatches by file extension.

### GraphStore (`src/codeatlas/graph/store.py`)

SQLite with WAL mode and FTS5 virtual tables over symbol names + qualified names. Stores:

- `files` — mtime, content hash, is_test flag, language
- `symbols` — one row per definition, with span, signature, docstring, confidence
- `relationships` — typed edges (CALLS, IMPORTS, INHERITS, IMPLEMENTS, ...)
- `pagerank` — cached PageRank scores
- `communities` — label-propagation cluster IDs

All long traversals use recursive CTEs to avoid roundtripping through Python.

### Indexer (`src/codeatlas/indexer.py`)

Walks the repo, respects `.codeatlas-ignore` (or `.gitignore`), and runs parsers. With `--workers N` it hands files to a `ProcessPoolExecutor`; each worker keeps its own `ParserRegistry` instance to avoid cross-process tree-sitter state sharing. Results are merged into the store in the parent process.

### MCP server (`src/codeatlas/server.py`)

FastMCP-based. Each tool is a typed function that validates inputs (canonical kind set, clamped limits, non-negative offsets) and returns JSON. Paginated tools follow the `{offset, has_more, next_offset}` contract.

### CLI (`src/codeatlas/cli.py`)

Click-based. Every CLI subcommand is a thin wrapper over a `GraphStore` method, so the CLI and MCP surfaces stay in sync. `install-completion` prints the source-able click completion script for bash/zsh/fish.

### Sync (`src/codeatlas/sync/`)

- `watcher.py` — watchdog observer that debounces rapid writes and triggers incremental re-index
- `webhook.py` — starlette app that verifies GitHub HMAC signatures and re-indexes changed files
- `pre_commit.py` — CLI-installable git hook

### Search (`src/codeatlas/search/`)

- `embeddings.py` — sentence-transformers MiniLM, cached per-model
- FAISS IndexFlatIP for cosine similarity
- `hybrid.py` — reciprocal-rank fusion over FTS5 and FAISS rankings

## Design rules of thumb

- **Parsers never touch the store.** They produce pure `ParseResult` objects; the indexer owns writes.
- **The store is the only source of truth.** CLI and MCP both read from it — no in-memory duplicates.
- **FTS5 is ranked by BM25.** Cross-ranker for semantic search is RRF (rank-based), not score-based, so heterogeneous scales compose.
- **Writes are batched.** The indexer wraps each file's merge in a transaction to keep WAL latency bounded.
