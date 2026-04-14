# Contributing to CodeAtlas

Thanks for your interest in contributing! Here's how to get started.

## Setup

```bash
git clone https://github.com/AryanSaini26/CodeAtlas.git
cd CodeAtlas
python3.12 -m venv .venv
.venv/bin/pip install -e ".[all,dev]"
```

## Running Tests

```bash
.venv/bin/pytest -v
```

## Linting and Formatting

```bash
# Check for issues
.venv/bin/ruff check src tests

# Auto-format
.venv/bin/ruff format src tests
```

## Type Checking

```bash
.venv/bin/mypy src/codeatlas --ignore-missing-imports
```

## Project Structure

```
src/codeatlas/
  parsers/         # Tree-sitter AST parsers (17 languages)
  graph/           # SQLite graph store, analysis, and export (DOT/JSON/Mermaid)
  search/          # FAISS semantic search and hybrid (BM25 + vector) search
  sync/            # File watcher and GitHub webhook handler
  server.py        # MCP server (23 tools)
  cli.py           # Click CLI
  config.py        # Pydantic config models
  models.py        # Core data models (Symbol, Relationship, etc.)
  indexer.py       # Repository indexer
  git_integration.py  # Git diff and churn integration
tests/
  test_parsers/    # Per-language parser tests
  test_graph/      # Graph store, analysis, and export tests
  test_search/     # Semantic and hybrid search tests
  test_sync/       # File watcher and webhook tests
  fixtures/        # Sample source files per language
```

## Adding a New Language Parser

1. Create `src/codeatlas/parsers/<lang>_parser.py` extending `BaseParser`
2. Add the tree-sitter grammar to `pyproject.toml` dependencies
3. Register the parser in `src/codeatlas/parsers/__init__.py`
4. Add test fixtures in `tests/fixtures/sample_<lang>/`
5. Add tests in `tests/test_parsers/test_<lang>_parser.py`
6. Update `config.py` to include the new file extensions

## Pull Requests

- Keep PRs focused on a single change
- Make sure `pytest` and `ruff check` pass before submitting
- Add tests for new functionality
