import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import {
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  FilePath,
  KindBadge,
  KindDot,
  ScoreBar,
  Skeleton,
} from "../components/ui";
import { Icon } from "../components/Icon";

type Tab = "pagerank" | "hotspots" | "communities" | "coverage";

const TABS: { value: Tab; label: string; icon: string }[] = [
  { value: "pagerank", label: "PageRank", icon: "analysis" },
  { value: "hotspots", label: "Hotspots", icon: "graph" },
  { value: "communities", label: "Communities", icon: "graph" },
  { value: "coverage", label: "Coverage gaps", icon: "info" },
];

export default function AnalysisPage() {
  const [tab, setTab] = useState<Tab>("pagerank");
  return (
    <div className="flex flex-col gap-4">
      <div className="glass rounded-[10px] flex gap-1 p-1.5 self-start">
        {TABS.map((t) => {
          const active = tab === t.value;
          return (
            <button
              key={t.value}
              type="button"
              onClick={() => setTab(t.value)}
              className={
                "flex items-center gap-1.5 px-3.5 py-1.5 rounded-md text-[12px] font-medium transition-colors " +
                (active
                  ? "bg-cyan/[0.12] text-cyan"
                  : "text-text-3 hover:text-text-1 hover:bg-white/[0.03]")
              }
            >
              <Icon name={t.icon} size={12} />
              {t.label}
            </button>
          );
        })}
      </div>

      {tab === "pagerank" && <PageRankTab />}
      {tab === "hotspots" && <HotspotsTab />}
      {tab === "communities" && <CommunitiesTab />}
      {tab === "coverage" && <CoverageTab />}
    </div>
  );
}

function PageRankTab() {
  const { data, isFetching } = useQuery({
    queryKey: ["pagerank", "analysis"],
    queryFn: () => api.pagerank({ limit: 100 }),
  });
  const maxScore = data?.ranking[0]?.score ?? 1;
  return (
    <Card>
      <CardHeader
        title="Top 100 symbols by PageRank"
        subtitle="Importance weighted by incoming references (call, import, inherit)"
      />
      <CardBody className="!p-0">
        {!data && isFetching && (
          <div className="p-4 space-y-2">
            <Skeleton /> <Skeleton /> <Skeleton /> <Skeleton /> <Skeleton />
          </div>
        )}
        {data && data.ranking.length === 0 && (
          <EmptyState
            icon={<Icon name="info" size={20} />}
            title="No PageRank data"
            hint="Run codeatlas index first."
          />
        )}
        {data?.ranking.map((r, i) => (
          <div
            key={r.id}
            className="flex items-center gap-3 px-4 py-2 border-b border-border last:border-b-0 hover:bg-white/[0.02]"
          >
            <span className="font-mono text-[10px] text-text-4 w-7 text-right shrink-0">
              {i + 1}
            </span>
            <KindDot kind={r.kind} />
            <Link
              to={`/symbol/${encodeURIComponent(r.id)}`}
              className="font-mono text-[12px] text-text-1 hover:text-cyan flex-1 truncate no-underline hover:no-underline"
            >
              {r.qualified_name}
            </Link>
            <div className="w-32">
              <KindBadge kind={r.kind} />
            </div>
            <div className="w-44">
              <ScoreBar score={r.score} max={maxScore} />
            </div>
          </div>
        ))}
      </CardBody>
    </Card>
  );
}

function HotspotsTab() {
  const { data, isFetching } = useQuery({
    queryKey: ["hotspots", "analysis"],
    queryFn: () => api.hotspots({ limit: 100 }),
  });
  const maxScore = data?.hotspots[0]?.score ?? 1;
  return (
    <Card>
      <CardHeader
        title="File hotspots"
        subtitle="score = git commit frequency × incoming reference count"
      />
      <CardBody className="!p-0">
        {!data && isFetching && (
          <div className="p-4 space-y-2">
            <Skeleton /> <Skeleton /> <Skeleton /> <Skeleton />
          </div>
        )}
        {data && data.hotspots.length === 0 && (
          <EmptyState
            icon={<Icon name="info" size={20} />}
            title="No git history found"
            hint="Run inside a git repository to get churn data."
          />
        )}
        {data && data.hotspots.length > 0 && (
          <table className="w-full border-collapse text-[12px]">
            <thead>
              <tr className="border-b border-border">
                {["#", "File", "Churn", "In-degree", "Score"].map((h, i) => (
                  <th
                    key={h}
                    className={`px-4 py-2 text-text-4 text-[11px] font-medium uppercase tracking-[0.05em] ${
                      i >= 2 ? "text-right" : "text-left"
                    }`}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.hotspots.map((h, i) => (
                <tr
                  key={h.file}
                  className="border-b border-border last:border-b-0 hover:bg-white/[0.02]"
                >
                  <td className="px-4 py-2 font-mono text-[10px] text-text-4 w-8">
                    {i + 1}
                  </td>
                  <td className="px-4 py-2 max-w-[340px] truncate">
                    <FilePath path={h.file} />
                  </td>
                  <td className="px-4 py-2 text-right font-mono text-text-2">
                    {h.churn}
                  </td>
                  <td className="px-4 py-2 text-right font-mono text-text-2">
                    {h.in_degree}
                  </td>
                  <td className="px-4 py-2 text-right w-44">
                    <ScoreBar
                      score={h.score}
                      max={maxScore}
                      color={i < 3 ? "#00f0ff" : "#52525b"}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardBody>
    </Card>
  );
}

const COMMUNITY_COLORS = [
  "#00f0ff",
  "#bd00ff",
  "#f59e0b",
  "#22c55e",
  "#f87171",
  "#a78bfa",
  "#38bdf8",
  "#fb923c",
];

function hashColor(id: string): string {
  let h = 0;
  for (let i = 0; i < id.length; i++) {
    h = (h * 31 + id.charCodeAt(i)) >>> 0;
  }
  return COMMUNITY_COLORS[h % COMMUNITY_COLORS.length];
}

function CommunitiesTab() {
  const { data, isFetching } = useQuery({
    queryKey: ["communities"],
    queryFn: () => api.communities(),
  });
  const maxSize = data?.communities[0]?.size ?? 1;
  return (
    <Card>
      <CardHeader
        title="Detected communities"
        subtitle="Strongly-connected clusters via Louvain modularity — cohesive subsystems in the codebase"
      />
      <CardBody className="!p-0">
        {!data && isFetching && (
          <div className="p-4 space-y-2">
            <Skeleton /> <Skeleton /> <Skeleton />
          </div>
        )}
        {data && data.communities.length === 0 && (
          <EmptyState
            icon={<Icon name="info" size={20} />}
            title="No communities detected"
            hint="Run codeatlas index first, then detect communities from the graph."
          />
        )}
        {data?.communities.map((c, i) => {
          const color = hashColor(c.community_id);
          return (
            <div
              key={c.community_id}
              className="px-4 py-3 border-b border-border last:border-b-0 hover:bg-white/[0.02]"
            >
              <div className="flex items-center gap-2.5 mb-2">
                <span className="font-mono text-[10px] text-text-4 w-7 text-right shrink-0">
                  {i + 1}
                </span>
                <span
                  className="w-2 h-2 rounded-full shrink-0"
                  style={{ backgroundColor: color }}
                />
                <span className="font-mono text-[12px] text-text-2 flex-1 truncate">
                  {c.community_id}
                </span>
                <span
                  className="font-mono text-[11px] rounded px-1.5 py-[1px] border"
                  style={{
                    color,
                    borderColor: `${color}40`,
                    backgroundColor: `${color}14`,
                  }}
                >
                  {c.size} members
                </span>
                <div className="w-32">
                  <ScoreBar score={c.size} max={maxSize} color={color} />
                </div>
              </div>
              {c.sample_symbols.length > 0 && (
                <div className="ml-11 flex flex-wrap gap-1.5">
                  {c.sample_symbols.map((s) => (
                    <span
                      key={s}
                      className="font-mono text-[10px] text-text-3 bg-surface border border-border rounded px-1.5 py-[1px] truncate max-w-[280px]"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </CardBody>
    </Card>
  );
}

function CoverageTab() {
  const [offset, setOffset] = useState(0);
  const LIMIT = 50;
  const { data, isFetching } = useQuery({
    queryKey: ["coverage", offset],
    queryFn: () => api.coverageGaps({ limit: LIMIT, offset }),
  });
  return (
    <Card>
      <CardHeader
        title="Coverage gaps"
        subtitle="Public symbols with no docstring — candidates for documentation"
      />
      <CardBody className="!p-0">
        {!data && isFetching && (
          <div className="p-4 space-y-2">
            <Skeleton /> <Skeleton /> <Skeleton /> <Skeleton />
          </div>
        )}
        {data && data.gaps.length === 0 && (
          <EmptyState
            icon={<Icon name="check" size={20} />}
            title="No coverage gaps"
            hint="Every public symbol has documentation."
          />
        )}
        {data?.gaps.map((g) => (
          <Link
            key={g.id}
            to={`/symbol/${encodeURIComponent(g.id)}`}
            className="flex items-center gap-3 px-4 py-2 border-b border-border last:border-b-0 hover:bg-white/[0.02] no-underline hover:no-underline"
          >
            <KindDot kind={g.kind} />
            <span className="font-mono text-[12px] text-text-1 hover:text-cyan flex-1 truncate">
              {g.qualified_name}
            </span>
            <KindBadge kind={g.kind} />
            <FilePath path={g.file} line={g.line} />
          </Link>
        ))}

        {data && data.count > LIMIT && (
          <div className="px-4 py-2.5 border-t border-border flex items-center gap-2">
            <button
              type="button"
              className="btn-ghost !text-[11px] !px-2.5 !py-1"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - LIMIT))}
            >
              ← Prev
            </button>
            <span className="flex-1 text-center text-[10px] text-text-4 font-mono">
              {offset + 1}–{Math.min(offset + LIMIT, data.count)} / {data.count}
            </span>
            <button
              type="button"
              className="btn-ghost !text-[11px] !px-2.5 !py-1"
              disabled={!data.has_more}
              onClick={() => setOffset(data.next_offset ?? offset + LIMIT)}
            >
              Next →
            </button>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
