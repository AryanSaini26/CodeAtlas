# CodeAtlas OSS Benchmark Suite

## Aggregate

| Metric | Value |
|--------|-------|
| Repos | 3 |
| Files | 314 |
| Symbols | 7,581 |
| Relationships | 21,443 |
| LOC | 90,546 |
| Total indexing time | 1.093s |

## Aggregate Retrieval Eval

| Mode | Symbol recall@k | File recall@k | MRR | Avg latency | Context savings | Misses |
|------|-----------------|---------------|-----|-------------|-----------------|--------|
| `fts` | 0.476 | 0.778 | 0.578 | 17.99 ms | 59.78% | 25 |
| `pagerank` | 0.476 | 0.778 | 0.578 | 17.45 ms | 59.78% | 25 |
| `semantic` | 0.476 | 0.778 | 0.578 | 16.80 ms | 59.78% | 45 |
| `hybrid` | 0.476 | 0.778 | 0.578 | 20.99 ms | 59.78% | 45 |
| `context-pack` | 0.476 | 0.778 | 0.578 | 17.01 ms | 59.78% | 25 |

## Repositories

| Repo | Commit | Files | Symbols | Relationships | Symbols/sec |
|------|--------|-------|---------|---------------|-------------|
| `requests` | `d64b9ad4bf1c` | 37 | 1,378 | 3,373 | 9,086.2 |
| `click` | `8a1b1a33d739` | 64 | 2,366 | 7,934 | 6,558.5 |
| `rich` | `46cebbb032f9` | 213 | 3,837 | 10,136 | 6,611.8 |

