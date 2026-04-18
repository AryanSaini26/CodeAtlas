"""FastAPI app factory for the CodeAtlas HTTP API."""

from __future__ import annotations

from pathlib import Path

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
except ImportError as exc:
    raise ImportError(
        "FastAPI is required for codeatlas.api. Install with: pip install 'codeatlas[api]'"
    ) from exc

from codeatlas.api.routes import build_router
from codeatlas.graph.store import GraphStore


def create_app(
    db_path: str | Path,
    allow_origins: list[str] | None = None,
    api_key: str | None = None,
) -> FastAPI:
    """Build a FastAPI app backed by a ``GraphStore``.

    The caller owns the ``db_path``; the app opens a single read-mostly
    connection against it. Pass ``api_key`` to require ``X-API-Key`` on
    every request.
    """
    store = GraphStore(Path(db_path))

    app = FastAPI(
        title="CodeAtlas API",
        version="1.0.0",
        description="HTTP/JSON interface over a CodeAtlas knowledge graph.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins or ["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(build_router(store, api_key=api_key), prefix="/api/v1")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": "1.0.0"}

    @app.on_event("shutdown")
    def _close_store() -> None:
        store.close()

    return app
