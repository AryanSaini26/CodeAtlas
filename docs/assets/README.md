# docs/assets

Screencast GIFs and screenshots referenced from `README.md` and `docs/landing/index.md`. None of these are committed yet — the user records them before launch.

## Expected files

| Path | What | Suggested length |
|---|---|---|
| `hero.gif` | `codeatlas index` on a 100k-LOC repo, then an agent chaining MCP tools, then the web UI graph | ~30s |
| `web-ui.gif` | Walkthrough of `/graph` → `/search` → `/symbol/:id` → `/diff` | ~20s |
| `ui-overview.png` | Static screenshot of the `/` overview dashboard | — |
| `ui-graph.png` | Static screenshot of the force graph with a community-coloring toggle | — |
| `ui-diff.png` | Static screenshot of the `/diff` page with real added/removed/modified symbols | — |

## Recording notes

- Use a dark terminal theme (matches the web UI).
- Keep window width ≤1200px so the README renders cleanly on mobile.
- Convert with `ffmpeg -i raw.mov -filter_complex 'fps=15,scale=720:-1' -loop 0 hero.gif`.
- Target ≤4 MB per GIF to stay under GitHub's inline-render limit.
