"""Tests for the CLI commands."""

from pathlib import Path

from click.testing import CliRunner

from codeatlas.cli import cli


def _make_repo(tmp_path: Path) -> Path:
    """Create a minimal repo with a couple of Python files."""
    (tmp_path / "main.py").write_text(
        'def run():\n    """Run the app."""\n    greet("world")\n\n'
        'def greet(name: str) -> str:\n    return f"Hello, {name}"\n'
    )
    (tmp_path / "helpers.py").write_text(
        'MAX = 10\n\ndef add(a: int, b: int) -> int:\n    return a + b\n'
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
    assert "already exists" in result.output


# --- config file loading ---


def test_index_with_config_file(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    # Create a config that only indexes .py files with a custom max size
    (repo / "codeatlas.toml").write_text(
        '[codeatlas]\n\n'
        '[codeatlas.parser]\n'
        'max_file_size_kb = 500\n'
        'include_extensions = [".py"]\n'
    )
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    result = runner.invoke(cli, ["index", str(repo), "--db", db_path])
    assert result.exit_code == 0
