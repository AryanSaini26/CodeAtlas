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
  Skeleton,
  StatTile,
} from "../components/ui";
import { Icon } from "../components/Icon";

const LANG_COLORS = [
  "#00f0ff",
  "#bd00ff",
  "#f59e0b",
  "#22c55e",
  "#f87171",
  "#a78bfa",
  "#38bdf8",
  "#fb923c",
];

const KIND_DONUT_COLORS = [
  "#00f0ff",
  "#bd00ff",
  "#f59e0b",
  "#22c55e",
  "#f87171",
  "#a78bfa",
  "#38bdf8",
];

function DonutChart({
  data,
  colors,
}: {
  data: { label: string; value: number }[];
  colors: string[];
}) {
  const size = 140;
  const r = 52;
  const cx = 70;
  const cy = 70;
  const circ = 2 * Math.PI * r;
  const total = data.reduce((s, d) => s + d.value, 0);
  let offset = 0;
  const slices = data.map((d, i) => {
    const pct = total > 0 ? d.value / total : 0;
    const dash = pct * circ;
    const slice = {
      dash,
      gap: circ - dash,
      offset,
      color: colors[i % colors.length],
    };
    offset += dash;
    return slice;
  });
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="#201f1f" strokeWidth={16} />
      {slices.map((s, i) => (
        <circle
          key={i}
          cx={cx}
          cy={cy}
          r={r}
          fill="none"
          stroke={s.color}
          strokeWidth={14}
          strokeDasharray={`${s.dash} ${s.gap}`}
          strokeDashoffset={-s.offset + circ * 0.25}
          style={{ transition: "stroke-dasharray 0.6s ease", opacity: 0.85 }}
        />
      ))}
      <text
        x={cx}
        y={cy - 6}
        textAnchor="middle"
        fill="#e4e4e7"
        fontSize="18"
        fontWeight={700}
        fontFamily='"Space Grotesk", sans-serif'
      >
        {total.toLocaleString()}
      </text>
      <text
        x={cx}
        y={cy + 12}
        textAnchor="middle"
        fill="#52525b"
        fontSize="10"
      >
        symbols
      </text>
    </svg>
  );
}

function LangBar({ langs }: { langs: Record<string, number> }) {
  const entries = Object.entries(langs)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);
  const max = entries[0]?.[1] ?? 1;
  return (
    <div className="flex flex-col gap-2">
      {entries.map(([lang, count], i) => (
        <div key={lang} className="flex items-center gap-2.5">
          <span className="font-mono text-[11px] text-text-2 w-20 shrink-0">
            {lang}
          </span>
          <div className="flex-1 h-1.5 bg-surface-hi rounded overflow-hidden">
            <div
              className="h-full rounded transition-[width] duration-700 ease-out"
              style={{
                width: `${(count / max) * 100}%`,
                backgroundColor: LANG_COLORS[i % LANG_COLORS.length],
              }}
            />
          </div>
          <span className="font-mono text-[11px] text-text-3 w-9 text-right">
            {count}
          </span>
        </div>
      ))}
      {entries.length === 0 && (
        <EmptyState title="No languages yet" hint="Run codeatlas index first." />
      )}
    </div>
  );
}

function ApiError({ message }: { message: string }) {
  return (
    <Card>
      <CardBody>
        <div className="text-bad text-[13px]">
          {message}
          <div className="mt-1.5 text-[11px] text-text-4">
            Is <code className="kbd">codeatlas server</code> running?
          </div>
        </div>
      </CardBody>
    </Card>
  );
}

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

  if (stats.isError) {
    return <ApiError message="API unreachable" />;
  }

  const s = stats.data;
  const kindEntries = s
    ? Object.entries(s.kinds).sort((a, b) => b[1] - a[1])
    : [];

  return (
    <div className="flex flex-col gap-4">
      {/* Hero tiles */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {s ? (
          <>
            <StatTile label="Files indexed" value={s.files.toLocaleString()} color="#00f0ff" />
            <StatTile label="Symbols" value={s.symbols.toLocaleString()} color="#bd00ff" />
            <StatTile
              label="Relationships"
              value={s.relationships.toLocaleString()}
              color="#f59e0b"
            />
          </>
        ) : (
          <>
            <Card><CardBody><Skeleton h={40} /></CardBody></Card>
            <Card><CardBody><Skeleton h={40} /></CardBody></Card>
            <Card><CardBody><Skeleton h={40} /></CardBody></Card>
          </>
        )}
      </div>

      {/* Language + kinds */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Card>
          <CardHeader title="Language breakdown" />
          <CardBody>
            {s ? (
              <LangBar langs={s.languages} />
            ) : (
              <div className="space-y-2">
                <Skeleton />
                <Skeleton />
                <Skeleton />
              </div>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Symbol kinds" />
          <CardBody className="flex items-center gap-5">
            {s ? (
              <>
                <DonutChart
                  data={kindEntries.map(([k, v]) => ({ label: k, value: v }))}
                  colors={KIND_DONUT_COLORS}
                />
                <div className="flex-1 flex flex-col gap-1.5">
                  {kindEntries.map(([kind, count], i) => (
                    <div key={kind} className="flex items-center gap-2">
                      <span
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{
                          backgroundColor:
                            KIND_DONUT_COLORS[i % KIND_DONUT_COLORS.length],
                        }}
                      />
                      <span className="font-mono text-[11px] text-text-2 flex-1">
                        {kind}
                      </span>
                      <span className="font-mono text-[11px] text-text-3">
                        {count}
                      </span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <Skeleton h={140} w={140} />
            )}
          </CardBody>
        </Card>
      </div>

      {/* PageRank */}
      <Card>
        <CardHeader
          title="Top symbols by PageRank"
          action={
            <Link
              to="/analysis"
              className="btn-ghost !text-[11px] !px-2.5 !py-1 no-underline hover:no-underline"
            >
              <Icon name="externalLink" size={12} /> Analysis
            </Link>
          }
        />
        <CardBody className="!px-4 !py-2">
          {pagerank.data ? (
            pagerank.data.ranking.length === 0 ? (
              <EmptyState title="No ranking yet" hint="Run codeatlas index first." />
            ) : (
              pagerank.data.ranking.slice(0, 10).map((r, i) => (
                <div
                  key={r.id}
                  className="flex items-center gap-2 py-1.5 border-b border-border last:border-b-0"
                >
                  <span className="font-mono text-[10px] text-text-4 w-4 text-right shrink-0">
                    {i + 1}
                  </span>
                  <KindDot kind={r.kind} />
                  <Link
                    to={`/symbol/${encodeURIComponent(r.id)}`}
                    className="font-mono text-[11px] text-text-1 hover:text-cyan flex-1 truncate no-underline hover:no-underline"
                  >
                    {r.qualified_name}
                  </Link>
                  <KindBadge kind={r.kind} />
                  <span className="font-mono text-[10px] text-text-4 w-14 text-right">
                    {r.score.toFixed(4)}
                  </span>
                </div>
              ))
            )
          ) : (
            <div className="space-y-2 py-2">
              <Skeleton /> <Skeleton /> <Skeleton />
            </div>
          )}
        </CardBody>
      </Card>

      {/* Hotspots */}
      <Card>
        <CardHeader
          title="File hotspots"
          subtitle="score = churn × in-degree (git commit frequency × incoming references)"
        />
        <CardBody className="!p-0">
          {hotspots.data ? (
            hotspots.data.hotspots.length === 0 ? (
              <EmptyState
                title="No git history found"
                hint="Run inside a git repository to get churn data."
              />
            ) : (
              <table className="w-full border-collapse text-[12px]">
                <thead>
                  <tr className="border-b border-border">
                    {["File", "Churn", "In-degree", "Score"].map((h, i) => (
                      <th
                        key={h}
                        className={`px-4 py-2 text-text-4 text-[11px] font-medium uppercase tracking-[0.05em] ${
                          i === 0 ? "text-left" : "text-right"
                        }`}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {hotspots.data.hotspots.map((h, i) => (
                    <tr
                      key={h.file}
                      className="border-b border-border last:border-b-0 hover:bg-white/[0.02]"
                    >
                      <td className="px-4 py-2 max-w-[260px] truncate">
                        <FilePath path={h.file} />
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-text-3">
                        {h.churn}
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-text-3">
                        {h.in_degree}
                      </td>
                      <td
                        className={`px-4 py-2 text-right font-mono ${
                          i < 3 ? "text-cyan font-semibold" : "text-text-2"
                        }`}
                      >
                        {h.score.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          ) : (
            <div className="p-4 space-y-2">
              <Skeleton /> <Skeleton /> <Skeleton />
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
