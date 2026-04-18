"""HTTP routes over ``GraphStore``.

Each route is a thin wrapper — no business logic lives here. Responses use
the schemas from ``codeatlas.api.schemas``; store helpers do the real work.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from codeatlas.api import schemas
from codeatlas.graph.export import ExportOptions, export_json
from codeatlas.graph.store import GraphStore

_MAX_LIMIT = 500


def _clamp_limit(limit: int, field: str = "limit") -> int:
    if limit < 1:
        raise HTTPException(
            status_code=400, detail={"error": f"{field} must be >= 1", "field": field}
        )
    return min(limit, _MAX_LIMIT)


def _check_auth(api_key: str | None, header_value: str | None) -> None:
    if api_key is None:
        return
    if header_value != api_key:
        raise HTTPException(status_code=401, detail={"error": "invalid API key"})


def build_router(store: GraphStore, api_key: str | None = None) -> APIRouter:
    async def auth_dep(x_api_key: str | None = Header(default=None)) -> None:
        _check_auth(api_key, x_api_key)

    dependencies = [Depends(auth_dep)] if api_key is not None else []
    router = APIRouter(dependencies=dependencies)

    @router.get("/stats", response_model=schemas.StatsResponse)
    async def get_stats(_: None = None) -> schemas.StatsResponse:
        base = store.get_stats()
        return schemas.StatsResponse(
            files=base["files"],
            symbols=base["symbols"],
            relationships=base["relationships"],
            languages=store.get_language_breakdown(),
            kinds=store.get_kind_breakdown(),
        )

    @router.get("/graph", response_model=schemas.GraphResponse)
    async def get_graph(
        file_filter: str | None = Query(default=None),
        communities: bool = Query(default=False),
        include_externals: bool = Query(default=False),
        limit: int = Query(default=2000, ge=1, le=10000),
    ) -> schemas.GraphResponse:
        opts = ExportOptions(
            file_filter=file_filter,
            include_communities=communities,
            include_externals=include_externals,
        )
        data = json.loads(export_json(store, opts))
        nodes = data["nodes"]
        links = data["links"]
        truncated = False
        if len(nodes) > limit:
            kept_ids = {n["id"] for n in nodes[:limit]}
            nodes = nodes[:limit]
            links = [lk for lk in links if lk["source"] in kept_ids and lk["target"] in kept_ids]
            truncated = True
        return schemas.GraphResponse(
            nodes=[schemas.GraphNode(**n) for n in nodes],
            links=[schemas.GraphLink(**lk) for lk in links],
            truncated=truncated,
        )

    @router.get("/symbols/{symbol_id}", response_model=schemas.SymbolDetails)
    async def get_symbol(symbol_id: str) -> schemas.SymbolDetails:
        sym = store.get_symbol_by_id(symbol_id)
        if sym is None:
            raise HTTPException(status_code=404, detail={"error": f"symbol {symbol_id} not found"})
        outgoing_rels = store.get_dependencies(sym.id)
        incoming_rels = store.get_dependents(sym.id)

        def _as_refs(rels: list[Any], *, attr: str) -> list[schemas.SymbolRef]:
            refs: list[schemas.SymbolRef] = []
            for r in rels:
                other_id = getattr(r, attr)
                other = store.get_symbol_by_id(other_id)
                if other is None:
                    continue
                refs.append(
                    schemas.SymbolRef(
                        id=other.id,
                        name=other.name,
                        qualified_name=other.qualified_name,
                        kind=other.kind.value,
                        file=other.file_path,
                        line=other.span.start.line + 1,
                    )
                )
            return refs

        return schemas.SymbolDetails(
            id=sym.id,
            name=sym.name,
            qualified_name=sym.qualified_name,
            kind=sym.kind.value,
            file=sym.file_path,
            start_line=sym.span.start.line + 1,
            end_line=sym.span.end.line + 1,
            signature=sym.signature,
            docstring=sym.docstring,
            outgoing=_as_refs(outgoing_rels, attr="target_id"),
            incoming=_as_refs(incoming_rels, attr="source_id"),
        )

    @router.get("/search", response_model=schemas.SearchResponse)
    async def search(
        q: str = Query(..., min_length=1),
        kind: str | None = None,
        file: str | None = None,
        limit: int = Query(default=20, ge=1, le=_MAX_LIMIT),
        offset: int = Query(default=0, ge=0),
    ) -> schemas.SearchResponse:
        clamped = _clamp_limit(limit)
        probe = store.search(q, limit=clamped + offset + 1, file_filter=file, kind_filter=kind)
        page = probe[offset : offset + clamped]
        has_more = len(probe) > offset + clamped
        hits = [
            schemas.SearchHit(
                id=s.id,
                name=s.name,
                qualified_name=s.qualified_name,
                kind=s.kind.value,
                file=s.file_path,
            )
            for s in page
        ]
        return schemas.SearchResponse(
            query=q,
            count=len(hits),
            offset=offset,
            has_more=has_more,
            next_offset=offset + len(hits) if has_more else None,
            hits=hits,
        )

    @router.get("/pagerank", response_model=schemas.PageRankResponse)
    async def pagerank(
        limit: int = Query(default=20, ge=1, le=_MAX_LIMIT),
        kind: str | None = None,
    ) -> schemas.PageRankResponse:
        results = store.get_pagerank_ranking(limit=_clamp_limit(limit), kind_filter=kind)
        return schemas.PageRankResponse(
            count=len(results),
            ranking=[schemas.PageRankEntry(**r) for r in results],
        )

    @router.get("/hotspots", response_model=schemas.HotspotsResponse)
    async def hotspots(
        repo_path: str = Query(default="."),
        limit: int = Query(default=20, ge=1, le=_MAX_LIMIT),
    ) -> schemas.HotspotsResponse:
        results = store.get_hotspots(repo_path, limit=_clamp_limit(limit))
        return schemas.HotspotsResponse(
            count=len(results),
            hotspots=[schemas.HotspotEntry(**r) for r in results],
        )

    @router.get("/communities", response_model=schemas.CommunitiesResponse)
    async def communities() -> schemas.CommunitiesResponse:
        mapping = store.detect_communities()
        by_community: dict[str, list[str]] = {}
        for sym_id, comm in mapping.items():
            by_community.setdefault(comm, []).append(sym_id)
        summaries: list[schemas.CommunitySummary] = []
        for comm, members in sorted(by_community.items(), key=lambda kv: -len(kv[1])):
            sample_ids = members[:5]
            samples: list[str] = []
            for sid in sample_ids:
                sym = store.get_symbol_by_id(sid)
                if sym:
                    samples.append(sym.qualified_name)
            summaries.append(
                schemas.CommunitySummary(
                    community_id=comm,
                    size=len(members),
                    sample_symbols=samples,
                )
            )
        return schemas.CommunitiesResponse(count=len(summaries), communities=summaries)

    @router.get("/coverage-gaps", response_model=schemas.CoverageGapsResponse)
    async def coverage_gaps(
        file_filter: str | None = None,
        limit: int = Query(default=100, ge=1, le=_MAX_LIMIT),
        offset: int = Query(default=0, ge=0),
    ) -> schemas.CoverageGapsResponse:
        clamped = _clamp_limit(limit)
        probe = store.get_coverage_gaps(file_filter=file_filter, limit=clamped + 1, offset=offset)
        page = probe[:clamped]
        has_more = len(probe) > clamped
        entries = [
            schemas.CoverageGapEntry(
                id=s.id,
                name=s.name,
                qualified_name=s.qualified_name,
                kind=s.kind.value,
                file=s.file_path,
                line=s.span.start.line + 1,
            )
            for s in page
        ]
        return schemas.CoverageGapsResponse(
            count=len(entries),
            offset=offset,
            has_more=has_more,
            next_offset=offset + len(entries) if has_more else None,
            gaps=entries,
        )

    return router
