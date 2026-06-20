"""Click CLI for CodeAtlas."""

import contextlib
import io
import json as _json
import platform
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
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
@click.option(
    "--workers",
    default=1,
    show_default=True,
    type=int,
    help="Parse files in parallel processes (1 = serial)",
)
@click.option("--json", "as_json", is_flag=True, help="Emit results as JSON only")
@click.option("-o", "--output", default=None, type=click.Path(), help="Write benchmark artifact")
@click.option("--profile", is_flag=True, help="Include runtime/platform metadata")
@click.option("--build-semantic", is_flag=True, help="Build/load semantic index for eval modes")
@click.option(
    "--require-semantic",
    is_flag=True,
    help="Fail if semantic/hybrid modes cannot use a real semantic index",
)
@click.option(
    "--eval-suite",
    default=None,
    type=click.Path(exists=True, dir_okay=False),
    help="Run a retrieval eval suite against the temporary benchmark DB",
)
def bench(
    repo_path: str,
    workers: int,
    as_json: bool,
    output: str | None,
    profile: bool,
    build_semantic: bool,
    require_semantic: bool,
    eval_suite: str | None,
) -> None:
    """Benchmark indexing throughput on this repo.

    Uses a throwaway temp database so the primary .codeatlas/graph.db is
    untouched. Reports wall-clock time plus files/sec, symbols/sec, and
    LOC/sec — useful for profiling parser changes or quoting numbers in
    a launch post.
    """
    payload = _benchmark_repo(
        repo_path,
        workers=workers,
        quiet=as_json,
        profile=profile,
        eval_suite=eval_suite,
        build_semantic=build_semantic,
        require_semantic=require_semantic,
    )

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if as_json or out_path.suffix.lower() == ".json":
            out_path.write_text(_json.dumps(payload, indent=2) + "\n")
        else:
            out_path.write_text(_render_bench_markdown(payload) + "\n")
        console.print(f"[green]Benchmark written to {out_path}[/green]")
        return

    if as_json:
        click.echo(_json.dumps(payload, indent=2))
        return

    table = Table(title="CodeAtlas bench", show_header=False, title_style="bold cyan")
    table.add_column("metric", style="dim")
    table.add_column("value", justify="right")
    table.add_row("Repo", str(payload["repo"]))
    table.add_row("Workers", str(workers))
    table.add_row("Files", f"{payload['files']:,}")
    table.add_row("Symbols", f"{payload['symbols']:,}")
    table.add_row("Relationships", f"{payload['relationships']:,}")
    table.add_row("LOC", f"{payload['loc']:,}")
    table.add_row("Elapsed", f"{payload['elapsed_seconds']:.2f}s")
    table.add_row("Files/sec", f"{payload['files_per_sec']:,.1f}")
    table.add_row("Symbols/sec", f"{payload['symbols_per_sec']:,.1f}")
    table.add_row("LOC/sec", f"{payload['loc_per_sec']:,.0f}")
    console.print(table)


def _benchmark_repo(
    repo_path: str,
    *,
    workers: int = 1,
    quiet: bool = False,
    profile: bool = False,
    eval_suite: str | None = None,
    build_semantic: bool = False,
    require_semantic: bool = False,
    repo_filter: str | None = None,
) -> dict[str, Any]:
    root = Path(repo_path)
    config = CodeAtlasConfig.find_and_load(root)
    semantic_meta: dict[str, Any] | None = None
    with tempfile.TemporaryDirectory(prefix="codeatlas-bench-") as tmp:
        db_path = Path(tmp) / "bench.db"
        config.graph.db_path = db_path
        store = _get_store(db_path)
        try:
            indexer = RepoIndexer(config, store, workers=workers)
            files = indexer._discover_files()
            loc = _count_loc(files)
            start = time.monotonic()
            if quiet:
                with (
                    contextlib.redirect_stdout(io.StringIO()),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    indexer.index_full(resolve=False)
            else:
                indexer.index_full(resolve=False)
            elapsed = time.monotonic() - start
            stats = store.get_stats()
            eval_report = None
            if eval_suite:
                from codeatlas.eval import run_eval_comparison

                semantic_index, semantic_meta = _semantic_index_for_eval(
                    db_path,
                    store,
                    build_semantic=build_semantic,
                    require_semantic=require_semantic,
                )
                eval_report = run_eval_comparison(
                    store,
                    eval_suite,
                    budget_tokens=2000,
                    semantic_index=semantic_index,
                    repo_filter=repo_filter,
                )
        finally:
            store.close()

    files_n = stats["files"]
    symbols_n = stats["symbols"]
    relationships_n = stats["relationships"]
    payload: dict[str, Any] = {
        "repo": repo_path,
        "workers": workers,
        "files": files_n,
        "symbols": symbols_n,
        "relationships": relationships_n,
        "loc": loc,
        "elapsed_seconds": round(elapsed, 3),
        "files_per_sec": round(files_n / elapsed, 1) if elapsed > 0 else 0.0,
        "symbols_per_sec": round(symbols_n / elapsed, 1) if elapsed > 0 else 0.0,
        "loc_per_sec": round(loc / elapsed, 1) if elapsed > 0 else 0.0,
    }
    if profile:
        payload["profile"] = _profile_payload()
    if semantic_meta:
        payload["semantic"] = semantic_meta
    if eval_report:
        payload["eval"] = eval_report
    return payload


def _profile_payload() -> dict[str, str]:
    return {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
    }


def _render_bench_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# CodeAtlas Benchmark",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Repo | `{payload['repo']}` |",
        f"| Workers | {payload['workers']} |",
        f"| Files | {payload['files']:,} |",
        f"| Symbols | {payload['symbols']:,} |",
        f"| Relationships | {payload['relationships']:,} |",
        f"| LOC | {payload['loc']:,} |",
        f"| Elapsed | {payload['elapsed_seconds']:.3f}s |",
        f"| Files/sec | {payload['files_per_sec']:,.1f} |",
        f"| Symbols/sec | {payload['symbols_per_sec']:,.1f} |",
        f"| LOC/sec | {payload['loc_per_sec']:,.0f} |",
    ]
    if "profile" in payload:
        profile = payload["profile"]
        lines.extend(
            [
                "",
                "## Environment",
                "",
                "| Field | Value |",
                "|-------|-------|",
                f"| Timestamp UTC | `{profile['timestamp_utc']}` |",
                f"| Python | `{profile['python']}` |",
                f"| Platform | `{profile['platform']}` |",
                f"| Machine | `{profile['machine']}` |",
            ]
        )
    if "eval" in payload:
        lines.extend(
            [
                "",
                "## Retrieval Eval",
                "",
                "| Mode | Effective | Symbol recall@k | File recall@k | MRR | Avg latency | Context savings | Misses |",
                "|------|-----------|-----------------|---------------|-----|-------------|-----------------|--------|",
            ]
        )
        for row in payload["eval"]["comparison"]:
            lines.append(
                f"| `{row['mode']}` | `{row['mode_effective']}` | "
                f"{row['symbol_recall_at_k']:.3f} | {row['file_recall_at_k']:.3f} | "
                f"{row['mrr']:.3f} | {row['avg_latency_ms']:.2f} ms | "
                f"{row['avg_context_savings']:.2%} | {row['miss_count']} |"
            )
    return "\n".join(lines)


def _load_existing_semantic_index(db: str) -> Any | None:
    """Load an already-built semantic index without downloading models in CI."""
    try:
        from codeatlas.search.embeddings import SemanticIndex
    except ImportError:
        return None

    sem_index = SemanticIndex()
    if sem_index.load(Path(db).parent):
        return sem_index
    return None


def _semantic_index_for_eval(
    db_path: Path,
    store: GraphStore,
    *,
    build_semantic: bool,
    require_semantic: bool,
) -> tuple[Any | None, dict[str, Any]]:
    try:
        from codeatlas.search.embeddings import DEFAULT_MODEL, SemanticIndex
    except ImportError as exc:
        if require_semantic:
            raise click.ClickException(
                "Semantic eval required but search dependencies are not installed. "
                "Install with: pip install codeatlas[search]"
            ) from exc
        return None, {
            "enabled": False,
            "required": require_semantic,
            "model": None,
            "reason": "search dependencies not installed",
        }

    data_dir = db_path.parent
    sem_index = SemanticIndex()
    if sem_index.load(data_dir):
        return sem_index, {
            "enabled": True,
            "required": require_semantic,
            "model": DEFAULT_MODEL,
            "built": False,
            "symbols": sem_index.size,
        }
    if not build_semantic:
        if require_semantic:
            raise click.ClickException("Semantic eval required but no semantic index exists.")
        return None, {
            "enabled": False,
            "required": require_semantic,
            "model": DEFAULT_MODEL,
            "reason": "semantic index not built; pass --build-semantic",
        }

    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        count = sem_index.build_from_store(store)
        sem_index.save(data_dir)
    except Exception as exc:
        if require_semantic:
            raise click.ClickException(f"Failed to build semantic index: {exc}") from exc
        return None, {
            "enabled": False,
            "required": require_semantic,
            "model": DEFAULT_MODEL,
            "reason": f"semantic index build failed: {exc}",
        }
    return sem_index, {
        "enabled": True,
        "required": require_semantic,
        "model": DEFAULT_MODEL,
        "built": True,
        "symbols": count,
    }


@cli.command("bench-suite")
@click.option("--repos", "repos_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--suite", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--out", required=True, type=click.Path(file_okay=False))
@click.option(
    "--cache-dir",
    default=".codeatlas/bench-repos",
    show_default=True,
    type=click.Path(file_okay=False),
    help="Where remote benchmark repos are cloned/reused",
)
@click.option("--workers", default=1, show_default=True, type=int)
@click.option("--build-semantic", is_flag=True, help="Build/load semantic index for semantic modes")
@click.option(
    "--require-semantic",
    is_flag=True,
    help="Fail if semantic/hybrid modes cannot use a real semantic index",
)
def bench_suite(
    repos_path: str,
    suite: str,
    out: str,
    cache_dir: str,
    workers: int,
    build_semantic: bool,
    require_semantic: bool,
) -> None:
    """Run benchmark/eval comparisons across pinned repositories."""
    specs = _load_bench_repos(Path(repos_path))
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_root = Path(cache_dir)
    cache_root.mkdir(parents=True, exist_ok=True)

    repo_reports: list[dict[str, Any]] = []
    all_misses: list[dict[str, Any]] = []
    for spec in specs:
        name = str(spec["name"])
        repo_path = _materialize_bench_repo(spec, cache_root)
        payload = _benchmark_repo(
            str(repo_path),
            workers=workers,
            quiet=True,
            profile=True,
            eval_suite=suite,
            build_semantic=build_semantic,
            require_semantic=require_semantic,
            repo_filter=name,
        )
        payload["repo_name"] = name
        payload["repo_url"] = spec.get("url", "local")
        payload["repo_commit"] = spec.get("commit", spec.get("ref", "unknown"))
        repo_reports.append(payload)
        if "eval" in payload:
            for mode, mode_report in payload["eval"]["modes"].items():
                for miss in mode_report.get("misses", []):
                    all_misses.append({"mode": mode, **miss})

    suite_payload = {
        "repos_file": repos_path,
        "suite": suite,
        "profile": _profile_payload(),
        "aggregate": _aggregate_bench_suite(repo_reports),
        "repos": repo_reports,
    }
    (out_dir / "results.json").write_text(_json.dumps(suite_payload, indent=2) + "\n")
    (out_dir / "misses.json").write_text(_json.dumps(all_misses, indent=2) + "\n")
    (out_dir / "report.md").write_text(_render_bench_suite_markdown(suite_payload) + "\n")
    console.print(f"[green]Benchmark suite written to {out_dir}[/green]")


def _load_bench_repos(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text()
    try:
        data = _json.loads(raw)
    except _json.JSONDecodeError as exc:
        raise click.ClickException(
            f"{path} must be JSON-compatible YAML in this build; failed to parse: {exc}"
        ) from exc
    repos = data.get("repos", data) if isinstance(data, dict) else data
    if not isinstance(repos, list) or not repos:
        raise click.ClickException("repos file must contain a non-empty repos list")
    normalized: list[dict[str, Any]] = []
    for idx, repo in enumerate(repos, 1):
        if not isinstance(repo, dict):
            raise click.ClickException(f"repo entry {idx} must be an object")
        name = str(repo.get("name", "")).strip()
        if not name:
            raise click.ClickException(f"repo entry {idx} is missing name")
        if not repo.get("path") and not repo.get("url"):
            raise click.ClickException(f"repo entry {name} must include path or url")
        normalized.append(repo)
    return normalized


def _materialize_bench_repo(spec: dict[str, Any], cache_root: Path) -> Path:
    if spec.get("path"):
        path = Path(str(spec["path"]))
        if not path.exists():
            raise click.ClickException(f"local benchmark repo does not exist: {path}")
        return path

    name = str(spec["name"])
    url = str(spec["url"])
    commit = str(spec.get("commit", spec.get("ref", "HEAD")))
    repo_dir = cache_root / name
    if not repo_dir.exists():
        subprocess.run(["git", "clone", url, str(repo_dir)], check=True)
    else:
        subprocess.run(["git", "-C", str(repo_dir), "fetch", "origin", commit], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "checkout", "--detach", commit], check=True)
    return repo_dir


def _aggregate_bench_suite(reports: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, Any] = {
        "repos": len(reports),
        "files": sum(int(r["files"]) for r in reports),
        "symbols": sum(int(r["symbols"]) for r in reports),
        "relationships": sum(int(r["relationships"]) for r in reports),
        "loc": sum(int(r["loc"]) for r in reports),
        "elapsed_seconds": round(sum(float(r["elapsed_seconds"]) for r in reports), 3),
    }
    mode_rows: dict[str, dict[str, float]] = {}
    mode_counts: dict[str, int] = {}
    for report in reports:
        for row in report.get("eval", {}).get("comparison", []):
            mode = str(row["mode"])
            bucket = mode_rows.setdefault(
                mode,
                {
                    "symbol_recall_at_k": 0.0,
                    "file_recall_at_k": 0.0,
                    "mrr": 0.0,
                    "avg_latency_ms": 0.0,
                    "avg_context_savings": 0.0,
                    "miss_count": 0.0,
                },
            )
            mode_counts[mode] = mode_counts.get(mode, 0) + 1
            for key in bucket:
                bucket[key] += float(row[key])
    comparison = []
    for mode, bucket in mode_rows.items():
        count = max(1, mode_counts[mode])
        comparison.append(
            {
                "mode": mode,
                "symbol_recall_at_k": round(bucket["symbol_recall_at_k"] / count, 6),
                "file_recall_at_k": round(bucket["file_recall_at_k"] / count, 6),
                "mrr": round(bucket["mrr"] / count, 6),
                "avg_latency_ms": round(bucket["avg_latency_ms"] / count, 3),
                "avg_context_savings": round(bucket["avg_context_savings"] / count, 4),
                "miss_count": int(bucket["miss_count"]),
            }
        )
    totals["comparison"] = comparison
    return totals


def _render_bench_suite_markdown(payload: dict[str, Any]) -> str:
    aggregate = payload["aggregate"]
    lines = [
        "# CodeAtlas OSS Benchmark Suite",
        "",
        "## Aggregate",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Repos | {aggregate['repos']} |",
        f"| Files | {aggregate['files']:,} |",
        f"| Symbols | {aggregate['symbols']:,} |",
        f"| Relationships | {aggregate['relationships']:,} |",
        f"| LOC | {aggregate['loc']:,} |",
        f"| Total indexing time | {aggregate['elapsed_seconds']:.3f}s |",
        "",
        "## Aggregate Retrieval Eval",
        "",
        "| Mode | Symbol recall@k | File recall@k | MRR | Avg latency | Context savings | Misses |",
        "|------|-----------------|---------------|-----|-------------|-----------------|--------|",
    ]
    for row in aggregate["comparison"]:
        lines.append(
            f"| `{row['mode']}` | {row['symbol_recall_at_k']:.3f} | "
            f"{row['file_recall_at_k']:.3f} | {row['mrr']:.3f} | "
            f"{row['avg_latency_ms']:.2f} ms | {row['avg_context_savings']:.2%} | "
            f"{row['miss_count']} |"
        )
    lines.extend(
        [
            "",
            "## Repositories",
            "",
            "| Repo | Commit | Files | Symbols | Relationships | Symbols/sec |",
            "|------|--------|-------|---------|---------------|-------------|",
        ]
    )
    for report in payload["repos"]:
        commit = str(report.get("repo_commit", "unknown"))
        lines.append(
            f"| `{report['repo_name']}` | `{commit[:12]}` | {report['files']:,} | "
            f"{report['symbols']:,} | {report['relationships']:,} | "
            f"{report['symbols_per_sec']:,.1f} |"
        )
    lines.append("")
    return "\n".join(lines)


@cli.command("perf-report")
@click.option("--repos", "repos_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--out", required=True, type=click.Path(file_okay=False))
@click.option("--profile", is_flag=True, help="Include runtime/platform metadata")
@click.option("--json", "as_json", is_flag=True, help="Print JSON payload after writing artifacts")
@click.option("--workers", default=1, show_default=True, type=int)
@click.option(
    "--cache-dir",
    default=".codeatlas/bench-repos",
    show_default=True,
    type=click.Path(file_okay=False),
)
def perf_report(
    repos_path: str,
    out: str,
    profile: bool,
    as_json: bool,
    workers: int,
    cache_dir: str,
) -> None:
    """Render a recruiter-facing scale/performance report for pinned repos."""
    repos = _load_bench_repos(Path(repos_path))
    output = Path(out)
    output.mkdir(parents=True, exist_ok=True)
    reports = []
    for spec in repos:
        repo_path = _materialize_bench_repo(spec, Path(cache_dir))
        report = _benchmark_repo(
            str(repo_path),
            workers=workers,
            quiet=True,
            profile=profile,
            repo_filter=str(spec["name"]),
        )
        report["repo_name"] = spec["name"]
        report["repo_commit"] = spec.get("commit", spec.get("ref", "unknown"))
        reports.append(report)
    payload = _render_perf_payload(repos_path, reports, profile=profile)
    (output / "results.json").write_text(_json.dumps(payload, indent=2) + "\n")
    (output / "report.md").write_text(_render_perf_markdown(payload) + "\n")
    if as_json:
        click.echo(_json.dumps(payload, indent=2))
    else:
        console.print(f"[green]Performance report written to {output}[/green]")


def _render_perf_payload(
    repos_path: str, reports: list[dict[str, Any]], *, profile: bool
) -> dict[str, Any]:
    total_elapsed = sum(float(report["elapsed_seconds"]) for report in reports)
    total_files = sum(int(report["files"]) for report in reports)
    total_symbols = sum(int(report["symbols"]) for report in reports)
    total_relationships = sum(int(report["relationships"]) for report in reports)
    total_loc = sum(int(report["loc"]) for report in reports)
    payload: dict[str, Any] = {
        "repos_file": repos_path,
        "repo_count": len(reports),
        "totals": {
            "files": total_files,
            "symbols": total_symbols,
            "relationships": total_relationships,
            "loc": total_loc,
            "elapsed_seconds": round(total_elapsed, 3),
            "files_per_sec": round(total_files / total_elapsed, 1) if total_elapsed else 0.0,
            "symbols_per_sec": round(total_symbols / total_elapsed, 1) if total_elapsed else 0.0,
            "relationships_per_sec": round(total_relationships / total_elapsed, 1)
            if total_elapsed
            else 0.0,
        },
        "repos": reports,
    }
    if profile:
        payload["profile"] = _profile_payload()
    return payload


def _render_perf_markdown(payload: dict[str, Any]) -> str:
    totals = payload["totals"]
    lines = [
        "# CodeAtlas Scale And Systems Report",
        "",
        "## Aggregate",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Repos | {payload['repo_count']} |",
        f"| Files | {totals['files']:,} |",
        f"| Symbols | {totals['symbols']:,} |",
        f"| Relationships | {totals['relationships']:,} |",
        f"| LOC | {totals['loc']:,} |",
        f"| Wall time | {totals['elapsed_seconds']:.3f}s |",
        f"| Files/sec | {totals['files_per_sec']:,.1f} |",
        f"| Symbols/sec | {totals['symbols_per_sec']:,.1f} |",
        f"| Relationships/sec | {totals['relationships_per_sec']:,.1f} |",
        "",
        "## Repositories",
        "",
        "| Repo | Commit | Files | Symbols | Relationships | LOC | Time | Symbols/sec |",
        "|------|--------|-------|---------|---------------|-----|------|-------------|",
    ]
    for report in payload["repos"]:
        lines.append(
            f"| `{report['repo_name']}` | `{str(report['repo_commit'])[:12]}` | "
            f"{report['files']:,} | {report['symbols']:,} | {report['relationships']:,} | "
            f"{report['loc']:,} | {report['elapsed_seconds']:.3f}s | "
            f"{report['symbols_per_sec']:,.1f} |"
        )
    lines.append("")
    return "\n".join(lines)


@cli.command("agent-eval")
@click.option("--suite", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--repos", "repos_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--out", required=True, type=click.Path(file_okay=False))
@click.option(
    "--context-mode",
    default="pagerank",
    show_default=True,
    type=click.Choice(["fts", "semantic", "hybrid", "pagerank"]),
    help="Retrieval mode used to build CodeAtlas context packs",
)
@click.option("--dry-run", is_flag=True, help="Validate and write planned artifacts only")
@click.option(
    "--agent-adapter",
    type=click.Choice(["shell", "codex", "claude", "aider", "mock"]),
    default="shell",
    show_default=True,
    help="Live-agent adapter. External adapters are only used when not in dry-run mode.",
)
@click.option(
    "--agent-command",
    default=None,
    help="Generic live-agent command. Receives CODEATLAS_* environment variables.",
)
@click.option(
    "--sandbox",
    type=click.Choice(["none", "docker"]),
    default="none",
    show_default=True,
    help="Safety label for live runs. Docker execution is reserved for manual live-agent runs.",
)
@click.option(
    "--compare-baseline",
    is_flag=True,
    help="Run both prompt-only baseline and CodeAtlas-context variants",
)
@click.option(
    "--cache-dir",
    default=".codeatlas/bench-repos",
    show_default=True,
    type=click.Path(file_okay=False),
    help="Where remote benchmark repos are cloned/reused for live runs",
)
@click.option("--json", "as_json", is_flag=True, help="Emit the resulting JSON payload")
def agent_eval_cmd(
    suite: str,
    repos_path: str,
    out: str,
    context_mode: str,
    dry_run: bool,
    agent_adapter: str,
    agent_command: str | None,
    sandbox: str,
    compare_baseline: bool,
    cache_dir: str,
    as_json: bool,
) -> None:
    """Run deterministic or live A/B agent outcome evaluation."""
    from codeatlas.agent_eval import run_agent_eval

    effective_dry_run = dry_run or (agent_adapter == "shell" and agent_command is None)
    try:
        payload = run_agent_eval(
            suite_path=suite,
            repos_path=repos_path,
            out_dir=out,
            context_mode=context_mode,  # type: ignore[arg-type]
            dry_run=effective_dry_run,
            agent_command=agent_command,
            agent_adapter=agent_adapter,  # type: ignore[arg-type]
            sandbox=sandbox,  # type: ignore[arg-type]
            compare_baseline=compare_baseline,
            cache_dir=cache_dir,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    if as_json:
        click.echo(_json.dumps(payload, indent=2))
        return
    mode = "dry-run" if effective_dry_run else "live"
    console.print(f"[green]Agent eval {mode} artifacts written to {out}[/green]")


def _count_loc(files: list[Path]) -> int:
    total = 0
    for path in files:
        try:
            with path.open("rb") as fh:
                total += sum(1 for _ in fh)
        except OSError:
            continue
    return total


@cli.command()
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option(
    "--check",
    default="all",
    show_default=True,
    help="Comma-separated checks: env,db,semantic,mcp,api,bench or all",
)
@click.option("--json", "as_json", is_flag=True, help="Emit results as JSON")
def doctor(db: str, check: str, as_json: bool) -> None:
    """Diagnose install health: Python, SQLite/FTS5, parsers, and optional deps."""
    checks = _run_doctor_checks(Path(db), check)
    if as_json:
        click.echo(
            _json.dumps(
                [{"name": c[0], "status": c[1], "detail": c[2]} for c in checks],
                indent=2,
            )
        )
        return

    table = Table(title="CodeAtlas doctor", title_style="bold cyan")
    table.add_column("check", style="bold")
    table.add_column("status", justify="center")
    table.add_column("detail", style="dim")
    for name, status, detail in checks:
        color = {"ok": "green", "warn": "yellow", "error": "red"}.get(status, "white")
        mark = {"ok": "✓", "warn": "!", "error": "✗"}.get(status, "?")
        table.add_row(name, f"[{color}]{mark} {status}[/{color}]", detail)
    console.print(table)

    if any(c[1] == "error" for c in checks):
        raise click.exceptions.Exit(1)


def _run_doctor_checks(db_path: Path, selected: str = "all") -> list[tuple[str, str, str]]:
    import sqlite3
    import sys

    results: list[tuple[str, str, str]] = []
    requested = {part.strip() for part in selected.split(",") if part.strip()}
    if not requested or "all" in requested:
        requested = {"env", "db", "semantic", "mcp", "api", "bench"}

    if "env" in requested:
        py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        py_status = "ok" if sys.version_info >= (3, 11) else "error"
        py_detail = py_version if py_status == "ok" else f"{py_version} (need >=3.11)"
        results.append(("Python", py_status, py_detail))

        sqlite_version = sqlite3.sqlite_version
        try:
            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
            conn.close()
            results.append(("SQLite + FTS5", "ok", sqlite_version))
        except sqlite3.OperationalError:
            results.append(("SQLite + FTS5", "error", f"{sqlite_version} (FTS5 not compiled in)"))

        try:
            from codeatlas.parsers import ParserRegistry

            reg = ParserRegistry()
            unique_parsers = {type(p).__name__ for p in reg._parsers.values()}
            extensions = len(reg._parsers)
            results.append(
                (
                    "Tree-sitter parsers",
                    "ok",
                    f"{len(unique_parsers)} languages, {extensions} file extensions",
                )
            )
        except Exception as exc:  # pragma: no cover - defensive
            results.append(("Tree-sitter parsers", "error", str(exc)))

    if "db" in requested:
        if db_path.exists():
            try:
                store = GraphStore(db_path)
                stats = store.get_stats()
                store.close()
                results.append(
                    (
                        "Graph DB",
                        "ok",
                        f"{stats['files']} files, {stats['symbols']} symbols, {stats['relationships']} relationships",
                    )
                )
            except Exception as exc:
                results.append(("Graph DB", "error", str(exc)))
        else:
            results.append(("Graph DB", "warn", f"{db_path} does not exist; run codeatlas index"))

    optional_modules = []
    if "semantic" in requested:
        optional_modules.extend(
            [
                ("faiss", "FAISS (semantic search)"),
                ("sentence_transformers", "sentence-transformers"),
            ]
        )
    if "env" in requested:
        optional_modules.append(("watchdog", "watchdog (file watcher)"))
    if "api" in requested:
        optional_modules.extend([("fastapi", "FastAPI (HTTP server)"), ("uvicorn", "Uvicorn")])
    if "mcp" in requested:
        optional_modules.append(("mcp", "MCP server"))
    if "bench" in requested:
        optional_modules.append(("build", "Python package build"))

    for mod, label in optional_modules:
        try:
            __import__(mod)
            results.append((label, "ok", "installed"))
        except ImportError:
            results.append((label, "warn", f"optional dependency missing: {mod}"))

    return results


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
            lang_table = Table(title="Languages")
            lang_table.add_column("Language", style="cyan")
            lang_table.add_column("Files", justify="right", style="green")
            for lang, count in sorted(lang_breakdown.items(), key=lambda kv: -kv[1]):
                lang_table.add_row(lang, str(count))
            console.print(lang_table)

        if kind_breakdown:
            kind_table = Table(title="Symbol Kinds")
            kind_table.add_column("Kind", style="cyan")
            kind_table.add_column("Count", justify="right", style="green")
            for kind, count in sorted(kind_breakdown.items(), key=lambda kv: -kv[1]):
                kind_table.add_row(kind, str(count))
            console.print(kind_table)

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


@cli.command(name="context")
@click.argument("query_text")
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option("--budget", default=2000, show_default=True, help="Approximate token budget")
@click.option("--limit", default=10, show_default=True, help="Maximum ranked symbols")
@click.option(
    "--mode",
    type=click.Choice(
        [
            "fts",
            "bm25",
            "semantic",
            "hybrid",
            "pagerank",
            "graph-neighborhood",
            "oracle-ablation",
        ]
    ),
    default="pagerank",
    show_default=True,
    help="Retrieval/ranking mode",
)
@click.option("--build-semantic", is_flag=True, help="Build/load semantic index for semantic modes")
@click.option(
    "--require-semantic",
    is_flag=True,
    help="Fail if semantic/hybrid modes cannot use a real semantic index",
)
@click.option("--json", "as_json", is_flag=True, help="Output full context pack as JSON")
def context_cmd(
    query_text: str,
    db: str,
    budget: int,
    limit: int,
    mode: str,
    build_semantic: bool,
    require_semantic: bool,
    as_json: bool,
) -> None:
    """Build a token-budgeted context pack for an AI coding agent."""
    import json as json_mod

    from codeatlas.agent_context import build_context_pack

    store = _get_store(Path(db))
    try:
        semantic_index = None
        if mode in {"semantic", "hybrid"} or build_semantic or require_semantic:
            semantic_index, _ = _semantic_index_for_eval(
                Path(db),
                store,
                build_semantic=build_semantic,
                require_semantic=require_semantic,
            )
        pack = build_context_pack(
            store,
            query_text,
            budget_tokens=budget,
            limit=limit,
            mode=mode,  # type: ignore[arg-type]
            semantic_index=semantic_index,
        )
    finally:
        store.close()

    if as_json:
        click.echo(json_mod.dumps(pack, indent=2))
        return

    table = Table(title=f"Agent Context: {query_text}")
    table.add_column("Score", justify="right", style="green")
    table.add_column("Symbol", style="cyan")
    table.add_column("Kind", style="magenta")
    table.add_column("File")
    table.add_column("Deps", justify="right")
    for entry in pack["results"]:
        sym = entry["symbol"]
        rels = entry["relationships"]
        table.add_row(
            f"{entry['score']:.2f}",
            sym["qualified_name"],
            sym["kind"],
            f"{sym['file']}:{sym['line']}",
            str(rels["incoming_count"] + rels["outgoing_count"]),
        )
    console.print(table)
    console.print(
        f"[dim]Mode {pack['mode']} ({pack['mode_effective']}); "
        f"estimated {pack['estimated_tokens']} tokens "
        f"({pack['context_savings']:.1%} smaller than the candidate set).[/dim]"
    )


@cli.command(name="explain")
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option("--json", "as_json", is_flag=True, help="Output the structured sections as JSON")
def explain_cmd(db: str, as_json: bool) -> None:
    """Generate an architecture overview of the indexed repo (great for agents)."""
    import json as _json

    from codeatlas.repo_overview import build_repo_explainer

    store = _get_store(Path(db))
    try:
        result = build_repo_explainer(store)
    finally:
        store.close()
    if as_json:
        click.echo(_json.dumps(result["sections"], indent=2))
    else:
        click.echo(result["markdown"])


@cli.command(name="eval")
@click.option("--suite", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option("--out", default=None, type=click.Path(file_okay=False), help="Write report files")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "markdown"]),
    default="markdown",
    show_default=True,
)
@click.option("--budget", default=2000, show_default=True, help="Context-pack token budget")
@click.option("--compare", is_flag=True, help="Compare fts, pagerank, semantic, and hybrid modes")
@click.option("--build-semantic", is_flag=True, help="Build/load semantic index for semantic modes")
@click.option(
    "--require-semantic",
    is_flag=True,
    help="Fail if semantic/hybrid modes cannot use a real semantic index",
)
@click.option(
    "--mode",
    type=click.Choice(["fts", "semantic", "hybrid", "pagerank", "rerank"]),
    default="pagerank",
    show_default=True,
    help="Retrieval/ranking mode when --compare is not set",
)
@click.option(
    "--with-rerank",
    is_flag=True,
    help="Include the cross-encoder rerank mode in --compare (adds latency)",
)
def eval_cmd(
    suite: str,
    db: str,
    out: str | None,
    output_format: str,
    budget: int,
    compare: bool,
    build_semantic: bool,
    require_semantic: bool,
    mode: str,
    with_rerank: bool,
) -> None:
    """Run golden retrieval/context evals and report recall, MRR, and latency."""
    import json as json_mod

    from codeatlas.eval import (
        DEFAULT_EVAL_MODES,
        render_eval_markdown,
        run_eval_comparison,
        run_eval_suite,
    )

    store = _get_store(Path(db))
    try:
        semantic_index = None
        if compare or mode in {"semantic", "hybrid"} or build_semantic or require_semantic:
            semantic_index, _ = _semantic_index_for_eval(
                Path(db),
                store,
                build_semantic=build_semantic,
                require_semantic=require_semantic,
            )
        if compare:
            compare_modes = (*DEFAULT_EVAL_MODES, "rerank") if with_rerank else DEFAULT_EVAL_MODES
            report = run_eval_comparison(
                store,
                suite,
                budget_tokens=budget,
                modes=compare_modes,
                semantic_index=semantic_index,
            )
        else:
            report = run_eval_suite(
                store,
                suite,
                budget_tokens=budget,
                mode=mode,  # type: ignore[arg-type]
                semantic_index=semantic_index,
            )
    finally:
        store.close()

    rendered = (
        json_mod.dumps(report, indent=2)
        if output_format == "json"
        else render_eval_markdown(report)
    )
    if out:
        out_dir = Path(out)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "report.json").write_text(json_mod.dumps(report, indent=2) + "\n")
        (out_dir / "report.md").write_text(render_eval_markdown(report) + "\n")
        latest_dir = Path(db).parent / "eval"
        latest_dir.mkdir(parents=True, exist_ok=True)
        (latest_dir / "report.json").write_text(json_mod.dumps(report, indent=2) + "\n")
        console.print(f"[green]Eval report written to {out_dir}[/green]")
        return
    click.echo(rendered)


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


@cli.command("data-lineage")
@click.option("--repo", "repo_path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "openlineage"]),
    default="text",
    show_default=True,
)
@click.option("-o", "--output", default=None, type=click.Path(), help="Write output to a file")
def data_lineage(repo_path: str, output_format: str, output: str | None) -> None:
    """Extract static dbt/Airflow/SQL lineage from a repository."""
    from codeatlas.data_lineage import build_lineage_graph, export_openlineage, render_lineage_text

    graph = build_lineage_graph(repo_path)
    if output_format == "json":
        rendered = _json.dumps(graph, indent=2)
    elif output_format == "openlineage":
        rendered = _json.dumps(export_openlineage(graph), indent=2)
    else:
        rendered = render_lineage_text(graph)
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(rendered + "\n")
        console.print(f"[green]Data lineage written to {output}[/green]")
    else:
        click.echo(rendered)


@cli.command("lineage-impact")
@click.argument("dataset_or_model")
@click.option("--repo", "repo_path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def lineage_impact_cmd(dataset_or_model: str, repo_path: str, as_json: bool) -> None:
    """Show downstream data-pipeline impact for a dataset, model, DAG, or task."""
    from codeatlas.data_lineage import build_lineage_graph, lineage_impact

    result = lineage_impact(build_lineage_graph(repo_path), dataset_or_model)
    if as_json:
        click.echo(_json.dumps(result, indent=2))
        return
    table = Table(title="CodeAtlas lineage impact", title_style="bold cyan")
    table.add_column("Field", style="dim")
    table.add_column("Value")
    table.add_row("Query", dataset_or_model)
    table.add_row("Matched", ", ".join(result["matched"]) or "none")
    table.add_row("Downstream", str(result["downstream_count"]))
    console.print(table)
    for item in result["downstream"]:
        console.print(f"  - {item}")


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
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "sarif"]),
    default="text",
    show_default=True,
    help="Audit output format",
)
@click.option("-o", "--output", default=None, type=click.Path(), help="Write audit output to file")
def audit(
    db: str,
    show_cycles: bool,
    show_unused: bool,
    show_centrality: bool,
    limit: int,
    include_tests: bool,
    as_json: bool,
    output_format: str,
    output: str | None,
) -> None:
    """Run code quality analysis: cycles, dead code, and complexity."""
    import json as json_mod

    store = _get_store(Path(db))
    if as_json:
        output_format = "json"

    # If no specific flag, show all
    show_all = not (show_cycles or show_unused or show_centrality)

    cycles = store.detect_cycles() if (show_all or show_cycles) else []
    unused = (
        store.find_unused_symbols(include_tests=include_tests) if (show_all or show_unused) else []
    )
    centrality = store.get_symbol_centrality(limit=limit) if (show_all or show_centrality) else []

    if output_format == "sarif":
        from codeatlas.sarif import build_audit_sarif

        payload = json_mod.dumps(
            build_audit_sarif(store, include_tests=include_tests, limit=max(limit, 100)),
            indent=2,
        )
        store.close()
        if output:
            Path(output).write_text(payload + "\n")
            console.print(f"[green]SARIF audit written to {output}[/green]")
        else:
            click.echo(payload)
        return

    store.close()

    if output_format == "json":
        payload = json_mod.dumps(
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
        if output:
            Path(output).write_text(payload + "\n")
            console.print(f"[green]Audit written to {output}[/green]")
        else:
            click.echo(payload)
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


@cli.group()
def hosted() -> None:
    """Manage the local-dev hosted CodeAtlas control plane."""


@hosted.command("bootstrap")
@click.option("--hosted-db", default=".codeatlas/hosted.db", show_default=True)
@click.option("--email", default="dev@codeatlas.local", show_default=True)
@click.option("--name", default="CodeAtlas Dev", show_default=True)
@click.option("--team", "team_slug", default="default", show_default=True)
@click.option("--team-name", default="Default Team", show_default=True)
def hosted_bootstrap(
    hosted_db: str,
    email: str,
    name: str,
    team_slug: str,
    team_name: str,
) -> None:
    """Create a dev user, team, and bearer token for local hosted demos."""
    from codeatlas.hosted import HostedStore

    store = HostedStore(Path(hosted_db))
    try:
        result = store.bootstrap_dev(
            email=email,
            name=name,
            team_slug=team_slug,
            team_name=team_name,
        )
    finally:
        store.close()
    console.print("[green]Hosted MVP bootstrap complete[/green]")
    console.print(f"Team: [cyan]{result.team.slug}[/cyan] ({result.team.id})")
    console.print(f"User: {result.user.email}")
    console.print(f"Bearer token: [bold]{result.token}[/bold]")
    console.print(
        "Set this in the UI as codeatlas.hostedToken or pass it as Authorization: Bearer ..."
    )


@hosted.command("register-repo")
@click.option("--hosted-db", default=".codeatlas/hosted.db", show_default=True)
@click.option("--team", "team_slug", default="default", show_default=True)
@click.option(
    "--path", "repo_path", default=".", show_default=True, type=click.Path(file_okay=False)
)
@click.option("--name", "repo_name", required=True, help="Hosted repo display/name slug")
@click.option("--provider", default="local", show_default=True)
@click.option("--provider-repo", default=None)
@click.option("--default-branch", default=None)
def hosted_register_repo(
    hosted_db: str,
    team_slug: str,
    repo_path: str,
    repo_name: str,
    provider: str,
    provider_repo: str | None,
    default_branch: str | None,
) -> None:
    """Register a local path as a hosted-MVP repo."""
    from codeatlas.hosted import HostedStore, RepoRegistration

    store = HostedStore(Path(hosted_db))
    try:
        repo = store.register_repo(
            RepoRegistration(
                team_slug=team_slug,
                name=repo_name,
                local_path=Path(repo_path),
                provider=provider,
                provider_repo=provider_repo,
                default_branch=default_branch,
            )
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    finally:
        store.close()
    console.print("[green]Registered hosted repo[/green]")
    console.print(f"Repo: [cyan]{repo.name}[/cyan] ({repo.id})")
    console.print(f"Path: {repo.local_path}")
    console.print(f"Graph DB: {repo.graph_db_path}")


@hosted.command("sync")
@click.option("--hosted-db", default=".codeatlas/hosted.db", show_default=True)
@click.option("--repo", "repo_id_or_name", required=True, help="Hosted repo id or name")
def hosted_sync(hosted_db: str, repo_id_or_name: str) -> None:
    """Index a registered hosted-MVP repo into its repo-specific graph DB."""
    from codeatlas.hosted import HostedStore

    store = HostedStore(Path(hosted_db))
    try:
        result = store.sync_repo(repo_id_or_name)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    finally:
        store.close()
    event = result.event
    console.print("[green]Hosted repo sync complete[/green]")
    console.print(f"Repo: [cyan]{result.repo.name}[/cyan] ({result.repo.id})")
    console.print(
        f"Parsed {event.parsed}, skipped {event.skipped}, errors {event.errors} "
        f"in {event.duration_ms}ms"
    )


@hosted.command("seed-demo")
@click.option("--hosted-db", default=".codeatlas/hosted.db", show_default=True)
@click.option(
    "--repo",
    "clone_url",
    default="https://github.com/pallets/flask.git",
    show_default=True,
    help="Public repo to clone + index for the read-only demo",
)
@click.option("--name", default=None, help="Override the demo repo name")
def hosted_seed_demo(hosted_db: str, clone_url: str, name: str | None) -> None:
    """Seed a public read-only demo repo and print its token + repo id.

    Set the printed values as STRATUM_DEMO_TOKEN and STRATUM_DEMO_REPO_ID so the
    landing page's "Explore live demo" button works without signup.
    """
    from codeatlas.hosted import HostedStore

    store = HostedStore(Path(hosted_db))
    try:
        repo, token = store.seed_demo_repo(clone_url, name=name)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    finally:
        store.close()
    console.print("[green]Demo repo seeded[/green]")
    console.print(f"Repo: [cyan]{repo.name}[/cyan] ({repo.id})")
    console.print("\nSet these on the server, then restart:")
    console.print(f'  STRATUM_DEMO_REPO_ID="{repo.id}"')
    console.print(f'  STRATUM_DEMO_TOKEN="{token}"')


@hosted.command("metrics")
@click.option("--hosted-db", default=".codeatlas/hosted.db", show_default=True)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def hosted_metrics(hosted_db: str, as_json: bool) -> None:
    """Show signup/activation metrics from the hosted control-plane DB."""
    import json as _json

    from codeatlas.hosted import HostedStore

    store = HostedStore(Path(hosted_db))
    try:
        data = store.metrics()
    finally:
        store.close()
    if as_json:
        click.echo(_json.dumps(data, indent=2))
        return
    console.print("[green]Stratum hosted metrics[/green]")
    for key, value in data.items():
        console.print(f"  {key.replace('_', ' ')}: [cyan]{value}[/cyan]")


@hosted.group("github")
def hosted_github() -> None:
    """Manage Stratum GitHub App metadata and webhook sync."""


@hosted_github.command("status")
@click.option("--hosted-db", default=".codeatlas/hosted.db", show_default=True)
def hosted_github_status(hosted_db: str) -> None:
    """Show GitHub App configuration and stored installation state."""
    from codeatlas.github_app import load_github_app_config
    from codeatlas.hosted import HostedStore

    config = load_github_app_config()
    store = HostedStore(Path(hosted_db))
    try:
        installations = store.list_github_installations()
        repositories = store.list_github_repositories()
    finally:
        store.close()

    table = Table(title="Stratum GitHub App")
    table.add_column("Check")
    table.add_column("Value")
    table.add_row("App configured", "yes" if config.configured else "no")
    table.add_row("OAuth configured", "yes" if config.oauth_configured else "no")
    table.add_row("Webhook secret", "yes" if config.webhook_configured else "no")
    table.add_row("Public URL", config.public_url or "not set")
    table.add_row(
        "Repo listing",
        "fixture"
        if config.repos_fixture_path
        else "token"
        if config.installation_token
        else "store",
    )
    table.add_row("Installations", str(len(installations)))
    table.add_row("GitHub repos", str(len(repositories)))
    console.print(table)


@hosted_github.command("refresh-repos")
@click.option("--hosted-db", default=".codeatlas/hosted.db", show_default=True)
@click.option("--installation", "installation_id", required=True, help="GitHub installation id")
def hosted_github_refresh_repos(hosted_db: str, installation_id: str) -> None:
    """Refresh GitHub repository metadata from fixture or GitHub token config."""
    from codeatlas.github_app import load_github_app_config, refresh_github_repositories
    from codeatlas.hosted import HostedStore

    store = HostedStore(Path(hosted_db))
    try:
        listing = refresh_github_repositories(
            store,
            installation_id=installation_id,
            config=load_github_app_config(),
        )
        repos = store.list_github_repositories(installation_id=installation_id)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    finally:
        store.close()
    console.print(f"[green]GitHub repos refreshed[/green] from {listing.source}")
    console.print(f"Repositories: {len(repos)}")


@hosted_github.command("sync")
@click.option("--hosted-db", default=".codeatlas/hosted.db", show_default=True)
@click.option(
    "--repo", "repo_id_or_name", required=True, help="Hosted repo id, name, or GitHub repo id"
)
def hosted_github_sync(hosted_db: str, repo_id_or_name: str) -> None:
    """Sync an activated GitHub repo through the hosted graph path."""
    from codeatlas.hosted import HostedStore

    store = HostedStore(Path(hosted_db))
    try:
        provider_repo = store.get_repo_by_provider_id(repo_id_or_name)
        if provider_repo is not None:
            result = store.sync_repo(provider_repo.id)
        else:
            try:
                result = store.sync_github_repository(repo_id_or_name)
            except KeyError:
                repo = store.get_repo(repo_id_or_name)
                result = store.sync_repo(repo.id)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    finally:
        store.close()
    console.print("[green]GitHub repo sync complete[/green]")
    console.print(f"Repo: [cyan]{result.repo.name}[/cyan] ({result.repo.id})")
    console.print(f"Status: {result.event.status} · {result.event.duration_ms}ms")


@hosted_github.command("webhook-test")
@click.option("--hosted-db", default=".codeatlas/hosted.db", show_default=True)
@click.option(
    "--delivery",
    "delivery_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="GitHub webhook fixture JSON path",
)
@click.option("--event", "event_name", default="push", show_default=True)
@click.option("--delivery-id", default="cli-fixture", show_default=True)
def hosted_github_webhook_test(
    hosted_db: str,
    delivery_path: str,
    event_name: str,
    delivery_id: str,
) -> None:
    """Replay a GitHub webhook fixture without network access."""
    from codeatlas.github_app import parse_webhook_payload, process_github_webhook
    from codeatlas.hosted import HostedStore

    payload = parse_webhook_payload(Path(delivery_path).read_text())
    store = HostedStore(Path(hosted_db))
    try:
        result = process_github_webhook(
            store,
            event=event_name,
            delivery_id=delivery_id,
            payload=payload,
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    finally:
        store.close()
    console.print(_json.dumps(result.model_dump(), indent=2))


@cli.command()
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option("--host", default="127.0.0.1", show_default=True, envvar="HOST")
@click.option("--port", default=8080, show_default=True, type=int, envvar="PORT")
@click.option(
    "--hosted-db",
    default=None,
    help="Mount hosted-MVP routes using this metadata DB (for example .codeatlas/hosted.db)",
)
@click.option(
    "--api-key",
    default=None,
    help="Require this value in the X-API-Key header on every request",
)
@click.option(
    "--allow-origin",
    "allow_origins",
    multiple=True,
    help="CORS allow-origin (repeat for multiple). Defaults to * if unset.",
)
def server(
    db: str,
    host: str,
    port: int,
    hosted_db: str | None,
    api_key: str | None,
    allow_origins: tuple[str, ...],
) -> None:
    """Start the HTTP API server (FastAPI + Uvicorn).

    Distinct from ``codeatlas serve`` (MCP/stdio). The HTTP API is what the
    bundled web UI and third-party integrations talk to.
    """
    try:
        import uvicorn
    except ImportError as exc:
        raise click.ClickException(
            "FastAPI/Uvicorn not installed. Run: pip install 'codeatlas[api]'"
        ) from exc

    from codeatlas.api import create_app

    app = create_app(
        db_path=db,
        allow_origins=list(allow_origins) if allow_origins else None,
        api_key=api_key,
        hosted_db_path=hosted_db,
    )
    console.print(f"[green]Starting CodeAtlas HTTP API[/green] on http://{host}:{port} (db: {db})")
    if hosted_db:
        console.print(f"[cyan]Hosted MVP routes mounted[/cyan] (metadata: {hosted_db})")
    uvicorn.run(app, host=host, port=port, log_level="info")


def _find_frontend_dist() -> Path | None:
    """Locate a built frontend bundle. Searches common install layouts."""
    import codeatlas as _pkg

    pkg_dir = Path(_pkg.__file__).resolve().parent
    candidates = [
        pkg_dir / "_ui",
        pkg_dir.parent / "_ui",
        pkg_dir.parent.parent / "frontend" / "dist",
        Path.cwd() / "frontend" / "dist",
    ]
    for candidate in candidates:
        if candidate.is_dir() and (candidate / "index.html").is_file():
            return candidate
    return None


@cli.command()
@click.option("--db", default=".codeatlas/graph.db", show_default=True)
@click.option("--host", default="127.0.0.1", show_default=True, envvar="HOST")
@click.option("--port", default=8080, show_default=True, type=int, envvar="PORT")
@click.option(
    "--hosted-db",
    default=None,
    help="Mount hosted-MVP routes using this metadata DB (for example .codeatlas/hosted.db)",
)
@click.option(
    "--dist",
    default=None,
    type=click.Path(exists=True, file_okay=False),
    help="Path to a built frontend bundle (default: auto-detect frontend/dist)",
)
@click.option("--no-browser", is_flag=True, help="Don't open the browser")
@click.option("--api-key", default=None, help="Require X-API-Key for every request")
def ui(
    db: str,
    host: str,
    port: int,
    hosted_db: str | None,
    dist: str | None,
    no_browser: bool,
    api_key: str | None,
) -> None:
    """Start the web UI: HTTP API + built frontend served from one process."""
    try:
        import uvicorn
    except ImportError as exc:
        raise click.ClickException(
            "FastAPI/Uvicorn not installed. Run: pip install 'codeatlas[api]'"
        ) from exc

    from codeatlas.api import create_app

    static_dir = Path(dist) if dist else _find_frontend_dist()
    if static_dir is None:
        raise click.ClickException(
            "No built frontend bundle found.\n"
            "Build it once: cd frontend && npm install && npm run build\n"
            "Or pass --dist /path/to/frontend/dist"
        )

    app = create_app(
        db_path=db,
        api_key=api_key,
        static_dir=static_dir,
        hosted_db_path=hosted_db,
    )

    url = f"http://{host}:{port}"
    console.print(f"[green]CodeAtlas UI[/green] on {url} (db: {db}, dist: {static_dir})")
    if hosted_db:
        console.print(f"[cyan]Hosted MVP dashboard enabled[/cyan] (metadata: {hosted_db})")

    if not no_browser:
        import threading
        import time
        import webbrowser

        def _open() -> None:
            time.sleep(1.0)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="info")


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
