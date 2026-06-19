"""FastAPI app factory for the CodeAtlas HTTP API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles
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
    static_dir: str | Path | None = None,
    hosted_db_path: str | Path | None = None,
) -> FastAPI:
    """Build a FastAPI app backed by a ``GraphStore``.

    The caller owns the ``db_path``; the app opens a single read-mostly
    connection against it. Pass ``api_key`` to require ``X-API-Key`` on
    every request. Pass ``static_dir`` pointing at a built frontend bundle
    (``frontend/dist``) to serve the SPA from the same origin under ``/``.
    """
    store = GraphStore(Path(db_path))
    hosted_store = None
    if hosted_db_path is not None:
        from codeatlas.hosted import HostedStore

        hosted_store = HostedStore(Path(hosted_db_path))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            store.close()
            if hosted_store is not None:
                hosted_store.close()

    app = FastAPI(
        title="CodeAtlas API",
        version="1.0.0",
        description="HTTP/JSON interface over a CodeAtlas knowledge graph.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins or ["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    eval_report_path = Path(db_path).parent / "eval" / "report.json"
    app.include_router(
        build_router(store, api_key=api_key, eval_report_path=eval_report_path),
        prefix="/api/v1",
    )
    if hosted_store is not None:
        from codeatlas.api.hosted_routes import build_hosted_router

        app.include_router(
            build_hosted_router(hosted_store),
            prefix="/api/hosted/v1",
            tags=["hosted"],
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": "1.0.0"}

    if static_dir is not None:
        dist = Path(static_dir)
        if not dist.is_dir():
            raise FileNotFoundError(
                f"Static directory {dist} does not exist. "
                "Run 'cd frontend && npm install && npm run build' first."
            )
        index_path = dist / "index.html"

        @app.get("/", include_in_schema=False)
        async def _index() -> FileResponse:
            return FileResponse(index_path)

        app.mount(
            "/",
            StaticFiles(directory=str(dist), html=True),
            name="ui",
        )

    return app
