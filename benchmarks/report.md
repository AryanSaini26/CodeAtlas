# CodeAtlas Benchmark

| Metric | Value |
|--------|-------|
| Repo | `.` |
| Workers | 1 |
| Files | 153 |
| Symbols | 3,341 |
| Relationships | 10,601 |
| LOC | 34,318 |
| Elapsed | 1.584s |
| Files/sec | 96.6 |
| Symbols/sec | 2,109.6 |
| LOC/sec | 21,670 |

## Environment

| Field | Value |
|-------|-------|
| Timestamp UTC | `2026-06-17T22:19:04.388505+00:00` |
| Python | `3.12.12` |
| Platform | `macOS-26.5.1-arm64-arm-64bit` |
| Machine | `arm64` |

## Retrieval Eval

| Mode | Effective | Recall@k | MRR | Avg latency | Context savings |
|------|-----------|----------|-----|-------------|-----------------|
| `fts` | `fts` | 1.000 | 0.978 | 28.84 ms | 27.09% |
| `pagerank` | `pagerank` | 1.000 | 0.978 | 26.85 ms | 27.12% |
| `semantic` | `fts-fallback` | 1.000 | 0.978 | 24.74 ms | 27.09% |
| `hybrid` | `pagerank-fallback` | 1.000 | 0.978 | 25.08 ms | 27.12% |
