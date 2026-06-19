# CodeAtlas Flagship Proof Report

This report ties together the recruiter-facing proof assets for CodeAtlas:
agent outcome evaluation, retrieval quality, scale/performance, and data-lineage
generalization. All numbers below are generated from committed local fixtures or
the local CodeAtlas repository so they are reproducible without paid APIs.

## Summary

| Proof area | Artifact | Highlight |
|------------|----------|-----------|
| Agent outcome | `benchmarks/agent-live/report.md` | Mock live A/B run: CodeAtlas-context variant solved 100%, baseline solved 0%, clearly labeled `mock_agent`. |
| Retrieval quality | `benchmarks/retrieval-v2/report.md` | 30 deterministic tasks, context-pack best mode, 1.000 recall@k and 1.000 MRR on the local suite. |
| Scale systems | `benchmarks/perf/report.md` | 3 local repos, 481 files, 11,077 symbols, 33,036 relationships, 4,856.2 symbols/sec. |
| Data engineering | `benchmarks/data-lineage/report.md` | dbt + Airflow + SQL fixture: 14 nodes and 11 lineage edges, with OpenLineage JSON export. |

## Honest Labels

- Semantic and hybrid rows in local retrieval reports are fallback rows unless generated with `--build-semantic --require-semantic`.
- `benchmarks/agent-live` uses the deterministic mock adapter, not a paid LLM or external coding agent.
- Large OSS and live-agent benchmarks are intentionally manual so CI stays deterministic.

## Reproduce

```bash
codeatlas eval --suite benchmarks/eval-suite.json --db .codeatlas/graph.db --out benchmarks/retrieval-v2 --compare
codeatlas perf-report --repos benchmarks/local-repos.json --out benchmarks/perf --profile
codeatlas agent-eval --suite benchmarks/local-agent-suite.json --repos benchmarks/local-repos.json --out benchmarks/agent-live --agent-adapter mock --compare-baseline
codeatlas data-lineage --repo examples/data-pipeline --format text -o benchmarks/data-lineage/report.md
```
