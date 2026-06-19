# Stratum Startup Plan

Stratum is the hosted product built on the CodeAtlas open-source engine. The
business should not be positioned as another coding assistant. The wedge is
agent infrastructure: persistent repository context, sync, eval, security, and
observability for teams using Claude Code, Codex, Cursor, Copilot, and whatever
agent comes next.

## Market Position

The crowded category is "AI writes code for you." Stratum should avoid that
fight. The more durable category is "AI coding agent infrastructure." Existing
assistants need repository context, policy, audit trails, and outcome
measurement, especially when multiple developers and agents touch the same
codebase.

Stratum's differentiated claim:

> Make every coding agent repo-aware, measurable, and governable.

That claim is stronger than "better search" because it turns context quality
into team-level reliability: did the agent find the right files, did tests pass,
which context was used, was sensitive data excluded, and did the result improve
over a baseline?

## Competitor Framing

- Cursor, Copilot, Claude Code, Codex, Amp, and Devin-like tools are agent or
  assistant experiences.
- Sourcegraph and code search platforms own mature enterprise search and
  navigation workflows.
- Greptile-style systems focus on AI code review and repository Q&A.
- MCP memory/code-graph projects prove developer demand but often stop at local
  single-user context.

Stratum's wedge is cross-agent infrastructure: it does not replace the coding
agent; it supplies persistent context, sync, evals, audit logs, and security
controls to whichever agent a team already uses.

## Ideal Customer

Start with small AI-heavy engineering teams:

- teams already using Claude Code, Codex, Cursor, or Copilot agents daily
- startups with fast-moving repos and low tolerance for repeated agent
  orientation
- open-source maintainers who want better issue-to-edit localization
- security-conscious teams evaluating MCP or agent workflows

The first buyer is likely a technical founder, staff engineer, or engineering
manager who wants agent productivity but needs proof and control.

## Product Sequence

1. Hosted GitHub App onboarding: connect GitHub, activate a repo, index it, and
   show sync freshness.
2. Remote context gateway: provide authenticated context API and MCP endpoints
   per repo/team.
3. Agent eval dashboard: compare prompt-only baseline vs Stratum context on
   deterministic tasks and optional live-agent runs.
4. Security layer: prompt-injection scanning, secret exclusion, policy filters,
   and audit logs for every context pack.
5. Observability: trace indexing, retrieval, MCP calls, agent runs, verifier
   results, and failure classes.
6. Enterprise path: self-hosting, SSO, VPC/private GitHub, retention controls,
   and policy exports.

## Pricing Hypothesis

| Tier | Price | Included |
|------|-------|----------|
| Free | $0 | Local CodeAtlas CLI/MCP, public benchmarks, one local repo |
| Pro | $19-$29/month | One private hosted repo, webhook sync, remote context API |
| Team | $99-$199/month | Multiple repos, members, eval dashboard, audit logs |
| Enterprise | Custom | Self-hosted, SSO, security policies, private networking |

Do not build billing first. Charge after GitHub connect, repo activation,
webhook sync, and context retrieval work end to end.

## Launch Plan

The demo should be a 90-second proof loop:

1. Connect a GitHub repo.
2. Index and auto-sync on push.
3. Paste the Stratum context endpoint or MCP config into an agent.
4. Run one task with baseline context and one with Stratum context.
5. Show solve rate, token savings, retrieved files, verifier result, and audit
   trail.

Distribution should focus on developers already using agents: Show HN, GitHub
Marketplace, MCP directories, LinkedIn technical threads, and communities where
AI coding tools are discussed. Avoid unsupported claims about competitor stars,
revenue, or benchmark wins.

## What To Build Next

The next money-making milestone is a real GitHub App flow:

- setup callback and installation registration
- GitHub API repo listing with mocked CI tests
- hosted clone/index jobs for activated repos
- webhook-triggered incremental sync
- repo-scoped remote MCP/context credentials
- dashboard view for sync status, graph stats, context preview, and audit logs

Stripe, team invites, and enterprise controls should wait until this loop is
demoable with one private repo.
