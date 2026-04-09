"""Git integration for change impact analysis."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from codeatlas.graph.store import GraphStore
from codeatlas.models import Symbol


@dataclass
class ChangedSymbol:
    """A symbol that was affected by a code change."""

    symbol: Symbol
    change_type: str  # "modified", "added", "deleted"


@dataclass
class ChangeImpact:
    """Full impact analysis result from a git diff."""

    changed_files: list[str]
    changed_symbols: list[ChangedSymbol]
    affected_symbols: list[Symbol] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)


def get_git_changed_files(repo_path: Path, ref: str = "HEAD", staged: bool = False) -> list[str]:
    """Get list of changed files from git.

    Args:
        repo_path: Path to the git repository
        ref: Git ref to diff against (default: HEAD)
        staged: If True, show staged changes only
    """
    try:
        if staged:
            cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"]
        elif ref == "HEAD":
            # Show both staged and unstaged changes vs HEAD
            cmd = ["git", "diff", "HEAD", "--name-only", "--diff-filter=ACMR"]
        else:
            cmd = ["git", "diff", ref, "--name-only", "--diff-filter=ACMR"]

        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def get_git_diff_lines(repo_path: Path, file_path: str, ref: str = "HEAD") -> list[int]:
    """Get the line numbers that changed in a specific file.

    Returns a list of line numbers (1-indexed) that were added or modified.
    """
    try:
        cmd = ["git", "diff", ref, "-U0", "--", file_path]
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        changed_lines: list[int] = []
        for line in result.stdout.split("\n"):
            if line.startswith("@@"):
                # Parse the @@ -old,count +new,count @@ format
                parts = line.split("+")
                if len(parts) >= 2:
                    new_part = parts[1].split("@@")[0].strip()
                    if "," in new_part:
                        start, count = new_part.split(",")
                        start_line = int(start)
                        line_count = int(count)
                    else:
                        start_line = int(new_part)
                        line_count = 1
                    changed_lines.extend(range(start_line, start_line + line_count))
        return changed_lines
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        return []


def analyze_change_impact(
    store: GraphStore,
    repo_path: Path,
    ref: str = "HEAD",
    max_depth: int = 3,
) -> ChangeImpact:
    """Analyze the impact of current git changes on the knowledge graph.

    Finds which symbols were modified by the diff, then traces their
    reverse dependencies to find all affected symbols.
    """
    changed_files = get_git_changed_files(repo_path, ref=ref)
    if not changed_files:
        return ChangeImpact(changed_files=[], changed_symbols=[])

    changed_symbols: list[ChangedSymbol] = []

    for file_path in changed_files:
        # Get all symbols in the changed file
        symbols = store.get_symbols_in_file(file_path)
        if not symbols:
            # File might be new and not yet indexed
            continue

        # Get changed line numbers to find specifically modified symbols
        changed_lines = get_git_diff_lines(repo_path, file_path, ref=ref)

        if changed_lines:
            # Find symbols whose span overlaps with changed lines
            for sym in symbols:
                sym_start = sym.span.start.line + 1  # 0-indexed to 1-indexed
                sym_end = sym.span.end.line + 1
                if any(sym_start <= line <= sym_end for line in changed_lines):
                    changed_symbols.append(ChangedSymbol(symbol=sym, change_type="modified"))
        else:
            # If we can't get line-level diff, mark all symbols as potentially modified
            for sym in symbols:
                changed_symbols.append(ChangedSymbol(symbol=sym, change_type="modified"))

    # Trace reverse dependencies to find affected symbols
    affected_ids: set[str] = set()
    for cs in changed_symbols:
        impact = store.get_impact_analysis(cs.symbol.id, max_depth=max_depth)
        for row in impact:
            affected_ids.add(str(row["source_id"]))

    # Resolve affected symbol IDs to full Symbol objects
    affected_symbols: list[Symbol] = []
    for sym_id in affected_ids:
        # Skip symbols that are themselves changed
        if any(cs.symbol.id == sym_id for cs in changed_symbols):
            continue
        maybe_sym = store.get_symbol_by_id(sym_id)
        if maybe_sym is not None:
            affected_symbols.append(maybe_sym)

    # Collect unique affected files
    affected_files = sorted({s.file_path for s in affected_symbols} - set(changed_files))

    return ChangeImpact(
        changed_files=changed_files,
        changed_symbols=changed_symbols,
        affected_symbols=affected_symbols,
        affected_files=affected_files,
    )
