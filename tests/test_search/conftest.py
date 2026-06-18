"""Shared search test fixtures."""

import numpy as np
import pytest

from codeatlas.search.embeddings import SemanticIndex


def _deterministic_encode(self: SemanticIndex, texts: list[str]) -> np.ndarray:
    rows: list[np.ndarray] = []
    concepts = [
        ("auth", "login", "credential", "verify"),
        ("database", "postgres", "connection", "migration"),
        ("password", "hash", "bcrypt"),
        ("request", "http"),
        ("response", "json"),
        ("create", "creation", "new user"),
        ("delete", "remove"),
        ("email",),
        ("notification", "push"),
    ]
    for text in texts:
        lowered = text.lower()
        row = np.full(len(concepts), 0.01, dtype=np.float32)
        for index, terms in enumerate(concepts):
            if any(term in lowered for term in terms):
                row[index] = 1.0
        norm = np.linalg.norm(row)
        if norm > 0:
            row = row / norm
        rows.append(row)
    return np.vstack(rows).astype(np.float32)


@pytest.fixture(autouse=True)
def deterministic_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(SemanticIndex, "_encode", _deterministic_encode)
