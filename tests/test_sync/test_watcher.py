"""Tests for the file watcher."""

import time
from pathlib import Path

import pytest

from codeatlas.config import CodeAtlasConfig, GraphConfig
from codeatlas.graph.store import GraphStore
from codeatlas.sync.watcher import FileWatcher


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Create a temporary repo with a Python file."""
    f = tmp_path / "hello.py"
    f.write_text('def greet():\n    return "hello"\n')
    return tmp_path


@pytest.fixture
def watcher_setup(tmp_repo: Path) -> tuple[FileWatcher, GraphStore]:
    config = CodeAtlasConfig(
        repo_root=tmp_repo,
        graph=GraphConfig(db_path=Path(":memory:")),
    )
    store = GraphStore(":memory:")
    watcher = FileWatcher(config, store)
    return watcher, store


def test_watcher_starts_and_stops(watcher_setup: tuple[FileWatcher, GraphStore]) -> None:
    watcher, _ = watcher_setup
    watcher.start(blocking=False)
    assert watcher.is_running
    watcher.stop()
    assert not watcher.is_running


def test_watcher_detects_new_file(
    watcher_setup: tuple[FileWatcher, GraphStore], tmp_repo: Path
) -> None:
    watcher, store = watcher_setup
    watcher.start(blocking=False)

    # Create a new Python file
    new_file = tmp_repo / "new_module.py"
    new_file.write_text('def new_func():\n    pass\n')

    # Wait for debounce + processing
    time.sleep(1.5)

    symbols = store.get_symbols_in_file(str(new_file))
    watcher.stop()

    assert len(symbols) >= 1
    assert any(s.name == "new_func" for s in symbols)


def test_watcher_detects_modification(
    watcher_setup: tuple[FileWatcher, GraphStore], tmp_repo: Path
) -> None:
    watcher, store = watcher_setup

    # First manually index the existing file
    existing = tmp_repo / "hello.py"
    from codeatlas.parsers import ParserRegistry
    registry = ParserRegistry()
    result = registry.parse_file(existing)
    if result:
        store.upsert_parse_result(result)

    watcher.start(blocking=False)

    # Modify the file
    existing.write_text('def greet():\n    return "hello"\n\ndef farewell():\n    return "bye"\n')

    time.sleep(1.5)

    symbols = store.get_symbols_in_file(str(existing))
    watcher.stop()

    names = {s.name for s in symbols}
    assert "farewell" in names


def test_watcher_detects_deletion(
    watcher_setup: tuple[FileWatcher, GraphStore], tmp_repo: Path
) -> None:
    watcher, store = watcher_setup

    existing = tmp_repo / "hello.py"
    from codeatlas.parsers import ParserRegistry
    registry = ParserRegistry()
    result = registry.parse_file(existing)
    if result:
        store.upsert_parse_result(result)

    watcher.start(blocking=False)

    existing.unlink()
    time.sleep(1.5)

    symbols = store.get_symbols_in_file(str(existing))
    watcher.stop()

    assert symbols == []


def test_watcher_ignores_non_code_files(
    watcher_setup: tuple[FileWatcher, GraphStore], tmp_repo: Path
) -> None:
    watcher, store = watcher_setup
    watcher.start(blocking=False)

    txt_file = tmp_repo / "notes.txt"
    txt_file.write_text("this is not code")

    time.sleep(1.5)

    symbols = store.get_symbols_in_file(str(txt_file))
    watcher.stop()

    assert symbols == []
