# Known limitations

Stated plainly — these are deliberate tradeoffs, not surprises.

- **Cross-file resolution is confidence-tagged.** Edges are labelled
  `extracted` (AST-proven), `inferred` (single unambiguous name match), or
  `ambiguous` (heuristic). Dynamic languages (e.g. runtime dispatch, monkey-
  patching) produce more `inferred`/`ambiguous` edges, so blast-radius and impact
  results should be read with their confidence in mind.
- **SQLite, per-repo, single-node.** Storage is intentionally simple for single-
  node deployments. Horizontal/multi-node hosted scale would need a shared DB or
  object store; that's out of scope for the MVP.
- **Cross-encoder reranking is opt-in.** It improves nothing on the current
  code-symbol golden suite (the graph/lexical baseline already saturates recall)
  and adds ~4× latency, so it's off by default. See
  [the benchmark](https://github.com/AryanSaini26/CodeAtlas/blob/main/benchmarks/rerank-report.md).
- **Semantic search needs the `search` extra.** Without sentence-transformers,
  `semantic`/`hybrid`/`rerank` modes fall back to FTS/PageRank (clearly labelled
  as `*-fallback`), and CI runs in that fallback mode.
- **The PR risk score is a transparent heuristic**, not a learned model — it's a
  documented weighted sum of changed-symbol count, blast radius, security hits,
  and missing tests.
- **Context-policy redaction is metadata-level.** Packs carry symbol metadata,
  signatures, and docstrings — not raw file bodies — so the dominant safety
  control is *excluding* denied files; secret redaction applies to those metadata
  fields.
- **Live-agent evals are optional.** They need external model access; CI runs the
  deterministic `--dry-run` path so no paid LLM or network clone is required.
