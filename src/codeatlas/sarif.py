"""SARIF export for CodeAtlas audit findings."""

from __future__ import annotations

import hashlib
from typing import Any

from codeatlas.graph.store import GraphStore
from codeatlas.models import Symbol


def _fingerprint(*parts: object) -> str:
    raw = "\0".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _location(sym: Symbol | None, fallback_file: str = ".") -> dict[str, Any]:
    if sym is None:
        return {"physicalLocation": {"artifactLocation": {"uri": fallback_file}}}
    return {
        "physicalLocation": {
            "artifactLocation": {"uri": sym.file_path},
            "region": {"startLine": sym.span.start.line + 1},
        }
    }


def _result(
    rule_id: str,
    message: str,
    *,
    sym: Symbol | None = None,
    fallback_file: str = ".",
    level: str = "warning",
    fingerprint_parts: tuple[object, ...],
) -> dict[str, Any]:
    return {
        "ruleId": rule_id,
        "level": level,
        "message": {"text": message},
        "locations": [_location(sym, fallback_file=fallback_file)],
        "partialFingerprints": {"codeatlasFingerprint": _fingerprint(rule_id, *fingerprint_parts)},
    }


def build_audit_sarif(
    store: GraphStore,
    *,
    repo_uri: str = ".",
    include_tests: bool = False,
    limit: int = 100,
) -> dict[str, Any]:
    """Build a GitHub code-scanning compatible SARIF 2.1.0 payload."""
    results: list[dict[str, Any]] = []

    for cycle in store.detect_cycles()[:limit]:
        first = store.get_symbol_by_id(cycle[0]) if cycle else None
        results.append(
            _result(
                "codeatlas.dependency-cycle",
                "Dependency cycle: " + " -> ".join(cycle + cycle[:1]),
                sym=first,
                fallback_file=repo_uri,
                fingerprint_parts=tuple(cycle),
            )
        )

    for sym in store.find_unused_symbols(include_tests=include_tests)[:limit]:
        results.append(
            _result(
                "codeatlas.unused-symbol",
                f"Unused {sym.kind.value} '{sym.qualified_name}' has no incoming graph references.",
                sym=sym,
                level="note",
                fingerprint_parts=(sym.id, sym.file_path, sym.span.start.line),
            )
        )

    for sym in store.get_coverage_gaps(limit=limit):
        results.append(
            _result(
                "codeatlas.coverage-gap",
                f"Public {sym.kind.value} '{sym.qualified_name}' has no test-file references.",
                sym=sym,
                level="warning",
                fingerprint_parts=(sym.id, sym.file_path, "coverage"),
            )
        )

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "CodeAtlas",
                        "informationUri": "https://github.com/AryanSaini26/CodeAtlas",
                        "rules": [
                            {
                                "id": "codeatlas.dependency-cycle",
                                "name": "Dependency cycle",
                                "shortDescription": {"text": "Symbols form a circular dependency."},
                            },
                            {
                                "id": "codeatlas.unused-symbol",
                                "name": "Unused symbol",
                                "shortDescription": {
                                    "text": "A symbol has no incoming graph references."
                                },
                            },
                            {
                                "id": "codeatlas.coverage-gap",
                                "name": "Coverage gap",
                                "shortDescription": {
                                    "text": "A public symbol has no test-file references."
                                },
                            },
                        ],
                    }
                },
                "invocations": [
                    {
                        "executionSuccessful": True,
                        "workingDirectory": {"uri": repo_uri},
                    }
                ],
                "results": results,
            }
        ],
    }
