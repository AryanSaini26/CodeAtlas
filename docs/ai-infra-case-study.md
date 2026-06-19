# AI Infra Case Study

CodeAtlas is code-intelligence infrastructure for AI coding agents. It turns a
repository into a persistent graph, then serves that graph through a CLI, HTTP
API, React UI, and MCP server so agents can retrieve the right context before
editing code.

The project is designed to answer one hiring-relevant question:

> Can a local system measurably improve code-agent context retrieval without a
> paid LLM dependency?

## System Shape

The architecture has five layers:

1. **Parsing**: tree-sitter parsers extract symbols, spans, docstrings,
   signatures, imports, calls, and test markers across 24 languages.
2. **Storage**: SQLite stores files, symbols, relationships, FTS rows, and graph
   metadata in a local database that can be copied, inspected, and benchmarked.
3. **Retrieval**: FTS, optional FAISS semantic search, reciprocal-rank hybrid
   search, and PageRank-boosted graph ranking produce candidate symbols.
4. **Agent context**: `codeatlas context` trims ranked results into
   token-budgeted packs containing definitions, callers, callees, file summaries,
   relationship confidence labels, and context-savings estimates.
5. **Surfaces**: the same graph backs CLI commands, FastAPI endpoints, MCP tools,
   MCP resources, MCP prompts, SARIF export, and a React visualization.

## Measured Proof

The flagship artifact is `benchmarks/report.md`, generated from:

```bash
codeatlas bench . --profile --eval-suite benchmarks/eval-suite.json --output benchmarks/report.md
codeatlas bench . --profile --eval-suite benchmarks/eval-suite.json --json --output benchmarks/results.json
```

The real-repo proof path is:

```bash
codeatlas bench-suite \
  --repos benchmarks/repos.lock.yml \
  --suite benchmarks/oss-eval-suite.json \
  --out benchmarks/oss \
  --build-semantic \
  --require-semantic
```

The benchmark captures:

- Indexing throughput: files/sec, symbols/sec, LOC/sec.
- Graph scale: files, symbols, relationships, LOC.
- Runtime metadata: Python version, platform, machine, timestamp.
- Retrieval quality: symbol recall@k, file recall@k, MRR, latency, misses,
  and context savings.
- Mode comparison: FTS, PageRank-boosted ranking, semantic, hybrid, and
  context-pack.
- Real-repo reproducibility: exact commits for `requests`, `click`, and `rich`
  are locked in `benchmarks/repos.lock.yml`.

The committed OSS baseline currently covers 314 files, 7,581 symbols, and
21,443 relationships across the three pinned repos. It reports 0.778 file
recall@k, 0.476 multi-symbol recall@k, 0.578 MRR, and about 60% context savings.
Semantic/hybrid rows are explicitly fallback rows in that committed artifact;
use `--build-semantic --require-semantic` before publishing vector-search claims.

The committed suite intentionally runs against the local repository so CI can
reproduce it without network access. `benchmarks/oss-eval-suite.json` is the
manual or scheduled proof suite for pinned OSS repos where cloning commits is
acceptable.

## Agent Outcome Evaluation

Retrieval metrics prove that CodeAtlas can find relevant symbols and files. The
next layer is outcome proof: can an agent complete the task more reliably when
it receives a CodeAtlas context pack?

`codeatlas agent-eval` adds that A/B harness without making CI depend on a paid
LLM or a specific agent vendor:

```bash
codeatlas agent-eval \
  --suite benchmarks/agent-suite.json \
  --repos benchmarks/repos.lock.yml \
  --out benchmarks/agent \
  --dry-run

codeatlas agent-eval \
  --suite benchmarks/agent-suite.json \
  --repos benchmarks/repos.lock.yml \
  --out benchmarks/agent-live \
  --agent-command "<your-agent-command>" \
  --compare-baseline
```

The dry-run path validates the suite and writes deterministic artifacts. The
live path creates isolated prompt-only and CodeAtlas-context repository copies,
runs a generic command adapter with `CODEATLAS_*` environment variables, then
executes task-specific verification commands. Reports include solve rate,
verification pass rate, runtime, context tokens, retrieval recall, and the
baseline-vs-context delta. CodeAtlas only claims agent improvement when both
variants actually ran.

## Retrieval Modes

`codeatlas context` supports:

- `fts`: lexical FTS over symbol names, qualified names, signatures, and docs.
- `pagerank`: FTS candidates re-ranked with graph centrality.
- `semantic`: FAISS-backed vector search when an index is present, with a
  deterministic FTS fallback in local CI.
- `hybrid`: reciprocal-rank fusion between FTS and semantic candidates, with a
  deterministic PageRank fallback when semantic dependencies are absent.

This gives recruiters and reviewers a concrete comparison story: the project
does not simply claim "graph search"; it measures graph-aware retrieval against
naive keyword search.

## Tradeoffs

SQLite was chosen over Neo4j because the product goal is local-first developer
infrastructure. SQLite keeps install friction low, supports FTS5, works in CI,
and lets the API/MCP server share the same store with the CLI.

Tree-sitter was chosen over regex parsing because CodeAtlas needs stable symbol
spans, nested definitions, decorators, imports, and cross-language consistency.
The cost is parser maintenance across languages, but the benefit is credible
navigation data.

Optional FAISS search was kept optional because benchmark correctness should not
depend on model downloads or external APIs. Semantic and hybrid modes are still
public interfaces, but the deterministic fallback keeps tests and CI reliable.
Publishing-quality benchmark runs should use `--require-semantic`, which fails
instead of reporting semantic/hybrid fallback numbers.

## Bottlenecks

The main bottlenecks are:

- Parsing large repos with many files, especially when relationship resolution is
  enabled.
- Recomputing PageRank on dense graphs during repeated context-pack generation.
- Optional embedding model startup time when semantic search is built from
  scratch.
- Rendering very large force graphs in the browser without filtering.

The current benchmark isolates indexing throughput from relationship resolution
by running `index_full(resolve=False)` in the bench command. That makes parser
throughput easier to compare across changes. Full correctness tests still cover
relationship behavior.

## Failure Modes

Known failure modes are tracked explicitly:

- **Ambiguous symbol names**: mitigated with qualified names, file paths, and
  graph-neighborhood context in context packs.
- **Missing semantic index**: semantic/hybrid modes report an effective fallback
  mode instead of silently pretending vector search ran.
- **Over-large context packs**: budget trimming keeps the first relevant result
  and skips later entries that would overflow the budget.
- **Presentation drift**: README counts, benchmark artifacts, and CI smoke tests
  are updated together so public claims stay reproducible.

## Data Lineage Angle

CodeAtlas includes a SQL parser, which means the same graph model can represent
code impact and data-pipeline lineage. The eval suite includes SQL lineage tasks
against `SQLParser`, framing dbt/Airflow-style dependency analysis as an
extension of the same core engine rather than a separate demo.

This matters for data engineering and ML infrastructure roles: the project can
explain how a code-intelligence graph generalizes to tables, models, DAG tasks,
and downstream consumers.

## What Changed After Profiling

The benchmark/eval path pushed the project toward proof over breadth:

- `codeatlas eval --compare` now reports retrieval quality by mode.
- `codeatlas bench --profile --eval-suite` emits one publishable Markdown/JSON
  artifact.
- `codeatlas agent-eval` separates deterministic dry-run validation from
  optional live-agent A/B outcome measurement.
- Context packs expose both requested and effective mode, making optional
  semantic dependencies auditable.
- README now points to one reproduction command instead of unsupported claims.

## Recruiter Narrative

CodeAtlas demonstrates:

- Systems engineering: parsers, persistence, APIs, CI, packaging, and local-first
  deployment.
- AI infrastructure: MCP, agent context packs, retrieval evals, and prompt
  templates.
- Search and graphs: FTS, semantic search, hybrid search, PageRank, impact
  analysis, and graph traversal.
- Production instincts: SARIF export, OpenTelemetry hooks, reproducible
  benchmarks, deterministic tests, and no mandatory paid services.
