"""Click CLI for CodeAtlas."""

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from codeatlas.config import CodeAtlasConfig, GraphConfig
from codeatlas.graph.export import ExportOptions, export_dot, export_json
from codeatlas.graph.store import GraphStore
from codeatlas.indexer import RepoIndexer
from codeatlas.sync.watcher import FileWatcher

console = Console()


def _get_store(db_path: Path) -> GraphStore:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return GraphStore(db_path)


@click.group()
def cli() -> None:
    """CodeAtlas - real-time code knowledge graphs for AI coding agents."""


@cli.command()
@click.argument("repo_path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--db", default=".codeatlas/graph.db", show_default=True, help="Database path")
@click.option("--incremental", is_flag=True, help="Only re-index changed files")
def index(repo_path: str, db: str, incremental: bool) -> None:
    """Index a repository into the knowledge graph."""
    config = CodeAtlasConfig(
        repo_root=Path(repo_path),
        graph=GraphConfig(db_path=Path(db)),
    )
    store = _get_store(Path(db))
    indexer = RepoIndexer(config, store)

    if incremental:
        indexer.index_incremental()
    else:
        indexer.index_full()

    store.close()


@cli.command()
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
def stats(db: str) -> None:
    """Show graph statistics."""
    store = _get_store(Path(db))
    s = store.get_stats()
    store.close()

    table = Table(title="CodeAtlas Graph Stats")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right", style="green")
    for key, val in s.items():
        table.add_row(key.capitalize(), str(val))
    console.print(table)


@cli.command()
@click.argument("query")
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option("--limit", default=20, show_default=True)
@click.option("--semantic", is_flag=True, help="Use semantic (vector) search")
@click.option("--hybrid", is_flag=True, help="Use hybrid (FTS + semantic) search")
def query(query: str, db: str, limit: int, semantic: bool, hybrid: bool) -> None:
    """Search for symbols by name or docstring."""
    store = _get_store(Path(db))

    if semantic or hybrid:
        from codeatlas.search.embeddings import SemanticIndex

        sem_index = SemanticIndex()
        data_dir = Path(db).parent
        if not sem_index.load(data_dir):
            console.print("[yellow]Building semantic index...[/yellow]")
            count = sem_index.build_from_store(store)
            sem_index.save(data_dir)
            console.print(f"[green]Indexed {count} symbols[/green]")

        if hybrid:
            from codeatlas.search.hybrid import HybridSearch
            searcher = HybridSearch(store, sem_index)
            results = searcher.search(query, limit=limit)
        else:
            raw = sem_index.search(query, store, limit=limit)
            results = [sym for sym, _ in raw]
    else:
        results = store.search(query, limit=limit)

    store.close()

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    table = Table(title=f"Search: {query}")
    table.add_column("Name", style="cyan")
    table.add_column("Kind", style="magenta")
    table.add_column("File")
    table.add_column("Line", justify="right")
    for sym in results:
        table.add_row(
            sym.qualified_name,
            sym.kind.value,
            sym.file_path,
            str(sym.span.start.line + 1),
        )
    console.print(table)


@cli.command()
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option("--format", "fmt", type=click.Choice(["dot", "json"]), default="dot", show_default=True)
@click.option("--file-filter", default=None, help="Only export symbols from files matching this prefix")
@click.option("--include-externals", is_flag=True, help="Include unresolved/external references")
@click.option("-o", "--output", default=None, type=click.Path(), help="Output file (default: stdout)")
def export(db: str, fmt: str, file_filter: str | None, include_externals: bool, output: str | None) -> None:
    """Export the knowledge graph to DOT or JSON format."""
    store = _get_store(Path(db))
    opts = ExportOptions(include_externals=include_externals, file_filter=file_filter)

    if fmt == "dot":
        result = export_dot(store, opts)
    else:
        result = export_json(store, opts)

    store.close()

    if output:
        Path(output).write_text(result)
        console.print(f"[green]Exported to {output}[/green]")
    else:
        console.print(result)


@cli.command()
@click.argument("repo_path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
def watch(repo_path: str, db: str) -> None:
    """Watch a repository for file changes and update the graph in real-time."""
    config = CodeAtlasConfig(
        repo_root=Path(repo_path),
        graph=GraphConfig(db_path=Path(db)),
    )
    store = _get_store(Path(db))
    watcher = FileWatcher(config, store)
    try:
        watcher.start(blocking=True)
    finally:
        store.close()


@cli.command()
@click.argument("repo_path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option("--port", default=9000, show_default=True, help="Port to listen on")
@click.option("--secret", default=None, help="GitHub webhook secret for signature verification")
def webhook(repo_path: str, db: str, port: int, secret: str | None) -> None:
    """Start a webhook server to receive GitHub push events."""
    import uvicorn

    from codeatlas.sync.webhook import WebhookHandler

    store = _get_store(Path(db))
    handler = WebhookHandler(store, Path(repo_path), secret=secret)
    app = handler.create_app()
    console.print(
        f"[green]Webhook server listening on port {port}[/green] "
        f"(POST /webhook, GET /health)"
    )
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


@cli.command()
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option("--transport", type=click.Choice(["stdio"]), default="stdio", show_default=True)
def serve(db: str, transport: str) -> None:
    """Start the MCP server."""
    from codeatlas.server import mcp, set_store

    store = _get_store(Path(db))
    set_store(store)
    console.print(f"[green]Starting CodeAtlas MCP server[/green] (db: {db})")
    mcp.run(transport=transport)
