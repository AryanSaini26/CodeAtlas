"""Pydantic response models for the HTTP API.

Keep these stable — the web UI and any third-party consumers key off them.
Breaking changes go behind a new ``/api/vN`` prefix rather than mutating the
existing shape.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    id: str
    name: str
    qualified_name: str
    kind: str
    file: str
    community_id: str | None = None


class GraphLink(BaseModel):
    source: str
    target: str
    kind: str
    confidence: str = "extracted"


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    links: list[GraphLink]
    truncated: bool = False


class StatsResponse(BaseModel):
    files: int
    symbols: int
    relationships: int
    languages: dict[str, int]
    kinds: dict[str, int]


class SymbolRef(BaseModel):
    id: str
    name: str
    qualified_name: str
    kind: str
    file: str
    line: int | None = None


class SymbolDetails(BaseModel):
    id: str
    name: str
    qualified_name: str
    kind: str
    file: str
    start_line: int
    end_line: int
    signature: str | None = None
    docstring: str | None = None
    incoming: list[SymbolRef] = Field(default_factory=list)
    outgoing: list[SymbolRef] = Field(default_factory=list)


class SearchHit(BaseModel):
    id: str
    name: str
    qualified_name: str
    kind: str
    file: str
    score: float | None = None


class SearchResponse(BaseModel):
    query: str
    count: int
    offset: int
    has_more: bool
    next_offset: int | None = None
    hits: list[SearchHit]


class PageRankEntry(BaseModel):
    id: str
    name: str
    qualified_name: str
    kind: str
    file: str
    score: float


class PageRankResponse(BaseModel):
    count: int
    ranking: list[PageRankEntry]


class HotspotEntry(BaseModel):
    file: str
    churn: int
    in_degree: int
    score: float


class HotspotsResponse(BaseModel):
    count: int
    hotspots: list[HotspotEntry]


class CommunitySummary(BaseModel):
    community_id: str
    size: int
    sample_symbols: list[str]


class CommunitiesResponse(BaseModel):
    count: int
    communities: list[CommunitySummary]


class CoverageGapEntry(BaseModel):
    id: str
    name: str
    qualified_name: str
    kind: str
    file: str
    line: int


class CoverageGapsResponse(BaseModel):
    count: int
    offset: int
    has_more: bool
    next_offset: int | None = None
    gaps: list[CoverageGapEntry]


class ErrorResponse(BaseModel):
    error: str
    field: str | None = None
    value: str | None = None
