"""Tests for the Prometheus /metrics endpoint."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("prometheus_client")

from fastapi.testclient import TestClient  # noqa: E402

from codeatlas.api.app import create_app  # noqa: E402
from codeatlas.graph.store import GraphStore  # noqa: E402


def _db(tmp_path: Path) -> Path:
    db = tmp_path / "graph.db"
    GraphStore(db).close()
    return db


def test_metrics_endpoint_exposes_prometheus(tmp_path: Path) -> None:
    app = create_app(db_path=_db(tmp_path))
    client = TestClient(app)
    # Generate at least one request so the counter is populated.
    client.get("/health")
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    body = resp.text
    assert "codeatlas_http_requests_total" in body
    assert "codeatlas_http_request_duration_seconds" in body
