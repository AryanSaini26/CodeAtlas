# Startup Roadmap

CodeAtlas should not compete as another AI coding assistant. Cursor, GitHub
Copilot, Claude Code, Codex, Sourcegraph Amp, and Devin-like products already
own that framing. CodeAtlas is stronger as agent infrastructure: the persistent
context, eval, security, and observability layer that makes any coding agent
more repo-aware and measurable.

## Positioning

The product promise is:

> CodeAtlas measures and improves the context given to any coding agent.

That keeps the story focused on infrastructure rather than model competition.
The core wedge is shared persistent code context for teams using multiple
agents across the same repositories.

## Hosted Team Context Gateway

The first startup-grade product should be a hosted GitHub-connected gateway:

- GitHub OAuth onboarding and GitHub App installation.
- One-click private repo indexing.
- Webhook auto-sync on push.
- A remote MCP endpoint per repo/team.
- Dashboard with index freshness, graph stats, MCP connection instructions,
  context-pack previews, and recent sync events.

SQLite remains acceptable for the first hosted single-repo instances. The
production migration path should be Postgres for users/teams/billing metadata
and per-repo graph stores for isolation.

## Paid Wedge

The paid feature is not "search my repo." It is proof and governance for AI
agent work:

- baseline vs CodeAtlas-context solve rate
- retrieval misses and failure classes
- estimated tokens saved
- changed files and tests passed/failed
- MCP request audit trail
- prompt-injection and secret-leak warnings

Teams pay when CodeAtlas tells them whether agents are helping, wasting context,
or creating risky changes.

## Security And Governance

MCP and agent workflows introduce real security risk. CodeAtlas should treat
security as a differentiator:

- Scan context packs for prompt-injection instructions.
- Exclude secrets, vendor folders, generated files, and ignored paths by policy.
- Label every run as dry-run, mock-agent, live unsandboxed, or live sandboxed.
- Preserve audit logs for every MCP request and context pack.
- Support self-hosted deployment for sensitive teams.

## Pricing Experiment

Start simple:

| Tier | Price | Included |
|------|-------|----------|
| Free | $0 | Local CLI/MCP, one local repo, public benchmark artifacts |
| Pro | $19-$29/month | One private hosted repo, remote MCP endpoint, webhook sync |
| Team | $99-$199/month | Multiple repos, team members, eval dashboard, audit logs |
| Enterprise | Custom | Self-hosted, SSO, security policies, private networking |

Do not add billing before the hosted repo flow works end-to-end.

## Distribution

The launch demo should show one thing clearly:

1. Connect a GitHub repo.
2. Index it.
3. Paste the MCP URL into Claude Code, Codex, Cursor, or another agent.
4. Run the same task with and without CodeAtlas context.
5. Show solve-rate, token-savings, and trace dashboard differences.

Launch channels: Show HN, GitHub Marketplace, MCP directories, LinkedIn
technical thread, and communities already using Claude Code/Codex/Cursor.
Avoid unsupported competitor claims, including unverified star counts.

## Next Build Sequence

1. GitHub App + OAuth onboarding.
2. Hosted repo registration: users, teams, repos, installations, indexes.
3. Remote MCP endpoint with per-repo auth token.
4. Webhook-triggered indexing jobs.
5. Hosted dashboard for index status, MCP URL, graph stats, and latest reports.
6. Billing after one hosted repo flow is reliable.
