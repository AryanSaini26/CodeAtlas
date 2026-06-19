"""Tests for agent outcome evaluation."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

from codeatlas.agent_eval import (
    aggregate_agent_metrics,
    build_agent_env,
    load_agent_suite,
    render_agent_eval_markdown,
    resolve_agent_command,
    run_agent_eval,
    run_shell_command,
)


def _make_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "main.py").write_text("def greet(name: str) -> str:\n    return f'Hello, {name}'\n")
    return path


def _write_repos(path: Path, repo: Path) -> Path:
    repos = path / "repos.json"
    repos.write_text(json.dumps({"repos": [{"name": "fixture", "path": str(repo)}]}))
    return repos


def _write_suite(path: Path) -> Path:
    suite = path / "agent-suite.json"
    suite.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": "fix-greet",
                        "repo": "fixture",
                        "task_type": "bug_fix",
                        "prompt": "Use context to fix greet and create solved.txt.",
                        "expected_symbols": ["greet"],
                        "expected_files": ["main.py"],
                        "expected_tests": ["test_main.py"],
                        "expected_patch": ["solved.txt"],
                        "setup_command": f"{sys.executable} -c \"print('setup')\"",
                        "verify_command": (
                            f"{sys.executable} -c "
                            "\"from pathlib import Path; assert Path('solved.txt').exists()\""
                        ),
                        "timeout_seconds": 20,
                        "budget": 512,
                        "difficulty": "easy",
                        "tags": ["mock", "context"],
                    }
                ]
            }
        )
    )
    return suite


def test_load_agent_suite_accepts_expected_shape(tmp_path: Path) -> None:
    suite = _write_suite(tmp_path)
    tasks = load_agent_suite(suite)
    assert tasks[0]["id"] == "fix-greet"
    assert tasks[0]["task_type"] == "bug_fix"
    assert tasks[0]["budget"] == 512
    assert tasks[0]["expected_tests"] == ["test_main.py"]
    assert tasks[0]["expected_patch"] == ["solved.txt"]
    assert tasks[0]["difficulty"] == "easy"
    assert tasks[0]["tags"] == ["mock", "context"]


def test_resolve_agent_command_requires_shell_command() -> None:
    assert "codeatlas_mock_solved.txt" in resolve_agent_command("mock", None)
    assert resolve_agent_command("codex", None).startswith("codex")
    assert resolve_agent_command("shell", "echo ok") == "echo ok"


def test_build_agent_env_sets_contract(tmp_path: Path) -> None:
    env = build_agent_env(
        task_prompt="prompt",
        context_path=tmp_path / "context.json",
        repo_dir=tmp_path / "repo",
        output_dir=tmp_path / "out",
        variant="codeatlas_context",
    )
    assert env["CODEATLAS_TASK_PROMPT"] == "prompt"
    assert env["CODEATLAS_CONTEXT_PATH"].endswith("context.json")
    assert env["CODEATLAS_REPO_DIR"].endswith("repo")
    assert env["CODEATLAS_OUTPUT_DIR"].endswith("out")
    assert env["CODEATLAS_VARIANT"] == "codeatlas_context"


def test_run_shell_command_reports_timeout(tmp_path: Path) -> None:
    result = run_shell_command(
        f'{sys.executable} -c "import time; time.sleep(2)"',
        cwd=tmp_path,
        env={},
        timeout_seconds=1,
    )
    assert result["timed_out"] is True
    assert result["returncode"] is None


def test_run_shell_command_docker_sandbox_uses_allowlisted_env(tmp_path: Path) -> None:
    captured = {}

    class Completed:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(args, **kwargs):  # type: ignore[no-untyped-def]
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Completed()

    env = {
        "CODEATLAS_TASK_PROMPT": "prompt",
        "CODEATLAS_OUTPUT_DIR": str(tmp_path / "out"),
        "CODEATLAS_CONTEXT_PATH": str(tmp_path / "out" / "context.json"),
        "SECRET_TOKEN": "nope",
    }
    (tmp_path / "out").mkdir()
    with patch("subprocess.run", fake_run):
        result = run_shell_command(
            "echo ok",
            cwd=tmp_path,
            env=env,
            timeout_seconds=5,
            sandbox="docker",
        )
    assert result["returncode"] == 0
    args = captured["args"]
    assert args[:3] == ["docker", "run", "--rm"]
    assert "--network" in args
    assert "SECRET_TOKEN=nope" not in args
    assert "CODEATLAS_CONTEXT_PATH=/out/context.json" in args


def test_agent_eval_dry_run_writes_artifacts(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo")
    repos = _write_repos(tmp_path, repo)
    suite = _write_suite(tmp_path)
    out = tmp_path / "agent"

    payload = run_agent_eval(
        suite_path=suite,
        repos_path=repos,
        out_dir=out,
        dry_run=True,
        compare_baseline=True,
    )

    assert payload["dry_run"] is True
    assert payload["task_count"] == 1
    assert (out / "results.json").exists()
    assert (out / "report.md").exists()
    assert (out / "failures.json").exists()
    assert payload["tasks"][0]["variants"][0]["status"] == "dry_run"


def test_agent_eval_live_mock_agent_compares_baseline(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo")
    repos = _write_repos(tmp_path, repo)
    suite = _write_suite(tmp_path)
    out = tmp_path / "agent"
    agent = tmp_path / "mock_agent.py"
    agent.write_text(
        "import os\n"
        "from pathlib import Path\n"
        "if os.environ.get('CODEATLAS_CONTEXT_PATH'):\n"
        "    Path('solved.txt').write_text('solved with context')\n"
    )

    payload = run_agent_eval(
        suite_path=suite,
        repos_path=repos,
        out_dir=out,
        dry_run=False,
        agent_command=f"{sys.executable} {agent}",
        compare_baseline=True,
    )

    assert payload["dry_run"] is False
    variants = {v["variant"]: v for v in payload["tasks"][0]["variants"]}
    assert variants["baseline"]["verification_passed"] is False
    assert variants["codeatlas_context"]["verification_passed"] is True
    assert payload["metrics"]["baseline_vs_context_delta"] == 1.0
    assert payload["metrics"]["context_tokens"] > 0
    assert payload["safety_label"] == "live_agent_unsandboxed"
    assert variants["codeatlas_context"]["trace_path"]
    assert "trace.jsonl" in variants["codeatlas_context"]["trace_path"]
    failures = json.loads((out / "failures.json").read_text())
    assert failures[0]["variant"] == "baseline"


def test_agent_eval_mock_adapter_runs_without_agent_command(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo")
    repos = _write_repos(tmp_path, repo)
    suite = tmp_path / "agent-suite.json"
    suite.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": "mock",
                        "repo": "fixture",
                        "task_type": "bug_fix",
                        "prompt": "solve with mock",
                        "expected_symbols": ["greet"],
                        "expected_files": ["main.py"],
                        "verify_command": (
                            f"{sys.executable} -c "
                            "\"from pathlib import Path; assert Path('codeatlas_mock_solved.txt').exists()\""
                        ),
                    }
                ]
            }
        )
    )
    payload = run_agent_eval(
        suite_path=suite,
        repos_path=repos,
        out_dir=tmp_path / "out",
        dry_run=False,
        agent_adapter="mock",
    )
    assert payload["safety_label"] == "mock_agent"
    assert payload["tasks"][0]["variants"][0]["verification_passed"] is True


def test_render_agent_eval_markdown_labels_dry_run() -> None:
    payload = {
        "dry_run": True,
        "task_count": 1,
        "context_mode": "pagerank",
        "metrics": {
            "live_variant_count": 0,
            "solve_rate": None,
            "verification_pass_rate": None,
            "baseline_vs_context_delta": None,
            "avg_runtime_seconds": None,
            "context_tokens": 0.0,
            "context_savings": 0.0,
            "retrieval_symbol_recall": 0.0,
            "retrieval_file_recall": 0.0,
        },
        "tasks": [
            {
                "id": "task",
                "repo": "fixture",
                "task_type": "context_retrieval",
                "expected_symbols": ["greet"],
                "expected_files": ["main.py"],
                "variants": [{"variant": "codeatlas_context", "status": "dry_run"}],
            }
        ],
    }
    report = render_agent_eval_markdown(payload)
    assert "Dry-run validates" in report
    assert "Agent Outcome Eval" in report


def test_aggregate_agent_metrics_handles_no_live_variants() -> None:
    metrics = aggregate_agent_metrics(
        [
            {
                "retrieval_symbol_recall": 0.5,
                "retrieval_file_recall": 1.0,
                "variants": [{"variant": "codeatlas_context", "status": "dry_run"}],
            }
        ]
    )
    assert metrics["solve_rate"] is None
    assert metrics["retrieval_symbol_recall"] == 0.5
