"""SARIF export for CodeAtlas audit + security findings."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from codeatlas.context_security import ContextSecurityFinding, scan_path, scan_text
from codeatlas.graph.store import GraphStore
from codeatlas.models import Symbol

_SEVERITY_TO_LEVEL = {"high": "error", "medium": "warning", "low": "note"}
_SCAN_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    ".next",
    "vendor",
    "site",
    ".codeatlas",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}
_SECURITY_RULES = [
    {"id": "prompt.ignore_previous", "name": "Prompt injection (ignore instructions)"},
    {"id": "prompt.system_override", "name": "Prompt injection (system prompt override)"},
    {"id": "prompt.exfiltrate", "name": "Prompt injection (secret exfiltration)"},
    {"id": "secret.private_key", "name": "Private key material"},
    {"id": "secret.aws_key", "name": "AWS access key"},
    {"id": "secret.env_assignment", "name": "Hard-coded secret assignment"},
    {"id": "path.generated_or_vendor", "name": "Generated/vendor path"},
]


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


def _line_for(text: str, finding: ContextSecurityFinding) -> int:
    """Best-effort source line for a finding (snippets drop newlines)."""
    needle = (finding.snippet or "").strip()
    token = max(needle.split(), key=len, default="")
    idx = text.find(token) if token else -1
    return text.count("\n", 0, idx) + 1 if idx >= 0 else 1


def _security_result(finding: ContextSecurityFinding, uri: str, line: int) -> dict[str, Any]:
    return {
        "ruleId": finding.rule_id,
        "level": _SEVERITY_TO_LEVEL.get(finding.severity, "warning"),
        "message": {"text": finding.message},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": uri},
                    "region": {"startLine": max(1, line)},
                }
            }
        ],
        "partialFingerprints": {"codeatlasFingerprint": _fingerprint(finding.rule_id, uri, line)},
    }


def build_security_sarif(
    repo_path: str = ".",
    *,
    max_files: int = 5000,
    max_bytes: int = 1_000_000,
) -> dict[str, Any]:
    """Scan a repo for secret-like content, prompt-injection text, and risky
    paths, emitting GitHub code-scanning compatible SARIF 2.1.0."""
    root = Path(repo_path)
    results: list[dict[str, Any]] = []
    scanned = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in _SCAN_SKIP_DIRS for part in path.parts):
            continue
        rel = path.relative_to(root).as_posix()
        for finding in scan_path(rel):
            results.append(_security_result(finding, rel, 1))
        try:
            if path.stat().st_size > max_bytes:
                continue
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for finding in scan_text(text, location=rel):
            results.append(_security_result(finding, rel, _line_for(text, finding)))
        scanned += 1
        if scanned >= max_files:
            break

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "CodeAtlas Security",
                        "informationUri": "https://github.com/AryanSaini26/CodeAtlas",
                        "rules": [
                            {
                                "id": rule["id"],
                                "name": rule["name"],
                                "shortDescription": {"text": rule["name"]},
                            }
                            for rule in _SECURITY_RULES
                        ],
                    }
                },
                "invocations": [
                    {"executionSuccessful": True, "workingDirectory": {"uri": str(root)}}
                ],
                "results": results,
            }
        ],
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
