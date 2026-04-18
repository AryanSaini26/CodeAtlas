# Example: index a TypeScript monorepo

```bash
bash examples/ts-monorepo/run.sh
```

Demonstrates:

- Parallel indexing with `--workers 4` for large codebases
- `--semantic` flag to build FAISS embeddings alongside the SQLite graph
- PageRank (via `codeatlas rank --kind module`) to surface the most-imported packages
- Coupling report to find tightly-coupled package pairs
- Community detection to reveal package boundaries that aren't declared in `package.json`
- Hybrid search (FTS + semantic) with `codeatlas query --hybrid`

Works on any TypeScript monorepo (Nx, Turborepo, pnpm workspaces, Lerna).
