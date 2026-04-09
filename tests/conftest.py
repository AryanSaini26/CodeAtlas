"""Shared pytest fixtures for CodeAtlas tests."""

from pathlib import Path

import pytest

from codeatlas.graph.store import GraphStore
from codeatlas.parsers.cpp_parser import CppParser
from codeatlas.parsers.csharp_parser import CSharpParser
from codeatlas.parsers.go_parser import GoParser
from codeatlas.parsers.java_parser import JavaParser
from codeatlas.parsers.python_parser import PythonParser
from codeatlas.parsers.ruby_parser import RubyParser
from codeatlas.parsers.rust_parser import RustParser
from codeatlas.parsers.typescript_parser import TypeScriptParser

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def python_parser() -> PythonParser:
    return PythonParser()


@pytest.fixture
def typescript_parser() -> TypeScriptParser:
    return TypeScriptParser()


@pytest.fixture
def go_parser() -> GoParser:
    return GoParser()


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


@pytest.fixture
def sample_go_path() -> Path:
    return FIXTURES_DIR / "sample_go" / "sample_module.go"


@pytest.fixture
def sample_go_source(sample_go_path: Path) -> str:
    return sample_go_path.read_text()


@pytest.fixture
def rust_parser() -> RustParser:
    return RustParser()


@pytest.fixture
def sample_rust_path() -> Path:
    return FIXTURES_DIR / "sample_rust" / "sample_module.rs"


@pytest.fixture
def sample_rust_source(sample_rust_path: Path) -> str:
    return sample_rust_path.read_text()


@pytest.fixture
def java_parser() -> JavaParser:
    return JavaParser()


@pytest.fixture
def sample_java_path() -> Path:
    return FIXTURES_DIR / "sample_java" / "SampleModule.java"


@pytest.fixture
def sample_java_source(sample_java_path: Path) -> str:
    return sample_java_path.read_text()


@pytest.fixture
def cpp_parser() -> CppParser:
    return CppParser()


@pytest.fixture
def sample_cpp_path() -> Path:
    return FIXTURES_DIR / "sample_cpp" / "sample_module.cpp"


@pytest.fixture
def sample_cpp_source(sample_cpp_path: Path) -> str:
    return sample_cpp_path.read_text()


@pytest.fixture
def csharp_parser() -> CSharpParser:
    return CSharpParser()


@pytest.fixture
def sample_csharp_path() -> Path:
    return FIXTURES_DIR / "sample_csharp" / "SampleModule.cs"


@pytest.fixture
def sample_csharp_source(sample_csharp_path: Path) -> str:
    return sample_csharp_path.read_text()


@pytest.fixture
def ruby_parser() -> RubyParser:
    return RubyParser()


@pytest.fixture
def sample_ruby_path() -> Path:
    return FIXTURES_DIR / "sample_ruby" / "sample_module.rb"


@pytest.fixture
def sample_ruby_source(sample_ruby_path: Path) -> str:
    return sample_ruby_path.read_text()
