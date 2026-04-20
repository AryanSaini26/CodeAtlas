import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, DiffResponse, DiffSymbolEntry } from "../api";
import { Badge, Button, Card, CardBody, CardHeader, EmptyState, Input, Skeleton } from "../components/ui";

function SymbolList({
  items,
  tone,
}: {
  items: DiffSymbolEntry[];
  tone: "success" | "danger" | "warn";
}) {
  if (items.length === 0) {
    return <EmptyState title="—" />;
  }
  return (
    <ul className="divide-y divide-border text-sm">
      {items.map((e, i) => (
        <li key={`${e.file}:${e.name}:${i}`} className="py-2 flex items-center gap-2">
          <Badge tone={tone}>{e.kind}</Badge>
          <span className="font-mono text-slate-100">{e.name}</span>
          <span className="text-xs text-slate-500 ml-auto">
            {e.file}
            {e.new_line ? `:${e.new_line}` : e.old_line ? `:${e.old_line}` : ""}
          </span>
        </li>
      ))}
    </ul>
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
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Symbol diff"
          subtitle="Compare symbols between two git refs"
        />
        <CardBody className="flex flex-wrap items-end gap-3">
          <label className="text-xs text-slate-400">
            Since
            <Input
              className="mt-1"
              value={since}
              onChange={(e) => {
                setSince(e.target.value);
                setArmed(false);
              }}
              placeholder="HEAD~5 or a commit SHA"
            />
          </label>
          <label className="text-xs text-slate-400">
            Until
            <Input
              className="mt-1"
              value={until}
              onChange={(e) => {
                setUntil(e.target.value);
                setArmed(false);
              }}
              placeholder="HEAD"
            />
          </label>
          <Button onClick={() => setArmed(true)} disabled={!since}>
            {isFetching ? "Comparing…" : "Compare"}
          </Button>
        </CardBody>
      </Card>

      {error ? (
        <Card>
          <CardBody>
            <div className="text-sm text-rose-400">
              {(error as Error).message}
            </div>
          </CardBody>
        </Card>
      ) : null}

      {isFetching && !data ? (
        <Card>
          <CardBody className="space-y-2">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
          </CardBody>
        </Card>
      ) : null}

      {data ? (
        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader title={`Added (${data.added.length})`} />
            <CardBody>
              <SymbolList items={data.added} tone="success" />
            </CardBody>
          </Card>
          <Card>
            <CardHeader title={`Removed (${data.removed.length})`} />
            <CardBody>
              <SymbolList items={data.removed} tone="danger" />
            </CardBody>
          </Card>
          <Card>
            <CardHeader title={`Modified (${data.modified.length})`} />
            <CardBody>
              <SymbolList items={data.modified} tone="warn" />
            </CardBody>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
