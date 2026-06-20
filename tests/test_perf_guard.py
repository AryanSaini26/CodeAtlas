"""Performance-regression guard.

Indexes a synthetic repo and asserts a conservative throughput floor, so a
catastrophic indexing regression (e.g. accidental O(n^2)) fails CI. The floor is
deliberately low (real throughput is ~1000+ symbols/sec) to avoid flakiness on
shared CI runners.
"""

from __future__ import annotations

import time
from pathlib import Path

from codeatlas.config import CodeAtlasConfig
from codeatlas.graph.store import GraphStore
from codeatlas.indexer import RepoIndexer

_MIN_SYMBOLS_PER_SEC = 50.0
_FILES = 60
_FUNCS_PER_FILE = 5


def test_indexing_throughput_floor(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    for i in range(_FILES):
        body = "\n\n".join(
            f'def func_{i}_{j}(x: int) -> int:\n    """Function {i}.{j}."""\n    return x + {j}'
            for j in range(_FUNCS_PER_FILE)
        )
        (repo / f"module_{i}.py").write_text(body + "\n")

    config = CodeAtlasConfig.find_and_load(repo)
    config.graph.db_path = tmp_path / "graph.db"
    store = GraphStore(config.graph.db_path)
    try:
        start = time.monotonic()
        RepoIndexer(config, store).index_full(resolve=True)
        elapsed = time.monotonic() - start
        symbols = store.get_stats()["symbols"]
    finally:
        store.close()

    assert symbols >= _FILES * _FUNCS_PER_FILE  # every function indexed
    rate = symbols / max(elapsed, 1e-6)
    assert rate >= _MIN_SYMBOLS_PER_SEC, f"indexing too slow: {rate:.0f} symbols/sec"
