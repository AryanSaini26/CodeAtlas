"""Tests for the CLI commands."""

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from codeatlas import __version__
from codeatlas.cli import cli

# --- version ---


def test_version_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output
    assert "codeatlas" in result.output


def _make_repo(tmp_path: Path) -> Path:
    """Create a minimal repo with a couple of Python files."""
    (tmp_path / "main.py").write_text(
        'def run():\n    """Run the app."""\n    greet("world")\n\n'
        'def greet(name: str) -> str:\n    return f"Hello, {name}"\n'
    )
    (tmp_path / "helpers.py").write_text(
        "MAX = 10\n\ndef add(a: int, b: int) -> int:\n    return a + b\n"
    )
    return tmp_path


# --- index command ---


def test_index_command(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    result = runner.invoke(cli, ["index", str(repo), "--db", db_path])
    assert result.exit_code == 0
    assert "parsed" in result.output.lower() or "complete" in result.output.lower()
    assert Path(db_path).exists()


def test_index_incremental(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    # Full index first
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    # Then incremental
    result = runner.invoke(cli, ["index", str(repo), "--db", db_path, "--incremental"])
    assert result.exit_code == 0


# --- stats command ---


def test_stats_command(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["stats", "--db", db_path])
    assert result.exit_code == 0
    assert "files" in result.output.lower()
    assert "symbols" in result.output.lower()


def test_stats_empty_db(tmp_path: Path) -> None:
    db_path = str(tmp_path / "empty.db")
    runner = CliRunner()
    result = runner.invoke(cli, ["stats", "--db", db_path])
    assert result.exit_code == 0


# --- query command ---


def test_query_fts(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["query", "greet", "--db", db_path])
    assert result.exit_code == 0
    assert "greet" in result.output


def test_query_no_results(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["query", "nonexistent_xyz", "--db", db_path])
    assert result.exit_code == 0
    assert "no results" in result.output.lower()


# --- export command ---


def test_export_dot(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    output = str(tmp_path / "graph.dot")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["export", "--db", db_path, "--format", "dot", "-o", output])
    assert result.exit_code == 0
    content = Path(output).read_text()
    assert "digraph" in content


def test_export_json(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    output = str(tmp_path / "graph.json")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["export", "--db", db_path, "--format", "json", "-o", output])
    assert result.exit_code == 0
    content = Path(output).read_text()
    assert "nodes" in content


def test_export_stdout(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["export", "--db", db_path, "--format", "json"])
    assert result.exit_code == 0
    assert "nodes" in result.output


# --- show command ---


def test_show_symbol(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["show", "greet", "--db", db_path])
    assert result.exit_code == 0
    assert "greet" in result.output
    assert "function" in result.output


def test_show_with_deps(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    # run should call greet, so show should have dependency info
    result = runner.invoke(cli, ["show", "run", "--db", db_path])
    assert result.exit_code == 0
    assert "run" in result.output


def test_show_not_found(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["show", "nonexistent_xyz", "--db", db_path])
    assert result.exit_code == 0
    assert "no symbol" in result.output.lower()


# --- init command ---


def test_init_creates_config(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["init", str(tmp_path)])
    assert result.exit_code == 0
    toml_path = tmp_path / "codeatlas.toml"
    assert toml_path.exists()
    content = toml_path.read_text()
    assert "[codeatlas]" in content
    assert "include_extensions" in content


def test_init_skips_existing(tmp_path: Path) -> None:
    (tmp_path / "codeatlas.toml").write_text("[codeatlas]\n")
    runner = CliRunner()
    result = runner.invoke(cli, ["init", str(tmp_path)])
    assert result.exit_code == 0
    # Rich may wrap text across lines, so collapse whitespace for the check
    output = " ".join(result.output.split())
    assert "already exists" in output


# --- config file loading ---


def test_index_with_config_file(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    # Create a config that only indexes .py files with a custom max size
    (repo / "codeatlas.toml").write_text(
        '[codeatlas]\n\n[codeatlas.parser]\nmax_file_size_kb = 500\ninclude_extensions = [".py"]\n'
    )
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    result = runner.invoke(cli, ["index", str(repo), "--db", db_path])
    assert result.exit_code == 0


# --- audit command ---


def test_audit_all(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["audit", "--db", db_path])
    assert result.exit_code == 0
    # Should show all three sections
    assert "circular" in result.output.lower() or "no circular" in result.output.lower()
    assert "unused" in result.output.lower() or "no unused" in result.output.lower()
    assert "centrality" in result.output.lower() or "no relationships" in result.output.lower()


def test_audit_cycles_only(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["audit", "--db", db_path, "--cycles"])
    assert result.exit_code == 0
    # Should NOT contain centrality output since we only asked for cycles
    assert "centrality" not in result.output.lower()


def test_audit_unused_only(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["audit", "--db", db_path, "--unused"])
    assert result.exit_code == 0


def test_audit_centrality_with_limit(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["audit", "--db", db_path, "--centrality", "--limit", "5"])
    assert result.exit_code == 0


def test_audit_empty_db(tmp_path: Path) -> None:
    db_path = str(tmp_path / "empty.db")
    runner = CliRunner()
    result = runner.invoke(cli, ["audit", "--db", db_path])
    assert result.exit_code == 0


# --- find-path command ---


def test_find_path_found(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["find-path", "run", "greet", "--db", db_path])
    assert result.exit_code == 0
    assert "path" in result.output.lower() or "hop" in result.output.lower()


def test_find_path_not_found(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["find-path", "add", "run", "--db", db_path])
    assert result.exit_code == 0
    assert "no path" in result.output.lower() or "not found" in result.output.lower()


def test_find_path_symbol_missing(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["find-path", "nonexistent", "run", "--db", db_path])
    assert result.exit_code == 0
    assert "not found" in result.output.lower()


# --- coupling command ---


def test_coupling_command(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["coupling", "--db", db_path])
    assert result.exit_code == 0


def test_coupling_empty_db(tmp_path: Path) -> None:
    db_path = str(tmp_path / "empty.db")
    runner = CliRunner()
    result = runner.invoke(cli, ["coupling", "--db", db_path])
    assert result.exit_code == 0
    assert "no cross-file" in result.output.lower()


# --- viz command ---


def test_viz_generates_html(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    output = str(tmp_path / "graph.html")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["viz", "--db", db_path, "-o", output])
    assert result.exit_code == 0
    content = Path(output).read_text()
    assert "d3.js" in content.lower() or "d3.v7" in content
    assert "CodeAtlas" in content


def test_viz_default_output(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    # Run from tmp_path so .codeatlas/ is created there
    import os

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = runner.invoke(cli, ["viz", "--db", db_path])
        assert result.exit_code == 0
        assert (tmp_path / ".codeatlas" / "graph.html").exists()
    finally:
        os.chdir(old_cwd)


def test_viz_empty_db(tmp_path: Path) -> None:
    db_path = str(tmp_path / "empty.db")
    output = str(tmp_path / "graph.html")
    runner = CliRunner()
    result = runner.invoke(cli, ["viz", "--db", db_path, "-o", output])
    assert result.exit_code == 0
    assert Path(output).exists()


# --- diff command ---


def test_diff_new_files(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    # Don't index first — all files should show as new
    result = runner.invoke(cli, ["diff", str(repo), "--db", db_path])
    assert result.exit_code == 0
    assert "new files" in result.output.lower() or "re-index" in result.output.lower()


def test_diff_no_changes(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["diff", str(repo), "--db", db_path])
    assert result.exit_code == 0
    assert "no changes" in result.output.lower()


def test_diff_modified_file(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    # Modify a file
    (repo / "main.py").write_text("def run():\n    pass\n")
    result = runner.invoke(cli, ["diff", str(repo), "--db", db_path])
    assert result.exit_code == 0
    assert "modified" in result.output.lower()


# --- list-files command ---


def test_list_files_command(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["list-files", "--db", db_path])
    assert result.exit_code == 0
    assert "python" in result.output.lower()
    assert "Indexed Files" in result.output


def test_list_files_filter_by_lang(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["list-files", "--db", db_path, "--lang", "python"])
    assert result.exit_code == 0
    assert "python" in result.output.lower()


def test_list_files_filter_no_match(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["list-files", "--db", db_path, "--lang", "rust"])
    assert result.exit_code == 0
    assert "no files" in result.output.lower()


def test_list_files_empty_db(tmp_path: Path) -> None:
    db_path = str(tmp_path / "empty.db")
    runner = CliRunner()
    result = runner.invoke(cli, ["list-files", "--db", db_path])
    assert result.exit_code == 0
    assert "no files" in result.output.lower()


# --- stats --json ---


def test_stats_json_output(tmp_path: Path) -> None:
    import json

    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["stats", "--db", db_path, "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "files" in data
    assert "symbols" in data
    assert "languages" in data


# --- query --kind filter ---


def test_query_kind_filter(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["query", "greet", "--db", db_path, "--kind", "function"])
    assert result.exit_code == 0
    assert "greet" in result.output


def test_query_kind_filter_no_match(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["query", "greet", "--db", db_path, "--kind", "class"])
    assert result.exit_code == 0
    assert "no results" in result.output.lower()


# --- show command: decorators ---


def test_show_symbol_with_decorator(tmp_path: Path) -> None:
    (tmp_path / "decorated.py").write_text("@staticmethod\ndef compute():\n    pass\n")
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(tmp_path), "--db", db_path])
    result = runner.invoke(cli, ["show", "compute", "--db", db_path])
    assert result.exit_code == 0
    assert "compute" in result.output


# --- clean command ---


def test_clean_no_dir(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["clean", str(tmp_path)])
    assert result.exit_code == 0
    assert "no .codeatlas" in result.output.lower()


def test_clean_with_yes_flag(tmp_path: Path) -> None:
    atlas_dir = tmp_path / ".codeatlas"
    atlas_dir.mkdir()
    (atlas_dir / "graph.db").write_text("fake")
    runner = CliRunner()
    result = runner.invoke(cli, ["clean", str(tmp_path), "--yes"])
    assert result.exit_code == 0
    assert not atlas_dir.exists()


# --- impact command ---


def test_impact_no_git(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["impact", str(repo), "--db", db_path])
    assert result.exit_code == 0
    assert "no changed" in result.output.lower()


@patch("codeatlas.git_integration.analyze_change_impact")
def test_impact_with_changed_symbols(mock_impact, tmp_path: Path) -> None:
    from codeatlas.git_integration import ChangedSymbol, ChangeImpact
    from codeatlas.models import Position, Span, Symbol, SymbolKind

    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])

    sym = Symbol(
        id="main.py::run",
        name="run",
        qualified_name="run",
        kind=SymbolKind.FUNCTION,
        file_path="main.py",
        span=Span(start=Position(line=0, column=0), end=Position(line=5, column=0)),
        language="python",
    )
    mock_impact.return_value = ChangeImpact(
        changed_files=["main.py"],
        changed_symbols=[ChangedSymbol(symbol=sym, change_type="modified")],
        affected_symbols=[],
        affected_files=[],
    )

    result = runner.invoke(cli, ["impact", str(repo), "--db", db_path])
    assert result.exit_code == 0
    assert "changed files" in result.output.lower()
    assert "changed symbols" in result.output.lower()
    assert "no other files" in result.output.lower()


@patch("codeatlas.git_integration.analyze_change_impact")
def test_impact_with_affected_symbols(mock_impact, tmp_path: Path) -> None:
    from codeatlas.git_integration import ChangedSymbol, ChangeImpact
    from codeatlas.models import Position, Span, Symbol, SymbolKind

    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])

    changed_sym = Symbol(
        id="helpers.py::add",
        name="add",
        qualified_name="add",
        kind=SymbolKind.FUNCTION,
        file_path="helpers.py",
        span=Span(start=Position(line=2, column=0), end=Position(line=4, column=0)),
        language="python",
    )
    affected_sym = Symbol(
        id="main.py::run",
        name="run",
        qualified_name="run",
        kind=SymbolKind.FUNCTION,
        file_path="main.py",
        span=Span(start=Position(line=0, column=0), end=Position(line=5, column=0)),
        language="python",
    )
    mock_impact.return_value = ChangeImpact(
        changed_files=["helpers.py"],
        changed_symbols=[ChangedSymbol(symbol=changed_sym, change_type="modified")],
        affected_symbols=[affected_sym],
        affected_files=["main.py"],
    )

    result = runner.invoke(cli, ["impact", str(repo), "--db", db_path])
    assert result.exit_code == 0
    assert "changed files" in result.output.lower()
    assert "affected symbols" in result.output.lower()
    assert "affected files" in result.output.lower()


# --- coupling with data ---


def test_coupling_with_cross_file_deps(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("from b import helper\ndef main():\n    helper()\n")
    (tmp_path / "b.py").write_text("def helper():\n    pass\n")
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(tmp_path), "--db", db_path])
    result = runner.invoke(cli, ["coupling", "--db", db_path])
    assert result.exit_code == 0


# --- find-path: target symbol missing ---


def test_find_path_target_missing(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["index", str(repo), "--db", db_path])
    result = runner.invoke(cli, ["find-path", "run", "nonexistent_xyz", "--db", db_path])
    assert result.exit_code == 0
    assert "not found" in result.output.lower()
