# Two-stage retrieval: cross-encoder reranking benchmark

Measured with
`codeatlas eval --compare --with-rerank --build-semantic --require-semantic`
against the 30-task golden suite (`benchmarks/eval-suite.json`) on the CodeAtlas
repo graph (488 files). Reranking is **stage 2** on top of hybrid recall: a
`cross-encoder/ms-marco-MiniLM-L-6-v2` re-scores the top candidates by joint
(query, symbol) relevance.

## Results (7 retrieval modes)

| Mode | Symbol recall@k | Precision@k | nDCG@k | MRR | Avg latency | Context savings |
|------|----------------:|------------:|-------:|----:|------------:|----------------:|
| fts | 1.000 | 0.702 | 0.988 | 0.983 | 401 ms | 32.2% |
| bm25 | 1.000 | 0.702 | 0.988 | 0.983 | 425 ms | 32.2% |
| pagerank | **1.000** | 0.709 | **1.000** | **1.000** | 462 ms | 31.9% |
| semantic | 0.967 | 0.592 | 0.967 | 0.967 | 470 ms | 51.1% |
| hybrid | 1.000 | 0.591 | 0.988 | 0.983 | 426 ms | 68.5% |
| **rerank** | 0.967 | 0.403 | 0.942 | 0.933 | 1918 ms | **88.5%** |
| graph-neighborhood | 1.000 | 0.709 | 1.000 | 1.000 | 473 ms | 31.9% |

## Findings (honest)

- **Reranking did not improve recall/MRR on this suite.** These are short,
  code-symbol queries where lexical + graph signals already *saturate* recall@k
  (pagerank: recall 1.000, MRR 1.000). A general-purpose MS-MARCO cross-encoder
  — trained on web passages, not code — slightly *hurt* ranking and added ~4×
  latency (1918 ms vs ~450 ms).
- **It did win on context density:** rerank produced the tightest packs (88.5%
  token savings), useful when an agent's budget is the binding constraint.
- **Decision:** ship reranking as an **opt-in** mode (`--mode rerank`), not the
  default. The eval harness turned this into a data-driven call rather than a
  guess — which is the point: we can *measure* retrieval changes.

## Next

- Try a **code-tuned** cross-encoder (e.g. CoRNStack-style contrastive data)
  instead of the web-passage model.
- Re-run on the harder OSS suite (`benchmarks/oss-eval-suite.json`), where
  baseline recall is lower (~0.78 file recall) and there is more room for a
  reranker to help.
