"""Click CLI for CodeAtlas."""

from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from codeatlas import __version__
from codeatlas.config import CodeAtlasConfig
from codeatlas.graph.export import (
    ExportOptions,
    export_csv,
    export_cypher,
    export_dot,
    export_graphml,
    export_json,
    export_mermaid,
)
from codeatlas.graph.store import GraphStore
from codeatlas.indexer import RepoIndexer
from codeatlas.sync.watcher import FileWatcher

console = Console()


def _get_store(db_path: Path) -> GraphStore:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return GraphStore(db_path)


@click.group()
@click.version_option(version=__version__, prog_name="codeatlas")
def cli() -> None:
    """CodeAtlas - real-time code knowledge graphs for AI coding agents."""


_COMPLETION_SCRIPTS = {
    "bash": {
        "script": 'eval "$(_CODEATLAS_COMPLETE=bash_source codeatlas)"',
        "rc": "~/.bashrc",
    },
    "zsh": {
        "script": 'eval "$(_CODEATLAS_COMPLETE=zsh_source codeatlas)"',
        "rc": "~/.zshrc",
    },
    "fish": {
        "script": "_CODEATLAS_COMPLETE=fish_source codeatlas | source",
        "rc": "~/.config/fish/completions/codeatlas.fish",
    },
}


@cli.command("install-completion")
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]), required=False)
def install_completion(shell: str | None) -> None:
    """Print the shell completion activation line for your shell.

    Example: `codeatlas install-completion zsh >> ~/.zshrc`
    """
    import os

    if shell is None:
        shell_env = os.environ.get("SHELL", "")
        if "zsh" in shell_env:
            shell = "zsh"
        elif "fish" in shell_env:
            shell = "fish"
        else:
            shell = "bash"
    info = _COMPLETION_SCRIPTS[shell]
    click.echo(info["script"])
    click.echo(
        f"# Add the line above to {info['rc']} to enable completion.",
        err=True,
    )


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
@click.option("--watch", is_flag=True, help="Keep watching for changes after indexing")
@click.option(
    "--workers",
    default=1,
    show_default=True,
    type=int,
    help="Parse files in parallel processes (1 = serial)",
)
def index(repo_path: str, db: str, incremental: bool, watch: bool, workers: int) -> None:
    """Index a repository into the knowledge graph."""
    config = CodeAtlasConfig.find_and_load(Path(repo_path))
    config.graph.db_path = Path(db)
    store = _get_store(Path(db))
    indexer = RepoIndexer(config, store, workers=workers)

    if incremental:
        indexer.index_incremental()
    else:
        indexer.index_full()

    if watch:
        watcher = FileWatcher(config, store)
        console.print("[green]Index complete — watching for changes (Ctrl+C to stop)...[/green]")
        try:
            watcher.start(blocking=True)
        finally:
            store.close()
    else:
        store.close()


@cli.command()
@click.argument("repo_path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option(
    "--since",
    default=None,
    help="Git ref; when set, show symbol-level diff (added/removed/modified) vs this ref",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON (only with --since)")
def diff(repo_path: str, db: str, since: str | None, as_json: bool) -> None:
    """Show files (or symbols with --since) that changed since a reference point.

    Without --since: compares current file hashes against the indexed DB.
    With --since <ref>: re-parses the old and new versions of each changed
    file and classifies symbols as added / removed / modified.
    """
    if since:
        import json as _json

        from codeatlas.git_integration import compute_symbol_diff

        result = compute_symbol_diff(Path(repo_path), since_ref=since)

        if as_json:
            console.print(_json.dumps(result, indent=2))
            return

        totals = {k: len(v) for k, v in result.items()}
        if not any(totals.values()):
            console.print(f"[dim]No symbol-level changes since {since}.[/dim]")
            return
        if result["added"]:
            console.print(f"[green]Added ({totals['added']}):[/green]")
            for s in result["added"]:
                console.print(f"  + {s['name']}  [dim]{s['kind']}  {s['file']}[/dim]")
        if result["removed"]:
            console.print(f"[red]Removed ({totals['removed']}):[/red]")
            for s in result["removed"]:
                console.print(f"  - {s['name']}  [dim]{s['kind']}  {s['file']}[/dim]")
        if result["modified"]:
            console.print(f"[yellow]Modified ({totals['modified']}):[/yellow]")
            for s in result["modified"]:
                console.print(
                    f"  ~ {s['name']}  [dim]{s['kind']}  {s['file']}"
                    f" (line {s['old_line']} -> {s['new_line']})[/dim]"
                )
        return

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


@cli.command()
def languages() -> None:
    """List all supported languages and their file extensions."""
    from codeatlas.parsers import ParserRegistry

    registry = ParserRegistry()
    # Build language → extensions mapping
    lang_exts: dict[str, list[str]] = {}
    for ext, parser in registry._parsers.items():
        lang = parser.language
        lang_exts.setdefault(lang, []).append(ext)

    table = Table(title="Supported Languages")
    table.add_column("Language", style="cyan")
    table.add_column("Extensions", style="green")
    for lang in sorted(lang_exts):
        exts = ", ".join(sorted(lang_exts[lang]))
        table.add_row(lang, exts)
    console.print(table)


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

        s_any: dict[str, Any] = dict(s)
        s_any["languages"] = lang_breakdown
        s_any["kinds"] = kind_breakdown
        console.print(json.dumps(s_any, indent=2))
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
    help="Filter by symbol kind — comma-separated for multiple (e.g. 'class,interface')",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def query(
    query: str, db: str, limit: int, semantic: bool, hybrid: bool, kind: str | None, as_json: bool
) -> None:
    """Search for symbols by name or docstring."""
    import json as json_mod

    store = _get_store(Path(db))

    # Parse comma-separated kinds
    kind_filter: str | list[str] | None = None
    if kind:
        parts = [k.strip() for k in kind.split(",") if k.strip()]
        kind_filter = parts[0] if len(parts) == 1 else parts

    if semantic or hybrid:
        try:
            from codeatlas.search.embeddings import SemanticIndex
        except ImportError:
            store.close()
            console.print(
                "[red]Semantic search requires extra dependencies.[/red]\n"
                "Install with: [cyan]pip install codeatlas[search][/cyan]"
            )
            return

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
        # Post-filter semantic/hybrid results by kind (no SQL path available)
        if kind_filter:
            kinds_set = {kind_filter} if isinstance(kind_filter, str) else set(kind_filter)
            results = [s for s in results if s.kind.value in kinds_set]
    else:
        results = store.search(query, limit=limit, kind_filter=kind_filter)

    store.close()

    if as_json:
        console.print(
            json_mod.dumps(
                [
                    {
                        "name": s.qualified_name,
                        "kind": s.kind.value,
                        "file": s.file_path,
                        "line": s.span.start.line + 1,
                        "signature": s.signature,
                        "docstring": s.docstring,
                    }
                    for s in results
                ],
                indent=2,
            )
        )
        return

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
    "--format",
    "fmt",
    type=click.Choice(["dot", "json", "mermaid", "graphml", "csv", "cypher"]),
    default="dot",
    show_default=True,
)
@click.option(
    "--file-filter", default=None, help="Only export symbols from files matching this prefix"
)
@click.option("--include-externals", is_flag=True, help="Include unresolved/external references")
@click.option(
    "--communities",
    "include_communities",
    is_flag=True,
    help="Include community_id on each node (and color by community in DOT)",
)
@click.option(
    "-o", "--output", default=None, type=click.Path(), help="Output file (default: stdout)"
)
def export(
    db: str,
    fmt: str,
    file_filter: str | None,
    include_externals: bool,
    include_communities: bool,
    output: str | None,
) -> None:
    """Export the knowledge graph to DOT, JSON, Mermaid, GraphML, CSV, or Cypher format."""
    store = _get_store(Path(db))
    opts = ExportOptions(
        include_externals=include_externals,
        file_filter=file_filter,
        include_communities=include_communities,
    )

    if fmt == "dot":
        result = export_dot(store, opts)
    elif fmt == "mermaid":
        result = export_mermaid(store, opts)
    elif fmt == "graphml":
        result = export_graphml(store, opts)
    elif fmt == "csv":
        result = export_csv(store, opts)
    elif fmt == "cypher":
        result = export_cypher(store, opts)
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
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def show(symbol_name: str, db: str, depth: int, as_json: bool) -> None:
    """Inspect a symbol: signature, docstring, dependencies, and dependents."""
    import json as json_mod

    store = _get_store(Path(db))
    matches = store.find_symbols_by_name(symbol_name)

    if not matches:
        console.print(f"[yellow]No symbol found matching '{symbol_name}'[/yellow]")
        store.close()
        return

    if as_json:
        output = []
        for sym in matches:
            deps = store.get_dependencies(sym.id)
            dependents = store.get_dependents(sym.id)
            output.append(
                {
                    "id": sym.id,
                    "name": sym.qualified_name,
                    "kind": sym.kind.value,
                    "file": sym.file_path,
                    "line": sym.span.start.line + 1,
                    "signature": sym.signature,
                    "docstring": sym.docstring,
                    "decorators": sym.decorators,
                    "is_test": sym.is_test,
                    "dependencies": [{"target": r.target_id, "kind": r.kind.value} for r in deps],
                    "dependents": [
                        {"source": r.source_id, "kind": r.kind.value} for r in dependents
                    ],
                }
            )
        store.close()
        console.print(json_mod.dumps(output, indent=2))
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
        if sym.is_test:
            console.print("  [dim](test file)[/dim]")

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
@click.option("--include-tests", is_flag=True, help="Include test symbols in dead code analysis")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def audit(
    db: str,
    show_cycles: bool,
    show_unused: bool,
    show_centrality: bool,
    limit: int,
    include_tests: bool,
    as_json: bool,
) -> None:
    """Run code quality analysis: cycles, dead code, and complexity."""
    import json as json_mod

    store = _get_store(Path(db))

    # If no specific flag, show all
    show_all = not (show_cycles or show_unused or show_centrality)

    cycles = store.detect_cycles() if (show_all or show_cycles) else []
    unused = (
        store.find_unused_symbols(include_tests=include_tests) if (show_all or show_unused) else []
    )
    centrality = store.get_symbol_centrality(limit=limit) if (show_all or show_centrality) else []

    store.close()

    if as_json:
        console.print(
            json_mod.dumps(
                {
                    "cycles": cycles,
                    "unused": [
                        {
                            "name": s.qualified_name,
                            "kind": s.kind.value,
                            "file": s.file_path,
                            "line": s.span.start.line + 1,
                            "is_test": s.is_test,
                        }
                        for s in unused
                    ],
                    "centrality": [dict(e) for e in centrality],
                },
                indent=2,
            )
        )
        return

    if show_all or show_cycles:
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
@click.argument("symbol_name")
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option("--depth", default=5, show_default=True, help="Max call depth to traverse")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def trace(symbol_name: str, db: str, depth: int, as_json: bool) -> None:
    """Trace the call chain from a symbol up to --depth levels deep.

    Shows every function that SYMBOL_NAME calls, and what those call, recursively.
    """
    import json as json_mod

    store = _get_store(Path(db))
    matches = store.find_symbols_by_name(symbol_name)
    if not matches:
        console.print(f"[yellow]Symbol '{symbol_name}' not found.[/yellow]")
        store.close()
        return

    sym = matches[0]
    chain = store.trace_call_chain(sym.id, max_depth=depth)
    store.close()

    if as_json:
        console.print(
            json_mod.dumps(
                {
                    "symbol": symbol_name,
                    "symbol_id": sym.id,
                    "depth": depth,
                    "edges": chain,
                },
                indent=2,
            )
        )
        return

    if not chain:
        console.print(f"[dim]No outgoing calls found for '{symbol_name}'.[/dim]")
        return

    table = Table(title=f"Call chain from '{symbol_name}' (depth ≤ {depth})")
    table.add_column("Depth", justify="right", style="dim")
    table.add_column("Caller", style="cyan")
    table.add_column("Callee", style="green")
    for edge in chain:
        table.add_row(
            str(edge["depth"]),
            str(edge["source_id"]).split("::")[-1],
            str(edge["target_id"]).split("::")[-1],
        )
    console.print(table)


@cli.command(name="find-usages")
@click.argument("symbol_name")
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option("--limit", default=50, show_default=True, help="Max usages to show")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def find_usages(symbol_name: str, db: str, limit: int, as_json: bool) -> None:
    """Find every call site, import, and reference to SYMBOL_NAME.

    Shows which files and callers depend on this symbol — useful before
    refactoring to understand the blast radius of a change.
    """
    import json as json_mod

    store = _get_store(Path(db))
    matches = store.find_symbols_by_name(symbol_name)
    if not matches:
        console.print(f"[yellow]Symbol '{symbol_name}' not found.[/yellow]")
        store.close()
        return

    sym = matches[0]
    dependents = store.get_dependents(sym.id)[:limit]
    store.close()

    if as_json:
        by_file: dict[str, list[dict[str, Any]]] = {}
        for rel in dependents:
            by_file.setdefault(rel.file_path, []).append(
                {
                    "caller_id": rel.source_id,
                    "kind": rel.kind.value,
                    "line": rel.span.start.line + 1 if rel.span else None,
                }
            )
        console.print(
            json_mod.dumps(
                {
                    "symbol": sym.qualified_name,
                    "usage_count": len(dependents),
                    "usages": [
                        {"file": fp, "references": refs} for fp, refs in sorted(by_file.items())
                    ],
                },
                indent=2,
            )
        )
        return

    if not dependents:
        console.print(f"[dim]No usages found for '{symbol_name}'.[/dim]")
        return

    table = Table(title=f"Usages of '{sym.qualified_name}' ({len(dependents)} reference(s))")
    table.add_column("Caller", style="cyan")
    table.add_column("Kind", style="magenta")
    table.add_column("File")
    table.add_column("Line", justify="right")
    for rel in dependents:
        table.add_row(
            rel.source_id.split("::")[-1],
            rel.kind.value,
            rel.file_path,
            str(rel.span.start.line + 1) if rel.span else "—",
        )
    console.print(table)


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
            ", ".join(str(k) for k in pair["kinds"]),
        )
    console.print(table)


@cli.command()
@click.argument("repo_path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option("--limit", default=20, show_default=True, help="Max hotspot files to show")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def hotspots(repo_path: str, db: str, limit: int, as_json: bool) -> None:
    """Show hotspot files: most git-churned AND most depended-upon code.

    Hotspot score = commit_count × (1 + in_degree). Files that both change
    frequently and have many dependents are highest risk.
    """
    import json as _json

    from codeatlas.git_integration import get_git_churn

    store = _get_store(Path(db))
    results = store.get_hotspots(repo_path=repo_path, limit=limit)
    store.close()

    if as_json:
        console.print(_json.dumps({"count": len(results), "hotspots": results}, indent=2))
        return

    if not results:
        churn = get_git_churn(Path(repo_path), limit=5)
        if not churn:
            console.print("[dim]No git history found in this repository.[/dim]")
        else:
            console.print("[dim]No indexed files matched git history.[/dim]")
        return

    table = Table(title=f"Hotspot Files (top {len(results)})")
    table.add_column("File", style="cyan", no_wrap=False)
    table.add_column("Commits", justify="right", style="yellow")
    table.add_column("In-Degree", justify="right", style="magenta")
    table.add_column("Symbols", justify="right")
    table.add_column("Score", justify="right", style="bold red")
    for r in results:
        table.add_row(
            str(r["file"]),
            str(r["commits"]),
            str(r["in_degree"]),
            str(r["symbol_count"]),
            str(r["hotspot_score"]),
        )
    console.print(table)


@cli.command()
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option("--limit", default=20, show_default=True, help="Max hub symbols to show")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def hubs(db: str, limit: int, as_json: bool) -> None:
    """Show hub symbols: the most-connected ("god") nodes in the graph.

    Ranks by total degree (incoming + outgoing relationships). A high-degree
    symbol is load-bearing — changes to it have wide blast radius.
    """
    import json as _json

    store = _get_store(Path(db))
    results = store.get_hub_symbols(limit=limit)
    store.close()

    if as_json:
        console.print(_json.dumps({"count": len(results), "hubs": results}, indent=2))
        return

    if not results:
        console.print("[dim]No symbols with relationships found.[/dim]")
        return

    table = Table(title=f"Hub Symbols (top {len(results)})")
    table.add_column("Symbol", style="cyan", no_wrap=False)
    table.add_column("Kind", style="magenta")
    table.add_column("File", style="dim")
    table.add_column("In", justify="right", style="green")
    table.add_column("Out", justify="right", style="yellow")
    table.add_column("Total", justify="right", style="bold red")
    for r in results:
        table.add_row(
            r["qualified_name"],
            r["kind"],
            r["file"],
            str(r["in_degree"]),
            str(r["out_degree"]),
            str(r["total_degree"]),
        )
    console.print(table)


@cli.command()
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option("--limit", default=20, show_default=True, help="Max symbols to show")
@click.option(
    "--kind",
    default=None,
    help="Filter to one symbol kind (class, function, method, ...)",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def rank(db: str, limit: int, kind: str | None, as_json: bool) -> None:
    """Rank symbols by PageRank importance.

    Unlike ``hubs`` (raw degree), PageRank weights a symbol by the importance
    of the symbols that point at it. Use this to surface quiet but critical
    code (small APIs that underpin the whole graph).
    """
    import json as _json

    store = _get_store(Path(db))
    results = store.get_pagerank_ranking(limit=limit, kind_filter=kind)
    store.close()

    if as_json:
        console.print(_json.dumps({"count": len(results), "ranking": results}, indent=2))
        return

    if not results:
        console.print("[dim]No symbols with relationships found.[/dim]")
        return

    table = Table(title=f"PageRank (top {len(results)})")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Symbol", style="cyan", no_wrap=False)
    table.add_column("Kind", style="magenta")
    table.add_column("File", style="dim")
    table.add_column("Score", justify="right", style="bold green")
    for i, r in enumerate(results, start=1):
        table.add_row(str(i), r["qualified_name"], r["kind"], r["file"], f"{r['score']:.4f}")
    console.print(table)


@cli.command()
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option("--min-size", default=3, show_default=True, help="Minimum community size to report")
@click.option("--limit", default=20, show_default=True, help="Max communities to show")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def communities(db: str, min_size: int, limit: int, as_json: bool) -> None:
    """Detect communities (tightly-connected subsystems) via label propagation.

    Each community groups symbols that form a cohesive module — useful for
    agents asking "what's related to X?" or for orienting in an unfamiliar repo.
    """
    import json as _json

    store = _get_store(Path(db))
    results = store.get_community_summary(min_size=min_size)[:limit]
    store.close()

    if as_json:
        console.print(_json.dumps({"count": len(results), "communities": results}, indent=2))
        return

    if not results:
        console.print("[dim]No communities found (try lowering --min-size).[/dim]")
        return

    table = Table(title=f"Communities (top {len(results)})")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Size", justify="right", style="bold green")
    table.add_column("Sample members", style="cyan")
    for i, c in enumerate(results, 1):
        sample = ", ".join(f"{m['name']}" for m in c["sample"])
        table.add_row(str(i), str(c["size"]), sample)
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
@click.option(
    "--communities",
    "include_communities",
    is_flag=True,
    help="Color nodes by community (label-propagation)",
)
def viz(
    db: str,
    file_filter: str | None,
    output: str | None,
    open_browser: bool,
    include_communities: bool,
) -> None:
    """Generate an interactive D3.js graph visualization."""
    from codeatlas.viz import generate_viz

    store = _get_store(Path(db))
    html = generate_viz(store, file_filter=file_filter, include_communities=include_communities)
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
    from typing import Literal, cast

    mcp.run(transport=cast(Literal["stdio", "sse", "streamable-http"], transport))


@cli.command(name="coverage-gaps")
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option(
    "--file-filter", default=None, help="Only show symbols from files matching this prefix"
)
@click.option("--limit", default=100, show_default=True)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def coverage_gaps(db: str, file_filter: str | None, limit: int, as_json: bool) -> None:
    """Show public symbols that have no test coverage.

    Lists symbols that are part of the public API but are never called
    or imported by any test file. Prioritise these for new test cases.
    """
    import json as _json

    store = _get_store(Path(db))
    gaps = store.get_coverage_gaps(file_filter=file_filter, limit=limit)
    store.close()

    if as_json:
        by_file: dict[str, list[dict[str, Any]]] = {}
        for s in gaps:
            by_file.setdefault(s.file_path, []).append(
                {"name": s.name, "kind": s.kind.value, "line": s.span.start.line + 1}
            )
        console.print(
            _json.dumps(
                {
                    "total_uncovered": len(gaps),
                    "files": [
                        {"file": fp, "symbols": syms} for fp, syms in sorted(by_file.items())
                    ],
                },
                indent=2,
            )
        )
        return

    if not gaps:
        console.print("[green]All public symbols have test coverage.[/green]")
        return

    table = Table(title=f"Coverage Gaps — {len(gaps)} uncovered symbol(s)")
    table.add_column("Symbol", style="cyan")
    table.add_column("Kind", style="magenta")
    table.add_column("File")
    table.add_column("Line", justify="right")
    for s in gaps:
        table.add_row(
            s.qualified_name,
            s.kind.value,
            s.file_path,
            str(s.span.start.line + 1),
        )
    console.print(table)


@cli.command()
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.argument("repo_path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--json", "as_json", is_flag=True, help="Output as JSON instead of Markdown")
@click.option("-o", "--output", default=None, type=click.Path(), help="Write report to file")
def report(db: str, repo_path: str, as_json: bool, output: str | None) -> None:
    """Generate a health report: cycles, dead code, hotspots, and coverage gaps.

    Combines all graph analysis results into a single Markdown or JSON summary
    suitable for dropping into a PR description or CI artifact.
    """
    import json as _json

    store = _get_store(Path(db))

    # Gather data
    stats = store.get_stats()
    cycles = store.detect_cycles()
    dead = store.find_unused_symbols(include_tests=False)
    hotspots = store.get_hotspots(repo_path=repo_path, limit=10)
    gaps = store.get_coverage_gaps(limit=50)
    hubs = store.get_hub_symbols(limit=10)
    confidence = store.get_confidence_stats()
    store.close()

    if as_json:
        data = {
            "stats": stats,
            "cycles": len(cycles),
            "dead_code": [{"name": s.qualified_name, "file": s.file_path} for s in dead[:20]],
            "hotspots": hotspots[:10],
            "hub_symbols": hubs[:10],
            "relationship_confidence": confidence,
            "coverage_gaps": [
                {"name": s.qualified_name, "kind": s.kind.value, "file": s.file_path}
                for s in gaps[:20]
            ],
        }
        result = _json.dumps(data, indent=2)
    else:
        lines = [
            "# CodeAtlas Health Report",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Files indexed | {stats.get('total_files', 0)} |",
            f"| Symbols | {stats.get('total_symbols', 0)} |",
            f"| Relationships | {stats.get('total_relationships', 0)} |",
            f"| Dependency cycles | {len(cycles)} |",
            f"| Dead code symbols | {len(dead)} |",
            f"| Uncovered public symbols | {len(gaps)} |",
            f"| Extracted relationships | {confidence['extracted']} |",
            f"| Inferred relationships | {confidence['inferred']} |",
            f"| Ambiguous relationships | {confidence['ambiguous']} |",
            "",
        ]

        if cycles:
            lines += ["## Dependency Cycles", ""]
            for i, cycle in enumerate(cycles[:5], 1):
                lines.append(f"{i}. `{'` → `'.join(str(n) for n in cycle)}`")
            if len(cycles) > 5:
                lines.append(f"…and {len(cycles) - 5} more.")
            lines.append("")

        if dead:
            lines += ["## Dead Code (top 15)", ""]
            lines.append("| Symbol | Kind | File |")
            lines.append("|--------|------|------|")
            for s in dead[:15]:
                lines.append(f"| `{s.qualified_name}` | {s.kind.value} | `{s.file_path}` |")
            lines.append("")

        if hotspots:
            lines += ["## Hotspot Files (highest risk)", ""]
            lines.append("| File | Commits | In-Degree | Score |")
            lines.append("|------|---------|-----------|-------|")
            for h in hotspots[:10]:
                lines.append(
                    f"| `{h['file']}` | {h['commits']} | {h['in_degree']} | {h['hotspot_score']} |"
                )
            lines.append("")

        if hubs:
            lines += ["## Hub Symbols (most-connected)", ""]
            lines.append("| Symbol | Kind | File | In | Out | Total |")
            lines.append("|--------|------|------|----|----|-------|")
            for h in hubs[:10]:
                lines.append(
                    f"| `{h['qualified_name']}` | {h['kind']} | `{h['file']}` | "
                    f"{h['in_degree']} | {h['out_degree']} | {h['total_degree']} |"
                )
            lines.append("")

        if gaps:
            lines += ["## Coverage Gaps (top 20)", ""]
            lines.append("| Symbol | Kind | File | Line |")
            lines.append("|--------|------|------|------|")
            for s in gaps[:20]:
                lines.append(
                    f"| `{s.qualified_name}` | {s.kind.value} | `{s.file_path}` | {s.span.start.line + 1} |"
                )
            lines.append("")

        if not cycles and not dead and not gaps:
            lines += ["## ", "> All checks passed — no issues detected.", ""]

        result = "\n".join(lines)

    if output:
        Path(output).write_text(result)
        console.print(f"[green]Report written to {output}[/green]")
    else:
        console.print(result)


@cli.command(name="pre-commit")
@click.option(
    "--hook-type",
    type=click.Choice(["pre-commit", "post-commit"]),
    default="post-commit",
    show_default=True,
    help="Which git hook stage to run on",
)
def pre_commit(hook_type: str) -> None:
    """Add a CodeAtlas incremental-index hook to .pre-commit-config.yaml.

    Appends a hook that keeps the knowledge graph up to date on every commit
    without blocking the commit (runs as post-commit by default).
    """
    config_path = Path(".pre-commit-config.yaml")
    hook_block = f"""
# CodeAtlas: keep knowledge graph in sync
- repo: local
  hooks:
    - id: codeatlas-index
      name: CodeAtlas incremental index
      language: system
      entry: codeatlas index --incremental
      stages: [{hook_type}]
      pass_filenames: false
"""
    if config_path.exists():
        existing = config_path.read_text()
        if "codeatlas-index" in existing:
            console.print(
                "[yellow]codeatlas-index hook already present in .pre-commit-config.yaml[/yellow]"
            )
            return
        config_path.write_text(existing + hook_block)
        console.print("[green]Appended codeatlas-index hook to .pre-commit-config.yaml[/green]")
    else:
        config_path.write_text(f"repos:{hook_block}")
        console.print("[green]Created .pre-commit-config.yaml with codeatlas-index hook[/green]")
    console.print("Run [cyan]pre-commit install[/cyan] to activate.")
