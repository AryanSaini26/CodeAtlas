"""Agent outcome evaluation harness for CodeAtlas.

The harness has two modes:
- dry-run: validate suites and render deterministic artifacts without cloning
  repositories or running agents.
- live: run a generic agent command against baseline and CodeAtlas-context
  variants in isolated temporary repository copies, then verify outcomes.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Literal

from codeatlas.agent_context import ContextMode, build_context_pack
from codeatlas.config import CodeAtlasConfig
from codeatlas.graph.store import GraphStore
from codeatlas.indexer import RepoIndexer

AGENT_TASK_TYPES = frozenset(
    {"bug_fix", "test_update", "impact_analysis", "architecture_question", "context_retrieval"}
)
AgentVariant = Literal["baseline", "codeatlas_context"]


def load_agent_suite(path: str | Path) -> list[dict[str, Any]]:
    """Load and validate an agent outcome suite."""
    raw = json.loads(Path(path).read_text())
    tasks = raw.get("tasks", raw) if isinstance(raw, dict) else raw
    if not isinstance(tasks, list):
        raise ValueError("agent suite must be a list or an object with a 'tasks' list")

    normalized: list[dict[str, Any]] = []
    for idx, task in enumerate(tasks, 1):
        if not isinstance(task, dict):
            raise ValueError(f"task {idx} must be an object")
        task_id = str(task.get("id", "")).strip()
        repo = str(task.get("repo", "")).strip()
        task_type = str(task.get("task_type", "")).strip()
        prompt = str(task.get("prompt", "")).strip()
        verify_command = str(task.get("verify_command", "")).strip()
        expected_symbols = task.get("expected_symbols", [])
        expected_files = task.get("expected_files", [])
        if not task_id:
            raise ValueError(f"task {idx} is missing id")
        if not repo:
            raise ValueError(f"task {task_id} is missing repo")
        if task_type not in AGENT_TASK_TYPES:
            raise ValueError(f"task {task_id} task_type must be one of {sorted(AGENT_TASK_TYPES)}")
        if not prompt:
            raise ValueError(f"task {task_id} is missing prompt")
        if not verify_command:
            raise ValueError(f"task {task_id} is missing verify_command")
        if not isinstance(expected_symbols, list):
            raise ValueError(f"task {task_id} expected_symbols must be a list")
        if not isinstance(expected_files, list):
            raise ValueError(f"task {task_id} expected_files must be a list")
        if not expected_symbols and not expected_files:
            raise ValueError(f"task {task_id} must include expected_symbols or expected_files")
        normalized.append(
            {
                "id": task_id,
                "repo": repo,
                "task_type": task_type,
                "prompt": prompt,
                "expected_symbols": [str(item) for item in expected_symbols],
                "expected_files": [str(item) for item in expected_files],
                "verify_command": verify_command,
                "timeout_seconds": int(task.get("timeout_seconds", 120)),
                "budget": int(task.get("budget", 2000)),
                "notes": task.get("notes"),
            }
        )
    return normalized


def load_agent_repos(path: str | Path) -> list[dict[str, Any]]:
    """Load JSON-compatible repo lock data used by benchmark commands."""
    raw = json.loads(Path(path).read_text())
    repos = raw.get("repos", raw) if isinstance(raw, dict) else raw
    if not isinstance(repos, list) or not repos:
        raise ValueError("repos file must contain a non-empty repos list")
    normalized: list[dict[str, Any]] = []
    for idx, repo in enumerate(repos, 1):
        if not isinstance(repo, dict):
            raise ValueError(f"repo entry {idx} must be an object")
        name = str(repo.get("name", "")).strip()
        if not name:
            raise ValueError(f"repo entry {idx} is missing name")
        if not repo.get("path") and not repo.get("url"):
            raise ValueError(f"repo entry {name} must include path or url")
        normalized.append(repo)
    return normalized


def build_agent_env(
    *,
    task_prompt: str,
    context_path: Path | None,
    repo_dir: Path,
    output_dir: Path,
    variant: AgentVariant,
) -> dict[str, str]:
    """Build the generic command-runner environment for a task variant."""
    env = os.environ.copy()
    env.update(
        {
            "CODEATLAS_TASK_PROMPT": task_prompt,
            "CODEATLAS_CONTEXT_PATH": "" if context_path is None else str(context_path),
            "CODEATLAS_REPO_DIR": str(repo_dir),
            "CODEATLAS_OUTPUT_DIR": str(output_dir),
            "CODEATLAS_VARIANT": variant,
        }
    )
    return env


def run_shell_command(
    command: str,
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: int,
) -> dict[str, Any]:
    """Run a shell command with captured output and timeout metadata."""
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        elapsed = time.monotonic() - started
        return {
            "command": command,
            "returncode": completed.returncode,
            "timed_out": False,
            "runtime_seconds": round(elapsed, 3),
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        return {
            "command": command,
            "returncode": None,
            "timed_out": True,
            "runtime_seconds": round(elapsed, 3),
            "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
        }


def run_agent_eval(
    *,
    suite_path: str | Path,
    repos_path: str | Path,
    out_dir: str | Path,
    context_mode: ContextMode = "pagerank",
    dry_run: bool = True,
    agent_command: str | None = None,
    compare_baseline: bool = False,
    cache_dir: str | Path = ".codeatlas/bench-repos",
) -> dict[str, Any]:
    """Run or plan an agent outcome evaluation and write report artifacts."""
    tasks = load_agent_suite(suite_path)
    repos = load_agent_repos(repos_path)
    repo_by_name = {str(repo["name"]): repo for repo in repos}
    missing_repos = sorted({task["repo"] for task in tasks} - set(repo_by_name))
    if missing_repos:
        joined = ", ".join(missing_repos)
        raise ValueError(f"agent suite references missing repos: {joined}")

    output_root = Path(out_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    if dry_run or not agent_command:
        payload = _dry_run_payload(
            suite_path=suite_path,
            repos_path=repos_path,
            tasks=tasks,
            repos=repos,
            context_mode=context_mode,
            compare_baseline=compare_baseline,
            agent_command=agent_command,
        )
    else:
        payload = _live_payload(
            tasks=tasks,
            repo_by_name=repo_by_name,
            output_root=output_root,
            context_mode=context_mode,
            agent_command=agent_command,
            compare_baseline=compare_baseline,
            cache_dir=Path(cache_dir),
            suite_path=suite_path,
            repos_path=repos_path,
        )

    failures = _collect_failures(payload)
    (output_root / "results.json").write_text(json.dumps(payload, indent=2) + "\n")
    (output_root / "failures.json").write_text(json.dumps(failures, indent=2) + "\n")
    (output_root / "report.md").write_text(render_agent_eval_markdown(payload) + "\n")
    return payload


def render_agent_eval_markdown(payload: dict[str, Any]) -> str:
    """Render a publishable agent outcome report."""
    metrics = payload["metrics"]
    lines = [
        "# CodeAtlas Agent Outcome Eval",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Mode | {'dry-run' if payload['dry_run'] else 'live'} |",
        f"| Tasks | {payload['task_count']} |",
        f"| Context mode | `{payload['context_mode']}` |",
        f"| Live variants | {metrics['live_variant_count']} |",
        f"| Solve rate | {_fmt_optional_pct(metrics['solve_rate'])} |",
        f"| Verification pass rate | {_fmt_optional_pct(metrics['verification_pass_rate'])} |",
        f"| Baseline vs context delta | {_fmt_optional_pct(metrics['baseline_vs_context_delta'])} |",
        f"| Avg runtime | {_fmt_seconds(metrics['avg_runtime_seconds'])} |",
        f"| Avg context tokens | {metrics['context_tokens']:.1f} |",
        f"| Avg context savings | {metrics['context_savings']:.2%} |",
        f"| Retrieval symbol recall | {metrics['retrieval_symbol_recall']:.3f} |",
        f"| Retrieval file recall | {metrics['retrieval_file_recall']:.3f} |",
        "",
    ]
    if payload["dry_run"]:
        lines.extend(
            [
                "> Dry-run validates the suite and planned A/B shape without cloning repos, "
                "running agents, or claiming live-agent improvement.",
                "",
            ]
        )
    lines.extend(
        [
            "## Tasks",
            "",
            "| Task | Repo | Type | Expected symbols | Expected files | Variants |",
            "|------|------|------|------------------|----------------|----------|",
        ]
    )
    for task in payload["tasks"]:
        variants = ", ".join(
            f"`{variant['variant']}:{variant['status']}`" for variant in task["variants"]
        )
        expected_symbols = ", ".join(f"`{s}`" for s in task["expected_symbols"]) or "_none_"
        expected_files = ", ".join(f"`{f}`" for f in task["expected_files"]) or "_none_"
        lines.append(
            f"| `{task['id']}` | `{task['repo']}` | `{task['task_type']}` | "
            f"{expected_symbols} | {expected_files} | {variants or '_none_'} |"
        )
    failures = _collect_failures(payload)
    lines.extend(["", "## Failure Analysis", ""])
    if not failures:
        lines.append("No live verification failures recorded.")
    else:
        lines.extend(
            [
                "| Task | Variant | Reason |",
                "|------|---------|--------|",
            ]
        )
        for failure in failures[:30]:
            lines.append(
                f"| `{failure['task_id']}` | `{failure['variant']}` | {failure['reason']} |"
            )
    return "\n".join(lines)


def aggregate_agent_metrics(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate task/variant outcomes into report-level metrics."""
    live_variants: list[dict[str, Any]] = []
    context_variants: list[dict[str, Any]] = []
    baseline_variants: list[dict[str, Any]] = []
    symbol_recall = 0.0
    file_recall = 0.0
    context_tokens = 0.0
    context_savings = 0.0
    context_count = 0

    for task in tasks:
        symbol_recall += float(task.get("retrieval_symbol_recall", 0.0))
        file_recall += float(task.get("retrieval_file_recall", 0.0))
        for variant in task["variants"]:
            if variant["status"] == "completed":
                live_variants.append(variant)
                if variant["variant"] == "baseline":
                    baseline_variants.append(variant)
                if variant["variant"] == "codeatlas_context":
                    context_variants.append(variant)
                    context_tokens += float(variant.get("context_tokens", 0))
                    context_savings += float(variant.get("context_savings", 0.0))
                    context_count += 1

    verification_passes = sum(1 for variant in live_variants if variant["verification_passed"])
    context_passes = sum(1 for variant in context_variants if variant["verification_passed"])
    baseline_passes = sum(1 for variant in baseline_variants if variant["verification_passed"])
    live_count = len(live_variants)
    context_count_for_rate = len(context_variants)
    baseline_count = len(baseline_variants)
    context_solve_rate = context_passes / context_count_for_rate if context_count_for_rate else None
    baseline_solve_rate = baseline_passes / baseline_count if baseline_count else None
    delta = (
        context_solve_rate - baseline_solve_rate
        if context_solve_rate is not None and baseline_solve_rate is not None
        else None
    )
    task_count = len(tasks)
    return {
        "solve_rate": context_solve_rate,
        "verification_pass_rate": verification_passes / live_count if live_count else None,
        "avg_runtime_seconds": (
            sum(float(variant["runtime_seconds"]) for variant in live_variants) / live_count
            if live_count
            else None
        ),
        "context_tokens": context_tokens / context_count if context_count else 0.0,
        "context_savings": context_savings / context_count if context_count else 0.0,
        "retrieval_symbol_recall": round(symbol_recall / task_count, 6) if task_count else 0.0,
        "retrieval_file_recall": round(file_recall / task_count, 6) if task_count else 0.0,
        "baseline_vs_context_delta": delta,
        "baseline_solve_rate": baseline_solve_rate,
        "context_solve_rate": context_solve_rate,
        "live_variant_count": live_count,
    }


def _dry_run_payload(
    *,
    suite_path: str | Path,
    repos_path: str | Path,
    tasks: list[dict[str, Any]],
    repos: list[dict[str, Any]],
    context_mode: ContextMode,
    compare_baseline: bool,
    agent_command: str | None,
) -> dict[str, Any]:
    variants: list[AgentVariant] = (
        ["baseline", "codeatlas_context"] if compare_baseline else ["codeatlas_context"]
    )
    task_results = [
        {
            **_task_public_fields(task),
            "retrieval_symbol_recall": 0.0,
            "retrieval_file_recall": 0.0,
            "variants": [
                {
                    "variant": variant,
                    "status": "dry_run",
                    "verification_passed": None,
                    "runtime_seconds": 0.0,
                    "context_tokens": 0,
                    "context_savings": 0.0,
                    "failure_reason": None,
                }
                for variant in variants
            ],
        }
        for task in tasks
    ]
    return {
        "suite": str(suite_path),
        "repos_file": str(repos_path),
        "repos": [_repo_public_fields(repo) for repo in repos],
        "dry_run": True,
        "agent_command_provided": bool(agent_command),
        "compare_baseline": compare_baseline,
        "context_mode": context_mode,
        "task_count": len(task_results),
        "metrics": aggregate_agent_metrics(task_results),
        "tasks": task_results,
    }


def _live_payload(
    *,
    tasks: list[dict[str, Any]],
    repo_by_name: dict[str, dict[str, Any]],
    output_root: Path,
    context_mode: ContextMode,
    agent_command: str,
    compare_baseline: bool,
    cache_dir: Path,
    suite_path: str | Path,
    repos_path: str | Path,
) -> dict[str, Any]:
    task_results: list[dict[str, Any]] = []
    cache_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="codeatlas-agent-eval-") as tmp:
        tmp_root = Path(tmp)
        for task in tasks:
            source_repo = _materialize_agent_repo(repo_by_name[task["repo"]], cache_dir)
            variants: list[AgentVariant] = (
                ["baseline", "codeatlas_context"] if compare_baseline else ["codeatlas_context"]
            )
            variant_results = []
            retrieval_symbol_recall = 0.0
            retrieval_file_recall = 0.0
            for variant in variants:
                variant_root = tmp_root / task["id"] / variant
                output_dir = output_root / "runs" / task["id"] / variant
                output_dir.mkdir(parents=True, exist_ok=True)
                _copy_repo(source_repo, variant_root)
                context_path: Path | None = None
                context_tokens = 0
                context_savings = 0.0
                if variant == "codeatlas_context":
                    context_path = output_dir / "context.json"
                    pack = _build_context_for_repo(
                        variant_root,
                        task["prompt"],
                        budget_tokens=task["budget"],
                        mode=context_mode,
                    )
                    context_path.write_text(json.dumps(pack, indent=2) + "\n")
                    context_tokens = int(pack["estimated_tokens"])
                    context_savings = float(pack["context_savings"])
                    hits = [result["symbol"]["qualified_name"] for result in pack["results"]]
                    hit_files = [result["symbol"]["file"] for result in pack["results"]]
                    hit_files.extend(summary["file"] for summary in pack["file_summaries"])
                    hit_files = list(dict.fromkeys(hit_files))
                    retrieval_symbol_recall = _recall_symbols(hits, task["expected_symbols"])
                    retrieval_file_recall = _recall_files(hit_files, task["expected_files"])

                env = build_agent_env(
                    task_prompt=task["prompt"],
                    context_path=context_path,
                    repo_dir=variant_root,
                    output_dir=output_dir,
                    variant=variant,
                )
                agent_result = run_shell_command(
                    agent_command,
                    cwd=variant_root,
                    env=env,
                    timeout_seconds=task["timeout_seconds"],
                )
                verify_result = run_shell_command(
                    task["verify_command"],
                    cwd=variant_root,
                    env=env,
                    timeout_seconds=task["timeout_seconds"],
                )
                passed = verify_result["returncode"] == 0 and not verify_result["timed_out"]
                failure_reason = _variant_failure_reason(agent_result, verify_result, passed)
                variant_results.append(
                    {
                        "variant": variant,
                        "status": "completed",
                        "verification_passed": passed,
                        "runtime_seconds": round(
                            float(agent_result["runtime_seconds"])
                            + float(verify_result["runtime_seconds"]),
                            3,
                        ),
                        "context_tokens": context_tokens,
                        "context_savings": context_savings,
                        "failure_reason": failure_reason,
                        "agent": agent_result,
                        "verify": verify_result,
                    }
                )
            task_results.append(
                {
                    **_task_public_fields(task),
                    "retrieval_symbol_recall": round(retrieval_symbol_recall, 6),
                    "retrieval_file_recall": round(retrieval_file_recall, 6),
                    "variants": variant_results,
                }
            )

    return {
        "suite": str(suite_path),
        "repos_file": str(repos_path),
        "repos": [_repo_public_fields(repo) for repo in repo_by_name.values()],
        "dry_run": False,
        "agent_command_provided": True,
        "compare_baseline": compare_baseline,
        "context_mode": context_mode,
        "task_count": len(task_results),
        "metrics": aggregate_agent_metrics(task_results),
        "tasks": task_results,
    }


def _build_context_for_repo(
    repo_path: Path,
    query: str,
    *,
    budget_tokens: int,
    mode: ContextMode,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="codeatlas-agent-context-") as tmp:
        db_path = Path(tmp) / "graph.db"
        config = CodeAtlasConfig.find_and_load(repo_path)
        config.graph.db_path = db_path
        store = GraphStore(db_path)
        try:
            with (
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                RepoIndexer(config, store).index_full()
            return build_context_pack(
                store,
                query,
                budget_tokens=budget_tokens,
                mode=mode,
                limit=10,
            )
        finally:
            store.close()


def _materialize_agent_repo(spec: dict[str, Any], cache_root: Path) -> Path:
    if spec.get("path"):
        path = Path(str(spec["path"]))
        if not path.exists():
            raise ValueError(f"local agent-eval repo does not exist: {path}")
        return path

    name = str(spec["name"])
    url = str(spec["url"])
    commit = str(spec.get("commit", spec.get("ref", "HEAD")))
    repo_dir = cache_root / name
    if not repo_dir.exists():
        subprocess.run(["git", "clone", url, str(repo_dir)], check=True)
    else:
        subprocess.run(["git", "-C", str(repo_dir), "fetch", "origin", commit], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "checkout", "--detach", commit], check=True)
    return repo_dir


def _copy_repo(source: Path, destination: Path) -> None:
    def ignore(_dir: str, names: list[str]) -> set[str]:
        return {name for name in names if name in {".git", ".codeatlas", "__pycache__"}}

    shutil.copytree(source, destination, ignore=ignore)


def _task_public_fields(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": task["id"],
        "repo": task["repo"],
        "task_type": task["task_type"],
        "prompt": task["prompt"],
        "expected_symbols": task["expected_symbols"],
        "expected_files": task["expected_files"],
        "verify_command": task["verify_command"],
        "timeout_seconds": task["timeout_seconds"],
        "budget": task["budget"],
        "notes": task["notes"],
    }


def _repo_public_fields(repo: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": repo["name"],
        "url": repo.get("url"),
        "path": repo.get("path"),
        "commit": repo.get("commit", repo.get("ref")),
    }


def _collect_failures(payload: dict[str, Any]) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    for task in payload["tasks"]:
        for variant in task["variants"]:
            if variant["status"] == "completed" and not variant["verification_passed"]:
                failures.append(
                    {
                        "task_id": str(task["id"]),
                        "repo": str(task["repo"]),
                        "variant": str(variant["variant"]),
                        "reason": str(variant.get("failure_reason") or "verification failed"),
                    }
                )
    return failures


def _variant_failure_reason(
    agent_result: dict[str, Any],
    verify_result: dict[str, Any],
    passed: bool,
) -> str | None:
    if passed:
        return None
    if agent_result["timed_out"]:
        return "agent command timed out"
    if agent_result["returncode"] not in (0, None):
        return f"agent command exited {agent_result['returncode']}"
    if verify_result["timed_out"]:
        return "verify command timed out"
    return f"verify command exited {verify_result['returncode']}"


def _recall_symbols(hits: list[str], expected: list[str]) -> float:
    if not expected:
        return 0.0
    matched = 0
    for exp in expected:
        exp_lower = exp.lower()
        if any(
            hit.lower() == exp_lower
            or hit.lower().endswith(f"::{exp_lower}")
            or hit.lower().endswith(f".{exp_lower}")
            for hit in hits
        ):
            matched += 1
    return matched / len(expected)


def _recall_files(hits: list[str], expected: list[str]) -> float:
    if not expected:
        return 0.0
    matched = 0
    for exp in expected:
        exp_lower = exp.lower()
        if any(hit.lower() == exp_lower or hit.lower().endswith(exp_lower) for hit in hits):
            matched += 1
    return matched / len(expected)


def _fmt_optional_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2%}"


def _fmt_seconds(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}s"
