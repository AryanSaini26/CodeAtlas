"""Tests for the cross-encoder reranking stage.

The real model is monkeypatched so these stay fast and offline; in CI
(sentence-transformers absent) the ``rerank`` mode falls back gracefully, which
is also covered here.
"""

from __future__ import annotations

from pathlib import Path

from codeatlas.agent_context import build_context_pack
from codeatlas.graph.store import GraphStore
from codeatlas.models import (
    FileInfo,
    ParseResult,
    Position,
    Span,
    Symbol,
    SymbolKind,
)
from codeatlas.search.rerank import CrossEncoderReranker


def _sym(name: str, fp: str) -> Symbol:
    return Symbol(
        id=f"{fp}::{name}",
        name=name,
        qualified_name=name,
        kind=SymbolKind.FUNCTION,
        file_path=fp,
        span=Span(start=Position(line=0, column=0), end=Position(line=4, column=0)),
        signature=f"def {name}()",
        docstring=f"docstring for {name}",
        language="python",
    )


def _graph(tmp_path: Path) -> Path:
    db = tmp_path / "graph.db"
    store = GraphStore(db)
    # Distinct files: upsert_parse_result replaces all symbols for a given file.
    for name, fp in [("login", "auth.py"), ("logout", "session.py"), ("render", "ui.py")]:
        store.upsert_parse_result(
            ParseResult(
                file_info=FileInfo(
                    path=fp,
                    language="python",
                    content_hash="x",
                    symbol_count=1,
                    relationship_count=0,
                ),
                symbols=[_sym(name, fp)],
                relationships=[],
            )
        )
    store.close()
    return db


class _FakeCrossEncoder:
    """Scores a pair higher when the query term appears in the document text."""

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        return [1.0 if query.lower() in doc.lower() else 0.0 for query, doc in pairs]


def test_cross_encoder_reranker_orders_by_score(monkeypatch) -> None:
    monkeypatch.setattr(CrossEncoderReranker, "_get_model", lambda self: _FakeCrossEncoder())
    symbols = [_sym("render", "ui.py"), _sym("login", "auth.py"), _sym("logout", "auth.py")]
    ranked = CrossEncoderReranker().rerank("login", symbols)
    assert ranked[0].name == "login"
    assert {s.name for s in ranked} == {"render", "login", "logout"}


def test_cross_encoder_reranker_empty() -> None:
    assert CrossEncoderReranker().rerank("anything", []) == []


def test_build_context_pack_rerank_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(CrossEncoderReranker, "_get_model", lambda self: _FakeCrossEncoder())
    store = GraphStore(_graph(tmp_path))
    try:
        pack = build_context_pack(store, "login", mode="rerank", budget_tokens=2000)
        assert pack["mode_effective"] == "rerank"
        assert pack["results"][0]["symbol"]["name"] == "login"
    finally:
        store.close()


def test_build_context_pack_rerank_falls_back_without_model(tmp_path: Path, monkeypatch) -> None:
    # Simulate sentence-transformers being unavailable (as in CI).
    def _boom(self) -> object:
        raise ImportError("sentence-transformers not installed")

    monkeypatch.setattr(CrossEncoderReranker, "_get_model", _boom)
    store = GraphStore(_graph(tmp_path))
    try:
        pack = build_context_pack(store, "login", mode="rerank", budget_tokens=2000)
        assert pack["mode_effective"].endswith("fallback")
        assert pack["result_count"] >= 1
    finally:
        store.close()
