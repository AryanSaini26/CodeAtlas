# CodeAtlas web UI

React + Vite + Tailwind front-end for the CodeAtlas HTTP API.

## Develop

```bash
# terminal 1: run the backend
cd ..
codeatlas server --port 8080

# terminal 2: run the dev server
cd frontend
npm install
npm run dev
```

Vite proxies `/api/v1/*` to `localhost:8080`, so no CORS configuration is needed during development. Open `http://localhost:5173`.

## Build

```bash
npm run build
```

Outputs static assets to `frontend/dist/`. `codeatlas ui` (planned) will serve `dist/` directly from the Python API so a single `pip install` ships both sides.

## Configuration

Set the following environment variables before `vite dev` or `vite build` to target a non-default backend:

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_BASE` | `/api/v1` | Base URL of the CodeAtlas HTTP API |
| `VITE_API_KEY` | *(unset)* | Value sent as `X-API-Key` header if the server requires one |

## Pages

- `/` — overview dashboard (stats, top-10 PageRank, hotspots)
- `/graph` — force-directed graph with community coloring + file filter
- `/search` — FTS5 symbol search with pagination
- `/analysis` — tabbed view: PageRank, hotspots, coverage gaps
- `/symbol/:id` — symbol details with incoming/outgoing refs
