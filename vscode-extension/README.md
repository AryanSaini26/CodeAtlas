# CodeAtlas VS Code Extension

Query your CodeAtlas knowledge graph from the editor. Assumes `codeatlas server` (or `codeatlas ui`) is running and reachable at `codeatlas.apiBase` (default `http://127.0.0.1:8080`).

## Commands

- **CodeAtlas: Search Symbols** — Full-text search the graph; jump to the match.
- **CodeAtlas: Show Symbol at Cursor** — Open a side panel with signature, docstring, and call neighbors for the symbol under the cursor.
- **CodeAtlas: Open Web UI** — Open the React UI in your browser.

## Settings

- `codeatlas.apiBase` — Base URL of the API (default `http://127.0.0.1:8080`).
- `codeatlas.apiKey` — Optional `X-API-Key` for servers started with `--api-key`.

## Development

```bash
cd vscode-extension
npm install
npm run compile
# Then press F5 in VS Code to launch an Extension Development Host
```

## Packaging

```bash
npm install -g @vscode/vsce
npm run package   # produces codeatlas-vscode-<version>.vsix
```
