import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";

type Tab = "pagerank" | "hotspots" | "coverage";

export default function AnalysisPage() {
  const [tab, setTab] = useState<Tab>("pagerank");
  return (
    <div className="flex flex-col gap-4">
      <div className="card flex gap-2 items-center">
        <TabButton current={tab} set={setTab} value="pagerank" label="PageRank" />
        <TabButton current={tab} set={setTab} value="hotspots" label="Hotspots" />
        <TabButton
          current={tab}
          set={setTab}
          value="coverage"
          label="Coverage gaps"
        />
      </div>
      <div className="card">
        {tab === "pagerank" && <PageRankTab />}
        {tab === "hotspots" && <HotspotsTab />}
        {tab === "coverage" && <CoverageTab />}
      </div>
    </div>
  );
}

function TabButton({
  current,
  set,
  value,
  label,
}: {
  current: Tab;
  set: (t: Tab) => void;
  value: Tab;
  label: string;
}) {
  const active = current === value;
  return (
    <button
      onClick={() => set(value)}
      className={
        "px-3 py-1.5 rounded-md text-sm " +
        (active
          ? "bg-accent/20 text-accent border border-accent"
          : "text-slate-400 hover:text-slate-100")
      }
    >
      {label}
    </button>
  );
}

function PageRankTab() {
  const { data } = useQuery({
    queryKey: ["pagerank", "analysis"],
    queryFn: () => api.pagerank({ limit: 100 }),
  });
  if (!data) return <p className="text-slate-500 text-sm">Loading…</p>;
  return (
    <ol className="space-y-1 text-sm">
      {data.ranking.map((r, i) => (
        <li key={r.id} className="flex items-baseline gap-2">
          <span className="text-slate-500 w-6 text-right">{i + 1}</span>
          <Link
            to={`/symbol/${encodeURIComponent(r.id)}`}
            className="font-bold"
          >
            {r.qualified_name}
          </Link>
          <span className="text-xs text-slate-500">{r.kind}</span>
          <span className="text-xs text-slate-500 ml-auto">
            {r.score.toFixed(5)}
          </span>
        </li>
      ))}
    </ol>
  );
}

function HotspotsTab() {
  const { data } = useQuery({
    queryKey: ["hotspots", "analysis"],
    queryFn: () => api.hotspots({ limit: 100 }),
  });
  if (!data) return <p className="text-slate-500 text-sm">Loading…</p>;
  return (
    <table className="w-full text-sm">
      <thead className="text-slate-500 text-xs uppercase text-left">
        <tr>
          <th>File</th>
          <th className="text-right">Churn</th>
          <th className="text-right">In-degree</th>
          <th className="text-right">Score</th>
        </tr>
      </thead>
      <tbody>
        {data.hotspots.map((h) => (
          <tr key={h.file} className="border-t border-border/60">
            <td className="py-1 truncate">{h.file}</td>
            <td className="py-1 text-right">{h.churn}</td>
            <td className="py-1 text-right">{h.in_degree}</td>
            <td className="py-1 text-right">{h.score.toFixed(2)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CoverageTab() {
  const [offset, setOffset] = useState(0);
  const { data } = useQuery({
    queryKey: ["coverage", offset],
    queryFn: () => api.coverageGaps({ limit: 50, offset }),
  });
  if (!data) return <p className="text-slate-500 text-sm">Loading…</p>;
  return (
    <div>
      <ul className="divide-y divide-border/60 text-sm">
        {data.gaps.map((g) => (
          <li key={g.id} className="py-2">
            <Link
              to={`/symbol/${encodeURIComponent(g.id)}`}
              className="font-bold"
            >
              {g.qualified_name}
            </Link>
            <span className="text-xs text-slate-500 ml-2">{g.kind}</span>
            <div className="text-xs text-slate-500">
              {g.file}:{g.line}
            </div>
          </li>
        ))}
      </ul>
      <div className="flex justify-between mt-3 text-xs">
        <button
          className="btn"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - 50))}
        >
          ← Prev
        </button>
        <span className="text-slate-500 self-center">offset {data.offset}</span>
        <button
          className="btn"
          disabled={!data.has_more}
          onClick={() => setOffset(data.next_offset ?? offset + 50)}
        >
          Next →
        </button>
      </div>
    </div>
  );
}
