# Example: index Flask and explore the graph

```bash
bash examples/flask/run.sh
```

The script clones Flask (or uses a path you pass in), runs `codeatlas index --workers 4`, then demonstrates:

- `codeatlas stats` — node/edge counts per language
- `codeatlas rank` — central symbols ranked by graph PageRank (not naive degree)
- `codeatlas hotspots` — churn × in-degree risk ranking
- `codeatlas query "request" --kind variable` — FTS search over the graph
- `codeatlas audit` — unreachable (dead) code

Expected runtime on Flask (~25k LOC): ~5 seconds to index, sub-second queries.

Try swapping Flask for `django`, `requests`, or any repo you have locally:

```bash
bash examples/flask/run.sh /path/to/your/repo
```
