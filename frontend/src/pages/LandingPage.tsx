import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { hostedApi, hostedOAuthLoginUrl } from "../api";
import { Badge, Button, Card, CardBody, StatTile } from "../components/ui";
import { Icon } from "../components/Icon";

const DOCS_URL = "https://aryansaini26.github.io/CodeAtlas/";

export default function LandingPage() {
  // oauth_configured tells us whether "Connect GitHub" can start the real flow.
  const githubApp = useQuery({
    queryKey: ["hosted", "github", "app"],
    queryFn: () => hostedApi.githubApp(),
    retry: false,
  });
  const oauthReady = githubApp.data?.oauth_configured ?? false;

  const demo = useQuery({
    queryKey: ["hosted", "demo-info"],
    queryFn: () => hostedApi.demoInfo(),
    retry: false,
  });
  const navigate = useNavigate();

  const openDemo = () => {
    const info = demo.data;
    if (!info?.enabled || !info.token) return;
    localStorage.setItem("codeatlas.hostedToken", info.token);
    navigate("/hosted");
  };

  return (
    <div className="mx-auto flex max-w-[920px] flex-col gap-8 py-6">
      {/* Hero */}
      <div className="flex flex-col gap-4">
        <Badge tone="cyan">Persistent MCP context for AI coding agents</Badge>
        <h1 className="font-head text-[34px] font-bold leading-tight text-text-1">
          Your AI agents start every session from zero. Stratum doesn&apos;t.
        </h1>
        <p className="max-w-[680px] text-[14px] leading-relaxed text-text-2">
          AI coding agents waste 60–80% of their context window just orienting
          themselves in a codebase before doing real work. Stratum gives your
          agents a persistent, shared CodeAtlas graph — structure plus semantics —
          so they navigate intelligently from the first token.
        </p>
        {/* Positioning line (the one sentence that separates us from diagram-first tools). */}
        <p className="max-w-[680px] text-[14px] font-medium leading-relaxed text-text-1">
          Most code graph tools show you structure. Stratum proves your AI agents
          are actually getting better context — with measured recall, not just a
          diagram.
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          {oauthReady ? (
            <Button onClick={() => (window.location.href = hostedOAuthLoginUrl())}>
              <Icon name="mcp" size={14} /> Connect GitHub
            </Button>
          ) : (
            <Link to="/hosted">
              <Button>
                <Icon name="mcp" size={14} /> Open the dashboard
              </Button>
            </Link>
          )}
          {demo.data?.enabled ? (
            <Button variant="ghost" onClick={openDemo}>
              <Icon name="graph" size={14} /> Explore live demo
            </Button>
          ) : null}
          <a href={DOCS_URL} target="_blank" rel="noreferrer">
            <Button variant="ghost">
              <Icon name="externalLink" size={14} /> Read the docs
            </Button>
          </a>
        </div>
      </div>

      {/* Proof — real numbers from the committed benchmark reports. */}
      <div>
        <div className="mb-3 text-[12px] uppercase tracking-[0.06em] text-text-3">
          Measured retrieval quality
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatTile label="Recall@k (local suite)" value="1.000" />
          <StatTile label="MRR" value="0.978" />
          <StatTile label="Context savings" value="27–60%" color="#a855f7" />
          <StatTile label="MCP tools" value="30" color="#22c55e" />
        </div>
        <p className="mt-3 text-[11px] text-text-4">
          From the committed retrieval reports (30 deterministic local tasks +
          a 3-repo OSS suite). Run it yourself: <code>codeatlas eval --compare</code>.
        </p>
      </div>

      {/* How */}
      <Card>
        <CardBody>
          <div className="mb-3 text-[13px] font-semibold text-text-1">
            How it works
          </div>
          <ol className="flex flex-col gap-2 text-[13px] text-text-2">
            <li>
              <span className="text-text-3">1.</span> Connect a GitHub repo — the
              App clones and indexes it into a persistent graph.
            </li>
            <li>
              <span className="text-text-3">2.</span> Every push auto-syncs the
              graph in the background (measured, deduplicated, rate-limited).
            </li>
            <li>
              <span className="text-text-3">3.</span> Your agents query a
              repo-scoped remote MCP endpoint for real context — and you can
              measure whether retrieval is actually improving.
            </li>
          </ol>
        </CardBody>
      </Card>
    </div>
  );
}
