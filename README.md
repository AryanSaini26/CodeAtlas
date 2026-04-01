# CodeAtlas

An open-source MCP server that constructs real-time code knowledge graphs for AI coding agents.

## Overview

CodeAtlas uses Tree-sitter AST parsing to build a structured knowledge graph of any repository,
exposing it to AI coding agents like Claude Code and Cursor via the MCP protocol.

## Features

- Tree-sitter AST parsing for Python, TypeScript, and Go
- SQLite + FTS5 knowledge graph (zero infrastructure)
- FAISS semantic search (coming Month 3)
- GitHub webhook real-time sync (coming Month 4)
- MCP server with graph traversal tools (coming Month 4)

## Quick Start

```bash
pip install codeatlas
codeatlas index /path/to/repo
codeatlas stats
codeatlas query "authentication"
```
