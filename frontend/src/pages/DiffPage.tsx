import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, DiffResponse, DiffSymbolEntry } from "../api";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  FilePath,
  KindBadge,
  KindDot,
  Skeleton,
} from "../components/ui";
import { Icon } from "../components/Icon";

type Tone = "added" | "removed" | "modified";

const TONE: Record<Tone, { color: string; label: string; icon: string }> = {
  added: { color: "#22c55e", label: "Added", icon: "check" },
  removed: { color: "#ef4444", label: "Removed", icon: "x" },
  modified: { color: "#f59e0b", label: "Modified", icon: "refresh" },
};

function DiffColumn({
  tone,
  items,
}: {
  tone: Tone;
  items: DiffSymbolEntry[];
}) {
  const meta = TONE[tone];
  return (
    <Card className="flex flex-col min-h-0">
      <div
        className="flex items-center gap-2 px-4 pt-3.5 pb-3 border-b border-border"
        style={{ borderLeft: `3px solid ${meta.color}` }}
      >
        <span style={{ color: meta.color }}>
          <Icon name={meta.icon} size={13} />
        </span>
        <span className="font-head font-bold text-[13px] text-text-1">
          {meta.label}
        </span>
        <span
          className="ml-auto font-mono text-[11px] rounded px-1.5 py-[1px] border"
          style={{
            color: meta.color,
            borderColor: `${meta.color}40`,
            backgroundColor: `${meta.color}14`,
          }}
        >
          {items.length}
        </span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {items.length === 0 ? (
          <EmptyState title="No changes" />
        ) : (
          items.map((e, i) => {
            const line = e.new_line ?? e.old_line ?? undefined;
            return (
              <div
                key={`${e.file}:${e.name}:${i}`}
                className="px-4 py-2 border-b border-border last:border-b-0 hover:bg-white/[0.02]"
              >
                <div className="flex items-center gap-2 mb-1">
                  <KindDot kind={e.kind} />
                  <span className="font-mono text-[12px] text-text-1 flex-1 truncate">
                    {e.name}
                  </span>
                  <KindBadge kind={e.kind} />
                </div>
                <FilePath path={e.file} line={line} />
              </div>
            );
          })
        )}
      </div>
    </Card>
  );
}

export default function DiffPage() {
  const [since, setSince] = useState("HEAD~1");
  const [until, setUntil] = useState("HEAD");
  const [armed, setArmed] = useState(true);

  const { data, error, isFetching } = useQuery<DiffResponse>({
    queryKey: ["diff", since, until],
    queryFn: () => api.diff({ since, until }),
    enabled: armed && since.length > 0,
  });

  return (
    <div className="flex flex-col gap-3 h-full min-h-0">
      <Card>
        <CardHeader
          title="Symbol diff"
          subtitle="Compare symbols added, removed, or modified between two git refs"
        />
        <CardBody className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-[11px] uppercase tracking-[0.06em] text-text-4">
            Since
            <input
              value={since}
              onChange={(e) => {
                setSince(e.target.value);
                setArmed(false);
              }}
              placeholder="HEAD~5 or commit SHA"
              className="bg-surface border border-border rounded-md px-3 py-1.5 font-mono text-[12px] text-text-1 outline-none focus:border-cyan/50 w-48"
            />
          </label>
          <label className="flex flex-col gap-1 text-[11px] uppercase tracking-[0.06em] text-text-4">
            Until
            <input
              value={until}
              onChange={(e) => {
                setUntil(e.target.value);
                setArmed(false);
              }}
              placeholder="HEAD"
              className="bg-surface border border-border rounded-md px-3 py-1.5 font-mono text-[12px] text-text-1 outline-none focus:border-cyan/50 w-40"
            />
          </label>
          <Button
            variant="primary"
            onClick={() => setArmed(true)}
            disabled={!since}
          >
            <Icon name="refresh" size={12} />
            <span className="ml-1.5">
              {isFetching ? "Comparing…" : "Compare"}
            </span>
          </Button>
          {data && (
            <div className="ml-auto text-[11px] text-text-3 font-mono">
              <span className="text-text-4">since</span> {data.since}{" "}
              <span className="text-text-4">→ until</span> {data.until}
            </div>
          )}
        </CardBody>
      </Card>

      {error ? (
        <Card>
          <CardBody>
            <div className="text-[12px] text-bad">
              {(error as Error).message}
            </div>
          </CardBody>
        </Card>
      ) : null}

      {isFetching && !data ? (
        <div className="grid gap-3 md:grid-cols-3 flex-1 min-h-0">
          {([0, 1, 2] as const).map((i) => (
            <Card key={i}>
              <CardBody className="space-y-2">
                <Skeleton /> <Skeleton /> <Skeleton w="60%" />
              </CardBody>
            </Card>
          ))}
        </div>
      ) : null}

      {data ? (
        <div className="grid gap-3 md:grid-cols-3 flex-1 min-h-0">
          <DiffColumn tone="added" items={data.added} />
          <DiffColumn tone="removed" items={data.removed} />
          <DiffColumn tone="modified" items={data.modified} />
        </div>
      ) : null}
    </div>
  );
}
