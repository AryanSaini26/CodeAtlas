"""Repository indexer - walks a repo and builds the knowledge graph."""

import hashlib
import time
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from codeatlas.config import CodeAtlasConfig
from codeatlas.graph.store import GraphStore
from codeatlas.parsers import ParserRegistry

console = Console()


class RepoIndexer:
    """Indexes an entire repository into the GraphStore."""

    def __init__(self, config: CodeAtlasConfig, store: GraphStore) -> None:
        self._config = config
        self._store = store
        self._registry = ParserRegistry()

    def index_full(self) -> dict[str, int]:
        """Full index: parse all supported files and upsert into the graph."""
        files = self._discover_files()
        return self._index_files(files, label="Full index")

    def index_incremental(self) -> dict[str, int]:
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
        return self._index_files(changed, label="Incremental index")

    def _discover_files(self) -> list[Path]:
        root = self._config.repo_root
        exclude = set(self._config.exclude_dirs)
        max_kb = self._config.parser.max_file_size_kb
        extensions = set(self._config.parser.include_extensions)

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
            result.append(path)
        return sorted(result)

    def _index_files(self, files: list[Path], label: str) -> dict[str, int]:
        stats: dict[str, int] = {"parsed": 0, "skipped": 0, "errors": 0}
        start = time.monotonic()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"{label}...", total=len(files))
            for path in files:
                progress.update(task, description=f"{label}: {path.name}")
                try:
                    result = self._registry.parse_file(path)
                    if result is not None:
                        self._store.upsert_parse_result(result)
                        stats["parsed"] += 1
                    else:
                        stats["skipped"] += 1
                except Exception as exc:
                    console.print(f"[red]Error parsing {path}: {exc}[/red]")
                    stats["errors"] += 1
                progress.advance(task)

        elapsed = time.monotonic() - start
        console.print(
            f"[green]{label} complete:[/green] "
            f"{stats['parsed']} parsed, {stats['skipped']} skipped, "
            f"{stats['errors']} errors in {elapsed:.2f}s"
        )
        return stats
