# CodeAtlas Agent Outcome Eval

## Summary

| Metric | Value |
|--------|-------|
| Mode | dry-run |
| Tasks | 6 |
| Context mode | `pagerank` |
| Live variants | 0 |
| Solve rate | n/a |
| Verification pass rate | n/a |
| Baseline vs context delta | n/a |
| Avg runtime | n/a |
| Avg context tokens | 0.0 |
| Avg context savings | 0.00% |
| Retrieval symbol recall | 0.000 |
| Retrieval file recall | 0.000 |

> Dry-run validates the suite and planned A/B shape without cloning repos, running agents, or claiming live-agent improvement.

## Tasks

| Task | Repo | Type | Expected symbols | Expected files | Variants |
|------|------|------|------------------|----------------|----------|
| `requests-session-redirect-context` | `requests` | `architecture_question` | `Session.request`, `Session.prepare_request`, `SessionRedirectMixin.rebuild_auth` | `requests/sessions.py` | `codeatlas_context:dry_run` |
| `requests-adapter-test-location` | `requests` | `context_retrieval` | `Session.mount`, `Session.get_adapter` | `requests/sessions.py`, `tests/test_requests.py` | `codeatlas_context:dry_run` |
| `click-command-invoke-context` | `click` | `architecture_question` | `Command.main`, `Command.make_context`, `Command.invoke` | `src/click/core.py` | `codeatlas_context:dry_run` |
| `click-decorator-test-location` | `click` | `context_retrieval` | `command`, `group`, `pass_context`, `make_pass_decorator` | `src/click/decorators.py`, `tests/test_context.py` | `codeatlas_context:dry_run` |
| `rich-console-render-context` | `rich` | `architecture_question` | `Console.print`, `Console.render`, `Console._collect_renderables` | `rich/console.py` | `codeatlas_context:dry_run` |
| `rich-table-column-context` | `rich` | `context_retrieval` | `Table.add_column`, `Table.add_row`, `Table.__rich_console__` | `rich/table.py` | `codeatlas_context:dry_run` |

## Failure Analysis

No live verification failures recorded.
