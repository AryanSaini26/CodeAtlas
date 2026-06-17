# Resume Bullets

Use these as raw material, then tailor numbers to the latest
`benchmarks/report.md` before sending applications.

## Software Engineer

- Built CodeAtlas, a local-first code-intelligence platform that parses 24
  languages into a SQLite/FTS5 graph with CLI, FastAPI, MCP, React UI, CI, and
  packaging.
- Implemented graph algorithms for PageRank, cycle detection, shortest paths,
  hotspots, dead-code detection, coverage gaps, and change-impact analysis.
- Added reproducible benchmark and eval tooling that reports indexing
  throughput, recall@k, MRR, latency, context savings, and runtime metadata.

## AI / ML Infrastructure

- Built agent-ready context packs that rank symbols with FTS, PageRank, optional
  semantic search, and hybrid reciprocal-rank fusion under a token budget.
- Exposed graph context through MCP tools, resources, and prompt templates for
  architecture explanation, code review, and impact-analysis workflows.
- Designed eval mode comparison for retrieval quality without requiring paid LLM
  APIs, enabling deterministic CI smoke tests and manual real-repo benchmarks.

## Data Engineering / Data Infrastructure

- Extended the same graph model used for source-code impact analysis to SQL
  lineage tasks, showing how table/model dependencies can share traversal,
  retrieval, and audit infrastructure.
- Added SARIF export for audit findings so static-analysis results can flow into
  GitHub code scanning and production-style developer workflows.
- Built local benchmark artifacts and repo pinning metadata for reproducible
  measurements across code and data-lineage workloads.

