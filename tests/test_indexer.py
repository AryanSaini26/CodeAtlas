"""Tests for the repository indexer."""

from pathlib import Path
from unittest.mock import patch

import pytest

from codeatlas.config import CodeAtlasConfig, GraphConfig, ParserConfig
from codeatlas.graph.store import GraphStore
from codeatlas.indexer import RepoIndexer


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """Create a small multi-file repo structure for indexing."""
    (tmp_path / "app.py").write_text(
        'import os\n\ndef main():\n    """Entry point."""\n    greet("world")\n\n'
        'def greet(name: str) -> str:\n    return f"Hello, {name}"\n'
    )
    (tmp_path / "utils.py").write_text(
        "MAX_SIZE = 100\n\ndef clamp(val: int, lo: int, hi: int) -> int:\n"
        '    """Clamp a value."""\n    return max(lo, min(val, hi))\n'
    )
    sub = tmp_path / "pkg"
    sub.mkdir()
    (sub / "helpers.py").write_text(
        "from pathlib import Path\n\ndef load(p: str) -> str:\n    return Path(p).read_text()\n"
    )
    return tmp_path


@pytest.fixture
def indexer_and_store(sample_repo: Path) -> tuple[RepoIndexer, GraphStore]:
    store = GraphStore(":memory:")
    config = CodeAtlasConfig(
        repo_root=sample_repo,
        graph=GraphConfig(db_path=Path(":memory:")),
    )
    return RepoIndexer(config, store), store


# --- File discovery ---


def test_discover_finds_python_files(sample_repo: Path) -> None:
    store = GraphStore(":memory:")
    config = CodeAtlasConfig(repo_root=sample_repo)
    indexer = RepoIndexer(config, store)
    files = indexer._discover_files()
    names = {f.name for f in files}
    assert "app.py" in names
    assert "utils.py" in names
    assert "helpers.py" in names


def test_discover_skips_excluded_dirs(sample_repo: Path) -> None:
    # Create a file inside an excluded directory
    venv = sample_repo / ".venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "site.py").write_text("x = 1\n")

    store = GraphStore(":memory:")
    config = CodeAtlasConfig(repo_root=sample_repo)
    indexer = RepoIndexer(config, store)
    files = indexer._discover_files()
    names = {f.name for f in files}
    assert "site.py" not in names


def test_discover_skips_unsupported_extensions(sample_repo: Path) -> None:
    (sample_repo / "notes.txt").write_text("just a note")
    (sample_repo / "data.json").write_text("{}")

    store = GraphStore(":memory:")
    config = CodeAtlasConfig(repo_root=sample_repo)
    indexer = RepoIndexer(config, store)
    files = indexer._discover_files()
    names = {f.name for f in files}
    assert "notes.txt" not in names
    assert "data.json" not in names


def test_discover_skips_large_files(sample_repo: Path) -> None:
    big = sample_repo / "huge.py"
    # Write a file bigger than 1 KB with a low max_file_size_kb config
    big.write_text("x = 1\n" * 500)

    store = GraphStore(":memory:")
    config = CodeAtlasConfig(
        repo_root=sample_repo,
        parser=ParserConfig(max_file_size_kb=1),
    )
    indexer = RepoIndexer(config, store)
    files = indexer._discover_files()
    names = {f.name for f in files}
    assert "huge.py" not in names


# --- Full index ---


def test_full_index_parses_all_files(
    indexer_and_store: tuple[RepoIndexer, GraphStore],
) -> None:
    indexer, store = indexer_and_store
    stats = indexer.index_full(resolve=False)
    assert stats["parsed"] == 3
    assert stats["errors"] == 0

    db_stats = store.get_stats()
    assert db_stats["files"] == 3
    assert db_stats["symbols"] > 0


def test_full_index_captures_symbols(
    indexer_and_store: tuple[RepoIndexer, GraphStore],
) -> None:
    indexer, store = indexer_and_store
    indexer.index_full(resolve=False)

    # Should find functions from both files
    main_syms = store.find_symbols_by_name("main")
    assert len(main_syms) >= 1
    clamp_syms = store.find_symbols_by_name("clamp")
    assert len(clamp_syms) >= 1
    load_syms = store.find_symbols_by_name("load")
    assert len(load_syms) >= 1


def test_full_index_with_resolve(
    indexer_and_store: tuple[RepoIndexer, GraphStore],
) -> None:
    indexer, store = indexer_and_store
    stats = indexer.index_full(resolve=True)
    assert stats["parsed"] == 3

    # greet is called from main, and greet exists in same file -> should resolve
    main_syms = store.find_symbols_by_name("main")
    assert len(main_syms) >= 1
    deps = store.get_dependencies(main_syms[0].id)
    # main calls greet, so there should be an outgoing relationship
    assert len(deps) >= 1


def test_full_index_is_idempotent(
    indexer_and_store: tuple[RepoIndexer, GraphStore],
) -> None:
    indexer, store = indexer_and_store
    indexer.index_full(resolve=False)
    stats_before = store.get_stats()

    # Index again
    indexer.index_full(resolve=False)
    stats_after = store.get_stats()

    assert stats_before["files"] == stats_after["files"]
    assert stats_before["symbols"] == stats_after["symbols"]


# --- Incremental index ---


def test_incremental_index_skips_unchanged(
    indexer_and_store: tuple[RepoIndexer, GraphStore],
    sample_repo: Path,
) -> None:
    indexer, store = indexer_and_store
    indexer.index_full(resolve=False)

    # Incremental should parse 0 files since nothing changed
    stats = indexer.index_incremental(resolve=False)
    assert stats["parsed"] == 0


def test_incremental_index_picks_up_changes(
    indexer_and_store: tuple[RepoIndexer, GraphStore],
    sample_repo: Path,
) -> None:
    indexer, store = indexer_and_store
    indexer.index_full(resolve=False)

    # Modify one file
    (sample_repo / "utils.py").write_text(
        "MAX_SIZE = 200\n\ndef clamp(val, lo, hi):\n    return max(lo, min(val, hi))\n\n"
        "def new_func():\n    pass\n"
    )

    stats = indexer.index_incremental(resolve=False)
    assert stats["parsed"] == 1  # Only utils.py re-parsed

    # new_func should be in the store now
    new_syms = store.find_symbols_by_name("new_func")
    assert len(new_syms) >= 1


def test_incremental_index_detects_new_files(
    indexer_and_store: tuple[RepoIndexer, GraphStore],
    sample_repo: Path,
) -> None:
    indexer, store = indexer_and_store
    indexer.index_full(resolve=False)

    # Add a new file
    (sample_repo / "extra.py").write_text("def bonus():\n    return 42\n")

    stats = indexer.index_incremental(resolve=False)
    assert stats["parsed"] == 1

    bonus_syms = store.find_symbols_by_name("bonus")
    assert len(bonus_syms) >= 1


def test_incremental_index_with_resolve(
    indexer_and_store: tuple[RepoIndexer, GraphStore],
    sample_repo: Path,
) -> None:
    """Cover the resolve_imports branch in incremental when files changed."""
    indexer, store = indexer_and_store
    indexer.index_full(resolve=False)

    # Modify a file so incremental detects a change
    (sample_repo / "utils.py").write_text("def new_util():\n    pass\n")

    stats = indexer.index_incremental(resolve=True)
    assert stats["parsed"] == 1


def test_incremental_oserror_skipped(
    indexer_and_store: tuple[RepoIndexer, GraphStore],
    sample_repo: Path,
) -> None:
    """Cover the OSError continue path in index_incremental."""
    indexer, _store = indexer_and_store

    # Make read_bytes raise OSError for one file
    original_read_bytes = Path.read_bytes

    call_count = [0]

    def patched_read_bytes(self: Path) -> bytes:
        if self.name == "app.py":
            call_count[0] += 1
            raise OSError("permission denied")
        return original_read_bytes(self)

    with patch.object(Path, "read_bytes", patched_read_bytes):
        indexer.index_incremental(resolve=False)

    # app.py was skipped via OSError, the rest were processed normally
    assert call_count[0] >= 1


def test_index_files_parse_error_counted(
    indexer_and_store: tuple[RepoIndexer, GraphStore],
    sample_repo: Path,
) -> None:
    """Cover the except Exception path in _index_files."""
    indexer, _store = indexer_and_store

    with patch.object(
        indexer._registry, "parse_file", side_effect=RuntimeError("bad parse")
    ):
        files = indexer._discover_files()
        stats = indexer._index_files(files, "Test label")

    assert stats["errors"] == len(files)
    assert stats["parsed"] == 0


def test_index_files_skipped_counted(
    indexer_and_store: tuple[RepoIndexer, GraphStore],
    sample_repo: Path,
) -> None:
    """Cover the stats['skipped'] path when parse_file returns None."""
    indexer, _store = indexer_and_store

    with patch.object(indexer._registry, "parse_file", return_value=None):
        files = indexer._discover_files()
        stats = indexer._index_files(files, "Test label")

    assert stats["skipped"] == len(files)
    assert stats["parsed"] == 0


def test_index_files_batch_flush(
    indexer_and_store: tuple[RepoIndexer, GraphStore],
    sample_repo: Path,
) -> None:
    """Cover the mid-batch flush when batch_size is small."""
    indexer, store = indexer_and_store
    files = indexer._discover_files()
    assert len(files) >= 3  # need more than batch_size=2

    stats = indexer._index_files(files, "Batch test", batch_size=2)
    assert stats["parsed"] == len(files)
    assert stats["errors"] == 0
