# Launch draft — CodeAtlas 1.0

> This file is an internal draft. Copy sections into HN / Reddit / X / the blog when it's time to ship. The GIFs live under `docs/assets/` and need to be recorded before posting.

---

## One-liner

CodeAtlas 1.0 — tree-sitter → SQLite + FAISS graph + 29 MCP tools + web UI. `pip install codeatlas`.

## Pitch (≤280 chars)

Open-sourced **CodeAtlas 1.0** — a persistent code knowledge graph for AI agents. Tree-sitter for 26 languages, PageRank + FAISS embeddings in SQLite, 29 MCP tools, 27 CLI commands, React web UI. One install. MIT licensed.

## HN title

Show HN: CodeAtlas – Persistent code knowledge graph for AI agents (26 langs, MCP)

## HN body

Hi HN — I've been building CodeAtlas for a few months and tagged 1.0 this week.

The premise is simple: most AI coding agents waste 60–80% of their context window orienting themselves in a codebase before doing real work. CodeAtlas parses the repo once with tree-sitter, stores symbols and relationships in a persistent SQLite + FTS5 graph, and exposes 29 MCP tools plus a CLI and web UI over it. Agents jump straight to the right symbol; humans get a force graph, PageRank ranking, and a diff view over two git refs.

A few things I'm proud of:

- **True semantic search.** FAISS + sentence-transformers embeddings, hybrid ranking with FTS5 via reciprocal rank fusion. Not "grep with bigger letters."
- **PageRank centrality**, not degree-based "god nodes." Callers weighted by the importance of *their* callers.
- **Persistent storage.** 1M+ symbols in SQLite, incremental reindex via content hashes, watchdog + GitHub webhook for live updates.
- **Visibility.** React + Vite + Tailwind web UI backed by a FastAPI layer — same data the MCP tools see. `codeatlas ui` launches both on one port.

26 languages: Python, TypeScript/TSX, Go, Rust, Java, C, C++, C#, Ruby, JavaScript, Kotlin, PHP, Scala, Bash, Lua, Elixir, Swift, Haskell, SQL, Zig, OCaml, Julia, PowerShell, Svelte.

Install: `pip install codeatlas` → `codeatlas index .` → `codeatlas ui`.

GitHub: https://github.com/AryanSaini26/CodeAtlas
Docs: https://aryansaini26.github.io/CodeAtlas/
MIT licensed. Would love feedback, especially on the MCP tool surface and what's missing for real agent workflows.

---

## X / Twitter thread

**1/** Shipped **CodeAtlas 1.0** — an open-source code knowledge graph for AI agents. `pip install codeatlas`.

26 languages. 29 MCP tools. FAISS semantic search. PageRank centrality. React web UI. MIT licensed.

**2/** Why it exists: AI coding agents burn most of their context just orienting. CodeAtlas indexes once → agents jump straight to the right symbol. No repeated greps, no hallucinated call chains.

**3/** What's in the box:
- Tree-sitter parsers (26 langs)
- SQLite + FTS5 graph (1M+ symbols)
- FAISS embeddings, hybrid search
- PageRank, communities, hotspots, dead code, coverage gaps
- 27 CLI commands, 29 MCP tools, 6 export formats
- React UI backed by FastAPI

**4/** Drop this in your Claude Code config:

```json
{ "mcpServers": { "codeatlas": { "command": "codeatlas", "args": ["serve"] } } }
```

and your agent gets instant structural + semantic access to the whole repo.

**5/** GitHub: https://github.com/AryanSaini26/CodeAtlas
GIF: [web UI walkthrough]
Docs: [mkdocs link]

Would love feedback. What MCP tools are missing for your workflow?

---

## Reddit (r/LocalLLaMA, r/ClaudeAI, r/programming)

Title: **CodeAtlas 1.0 — an open-source persistent code graph + MCP server for AI agents (26 languages, FAISS, PageRank)**

Body: *(reuse HN body, adjust opener to the subreddit tone)*

---

## Blog post outline

1. **The problem.** How much of an agent's context is wasted on orientation? Concrete numbers from a small experiment.
2. **Prior art.** Tree-sitter ecosystem, LangGraph/LlamaIndex for RAG, Sourcegraph. Where CodeAtlas sits (local-first, graph-first, MCP-native).
3. **Design choices.** Why SQLite over Neo4j. Why FAISS over Chroma. Why PageRank over degree.
4. **MCP surface.** Walk through `get_symbol_details`, `find_similar_code`, `get_change_impact`.
5. **Web UI screenshots.**
6. **What's next.** Multi-repo, more languages, better ranking for hybrid search.

---

## Checklist before posting

- [ ] `docs/assets/hero.gif` recorded (indexing + agent chaining MCP tools + web UI).
- [ ] `docs/assets/web-ui.gif` recorded (graph → search → symbol detail → diff).
- [ ] Screenshots PNGed under `docs/assets/ui-overview.png`, `ui-graph.png`, `ui-diff.png`.
- [ ] PyPI `codeatlas==1.0.0` live.
- [ ] `brew install AryanSaini26/tap/codeatlas` works.
- [ ] VS Code marketplace listing live.
- [ ] GH Pages docs site live at `https://aryansaini26.github.io/CodeAtlas/`.
- [ ] Post to HN, Reddit, X in that order — HN traffic usually seeds the rest.
