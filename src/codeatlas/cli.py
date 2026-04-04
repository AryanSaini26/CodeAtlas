"""Click CLI for CodeAtlas."""

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from codeatlas.config import CodeAtlasConfig
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
def init(repo_path: str) -> None:
    """Generate a codeatlas.toml config file in the repository root."""
    root = Path(repo_path)
    toml_path = root / "codeatlas.toml"
    if toml_path.exists():
        console.print(f"[yellow]{toml_path} already exists, skipping.[/yellow]")
        return

    toml_path.write_text(
        "[codeatlas]\n"
        "# repo_root is set automatically when loading\n\n"
        "[codeatlas.parser]\n"
        "max_file_size_kb = 500\n"
        'include_extensions = [".py", ".ts", ".tsx", ".go", ".rs", ".java", ".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".h", ".cs"]\n\n'
        "[codeatlas.graph]\n"
        'db_path = ".codeatlas/graph.db"\n\n'
        "[codeatlas.server]\n"
        'host = "localhost"\n'
        "port = 8765\n"
        'name = "codeatlas"\n\n'
        "# Directories to skip during indexing\n"
        '# exclude_dirs = [".git", ".venv", "node_modules", "__pycache__", "dist", "build"]\n'
    )
    console.print(f"[green]Created {toml_path}[/green]")


@cli.command()
@click.argument("repo_path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--db", default=".codeatlas/graph.db", show_default=True, help="Database path")
@click.option("--incremental", is_flag=True, help="Only re-index changed files")
def index(repo_path: str, db: str, incremental: bool) -> None:
    """Index a repository into the knowledge graph."""
    config = CodeAtlasConfig.find_and_load(Path(repo_path))
    config.graph.db_path = Path(db)
    store = _get_store(Path(db))
    indexer = RepoIndexer(config, store)

    if incremental:
        indexer.index_incremental()
    else:
        indexer.index_full()

    store.close()


@cli.command()
@click.argument("repo_path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
def diff(repo_path: str, db: str) -> None:
    """Show files that changed since the last index."""
    import hashlib

    config = CodeAtlasConfig.find_and_load(Path(repo_path))
    config.graph.db_path = Path(db)
    store = _get_store(Path(db))
    indexer = RepoIndexer(config, store)

    files = indexer._discover_files()
    added, modified, unchanged = [], [], []

    for path in files:
        try:
            content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
        existing = store.get_file_info(str(path))
        if existing is None:
            added.append(str(path))
        elif existing.content_hash != content_hash:
            modified.append(str(path))
        else:
            unchanged.append(str(path))

    store.close()

    if added:
        console.print(f"[green]New files ({len(added)}):[/green]")
        for f in added:
            console.print(f"  + {f}")
    if modified:
        console.print(f"[yellow]Modified files ({len(modified)}):[/yellow]")
        for f in modified:
            console.print(f"  ~ {f}")
    if not added and not modified:
        console.print("[dim]No changes since last index.[/dim]")
    else:
        total = len(added) + len(modified)
        console.print(f"\n[bold]{total} file(s) to re-index[/bold] ({len(unchanged)} unchanged)")


@cli.command(name="list-files")
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option("--lang", default=None, help="Filter by language (python, typescript, go)")
def list_files(db: str, lang: str | None) -> None:
    """List all files in the knowledge graph."""
    store = _get_store(Path(db))
    files = store.list_files()
    store.close()

    if lang:
        files = [f for f in files if f.language == lang.lower()]

    if not files:
        console.print("[yellow]No files indexed.[/yellow]")
        return

    table = Table(title="Indexed Files")
    table.add_column("File", style="cyan")
    table.add_column("Language", style="magenta")
    table.add_column("Symbols", justify="right", style="green")
    table.add_column("Relationships", justify="right")
    table.add_column("Size", justify="right")
    for f in files:
        size_str = f"{f.size_bytes / 1024:.1f} KB" if f.size_bytes >= 1024 else f"{f.size_bytes} B"
        table.add_row(f.path, f.language, str(f.symbol_count), str(f.relationship_count), size_str)
    console.print(table)


@cli.command()
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def stats(db: str, as_json: bool) -> None:
    """Show graph statistics."""
    store = _get_store(Path(db))
    s = store.get_stats()
    lang_breakdown = store.get_language_breakdown()
    kind_breakdown = store.get_kind_breakdown()
    store.close()

    if as_json:
        import json

        s["languages"] = lang_breakdown
        s["kinds"] = kind_breakdown
        console.print(json.dumps(s, indent=2))
    else:
        table = Table(title="CodeAtlas Graph Stats")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right", style="green")
        for key, val in s.items():
            table.add_row(key.capitalize(), str(val))
        console.print(table)

        if lang_breakdown:
            lang_table = Table(title="By Language")
            lang_table.add_column("Language", style="cyan")
            lang_table.add_column("Symbols", justify="right", style="green")
            for lang, count in lang_breakdown.items():
                lang_table.add_row(lang, str(count))
            console.print(lang_table)

        if kind_breakdown:
            kind_table = Table(title="By Kind")
            kind_table.add_column("Kind", style="cyan")
            kind_table.add_column("Count", justify="right", style="green")
            for kind, count in kind_breakdown.items():
                kind_table.add_row(kind, str(count))
            console.print(kind_table)


@cli.command()
@click.argument("query")
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option("--limit", default=20, show_default=True)
@click.option("--semantic", is_flag=True, help="Use semantic (vector) search")
@click.option("--hybrid", is_flag=True, help="Use hybrid (FTS + semantic) search")
@click.option(
    "--kind",
    default=None,
    help="Filter by symbol kind (function, class, method, interface, etc.)",
)
def query(query: str, db: str, limit: int, semantic: bool, hybrid: bool, kind: str | None) -> None:
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

    if kind:
        results = [s for s in results if s.kind.value == kind.lower()]

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
@click.option(
    "--format", "fmt", type=click.Choice(["dot", "json"]), default="dot", show_default=True
)
@click.option(
    "--file-filter", default=None, help="Only export symbols from files matching this prefix"
)
@click.option("--include-externals", is_flag=True, help="Include unresolved/external references")
@click.option(
    "-o", "--output", default=None, type=click.Path(), help="Output file (default: stdout)"
)
def export(
    db: str, fmt: str, file_filter: str | None, include_externals: bool, output: str | None
) -> None:
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
@click.argument("symbol_name")
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option("--depth", default=3, show_default=True, help="Max traversal depth for call chain")
def show(symbol_name: str, db: str, depth: int) -> None:
    """Inspect a symbol: signature, docstring, dependencies, and dependents."""
    store = _get_store(Path(db))
    matches = store.find_symbols_by_name(symbol_name)

    if not matches:
        console.print(f"[yellow]No symbol found matching '{symbol_name}'[/yellow]")
        store.close()
        return

    for sym in matches:
        # Header
        console.print(f"\n[bold cyan]{sym.qualified_name}[/bold cyan] ({sym.kind.value})")
        console.print(f"  File: {sym.file_path}:{sym.span.start.line + 1}")
        if sym.signature:
            console.print(f"  Signature: [green]{sym.signature}[/green]")
        if sym.docstring:
            console.print(f"  Docstring: [dim]{sym.docstring}[/dim]")
        if sym.decorators:
            console.print(f"  Decorators: {', '.join(sym.decorators)}")

        # Dependencies (what it calls/imports)
        deps = store.get_dependencies(sym.id)
        if deps:
            dep_table = Table(title="Dependencies (outgoing)", show_header=True)
            dep_table.add_column("Target", style="cyan")
            dep_table.add_column("Kind", style="magenta")
            for rel in deps:
                dep_table.add_row(rel.target_id, rel.kind.value)
            console.print(dep_table)

        # Dependents (what calls/imports it)
        dependents = store.get_dependents(sym.id)
        if dependents:
            rev_table = Table(title="Dependents (incoming)", show_header=True)
            rev_table.add_column("Source", style="cyan")
            rev_table.add_column("Kind", style="magenta")
            for rel in dependents:
                rev_table.add_row(rel.source_id, rel.kind.value)
            console.print(rev_table)

        # Call chain
        chain = store.trace_call_chain(sym.id, max_depth=depth)
        if chain:
            chain_table = Table(title=f"Call Chain (depth={depth})", show_header=True)
            chain_table.add_column("Caller", style="cyan")
            chain_table.add_column("Callee", style="green")
            chain_table.add_column("Depth", justify="right")
            for row in chain:
                chain_table.add_row(str(row["source_id"]), str(row["target_id"]), str(row["depth"]))
            console.print(chain_table)

    store.close()


@cli.command()
@click.argument("repo_path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
def watch(repo_path: str, db: str) -> None:
    """Watch a repository for file changes and update the graph in real-time."""
    config = CodeAtlasConfig.find_and_load(Path(repo_path))
    config.graph.db_path = Path(db)
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
        f"[green]Webhook server listening on port {port}[/green] (POST /webhook, GET /health)"
    )
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


@cli.command()
@click.argument("repo_path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def clean(repo_path: str, yes: bool) -> None:
    """Remove the .codeatlas directory (database, indexes, etc.)."""
    import shutil

    atlas_dir = Path(repo_path) / ".codeatlas"
    if not atlas_dir.exists():
        console.print("[yellow]No .codeatlas directory found.[/yellow]")
        return

    if not yes:
        click.confirm(f"Delete {atlas_dir} and all its contents?", abort=True)

    shutil.rmtree(atlas_dir)
    console.print(f"[green]Removed {atlas_dir}[/green]")


@cli.command()
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option("--cycles", "show_cycles", is_flag=True, help="Show circular dependencies only")
@click.option("--unused", "show_unused", is_flag=True, help="Show unused symbols only")
@click.option("--centrality", "show_centrality", is_flag=True, help="Show symbol centrality only")
@click.option("--limit", default=20, show_default=True, help="Max results for centrality")
def audit(db: str, show_cycles: bool, show_unused: bool, show_centrality: bool, limit: int) -> None:
    """Run code quality analysis: cycles, dead code, and complexity."""
    store = _get_store(Path(db))

    # If no specific flag, show all
    show_all = not (show_cycles or show_unused or show_centrality)

    if show_all or show_cycles:
        cycles = store.detect_cycles()
        if cycles:
            table = Table(title=f"Circular Dependencies ({len(cycles)} cycles)")
            table.add_column("#", justify="right", style="dim")
            table.add_column("Cycle", style="red")
            table.add_column("Length", justify="right")
            for i, cycle in enumerate(cycles, 1):
                table.add_row(str(i), " -> ".join(cycle) + " -> " + cycle[0], str(len(cycle)))
            console.print(table)
        else:
            console.print("[green]No circular dependencies found.[/green]")
        console.print()

    if show_all or show_unused:
        unused = store.find_unused_symbols()
        if unused:
            table = Table(title=f"Unused Symbols ({len(unused)} found)")
            table.add_column("Name", style="yellow")
            table.add_column("Kind", style="magenta")
            table.add_column("File")
            table.add_column("Line", justify="right")
            for sym in unused:
                table.add_row(
                    sym.qualified_name, sym.kind.value, sym.file_path, str(sym.span.start.line + 1)
                )
            console.print(table)
        else:
            console.print("[green]No unused symbols found.[/green]")
        console.print()

    if show_all or show_centrality:
        centrality = store.get_symbol_centrality(limit=limit)
        if centrality:
            table = Table(title=f"Symbol Centrality (top {len(centrality)})")
            table.add_column("Name", style="cyan")
            table.add_column("Kind", style="magenta")
            table.add_column("File")
            table.add_column("In", justify="right", style="green")
            table.add_column("Out", justify="right", style="yellow")
            table.add_column("Total", justify="right", style="bold")
            for entry in centrality:
                table.add_row(
                    str(entry["qualified_name"]),
                    str(entry["kind"]),
                    str(entry["file"]),
                    str(entry["in_degree"]),
                    str(entry["out_degree"]),
                    str(entry["total_degree"]),
                )
            console.print(table)
        else:
            console.print("[dim]No relationships found for centrality analysis.[/dim]")

    store.close()


@cli.command(name="find-path")
@click.argument("source")
@click.argument("target")
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option("--depth", default=10, show_default=True, help="Max path length")
def find_path(source: str, target: str, db: str, depth: int) -> None:
    """Find the shortest dependency path between two symbols."""
    store = _get_store(Path(db))
    src_matches = store.find_symbols_by_name(source)
    tgt_matches = store.find_symbols_by_name(target)

    if not src_matches:
        console.print(f"[yellow]Source symbol '{source}' not found.[/yellow]")
        store.close()
        return
    if not tgt_matches:
        console.print(f"[yellow]Target symbol '{target}' not found.[/yellow]")
        store.close()
        return

    path = store.find_path(src_matches[0].id, tgt_matches[0].id, max_depth=depth)
    store.close()

    if path is None:
        console.print(f"[yellow]No path found between '{source}' and '{target}'.[/yellow]")
        return

    console.print(f"[bold]Path ({len(path) - 1} hops):[/bold]")
    for i, node_id in enumerate(path):
        prefix = "  " if i > 0 else ""
        arrow = "-> " if i > 0 else "   "
        console.print(f"{prefix}{arrow}[cyan]{node_id}[/cyan]")


@cli.command()
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option("--limit", default=20, show_default=True, help="Max file pairs to show")
def coupling(db: str, limit: int) -> None:
    """Show file coupling analysis — which files are most interconnected."""
    store = _get_store(Path(db))
    pairs = store.get_file_coupling(limit=limit)
    store.close()

    if not pairs:
        console.print("[dim]No cross-file relationships found.[/dim]")
        return

    table = Table(title=f"File Coupling (top {len(pairs)} pairs)")
    table.add_column("Source File", style="cyan")
    table.add_column("Target File", style="green")
    table.add_column("Relationships", justify="right", style="bold")
    table.add_column("Kinds")
    for pair in pairs:
        table.add_row(
            str(pair["source_file"]),
            str(pair["target_file"]),
            str(pair["relationship_count"]),
            ", ".join(pair["kinds"]),
        )
    console.print(table)


@cli.command()
@click.argument("repo_path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option("--ref", default="HEAD", show_default=True, help="Git ref to diff against")
@click.option("--depth", default=3, show_default=True, help="Max depth for impact traversal")
def impact(repo_path: str, db: str, ref: str, depth: int) -> None:
    """Analyze the impact of current git changes on the codebase."""
    from codeatlas.git_integration import analyze_change_impact

    store = _get_store(Path(db))
    result = analyze_change_impact(store, Path(repo_path), ref=ref, max_depth=depth)
    store.close()

    if not result.changed_files:
        console.print(
            "[dim]No changed files detected (is this a git repo with uncommitted changes?).[/dim]"
        )
        return

    console.print(f"[bold]Changed files ({len(result.changed_files)}):[/bold]")
    for f in result.changed_files:
        console.print(f"  [yellow]~ {f}[/yellow]")
    console.print()

    if result.changed_symbols:
        table = Table(title=f"Changed Symbols ({len(result.changed_symbols)})")
        table.add_column("Symbol", style="yellow")
        table.add_column("Kind", style="magenta")
        table.add_column("File")
        table.add_column("Line", justify="right")
        for cs in result.changed_symbols:
            table.add_row(
                cs.symbol.qualified_name,
                cs.symbol.kind.value,
                cs.symbol.file_path,
                str(cs.symbol.span.start.line + 1),
            )
        console.print(table)
        console.print()

    if result.affected_symbols:
        table = Table(title=f"Affected Symbols ({len(result.affected_symbols)})")
        table.add_column("Symbol", style="red")
        table.add_column("Kind", style="magenta")
        table.add_column("File")
        table.add_column("Line", justify="right")
        for sym in result.affected_symbols:
            table.add_row(
                sym.qualified_name,
                sym.kind.value,
                sym.file_path,
                str(sym.span.start.line + 1),
            )
        console.print(table)
        console.print()

    if result.affected_files:
        console.print(f"[bold]Affected files ({len(result.affected_files)}):[/bold]")
        for f in result.affected_files:
            console.print(f"  [red]! {f}[/red]")
    elif result.changed_symbols:
        console.print("[green]No other files affected by these changes.[/green]")


@cli.command()
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option(
    "--file-filter", default=None, help="Only include symbols from files matching this prefix"
)
@click.option("-o", "--output", default=None, type=click.Path(), help="Output HTML file path")
@click.option("--open", "open_browser", is_flag=True, help="Open in default browser")
def viz(db: str, file_filter: str | None, output: str | None, open_browser: bool) -> None:
    """Generate an interactive D3.js graph visualization."""
    from codeatlas.viz import generate_viz

    store = _get_store(Path(db))
    html = generate_viz(store, file_filter=file_filter)
    store.close()

    out_path = Path(output) if output else Path(".codeatlas/graph.html")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)
    console.print(f"[green]Visualization saved to {out_path}[/green]")

    if open_browser:
        import webbrowser

        webbrowser.open(f"file://{out_path.resolve()}")


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
