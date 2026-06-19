"""Deterministic security checks for hosted context packs."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel

Severity = Literal["low", "medium", "high"]


class ContextSecurityFinding(BaseModel):
    rule_id: str
    severity: Severity
    message: str
    location: str | None = None
    snippet: str | None = None


_PROMPT_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("prompt.ignore_previous", re.compile(r"ignore (all )?(previous|prior) instructions", re.I)),
    ("prompt.system_override", re.compile(r"\b(system|developer) prompt\b", re.I)),
    ("prompt.exfiltrate", re.compile(r"\b(exfiltrate|leak|send).{0,40}\b(secret|token|key)", re.I)),
)

_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("secret.private_key", re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("secret.aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("secret.env_assignment", re.compile(r"\b[A-Z0-9_]*(SECRET|TOKEN|PASSWORD|API_KEY)\s*=", re.I)),
)

_RISKY_PATH_PARTS = {
    "node_modules",
    "vendor",
    "dist",
    "build",
    ".venv",
    "__pycache__",
    "coverage",
    ".next",
}


def _snippet(text: str, match: re.Match[str]) -> str:
    start = max(0, match.start() - 32)
    end = min(len(text), match.end() + 32)
    return text[start:end].replace("\n", " ")[:160]


def scan_text(text: str, *, location: str | None = None) -> list[ContextSecurityFinding]:
    findings: list[ContextSecurityFinding] = []
    for rule_id, pattern in _PROMPT_INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            findings.append(
                ContextSecurityFinding(
                    rule_id=rule_id,
                    severity="high",
                    message="Context contains prompt-injection-like instructions",
                    location=location,
                    snippet=_snippet(text, match),
                )
            )
    for rule_id, pattern in _SECRET_PATTERNS:
        match = pattern.search(text)
        if match:
            findings.append(
                ContextSecurityFinding(
                    rule_id=rule_id,
                    severity="high",
                    message="Context contains secret-like material",
                    location=location,
                    snippet=_snippet(text, match),
                )
            )
    return findings


def scan_path(path: str) -> list[ContextSecurityFinding]:
    parts = {part for part in path.replace("\\", "/").split("/") if part}
    risky = sorted(parts & _RISKY_PATH_PARTS)
    if not risky:
        return []
    return [
        ContextSecurityFinding(
            rule_id="path.generated_or_vendor",
            severity="medium",
            message=f"Context includes generated/vendor path component: {', '.join(risky)}",
            location=path,
        )
    ]


def scan_context_pack(pack: dict[str, Any]) -> dict[str, Any]:
    findings: list[ContextSecurityFinding] = []
    for result in pack.get("results", []):
        if not isinstance(result, dict):
            continue
        symbol = result.get("symbol")
        if not isinstance(symbol, dict):
            continue
        file_path = str(symbol.get("file") or "")
        findings.extend(scan_path(file_path))
        for key in ("qualified_name", "signature", "docstring"):
            value = symbol.get(key)
            if value:
                findings.extend(scan_text(str(value), location=file_path or None))
    for summary in pack.get("file_summaries", []):
        if isinstance(summary, dict):
            file_path = str(summary.get("file") or "")
            findings.extend(scan_path(file_path))

    severity_order = {"low": 1, "medium": 2, "high": 3}
    max_severity = "low"
    if findings:
        max_severity = max(findings, key=lambda item: severity_order[item.severity]).severity
    return {
        "status": "blocked" if any(item.severity == "high" for item in findings) else "ok",
        "max_severity": max_severity,
        "finding_count": len(findings),
        "findings": [finding.model_dump() for finding in findings],
    }
