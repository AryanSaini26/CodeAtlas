"""Graph-aware pull-request analysis.

Given the files a PR changes, derive — from the indexed graph — the changed
symbols, their downstream blast radius, suggested/missing tests, security
findings, and a transparent risk score. Used by both the `codeatlas pr-analyze`
CLI/Action and the hosted GitHub PR bot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeatlas.context_security import scan_text
from codeatlas.git_integration import get_git_changed_files_range
from codeatlas.graph.store import GraphStore

PR_BOT_MARKER = "<!-- stratum-pr-bot -->"


@dataclass
class PRAnalysis:
    base: str
    head: str
    changed_files: list[str]
    changed_symbols: list[dict[str, str]] = field(default_factory=list)
    impacted: list[dict[str, str]] = field(default_factory=list)
    impacted_file_count: int = 0
    suggested_tests: list[str] = field(default_factory=list)
    untested_changes: list[dict[str, str]] = field(default_factory=list)
    security_findings: list[dict[str, str]] = field(default_factory=list)
    risk_score: float = 0.0
    risk_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "base": self.base,
            "head": self.head,
            "changed_files": self.changed_files,
            "changed_symbols": self.changed_symbols,
            "impacted": self.impacted,
            "impacted_file_count": self.impacted_file_count,
            "suggested_tests": self.suggested_tests,
            "untested_changes": self.untested_changes,
            "security_findings": self.security_findings,
            "risk_score": self.risk_score,
            "risk_reasons": self.risk_reasons,
        }


def _to_rel(path: str, root: Path) -> str:
    """Repo-relative posix path (the indexer stores absolute paths)."""
    pp = Path(path)
    try:
        return pp.relative_to(root).as_posix()
    except ValueError:
        return pp.name


def _symbols_for(store: GraphStore, root: Path, rel_file: str) -> list[Any]:
    # The graph may key files by absolute path (index .) or relative; try both.
    syms = store.get_symbols_in_file(str(root / rel_file))
    return syms or store.get_symbols_in_file(rel_file)


def _risk(
    changed_count: int, impacted_count: int, high_sec: int, has_untested: bool
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    if changed_count:
        s = min(4.0, changed_count * 0.3)
        score += s
        reasons.append(f"{changed_count} changed symbol(s)")
    if impacted_count:
        s = min(3.0, impacted_count * 0.2)
        score += s
        reasons.append(f"{impacted_count} downstream dependent(s)")
    if high_sec:
        score += min(2.0, float(high_sec))
        reasons.append(f"{high_sec} high-severity security finding(s)")
    if has_untested:
        score += 1.0
        reasons.append("changed public symbols without test references")
    return round(min(10.0, score), 1), reasons


def analyze_changed_files(
    store: GraphStore, repo_root: Path | str, changed_files: list[str], *, base: str, head: str
) -> PRAnalysis:
    root = Path(repo_root)
    changed_rel = set(changed_files)

    changed_syms: list[Any] = []
    for rel_file in changed_files:
        # Skip import pseudo-symbols — they're noise in a PR report.
        changed_syms.extend(
            s for s in _symbols_for(store, root, rel_file) if s.kind.value != "import"
        )

    changed_symbols = [
        {
            "qualified_name": s.qualified_name,
            "kind": s.kind.value,
            "file": _to_rel(s.file_path, root),
        }
        for s in changed_syms
    ]

    # Blast radius + suggested/missing tests from one-hop dependents.
    affected: dict[str, tuple[str, str]] = {}
    suggested_tests: set[str] = set()
    untested: list[dict[str, str]] = []
    for sym in changed_syms:
        dependents = [store.get_symbol_by_id(r.source_id) for r in store.get_dependents(sym.id)]
        test_refs: set[str] = set()
        for dep in dependents:
            if dep is None:
                continue
            dep_rel = _to_rel(dep.file_path, root)
            if dep.is_test:
                test_refs.add(dep_rel)
            elif dep_rel not in changed_rel:
                affected[dep.id] = (dep.qualified_name, dep_rel)
        suggested_tests |= test_refs
        is_public = not sym.is_test and not sym.name.startswith("_")
        if is_public and not test_refs:
            untested.append(
                {"qualified_name": sym.qualified_name, "file": _to_rel(sym.file_path, root)}
            )

    # Security: scan only the changed files.
    security: list[dict[str, str]] = []
    high_sec = 0
    for rel in changed_files:
        path = root / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for finding in scan_text(text, location=rel):
            security.append(
                {
                    "rule_id": finding.rule_id,
                    "severity": finding.severity,
                    "message": finding.message,
                }
            )
            if finding.severity == "high":
                high_sec += 1

    risk_score, reasons = _risk(len(changed_syms), len(affected), high_sec, bool(untested))
    return PRAnalysis(
        base=base,
        head=head,
        changed_files=sorted(changed_rel),
        changed_symbols=changed_symbols,
        impacted=[{"qualified_name": qn, "file": f} for qn, f in sorted(affected.values())],
        impacted_file_count=len({f for _, f in affected.values()}),
        suggested_tests=sorted(suggested_tests),
        untested_changes=untested,
        security_findings=security,
        risk_score=risk_score,
        risk_reasons=reasons,
    )


def analyze_pr(
    graph_db_path: Path | str, repo_root: Path | str, base: str, head: str = "HEAD"
) -> PRAnalysis:
    changed_files = get_git_changed_files_range(Path(repo_root), base, head)
    store = GraphStore(Path(graph_db_path))
    try:
        return analyze_changed_files(store, repo_root, changed_files, base=base, head=head)
    finally:
        store.close()


def _risk_band(score: float) -> str:
    return "High" if score >= 7 else "Medium" if score >= 4 else "Low"


def render_pr_markdown(a: PRAnalysis, *, marker: bool = False) -> str:
    lines = [
        "## 🛰️ CodeAtlas PR intelligence",
        "",
        f"**Risk: {_risk_band(a.risk_score)} ({a.risk_score}/10)** — "
        + (", ".join(a.risk_reasons) if a.risk_reasons else "no notable risk signals"),
        "",
        f"Touches **{len(a.changed_files)} file(s)** / **{len(a.changed_symbols)} symbol(s)**; "
        f"downstream blast radius **{len(a.impacted)} symbol(s)** across "
        f"**{a.impacted_file_count} file(s)**.",
    ]
    if a.changed_symbols:
        lines += ["", "**Changed symbols:**"]
        lines += [
            f"- `{s['qualified_name']}` ({s['kind']}) — {s['file']}" for s in a.changed_symbols[:15]
        ]
    if a.impacted:
        lines += ["", "**Most affected (downstream):**"]
        lines += [f"- `{i['qualified_name']}` — {i['file']}" for i in a.impacted[:10]]
    if a.suggested_tests:
        lines += ["", "**Relevant existing tests to run:**"]
        lines += [f"- {t}" for t in a.suggested_tests[:10]]
    if a.untested_changes:
        lines += ["", "**Changed public symbols missing tests:**"]
        lines += [f"- `{u['qualified_name']}` — {u['file']}" for u in a.untested_changes[:10]]
    if a.security_findings:
        lines += ["", "**Security findings in changed files:**"]
        lines += [
            f"- `{f['rule_id']}` ({f['severity']}): {f['message']}"
            for f in a.security_findings[:10]
        ]
    lines += ["", "_Measured from the CodeAtlas graph._"]
    if marker:
        lines += ["", PR_BOT_MARKER]
    return "\n".join(lines)
