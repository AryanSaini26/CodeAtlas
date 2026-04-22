import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, type SymbolRef } from "../api";
import {
  Card,
  CardBody,
  EmptyState,
  FilePath,
  KindBadge,
  KindDot,
  Skeleton,
} from "../components/ui";
import { Icon } from "../components/Icon";

export default function SymbolPage() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading, isError, error } = useQuery({
    enabled: !!id,
    queryKey: ["symbol", id],
    queryFn: () => api.symbol(id!),
  });

  if (isLoading)
    return (
      <div className="flex flex-col gap-4">
        <Card>
          <CardBody className="space-y-3">
            <Skeleton w="30%" />
            <Skeleton w="60%" h={24} />
            <Skeleton w="45%" />
          </CardBody>
        </Card>
        <Card>
          <CardBody className="space-y-2">
            <Skeleton /> <Skeleton /> <Skeleton w="70%" />
          </CardBody>
        </Card>
      </div>
    );

  if (isError)
    return (
      <Card>
        <CardBody>
          <EmptyState
            icon={<Icon name="info" size={20} />}
            title="Symbol not found"
            hint={(error as Error)?.message ?? "Unknown error"}
          />
          <div className="flex justify-center mt-3">
            <Link
              to="/search"
              className="btn-ghost !text-[12px] no-underline hover:no-underline"
            >
              ← Back to search
            </Link>
          </div>
        </CardBody>
      </Card>
    );

  if (!data) return null;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <section className="lg:col-span-2 flex flex-col gap-4">
        <Card>
          <div className="px-5 py-4 border-b border-border">
            <div className="flex items-center gap-2 mb-2">
              <KindBadge kind={data.kind} />
            </div>
            <div className="font-mono text-[20px] font-semibold text-text-1 break-all leading-tight">
              {data.name}
            </div>
            <div className="font-mono text-[12px] text-text-3 mt-1 break-all">
              {data.qualified_name}
            </div>
            <div className="mt-2 flex items-center gap-3 flex-wrap">
              <FilePath path={data.file} line={data.start_line} />
              <span className="text-[11px] text-text-4">
                lines {data.start_line}–{data.end_line}
              </span>
              <a
                href={`vscode://file/${data.file}:${data.start_line}`}
                className="font-mono text-[11px] text-cyan inline-flex items-center gap-1 no-underline hover:no-underline"
              >
                <Icon name="externalLink" size={11} /> Open in VS Code
              </a>
            </div>
          </div>
          <CardBody className="space-y-4">
            {data.signature && (
              <div>
                <div className="text-[10px] text-text-4 uppercase tracking-[0.06em] mb-1.5">
                  Signature
                </div>
                <div className="bg-surface border border-border rounded-md px-3.5 py-2.5 font-mono text-[12px] text-cyan-dim leading-relaxed break-all">
                  {data.signature}
                </div>
              </div>
            )}
            {data.docstring && (
              <div>
                <div className="text-[10px] text-text-4 uppercase tracking-[0.06em] mb-1.5">
                  Docstring
                </div>
                <div className="text-[12px] text-text-2 leading-relaxed whitespace-pre-wrap">
                  {data.docstring}
                </div>
              </div>
            )}
            {!data.signature && !data.docstring && (
              <EmptyState
                title="No signature or docstring"
                hint="This symbol hasn't been documented."
              />
            )}
          </CardBody>
        </Card>
      </section>

      <aside className="flex flex-col gap-4">
        <RefCard
          title="Outgoing"
          subtitle="Symbols this one references"
          refs={data.outgoing}
        />
        <RefCard
          title="Incoming"
          subtitle="Symbols referencing this one"
          refs={data.incoming}
        />
      </aside>
    </div>
  );
}

function RefCard({
  title,
  subtitle,
  refs,
}: {
  title: string;
  subtitle: string;
  refs: SymbolRef[];
}) {
  return (
    <Card>
      <div className="px-4 pt-3.5 pb-3 border-b border-border">
        <div className="flex items-center justify-between">
          <h2 className="font-head font-bold text-[13px] text-text-1">
            {title}
          </h2>
          <span className="font-mono text-[11px] text-text-4">
            {refs.length}
          </span>
        </div>
        <p className="text-[11px] text-text-3 mt-0.5">{subtitle}</p>
      </div>
      <div className="max-h-[280px] overflow-y-auto">
        {refs.length === 0 ? (
          <EmptyState title="No references" />
        ) : (
          refs.slice(0, 100).map((r) => (
            <Link
              key={r.id}
              to={`/symbol/${encodeURIComponent(r.id)}`}
              className="flex items-center gap-2 px-4 py-2 border-b border-border last:border-b-0 hover:bg-white/[0.02] no-underline hover:no-underline"
            >
              <KindDot kind={r.kind} size={6} />
              <span className="font-mono text-[11px] text-text-1 hover:text-cyan flex-1 truncate">
                {r.name}
              </span>
              <FilePath path={r.file} line={r.line ?? undefined} />
            </Link>
          ))
        )}
      </div>
    </Card>
  );
}
