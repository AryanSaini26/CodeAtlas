"""Policy-aware, secret-safe context packs.

The context-security scanner *flags* risky content; this module *enforces* a
policy: deny-listed paths are dropped from a context pack and secret-like
material is redacted before an agent ever sees it.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codeatlas.context_security import _SECRET_PATTERNS, scan_path, scan_text

_DEFAULT_DENY = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "id_rsa",
    "id_ed25519",
    "*.p12",
    "*.pfx",
    "secrets/**",
    "**/secrets/**",
    "*.tfvars",
)
_VENDOR_PARTS = {"node_modules", "vendor", "dist", "build", ".venv", "__pycache__", ".next"}
_REDACTION = "«redacted-secret»"


@dataclass
class ContextPolicy:
    deny_patterns: tuple[str, ...] = _DEFAULT_DENY
    redact_secrets: bool = True
    allow_vendor: bool = False
    allow_tests: bool = True

    @classmethod
    def from_config(cls, config: Any | None = None) -> ContextPolicy:
        """Load from an optional ``[context_policy]`` config section; else defaults."""
        section = getattr(config, "context_policy", None) if config is not None else None
        if not isinstance(section, dict):
            return cls()
        return cls(
            deny_patterns=tuple(section.get("deny_patterns", _DEFAULT_DENY)),
            redact_secrets=bool(section.get("redact_secrets", True)),
            allow_vendor=bool(section.get("allow_vendor", False)),
            allow_tests=bool(section.get("allow_tests", True)),
        )


def is_denied(path: str, policy: ContextPolicy) -> bool:
    posix = path.replace("\\", "/")
    parts = set(posix.split("/"))
    if not policy.allow_vendor and (parts & _VENDOR_PARTS):
        return True
    name = Path(posix).name
    return any(
        fnmatch.fnmatch(posix, pat) or fnmatch.fnmatch(name, pat) for pat in policy.deny_patterns
    )


def redact(text: str, policy: ContextPolicy) -> tuple[str, int]:
    """Return (redacted_text, count) — replaces secret-like spans."""
    if not policy.redact_secrets or not text:
        return text, 0
    count = 0
    for _rule_id, pattern in _SECRET_PATTERNS:
        text, n = pattern.subn(_REDACTION, text)
        count += n
    return text, count


def safety_report(repo_path: str, policy: ContextPolicy | None = None) -> dict[str, Any]:
    """Scan a repo and summarise what a policy would exclude/redact/flag."""
    pol = policy or ContextPolicy()
    root = Path(repo_path)
    skip_dirs = _VENDOR_PARTS | {".git", ".codeatlas", "site", ".mypy_cache", ".ruff_cache"}
    excluded: list[str] = []
    secrets_found = 0
    injection_warnings = 0
    vendor_included = 0
    for path in sorted(root.rglob("*")):
        # Don't descend into heavy vendored/build trees (they're denied anyway).
        if not path.is_file() or skip_dirs.intersection(path.parts):
            continue
        rel = path.relative_to(root).as_posix()
        if is_denied(rel, pol):
            excluded.append(rel)
            continue
        if scan_path(rel):
            vendor_included += 1
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for finding in scan_text(text, location=rel):
            if finding.rule_id.startswith("secret."):
                secrets_found += 1
            elif finding.rule_id.startswith("prompt."):
                injection_warnings += 1
    return {
        "excluded_count": len(excluded),
        "excluded": excluded[:50],
        "secrets_found": secrets_found,
        "injection_warnings": injection_warnings,
        "vendor_included": vendor_included,
    }
