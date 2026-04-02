"""Tests for configuration loading."""

from pathlib import Path

from codeatlas.config import CodeAtlasConfig


def test_find_and_load_defaults(tmp_path: Path) -> None:
    config = CodeAtlasConfig.find_and_load(tmp_path)
    assert config.repo_root == tmp_path
    assert ".py" in config.parser.include_extensions
    assert ".git" in config.exclude_dirs


def test_find_and_load_from_toml(tmp_path: Path) -> None:
    (tmp_path / "codeatlas.toml").write_text(
        "[codeatlas]\n"
        'exclude_dirs = [".git", "vendor"]\n\n'
        "[codeatlas.parser]\n"
        "max_file_size_kb = 200\n"
        'include_extensions = [".py", ".go"]\n'
    )
    config = CodeAtlasConfig.find_and_load(tmp_path)
    assert config.repo_root == tmp_path
    assert config.parser.max_file_size_kb == 200
    assert ".go" in config.parser.include_extensions
    assert ".ts" not in config.parser.include_extensions
    assert "vendor" in config.exclude_dirs


def test_from_toml_direct(tmp_path: Path) -> None:
    toml_path = tmp_path / "codeatlas.toml"
    toml_path.write_text("[codeatlas]\n\n[codeatlas.parser]\nmax_file_size_kb = 1000\n")
    config = CodeAtlasConfig.from_toml(toml_path)
    assert config.parser.max_file_size_kb == 1000
    # Defaults still apply for unset fields
    assert ".py" in config.parser.include_extensions


def test_find_and_load_no_toml(tmp_path: Path) -> None:
    # No codeatlas.toml -> should return defaults
    config = CodeAtlasConfig.find_and_load(tmp_path)
    assert config.parser.max_file_size_kb == 500
    assert config.repo_root == tmp_path
