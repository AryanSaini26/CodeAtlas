#!/usr/bin/env bash
# Index the Flask repo and run a handful of demo queries.
#
# Usage:
#   bash examples/flask/run.sh [flask-clone-path]
#
# If no path is given, Flask is cloned into ./flask-demo.

set -euo pipefail

REPO_DIR="${1:-./flask-demo}"

if [ ! -d "$REPO_DIR" ]; then
    echo "==> Cloning Flask into $REPO_DIR"
    git clone --depth=1 https://github.com/pallets/flask "$REPO_DIR"
fi

cd "$REPO_DIR"

echo "==> Indexing $REPO_DIR (parallel workers=4)"
codeatlas index --db .codeatlas/graph.db --workers 4 .

echo "==> Repo stats"
codeatlas stats --db .codeatlas/graph.db

echo "==> Top-10 PageRank (most-central symbols)"
codeatlas rank --db .codeatlas/graph.db --limit 10

echo "==> Hotspots (high churn x high in-degree)"
codeatlas hotspots --db .codeatlas/graph.db --limit 10

echo "==> Where is 'request' used?"
codeatlas query --db .codeatlas/graph.db "request" --kind variable --limit 10

echo "==> Dead code (non-test symbols with no incoming edges)"
codeatlas audit --db .codeatlas/graph.db --limit 10
