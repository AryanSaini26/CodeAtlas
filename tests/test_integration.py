"""End-to-end integration tests for the full CodeAtlas pipeline.

Tests the complete flow: parse files -> store in graph -> search -> export.
"""

import json
from pathlib import Path

import pytest

from codeatlas.config import CodeAtlasConfig, GraphConfig
from codeatlas.graph.export import ExportOptions, export_dot, export_json
from codeatlas.graph.store import GraphStore
from codeatlas.indexer import RepoIndexer


@pytest.fixture
def multi_lang_repo(tmp_path: Path) -> Path:
    """Create a repo with Python, TypeScript, and Go files that reference each other."""
    # Python: a service with imports and calls
    (tmp_path / "service.py").write_text(
        "from pathlib import Path\n\n"
        "class UserService:\n"
        '    """Manages user operations."""\n\n'
        "    def get_user(self, user_id: int) -> dict:\n"
        '        """Fetch a user by ID."""\n'
        "        return validate(user_id)\n\n"
        "def validate(user_id: int) -> dict:\n"
        '    """Validate and return user data."""\n'
        '    return {"id": user_id}\n'
    )

    # Python: a second file that imports from the first
    (tmp_path / "handler.py").write_text(
        "from service import UserService\n\n"
        "def handle_request(uid: int) -> dict:\n"
        '    """Handle an incoming request."""\n'
        "    svc = UserService()\n"
        "    return svc.get_user(uid)\n"
    )

    # TypeScript: an API layer
    (tmp_path / "api.ts").write_text(
        'import { Router } from "express";\n\n'
        "interface ApiResponse {\n"
        "    status: number;\n"
        "    data: unknown;\n"
        "}\n\n"
        "export function createRouter(): Router {\n"
        "    const router = Router();\n"
        "    return router;\n"
        "}\n\n"
        "export class ApiClient {\n"
        "    async fetch(url: string): Promise<ApiResponse> {\n"
        "        return { status: 200, data: null };\n"
        "    }\n"
        "}\n"
    )

    # Go: a utility module
    (tmp_path / "util.go").write_text(
        "package util\n\n"
        'import "fmt"\n\n'
        "// FormatID formats an integer ID as a string.\n"
        "func FormatID(id int) string {\n"
        '    return fmt.Sprintf("id-%d", id)\n'
        "}\n\n"
        "type Config struct {\n"
        "    Host string\n"
        "    Port int\n"
        "}\n"
    )
    return tmp_path


@pytest.fixture
def indexed_store(multi_lang_repo: Path) -> GraphStore:
    """Index the multi-language repo and return the populated store."""
    store = GraphStore(":memory:")
    config = CodeAtlasConfig(
        repo_root=multi_lang_repo,
        graph=GraphConfig(db_path=Path(":memory:")),
    )
    indexer = RepoIndexer(config, store)
    indexer.index_full(resolve=True)
    return store


# --- Pipeline: index -> stats ---


def test_stats_after_indexing(indexed_store: GraphStore) -> None:
    stats = indexed_store.get_stats()
    assert stats["files"] == 4  # .py, .py, .ts, .go
    assert stats["symbols"] > 10
    assert stats["relationships"] > 0


# --- Pipeline: index -> symbol lookup ---


def test_find_python_class(indexed_store: GraphStore) -> None:
    results = indexed_store.find_symbols_by_name("UserService")
    classes = [s for s in results if s.kind.value == "class"]
    assert len(classes) == 1
    assert classes[0].language == "python"


def test_find_typescript_interface(indexed_store: GraphStore) -> None:
    results = indexed_store.find_symbols_by_name("ApiResponse")
    assert len(results) == 1
    assert results[0].kind.value == "interface"
    assert results[0].language == "typescript"


def test_find_go_function(indexed_store: GraphStore) -> None:
    results = indexed_store.find_symbols_by_name("FormatID")
    assert len(results) == 1
    assert results[0].kind.value == "function"
    assert results[0].language == "go"


def test_find_go_struct(indexed_store: GraphStore) -> None:
    results = indexed_store.find_symbols_by_name("Config")
    assert len(results) == 1
    assert results[0].kind.value == "class"  # struct maps to CLASS


# --- Pipeline: index -> FTS search ---


def test_fts_search_by_name(indexed_store: GraphStore) -> None:
    results = indexed_store.search("validate")
    names = [s.name for s in results]
    assert "validate" in names


def test_fts_search_by_docstring(indexed_store: GraphStore) -> None:
    results = indexed_store.search("incoming request")
    names = [s.name for s in results]
    assert "handle_request" in names


# --- Pipeline: index -> dependency graph ---


def test_call_chain_from_function(indexed_store: GraphStore) -> None:
    syms = indexed_store.find_symbols_by_name("handle_request")
    assert len(syms) >= 1
    chain = indexed_store.trace_call_chain(syms[0].id, max_depth=5)
    # handle_request calls UserService() and svc.get_user
    assert len(chain) >= 1


def test_impact_analysis(indexed_store: GraphStore) -> None:
    syms = indexed_store.find_symbols_by_name("validate")
    assert len(syms) >= 1
    impact = indexed_store.get_impact_analysis(syms[0].id, max_depth=5)
    # validate is called by UserService.get_user
    callers = [row["source_id"] for row in impact]
    assert any("get_user" in c for c in callers)


# --- Pipeline: index -> file dependencies ---


def test_file_dependencies(indexed_store: GraphStore, multi_lang_repo: Path) -> None:
    service_path = str(multi_lang_repo / "service.py")
    deps = indexed_store.get_file_dependencies(service_path)
    assert isinstance(deps["depends_on"], list)
    assert isinstance(deps["depended_by"], list)


# --- Pipeline: index -> module overview ---


def test_module_overview(indexed_store: GraphStore, multi_lang_repo: Path) -> None:
    overview = indexed_store.get_module_overview(str(multi_lang_repo))
    assert overview["file_count"] == 4
    assert overview["symbol_count"] > 10


# --- Pipeline: index -> export ---


def test_export_dot_format(indexed_store: GraphStore) -> None:
    dot = export_dot(indexed_store, ExportOptions())
    assert "digraph" in dot
    assert "UserService" in dot
    assert "FormatID" in dot


def test_export_json_format(indexed_store: GraphStore) -> None:
    raw = export_json(indexed_store, ExportOptions())
    data = json.loads(raw)
    assert "nodes" in data
    assert "links" in data
    assert len(data["nodes"]) > 10

    # Check that nodes have expected fields
    node = data["nodes"][0]
    assert "id" in node
    assert "name" in node
    assert "kind" in node


def test_export_with_file_filter(indexed_store: GraphStore, multi_lang_repo: Path) -> None:
    opts = ExportOptions(file_filter=str(multi_lang_repo / "service.py"))
    raw = export_json(indexed_store, opts)
    data = json.loads(raw)
    # Should only contain symbols from service.py
    files = {n.get("file") for n in data["nodes"]}
    assert all(str(multi_lang_repo / "service.py") in f for f in files if f)


# --- Pipeline: index -> incremental re-index ---


def test_incremental_after_file_change(multi_lang_repo: Path) -> None:
    store = GraphStore(":memory:")
    config = CodeAtlasConfig(
        repo_root=multi_lang_repo,
        graph=GraphConfig(db_path=Path(":memory:")),
    )
    indexer = RepoIndexer(config, store)
    indexer.index_full(resolve=False)

    initial_stats = store.get_stats()

    # Modify a file to add a new function
    service = multi_lang_repo / "service.py"
    service.write_text(
        service.read_text()
        + '\ndef audit_log(msg: str) -> None:\n    """Log an audit event."""\n    pass\n'
    )

    stats = indexer.index_incremental(resolve=False)
    assert stats["parsed"] == 1

    # New function should be findable
    results = store.find_symbols_by_name("audit_log")
    assert len(results) == 1

    # Total symbols should have increased
    new_stats = store.get_stats()
    assert new_stats["symbols"] > initial_stats["symbols"]


# --- Cross-language in same graph ---


def test_all_languages_coexist(indexed_store: GraphStore) -> None:
    """Verify all three languages are represented in the same graph."""
    py_syms = [
        s for s in indexed_store.find_symbols_by_name("UserService") if s.language == "python"
    ]
    ts_syms = [
        s for s in indexed_store.find_symbols_by_name("ApiClient") if s.language == "typescript"
    ]
    go_syms = [s for s in indexed_store.find_symbols_by_name("FormatID") if s.language == "go"]

    assert len(py_syms) >= 1
    assert len(ts_syms) >= 1
    assert len(go_syms) >= 1
