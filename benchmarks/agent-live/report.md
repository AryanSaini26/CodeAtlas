# CodeAtlas Agent Outcome Eval

## Summary

| Metric | Value |
|--------|-------|
| Mode | live |
| Tasks | 1 |
| Context mode | `pagerank` |
| Agent adapter | `mock` |
| Safety label | `mock_agent` |
| Live variants | 2 |
| Solve rate | 100.00% |
| Verification pass rate | 50.00% |
| Baseline vs context delta | 100.00% |
| Avg runtime | 0.089s |
| Avg context tokens | 212.0 |
| Avg context savings | 0.00% |
| Retrieval symbol recall | 1.000 |
| Retrieval file recall | 1.000 |

## Tasks

| Task | Repo | Type | Difficulty | Expected symbols | Expected files | Variants |
|------|------|------|------------|------------------|----------------|----------|
| `local-greet-context` | `agent-fixture` | `bug_fix` | `smoke` | `greet` | `main.py` | `baseline:completed`, `codeatlas_context:completed` |

## Failure Analysis

| Task | Variant | Reason |
|------|---------|--------|
| `local-greet-context` | `baseline` | verify command exited 1 |
