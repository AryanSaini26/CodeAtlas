# AI Infra Case Study

CodeAtlas is positioned as code-intelligence infrastructure for AI coding agents:
it turns a repository into a queryable graph, then exposes that graph through a
CLI, HTTP API, React UI, and MCP server.

## What makes it infrastructure-grade

- **Measurable retrieval**: `codeatlas eval` runs golden tasks and reports recall@k,
  MRR, latency, indexed graph size, and context-size savings.
- **Agent context packs**: `codeatlas context` and `/api/v1/context` return ranked,
  token-budgeted symbol bundles with dependencies, dependents, confidence labels,
  and file summaries.
- **Standards-aware output**: `codeatlas audit --format sarif` emits SARIF 2.1.0 so
  findings can flow into GitHub code scanning.
- **Protocol breadth**: the MCP server exposes tools, resources, and prompt
  templates for graph-aware review, architecture explanation, and impact analysis.
- **Production posture**: optional OpenTelemetry hooks make indexing, retrieval,
  API calls, and MCP workflows instrumentable by embedding applications.

## Example workflow

```bash
codeatlas index . --workers 4
codeatlas context "authentication flow" --budget 2000 --json
codeatlas eval --suite benchmarks/eval-suite.json --out benchmarks/eval
codeatlas audit --format sarif -o codeatlas.sarif
codeatlas bench . --workers 4 --json -o benchmarks/results.json
```

## Resume story

CodeAtlas demonstrates static analysis, graph algorithms, search/retrieval,
agent protocol design, API design, frontend integration, CI quality gates, and
reproducible benchmarking in one cohesive system.
