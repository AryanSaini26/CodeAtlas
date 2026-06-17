# CodeAtlas Benchmark

| Metric | Value |
|--------|-------|
| Repo | `.` |
| Workers | 1 |
| Files | 154 |
| Symbols | 3,371 |
| Relationships | 10,837 |
| LOC | 35,052 |
| Elapsed | 3.448s |
| Files/sec | 44.7 |
| Symbols/sec | 977.7 |
| LOC/sec | 10,166 |

## Environment

| Field | Value |
|-------|-------|
| Timestamp UTC | `2026-06-17T22:42:11.834398+00:00` |
| Python | `3.12.12` |
| Platform | `macOS-26.5.1-arm64-arm-64bit` |
| Machine | `arm64` |

## Retrieval Eval

| Mode | Effective | Symbol recall@k | File recall@k | MRR | Avg latency | Context savings | Misses |
|------|-----------|-----------------|---------------|-----|-------------|-----------------|--------|
| `fts` | `fts` | 1.000 | 0.000 | 0.978 | 38.17 ms | 26.98% | 0 |
| `pagerank` | `pagerank` | 1.000 | 0.000 | 0.978 | 30.26 ms | 27.00% | 0 |
| `semantic` | `fts-fallback` | 1.000 | 0.000 | 0.978 | 43.39 ms | 26.98% | 30 |
| `hybrid` | `pagerank-fallback` | 1.000 | 0.000 | 0.978 | 34.97 ms | 27.00% | 30 |
| `context-pack` | `context-pack` | 1.000 | 0.000 | 0.978 | 28.99 ms | 27.00% | 0 |
