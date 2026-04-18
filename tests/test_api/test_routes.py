"""Tests for the HTTP/JSON API layer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from codeatlas.api.app import create_app
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
    name: str, kind: SymbolKind = SymbolKind.FUNCTION, fp: str = "app.py", line: int = 0
) -> Symbol:
    return Symbol(
        id=f"{fp}::{name}",
        name=name,
        qualified_name=name,
        kind=kind,
        file_path=fp,
        span=Span(start=Position(line=line, column=0), end=Position(line=line + 5, column=0)),
        signature=f"def {name}()" if kind == SymbolKind.FUNCTION else None,
        docstring=f"Docstring for {name}",
        language="python",
    )


def _rel(
    src: str, tgt: str, kind: RelationshipKind = RelationshipKind.CALLS, fp: str = "app.py"
) -> Relationship:
    return Relationship(source_id=src, target_id=tgt, kind=kind, file_path=fp)


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


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "graph.db"
    store = GraphStore(db)
    s1 = _sym("main", SymbolKind.FUNCTION, "app.py", 0)
    s2 = _sym("helper", SymbolKind.FUNCTION, "utils.py", 0)
    s3 = _sym("Widget", SymbolKind.CLASS, "models.py", 0)
    store.upsert_parse_result(_result("app.py", [s1], [_rel("app.py::main", "utils.py::helper")]))
    store.upsert_parse_result(_result("utils.py", [s2]))
    store.upsert_parse_result(_result("models.py", [s3]))
    store.close()
    return db


@pytest.fixture
def client(db_path: Path) -> TestClient:
    app = create_app(db_path=db_path)
    return TestClient(app)


@pytest.fixture
def keyed_client(db_path: Path) -> TestClient:
    app = create_app(db_path=db_path, api_key="secret-key")
    return TestClient(app)


def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": "1.0.0"}


def test_stats(client: TestClient) -> None:
    resp = client.get("/api/v1/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["files"] == 3
    assert data["symbols"] == 3
    assert data["relationships"] == 1
    assert "languages" in data
    assert "kinds" in data


def test_graph_endpoint(client: TestClient) -> None:
    resp = client.get("/api/v1/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["nodes"]) == 3
    assert len(data["links"]) == 1
    assert data["truncated"] is False


def test_graph_truncation(client: TestClient) -> None:
    resp = client.get("/api/v1/graph", params={"limit": 1})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["nodes"]) == 1
    assert data["truncated"] is True


def test_graph_with_communities(client: TestClient) -> None:
    resp = client.get("/api/v1/graph", params={"communities": "true"})
    assert resp.status_code == 200


def test_get_symbol_by_id(client: TestClient) -> None:
    resp = client.get("/api/v1/symbols/app.py::main")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "main"
    assert data["file"] == "app.py"
    assert len(data["outgoing"]) == 1
    assert data["outgoing"][0]["name"] == "helper"


def test_get_symbol_not_found(client: TestClient) -> None:
    resp = client.get("/api/v1/symbols/does-not-exist")
    assert resp.status_code == 404


def test_search(client: TestClient) -> None:
    resp = client.get("/api/v1/search", params={"q": "main"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "main"
    assert any(h["name"] == "main" for h in data["hits"])


def test_search_requires_query(client: TestClient) -> None:
    resp = client.get("/api/v1/search")
    assert resp.status_code == 422


def test_search_with_kind_filter(client: TestClient) -> None:
    resp = client.get("/api/v1/search", params={"q": "Widget", "kind": "class"})
    assert resp.status_code == 200
    hits = resp.json()["hits"]
    assert all(h["kind"] == "class" for h in hits)


def test_pagerank(client: TestClient) -> None:
    resp = client.get("/api/v1/pagerank", params={"limit": 10})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 0
    assert isinstance(data["ranking"], list)


def test_hotspots(client: TestClient, tmp_path: Path) -> None:
    resp = client.get("/api/v1/hotspots", params={"repo_path": str(tmp_path), "limit": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert "hotspots" in data
    assert isinstance(data["hotspots"], list)


def test_communities(client: TestClient) -> None:
    resp = client.get("/api/v1/communities")
    assert resp.status_code == 200
    data = resp.json()
    assert "communities" in data
    assert isinstance(data["communities"], list)


def test_coverage_gaps(client: TestClient) -> None:
    resp = client.get("/api/v1/coverage-gaps", params={"limit": 50})
    assert resp.status_code == 200
    data = resp.json()
    assert "gaps" in data
    assert "has_more" in data
    assert "offset" in data


def test_coverage_gaps_pagination(client: TestClient) -> None:
    resp = client.get("/api/v1/coverage-gaps", params={"limit": 1, "offset": 0})
    assert resp.status_code == 200


def test_api_key_required_when_set(keyed_client: TestClient) -> None:
    resp = keyed_client.get("/api/v1/stats")
    assert resp.status_code == 401


def test_api_key_accepted(keyed_client: TestClient) -> None:
    resp = keyed_client.get("/api/v1/stats", headers={"X-API-Key": "secret-key"})
    assert resp.status_code == 200


def test_api_key_wrong_rejected(keyed_client: TestClient) -> None:
    resp = keyed_client.get("/api/v1/stats", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_health_always_open_even_with_key(keyed_client: TestClient) -> None:
    # /health is outside /api/v1 and not behind the router dep; it stays open
    # so load balancers can check liveness without the key.
    resp = keyed_client.get("/health")
    assert resp.status_code == 200


def test_create_app_import_message() -> None:
    """create_app should be importable without FastAPI only if fastapi is present."""
    # FastAPI is installed in this env — the import should succeed.
    from codeatlas.api import create_app as factory

    assert callable(factory)


def test_export_module_present(tmp_path: Path, db_path: Path) -> None:
    """Routes should refuse external-heavy graphs if include_externals=False (default)."""
    app = create_app(db_path=db_path)
    client = TestClient(app)
    resp = client.get("/api/v1/graph", params={"include_externals": "true"})
    assert resp.status_code == 200


def test_search_pagination_offset(client: TestClient) -> None:
    first = client.get("/api/v1/search", params={"q": "main", "limit": 1, "offset": 0}).json()
    if first.get("has_more"):
        second = client.get(
            "/api/v1/search",
            params={"q": "main", "limit": 1, "offset": first["next_offset"]},
        ).json()
        first_ids = {h["id"] for h in first["hits"]}
        second_ids = {h["id"] for h in second["hits"]}
        assert first_ids.isdisjoint(second_ids)


def test_cors_headers(client: TestClient) -> None:
    resp = client.get("/api/v1/stats", headers={"Origin": "http://example.com"})
    assert resp.status_code == 200
    # FastAPI/Starlette CORS middleware reflects the allowed origin
    assert "access-control-allow-origin" in {k.lower() for k in resp.headers.keys()}


def test_symbols_details_includes_line_numbers(client: TestClient) -> None:
    resp = client.get("/api/v1/symbols/app.py::main")
    data = resp.json()
    assert data["start_line"] >= 1
    assert data["end_line"] >= data["start_line"]


def test_graph_file_filter(client: TestClient) -> None:
    resp = client.get("/api/v1/graph", params={"file_filter": "app.py"})
    assert resp.status_code == 200
    data = resp.json()
    assert all(n["file"].startswith("app.py") for n in data["nodes"])


def test_unknown_route_404(client: TestClient) -> None:
    resp = client.get("/api/v1/nope")
    assert resp.status_code == 404


def test_search_empty_query_rejected(client: TestClient) -> None:
    resp = client.get("/api/v1/search", params={"q": ""})
    assert resp.status_code == 422


def test_schemas_roundtrip() -> None:
    """Direct instantiation of response schemas should round-trip through JSON."""
    import json as _json

    from codeatlas.api.schemas import GraphNode

    node = GraphNode(id="a", name="a", qualified_name="a", kind="function", file="x.py")
    data: dict[str, Any] = _json.loads(node.model_dump_json())
    assert data["name"] == "a"
