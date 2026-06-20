# Demo video script (2–3 min Loom)

A tight, recruiter-friendly walkthrough. Record at 1080p, talk over it, keep it
under 3 minutes. The goal: someone who never opens the repo still understands the
problem, the product, and the technical depth. Export a 10–15s slice as the
README hero GIF.

> Pre-record checklist: live instance up (`/health` ok), demo repo seeded
> (`codeatlas hosted seed-demo`), `STRATUM_DEMO_TOKEN` / `STRATUM_DEMO_REPO_ID`
> set, Claude Code open in a second window with the `codeatlas` MCP server
> connected.

## Beat 1 — The problem (0:00–0:20)
- Land on `/welcome`. Read the one-liner: AI agents waste 60–80% of context
  orienting themselves.
- Say the positioning line out loud: "Most tools show you structure — Stratum
  proves your agents get better context, with measured recall."

## Beat 2 — Zero-setup exploration (0:20–0:45)
- Click **Explore live demo** → dashboard opens pre-loaded with a real repo
  (e.g. Flask), no signup.
- Note: "This is a real, indexed codebase — graph, retrieval, and metrics are
  live, not mocked."

## Beat 3 — The graph (the hero shot) (0:45–1:20)
- Open the **Graph** page. Pan/zoom the force graph.
- Point out: node size = PageRank centrality, color = detected community.
- Click a central node → **blast radius** lights up its dependencies; everything
  else dims. "This is what an agent needs to know before touching that symbol."
- Type a name in search → it zooms to the symbol.

## Beat 4 — The wedge: measured value (1:20–2:00)
- Back on the dashboard, the **Context Savings** card: type a query, hit Measure.
  Show the Without-vs-With bars and the "% fewer tokens" headline.
- Then the **Agent Retrieval Eval** card: Run eval → the per-mode recall/MRR/nDCG
  table. "I can prove retrieval quality, not just draw a diagram."

## Beat 5 — It's real infrastructure (2:00–2:40)
- Switch to Claude Code. Ask it something about the codebase; show it calling the
  `codeatlas` MCP tools (get_agent_context / trace_call_chain) instead of grepping.
- One line on the stack: "FastAPI + React + SQLite, GitHub App with OAuth and
  signed webhooks, a background sync worker, rate limiting, and 1,100+ tests in
  CI — deployed on a single VPS."

## Beat 6 — Close (2:40–3:00)
- Back to `/welcome`. "Live demo and docs are linked below; it's open source."
- End on the graph view (best freeze-frame for a thumbnail).
