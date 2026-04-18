"""Repository indexer - walks a repo and builds the knowledge graph."""

import hashlib
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from codeatlas.config import CodeAtlasConfig
from codeatlas.graph.store import GraphStore
from codeatlas.ignore import load_ignore_file
from codeatlas.models import ParseResult
from codeatlas.parsers import ParserRegistry

console = Console()

_WORKER_REGISTRY: ParserRegistry | None = None


def _parse_one(path_str: str) -> tuple[str, ParseResult | None, str | None]:
    """Worker-local parse. Instantiates a per-process ParserRegistry once.

    Must be module-level so `ProcessPoolExecutor` (spawn context) can pickle it.
    """
    global _WORKER_REGISTRY
    if _WORKER_REGISTRY is None:
        _WORKER_REGISTRY = ParserRegistry()
    try:
        return (path_str, _WORKER_REGISTRY.parse_file(Path(path_str)), None)
    except Exception as exc:
        return (path_str, None, str(exc))


class RepoIndexer:
    """Indexes an entire repository into the GraphStore."""

    def __init__(self, config: CodeAtlasConfig, store: GraphStore, workers: int = 1) -> None:
        self._config = config
        self._store = store
        self._registry = ParserRegistry()
        self._workers = max(1, workers)

    def index_full(self, resolve: bool = True) -> dict[str, int]:
        """Full index: parse all supported files and upsert into the graph."""
        files = self._discover_files()
        stats = self._index_files(files, label="Full index")
        if resolve:
            res = self._store.resolve_imports()
            console.print(
                f"[blue]Import resolution:[/blue] "
                f"{res['resolved']} resolved, {res['unresolved']} unresolved"
            )
        return stats

    def index_incremental(self, resolve: bool = True) -> dict[str, int]:
        """Incremental index: only re-parse files whose content hash has changed."""
        files = self._discover_files()
        changed: list[Path] = []
        for path in files:
            try:
                content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                continue
            existing = self._store.get_file_info(str(path))
            if existing is None or existing.content_hash != content_hash:
                changed.append(path)
        stats = self._index_files(changed, label="Incremental index")
        if resolve and changed:
            res = self._store.resolve_imports()
            console.print(
                f"[blue]Import resolution:[/blue] "
                f"{res['resolved']} resolved, {res['unresolved']} unresolved"
            )
        return stats

    def _discover_files(self) -> list[Path]:
        root = self._config.repo_root
        exclude = set(self._config.exclude_dirs)
        max_kb = self._config.parser.max_file_size_kb
        extensions = set(self._config.parser.include_extensions)
        ignore = load_ignore_file(root)

        result: list[Path] = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in exclude for part in path.parts):
                continue
            if path.suffix.lower() not in extensions:
                continue
            if path.stat().st_size > max_kb * 1024:
                continue
            rel = path.relative_to(root).as_posix()
            if ignore.is_ignored(rel):
                continue
            result.append(path)
        return sorted(result)

    def _index_files(self, files: list[Path], label: str, batch_size: int = 50) -> dict[str, int]:
        stats: dict[str, int] = {"parsed": 0, "skipped": 0, "errors": 0}
        start = time.monotonic()
        batch: list[ParseResult] = []

        def _handle(path: str, result: ParseResult | None, err: str | None) -> None:
            if err is not None:
                console.print(f"[red]Error parsing {path}: {err}[/red]")
                stats["errors"] += 1
            elif result is not None:
                batch.append(result)
                stats["parsed"] += 1
            else:
                stats["skipped"] += 1

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"{label}...", total=len(files))

            if self._workers > 1 and len(files) > 1:
                path_strs = [str(p) for p in files]
                chunk = max(1, min(16, len(files) // (self._workers * 4) or 1))
                with ProcessPoolExecutor(max_workers=self._workers) as pool:
                    for path_str, result, err in pool.map(_parse_one, path_strs, chunksize=chunk):
                        progress.update(task, description=f"{label}: {Path(path_str).name}")
                        _handle(path_str, result, err)
                        if len(batch) >= batch_size:
                            self._store.upsert_batch(batch)
                            batch.clear()
                        progress.advance(task)
            else:
                for path in files:
                    progress.update(task, description=f"{label}: {path.name}")
                    try:
                        result = self._registry.parse_file(path)
                        _handle(str(path), result, None)
                    except Exception as exc:
                        _handle(str(path), None, str(exc))
                    if len(batch) >= batch_size:
                        self._store.upsert_batch(batch)
                        batch.clear()
                    progress.advance(task)

            if batch:
                self._store.upsert_batch(batch)

        elapsed = time.monotonic() - start
        console.print(
            f"[green]{label} complete:[/green] "
            f"{stats['parsed']} parsed, {stats['skipped']} skipped, "
            f"{stats['errors']} errors in {elapsed:.2f}s"
        )
        return stats
