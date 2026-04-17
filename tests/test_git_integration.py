"""Tests for git integration and change impact analysis."""

from pathlib import Path
from unittest.mock import patch

from codeatlas.git_integration import (
    analyze_change_impact,
    get_git_changed_files,
    get_git_churn,
    get_git_diff_lines,
)
from codeatlas.graph.store import GraphStore
from codeatlas.models import (
    FileInfo,
    ParseResult,
    Position,
    Relationship,
    RelationshipKind,
    Span,
    Symbol,
    SymbolKind,
)


def _sym(
    name: str,
    file_path: str = "app.py",
    kind: SymbolKind = SymbolKind.FUNCTION,
    line: int = 0,
) -> Symbol:
    return Symbol(
        id=f"{file_path}::{name}",
        name=name,
        qualified_name=name,
        kind=kind,
        file_path=file_path,
        span=Span(
            start=Position(line=line, column=0),
            end=Position(line=line + 10, column=0),
        ),
        language="python",
    )


def _rel(src: str, tgt: str, fp: str = "app.py") -> Relationship:
    return Relationship(
        source_id=src,
        target_id=tgt,
        kind=RelationshipKind.CALLS,
        file_path=fp,
    )


def _result(fp: str, syms: list[Symbol], rels: list[Relationship] | None = None) -> ParseResult:
    r = rels or []
    return ParseResult(
        file_info=FileInfo(
            path=fp,
            language="python",
            content_hash="abc",
            symbol_count=len(syms),
            relationship_count=len(r),
        ),
        symbols=syms,
        relationships=r,
    )


# --- get_git_changed_files ---


@patch("codeatlas.git_integration.subprocess.run")
def test_get_git_changed_files(mock_run) -> None:
    mock_run.return_value.stdout = "src/main.py\nsrc/utils.py\n"
    mock_run.return_value.returncode = 0
    files = get_git_changed_files(Path("/repo"))
    assert files == ["src/main.py", "src/utils.py"]


@patch("codeatlas.git_integration.subprocess.run")
def test_get_git_changed_files_empty(mock_run) -> None:
    mock_run.return_value.stdout = ""
    mock_run.return_value.returncode = 0
    files = get_git_changed_files(Path("/repo"))
    assert files == []


@patch("codeatlas.git_integration.subprocess.run")
def test_get_git_changed_files_error(mock_run) -> None:
    from subprocess import CalledProcessError

    mock_run.side_effect = CalledProcessError(1, "git")
    files = get_git_changed_files(Path("/repo"))
    assert files == []


# --- get_git_diff_lines ---


@patch("codeatlas.git_integration.subprocess.run")
def test_get_git_diff_lines(mock_run) -> None:
    mock_run.return_value.stdout = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -5,3 +5,4 @@\n"
        " unchanged\n"
        "+new line\n"
    )
    mock_run.return_value.returncode = 0
    lines = get_git_diff_lines(Path("/repo"), "app.py")
    assert 5 in lines
    assert 6 in lines
    assert 7 in lines
    assert 8 in lines


@patch("codeatlas.git_integration.subprocess.run")
def test_get_git_diff_lines_single_line(mock_run) -> None:
    mock_run.return_value.stdout = "@@ -10,1 +10,1 @@\n-old\n+new\n"
    mock_run.return_value.returncode = 0
    lines = get_git_diff_lines(Path("/repo"), "app.py")
    assert lines == [10]


# --- analyze_change_impact ---


@patch("codeatlas.git_integration.get_git_diff_lines")
@patch("codeatlas.git_integration.get_git_changed_files")
def test_analyze_no_changes(mock_changed_files, mock_diff_lines) -> None:
    mock_changed_files.return_value = []
    store = GraphStore(":memory:")
    result = analyze_change_impact(store, Path("/repo"))
    assert result.changed_files == []
    assert result.changed_symbols == []


@patch("codeatlas.git_integration.get_git_diff_lines")
@patch("codeatlas.git_integration.get_git_changed_files")
def test_analyze_finds_changed_symbols(mock_changed_files, mock_diff_lines) -> None:
    mock_changed_files.return_value = ["app.py"]
    mock_diff_lines.return_value = [5]  # Line 5 is within the symbol's span (lines 1-11)

    store = GraphStore(":memory:")
    s1 = _sym("main", "app.py", line=0)
    s2 = _sym("helper", "utils.py", line=0)
    store.upsert_parse_result(_result("app.py", [s1]))
    store.upsert_parse_result(_result("utils.py", [s2]))

    result = analyze_change_impact(store, Path("/repo"))
    assert len(result.changed_symbols) == 1
    assert result.changed_symbols[0].symbol.name == "main"


@patch("codeatlas.git_integration.get_git_diff_lines")
@patch("codeatlas.git_integration.get_git_changed_files")
def test_analyze_finds_affected_symbols(mock_changed_files, mock_diff_lines) -> None:
    mock_changed_files.return_value = ["utils.py"]
    mock_diff_lines.return_value = [5]

    store = GraphStore(":memory:")
    s1 = _sym("main", "app.py", line=0)
    s2 = _sym("helper", "utils.py", line=0)
    rel = _rel("app.py::main", "utils.py::helper", fp="app.py")
    store.upsert_parse_result(_result("app.py", [s1], [rel]))
    store.upsert_parse_result(_result("utils.py", [s2]))

    result = analyze_change_impact(store, Path("/repo"))
    # helper changed, main calls helper so main is affected
    assert len(result.changed_symbols) == 1
    assert result.changed_symbols[0].symbol.name == "helper"
    affected_names = [s.name for s in result.affected_symbols]
    assert "main" in affected_names


@patch("codeatlas.git_integration.get_git_diff_lines")
@patch("codeatlas.git_integration.get_git_changed_files")
def test_analyze_affected_files(mock_changed_files, mock_diff_lines) -> None:
    mock_changed_files.return_value = ["utils.py"]
    mock_diff_lines.return_value = [5]

    store = GraphStore(":memory:")
    s1 = _sym("main", "app.py", line=0)
    s2 = _sym("helper", "utils.py", line=0)
    rel = _rel("app.py::main", "utils.py::helper", fp="app.py")
    store.upsert_parse_result(_result("app.py", [s1], [rel]))
    store.upsert_parse_result(_result("utils.py", [s2]))

    result = analyze_change_impact(store, Path("/repo"))
    assert "app.py" in result.affected_files
    assert "utils.py" not in result.affected_files  # changed, not affected


@patch("codeatlas.git_integration.get_git_diff_lines")
@patch("codeatlas.git_integration.get_git_changed_files")
def test_analyze_skips_unindexed_files(mock_changed_files, mock_diff_lines) -> None:
    mock_changed_files.return_value = ["new_file.py"]
    mock_diff_lines.return_value = []

    store = GraphStore(":memory:")
    result = analyze_change_impact(store, Path("/repo"))
    assert result.changed_files == ["new_file.py"]
    assert result.changed_symbols == []


@patch("codeatlas.git_integration.get_git_diff_lines")
@patch("codeatlas.git_integration.get_git_changed_files")
def test_analyze_line_outside_symbol(mock_changed_files, mock_diff_lines) -> None:
    mock_changed_files.return_value = ["app.py"]
    mock_diff_lines.return_value = [999]  # Line outside any symbol's span

    store = GraphStore(":memory:")
    s1 = _sym("main", "app.py", line=0)  # spans lines 1-11
    store.upsert_parse_result(_result("app.py", [s1]))

    result = analyze_change_impact(store, Path("/repo"))
    assert result.changed_symbols == []


# --- staged and custom ref ---


@patch("codeatlas.git_integration.subprocess.run")
def test_get_git_changed_files_staged(mock_run) -> None:
    mock_run.return_value.stdout = "staged.py\n"
    mock_run.return_value.returncode = 0
    files = get_git_changed_files(Path("/repo"), staged=True)
    assert files == ["staged.py"]
    # Verify --cached flag was used
    cmd = mock_run.call_args[0][0]
    assert "--cached" in cmd


@patch("codeatlas.git_integration.subprocess.run")
def test_get_git_changed_files_custom_ref(mock_run) -> None:
    mock_run.return_value.stdout = "changed.py\n"
    mock_run.return_value.returncode = 0
    files = get_git_changed_files(Path("/repo"), ref="main")
    assert files == ["changed.py"]
    cmd = mock_run.call_args[0][0]
    assert "main" in cmd


# --- no diff lines fallback ---


@patch("codeatlas.git_integration.get_git_diff_lines")
@patch("codeatlas.git_integration.get_git_changed_files")
def test_analyze_no_diff_lines_marks_all(mock_changed_files, mock_diff_lines) -> None:
    """When diff lines can't be determined, all symbols in the file are marked as modified."""
    mock_changed_files.return_value = ["app.py"]
    mock_diff_lines.return_value = []  # empty = can't determine lines

    store = GraphStore(":memory:")
    s1 = _sym("main", "app.py", line=0)
    s2 = _sym("helper", "app.py", line=20)
    store.upsert_parse_result(_result("app.py", [s1, s2]))

    result = analyze_change_impact(store, Path("/repo"))
    assert len(result.changed_symbols) == 2
    names = {cs.symbol.name for cs in result.changed_symbols}
    assert names == {"main", "helper"}


@patch("codeatlas.git_integration.subprocess.run")
def test_get_git_diff_lines_no_comma(mock_run) -> None:
    """Single line change: +10 without ,count."""
    mock_run.return_value.stdout = "@@ -10 +10 @@\n-old\n+new\n"
    mock_run.return_value.returncode = 0
    lines = get_git_diff_lines(Path("/repo"), "app.py")
    assert lines == [10]


@patch("codeatlas.git_integration.subprocess.run")
def test_get_git_diff_lines_error(mock_run) -> None:
    from subprocess import CalledProcessError

    mock_run.side_effect = CalledProcessError(1, "git")
    lines = get_git_diff_lines(Path("/repo"), "app.py")
    assert lines == []


# --- get_git_churn ---


@patch("codeatlas.git_integration.subprocess.run")
def test_get_git_churn_parses_output(mock_run) -> None:
    """Cover the non-empty line parsing path in get_git_churn (lines 175-177)."""
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = "app.py\nhelpers.py\napp.py\n\nhelpers.py\n"
    result = get_git_churn(Path("/repo"))
    files = [r["file"] for r in result]
    assert "app.py" in files
    assert "helpers.py" in files
    # app.py appeared twice
    app_entry = next(r for r in result if r["file"] == "app.py")
    assert app_entry["commits"] == 2


@patch("codeatlas.git_integration.subprocess.run")
def test_get_git_churn_timeout_returns_empty(mock_run) -> None:
    """Cover the TimeoutExpired exception path (line 180)."""
    from subprocess import TimeoutExpired

    mock_run.side_effect = TimeoutExpired("git", 20)
    result = get_git_churn(Path("/repo"))
    assert result == []


@patch("codeatlas.git_integration.subprocess.run")
def test_get_git_churn_file_not_found_returns_empty(mock_run) -> None:
    """Cover the FileNotFoundError exception path (line 181)."""
    mock_run.side_effect = FileNotFoundError("git not found")
    result = get_git_churn(Path("/repo"))
    assert result == []


# --- analyze_change_impact: skip changed symbols in affected ---


@patch("codeatlas.git_integration.get_git_diff_lines")
@patch("codeatlas.git_integration.get_git_changed_files")
def test_analyze_skips_changed_symbol_in_affected(
    mock_changed_files,  # type: ignore[no-untyped-def]
    mock_diff_lines,  # type: ignore[no-untyped-def]
) -> None:
    """Cover line 144: symbol already in changed_symbols is skipped from affected."""
    store = GraphStore(":memory:")
    caller = _sym("caller", file_path="app.py", line=1)
    callee = _sym("callee", file_path="app.py", line=10)
    rel = Relationship(
        source_id=caller.id,
        target_id=callee.id,
        kind=RelationshipKind.CALLS,
        file_path="app.py",
    )
    result = ParseResult(
        file_info=FileInfo(path="app.py", language="python", content_hash="x", symbol_count=2),
        symbols=[caller, callee],
        relationships=[rel],
    )
    store.upsert_parse_result(result)

    # Both caller and callee are in the changed file
    mock_changed_files.return_value = ["app.py"]
    mock_diff_lines.return_value = [
        2,
        11,
    ]  # covers both symbols (1-indexed lines, spans start_line+1)

    impact = analyze_change_impact(store, Path("/repo"))
    # callee appears in changed_symbols, so it shouldn't also appear in affected_symbols
    changed_ids = {cs.symbol.id for cs in impact.changed_symbols}
    affected_ids = {s.id for s in impact.affected_symbols}
    assert not (changed_ids & affected_ids), "Changed symbols must not appear in affected"
