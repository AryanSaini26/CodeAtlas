"""Shared pytest fixtures for CodeAtlas tests."""

from pathlib import Path

import pytest

from codeatlas.graph.store import GraphStore
from codeatlas.parsers.bash_parser import BashParser
from codeatlas.parsers.cpp_parser import CppParser
from codeatlas.parsers.csharp_parser import CSharpParser
from codeatlas.parsers.elixir_parser import ElixirParser
from codeatlas.parsers.go_parser import GoParser
from codeatlas.parsers.java_parser import JavaParser
from codeatlas.parsers.javascript_parser import JavaScriptParser
from codeatlas.parsers.kotlin_parser import KotlinParser
from codeatlas.parsers.lua_parser import LuaParser
from codeatlas.parsers.php_parser import PhpParser
from codeatlas.parsers.python_parser import PythonParser
from codeatlas.parsers.ruby_parser import RubyParser
from codeatlas.parsers.rust_parser import RustParser
from codeatlas.parsers.scala_parser import ScalaParser
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


@pytest.fixture
def javascript_parser() -> JavaScriptParser:
    return JavaScriptParser()


@pytest.fixture
def sample_javascript_path() -> Path:
    return FIXTURES_DIR / "sample_javascript" / "sample_module.js"


@pytest.fixture
def sample_javascript_source(sample_javascript_path: Path) -> str:
    return sample_javascript_path.read_text()


@pytest.fixture
def kotlin_parser() -> KotlinParser:
    return KotlinParser()


@pytest.fixture
def sample_kotlin_path() -> Path:
    return FIXTURES_DIR / "sample_kotlin" / "SampleModule.kt"


@pytest.fixture
def sample_kotlin_source(sample_kotlin_path: Path) -> str:
    return sample_kotlin_path.read_text()


@pytest.fixture
def php_parser() -> PhpParser:
    return PhpParser()


@pytest.fixture
def sample_php_path() -> Path:
    return FIXTURES_DIR / "sample_php" / "SampleModule.php"


@pytest.fixture
def sample_php_source(sample_php_path: Path) -> str:
    return sample_php_path.read_text()


@pytest.fixture
def scala_parser() -> ScalaParser:
    return ScalaParser()


@pytest.fixture
def sample_scala_path() -> Path:
    return FIXTURES_DIR / "sample_scala" / "SampleModule.scala"


@pytest.fixture
def sample_scala_source(sample_scala_path: Path) -> str:
    return sample_scala_path.read_text()


@pytest.fixture
def bash_parser() -> BashParser:
    return BashParser()


@pytest.fixture
def sample_bash_path() -> Path:
    return FIXTURES_DIR / "sample_bash" / "sample_script.sh"


@pytest.fixture
def sample_bash_source(sample_bash_path: Path) -> str:
    return sample_bash_path.read_text()


@pytest.fixture
def lua_parser() -> LuaParser:
    return LuaParser()


@pytest.fixture
def sample_lua_path() -> Path:
    return FIXTURES_DIR / "sample_lua" / "sample_module.lua"


@pytest.fixture
def sample_lua_source(sample_lua_path: Path) -> str:
    return sample_lua_path.read_text()


@pytest.fixture
def elixir_parser() -> ElixirParser:
    return ElixirParser()


@pytest.fixture
def sample_elixir_path() -> Path:
    return FIXTURES_DIR / "sample_elixir" / "sample_module.ex"


@pytest.fixture
def sample_elixir_source(sample_elixir_path: Path) -> str:
    return sample_elixir_path.read_text()
