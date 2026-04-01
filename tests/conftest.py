"""Shared pytest fixtures for CodeAtlas tests."""

from pathlib import Path

import pytest

from codeatlas.graph.store import GraphStore
from codeatlas.parsers.python_parser import PythonParser
from codeatlas.parsers.typescript_parser import TypeScriptParser

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def python_parser() -> PythonParser:
    return PythonParser()


@pytest.fixture
def typescript_parser() -> TypeScriptParser:
    return TypeScriptParser()


@pytest.fixture
def graph_store() -> GraphStore:
    """In-memory graph store, fresh per test."""
    return GraphStore(":memory:")


@pytest.fixture
def sample_python_path() -> Path:
    return FIXTURES_DIR / "sample_python" / "sample_module.py"


@pytest.fixture
def sample_python_source(sample_python_path: Path) -> str:
    return sample_python_path.read_text()


@pytest.fixture
def sample_typescript_path() -> Path:
    return FIXTURES_DIR / "sample_typescript" / "sample_module.ts"


@pytest.fixture
def sample_typescript_source(sample_typescript_path: Path) -> str:
    return sample_typescript_path.read_text()
