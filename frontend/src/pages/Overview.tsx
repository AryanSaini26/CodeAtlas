import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";

export default function Overview() {
  const stats = useQuery({ queryKey: ["stats"], queryFn: () => api.stats() });
  const pagerank = useQuery({
    queryKey: ["pagerank", "overview"],
    queryFn: () => api.pagerank({ limit: 10 }),
  });
  const hotspots = useQuery({
    queryKey: ["hotspots", "overview"],
    queryFn: () => api.hotspots({ limit: 10 }),
  });

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <section className="card">
        <h2 className="text-sm text-slate-400 uppercase tracking-wide mb-3">
          Repository
        </h2>
        {stats.isLoading && <p className="text-slate-500">Loading…</p>}
        {stats.isError && (
          <p className="text-red-400 text-sm">
            API unreachable. Is <code className="kbd">codeatlas server</code>{" "}
            running?
          </p>
        )}
        {stats.data && (
          <dl className="space-y-2">
            <Row label="Files" value={stats.data.files} />
            <Row label="Symbols" value={stats.data.symbols} />
            <Row label="Relationships" value={stats.data.relationships} />
            <Row
              label="Languages"
              value={Object.keys(stats.data.languages).length}
            />
          </dl>
        )}
      </section>

      <section className="card md:col-span-2">
        <h2 className="text-sm text-slate-400 uppercase tracking-wide mb-3">
          Top PageRank
        </h2>
        {pagerank.data && (
          <ul className="space-y-1 text-sm">
            {pagerank.data.ranking.map((r, i) => (
              <li key={r.id} className="flex items-baseline gap-2">
                <span className="text-slate-500 w-4 text-right">{i + 1}</span>
                <Link
                  to={`/symbol/${encodeURIComponent(r.id)}`}
                  className="font-bold"
                >
                  {r.qualified_name}
                </Link>
                <span className="text-xs text-slate-500">{r.kind}</span>
                <span className="text-xs text-slate-500 ml-auto">
                  {r.score.toFixed(4)}
                </span>
              </li>
            ))}
            {pagerank.data.ranking.length === 0 && (
              <li className="text-slate-500 text-sm">No ranking yet.</li>
            )}
          </ul>
        )}
      </section>

      <section className="card md:col-span-3">
        <h2 className="text-sm text-slate-400 uppercase tracking-wide mb-3">
          Hotspots (churn × in-degree)
        </h2>
        {hotspots.data && (
          <table className="w-full text-sm">
            <thead className="text-slate-500 text-left text-xs uppercase">
              <tr>
                <th className="py-1">File</th>
                <th className="py-1 text-right">Churn</th>
                <th className="py-1 text-right">In-degree</th>
                <th className="py-1 text-right">Score</th>
              </tr>
            </thead>
            <tbody>
              {hotspots.data.hotspots.map((h) => (
                <tr
                  key={h.file}
                  className="border-t border-border/60 hover:bg-panel/60"
                >
                  <td className="py-1 truncate">{h.file}</td>
                  <td className="py-1 text-right">{h.churn}</td>
                  <td className="py-1 text-right">{h.in_degree}</td>
                  <td className="py-1 text-right">{h.score.toFixed(2)}</td>
                </tr>
              ))}
              {hotspots.data.hotspots.length === 0 && (
                <tr>
                  <td
                    className="py-2 text-slate-500 text-center"
                    colSpan={4}
                  >
                    No git history found — run inside a git repo.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function Row({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex justify-between items-baseline border-b border-border/60 pb-1 last:border-0">
      <dt className="text-slate-400">{label}</dt>
      <dd className="font-bold">{value.toLocaleString()}</dd>
    </div>
  );
}
