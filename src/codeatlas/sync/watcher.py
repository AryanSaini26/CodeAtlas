"""File system watcher for real-time incremental graph updates."""

import threading
import time
from pathlib import Path

from rich.console import Console
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from codeatlas.config import CodeAtlasConfig
from codeatlas.graph.store import GraphStore
from codeatlas.parsers import ParserRegistry

console = Console()


class _ChangeCollector(FileSystemEventHandler):
    """Collects file change events and debounces them."""

    def __init__(
        self,
        config: CodeAtlasConfig,
        store: GraphStore,
        registry: ParserRegistry,
        debounce_seconds: float = 0.5,
    ) -> None:
        self._config = config
        self._store = store
        self._registry = registry
        self._debounce = debounce_seconds
        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._exclude = set(config.exclude_dirs)
        self._extensions = set(config.parser.include_extensions)

    def _should_process(self, path: str) -> bool:
        p = Path(path)
        if not p.is_file():
            return False
        if p.suffix.lower() not in self._extensions:
            return False
        if any(part in self._exclude for part in p.parts):
            return False
        return True

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._schedule(str(event.src_path))

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._schedule(str(event.src_path))

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = str(event.src_path)
        if self._should_process_extension(path):
            with self._lock:
                self._pending[path] = -1  # sentinel for deletion
            self._reset_timer()

    def _should_process_extension(self, path: str) -> bool:
        return Path(path).suffix.lower() in self._extensions

    def _schedule(self, path: str) -> None:
        if not self._should_process(path):
            return
        with self._lock:
            self._pending[path] = time.monotonic()
        self._reset_timer()

    def _reset_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(self._debounce, self._flush)
        self._timer.daemon = True
        self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            batch = dict(self._pending)
            self._pending.clear()

        for path, ts in batch.items():
            if ts == -1:
                # File was deleted
                self._store.delete_file(path)
                console.print(f"[red]Removed:[/red] {path}")
            else:
                # File was created or modified
                try:
                    result = self._registry.parse_file(Path(path))
                    if result is not None:
                        self._store.upsert_parse_result(result)
                        console.print(
                            f"[green]Updated:[/green] {path} "
                            f"({result.file_info.symbol_count} symbols)"
                        )
                except Exception as exc:
                    console.print(f"[red]Error parsing {path}:[/red] {exc}")


class FileWatcher:
    """Watches a repository directory and incrementally updates the graph."""

    def __init__(self, config: CodeAtlasConfig, store: GraphStore) -> None:
        self._config = config
        self._store = store
        self._registry = ParserRegistry()
        self._observer: Observer | None = None

    def start(self, blocking: bool = True) -> None:
        """Start watching the repository for file changes.

        Args:
            blocking: If True, block until interrupted. If False, run in background.
        """
        handler = _ChangeCollector(self._config, self._store, self._registry)
        self._observer = Observer()
        self._observer.schedule(handler, str(self._config.repo_root), recursive=True)
        self._observer.start()

        console.print(
            f"[blue]Watching[/blue] {self._config.repo_root} for changes... "
            f"(Ctrl+C to stop)"
        )

        if blocking:
            try:
                while self._observer.is_alive():
                    self._observer.join(timeout=1)
            except KeyboardInterrupt:
                self.stop()

    def stop(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            console.print("[yellow]Watcher stopped.[/yellow]")

    @property
    def is_running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()
