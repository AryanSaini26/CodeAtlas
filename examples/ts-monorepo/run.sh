#!/usr/bin/env bash
# Index a TypeScript monorepo and explore cross-package imports.
#
# Usage:
#   bash examples/ts-monorepo/run.sh [repo-path]
#
# Defaults to cloning the Nx reference monorepo into ./nx-demo.

set -euo pipefail

REPO_DIR="${1:-./nx-demo}"

if [ ! -d "$REPO_DIR" ]; then
    echo "==> Cloning Nx reference monorepo into $REPO_DIR"
    git clone --depth=1 https://github.com/nrwl/nx "$REPO_DIR"
fi

cd "$REPO_DIR"

echo "==> Indexing (workers=4, semantic search enabled)"
codeatlas index --db .codeatlas/graph.db --workers 4 --semantic .

echo "==> Stats by language"
codeatlas stats --db .codeatlas/graph.db --json | jq '.by_language'

echo "==> Top-10 most imported modules"
codeatlas rank --db .codeatlas/graph.db --kind module --limit 10

echo "==> Cross-package coupling (top-10 pairs)"
codeatlas coupling --db .codeatlas/graph.db --limit 10

echo "==> Communities (package-like clusters)"
codeatlas export --db .codeatlas/graph.db --format json --communities -o communities.json
echo "Communities written to communities.json — open in any D3 viewer."

echo "==> Hybrid search: 'debounce event handler'"
codeatlas query --db .codeatlas/graph.db "debounce event handler" --hybrid --limit 5
