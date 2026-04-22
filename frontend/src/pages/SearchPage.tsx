import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type SearchHit } from "../api";
import {
  Badge,
  EmptyState,
  FilePath,
  KindBadge,
  KindDot,
  Skeleton,
} from "../components/ui";
import { Icon } from "../components/Icon";

const KINDS = ["", "function", "method", "class", "module", "variable", "interface", "type"];
const PAGE = 25;

function useDebounce<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

function DetailPane({ hit }: { hit: SearchHit | null }) {
  const details = useQuery({
    enabled: !!hit,
    queryKey: ["symbol", hit?.id],
    queryFn: () => api.symbol(hit!.id),
  });

  if (!hit) {
    return (
      <div className="flex-1 glass rounded-[10px] flex items-center justify-center">
        <EmptyState
          icon={<Icon name="search" size={24} />}
          title="Select a result"
          hint="Click a symbol to see its signature, docstring, and references."
        />
      </div>
    );
  }

  const d = details.data;
  return (
    <div className="flex-1 glass rounded-[10px] overflow-hidden flex flex-col animate-slide-right">
      <div className="px-5 py-4 border-b border-border">
        <div className="flex items-center gap-2 mb-1.5">
          <KindBadge kind={hit.kind} />
          {hit.score != null && (
            <span className="font-mono text-[10px] text-text-4">
              score {hit.score.toFixed(2)}
            </span>
          )}
        </div>
        <div className="font-mono text-[16px] font-semibold text-text-1 mb-1">
          {hit.name}
        </div>
        <div className="font-mono text-[11px] text-text-3">
          {hit.qualified_name}
        </div>
        <div className="mt-1.5">
          <FilePath path={hit.file} line={d?.start_line} />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-4">
        {!d && details.isFetching && (
          <div className="space-y-2">
            <Skeleton /> <Skeleton /> <Skeleton w="60%" />
          </div>
        )}

        {d?.signature && (
          <div>
            <div className="text-[10px] text-text-4 uppercase tracking-[0.06em] mb-1.5">
              Signature
            </div>
            <div className="bg-surface border border-border rounded-md px-3.5 py-2.5 font-mono text-[12px] text-cyan-dim leading-relaxed break-all">
              {d.signature}
            </div>
          </div>
        )}

        {d?.docstring && (
          <div>
            <div className="text-[10px] text-text-4 uppercase tracking-[0.06em] mb-1.5">
              Docstring
            </div>
            <div className="text-[12px] text-text-2 leading-relaxed whitespace-pre-wrap">
              {d.docstring}
            </div>
          </div>
        )}

        {d && (
          <div className="flex gap-5">
            <div>
              <div className="text-[10px] text-text-4 uppercase tracking-[0.06em] mb-1">
                Lines
              </div>
              <span className="font-mono text-[12px] text-text-2">
                {d.start_line}–{d.end_line}
              </span>
            </div>
            <div>
              <div className="text-[10px] text-text-4 uppercase tracking-[0.06em] mb-1">
                Open
              </div>
              <a
                href={`vscode://file/${d.file}:${d.start_line}`}
                className="font-mono text-[11px] text-cyan inline-flex items-center gap-1 no-underline hover:no-underline"
              >
                <Icon name="externalLink" size={11} /> VS Code
              </a>
            </div>
          </div>
        )}

        {d && (
          <RefList label={`Incoming (${d.incoming.length})`} refs={d.incoming} />
        )}
        {d && (
          <RefList label={`Outgoing (${d.outgoing.length})`} refs={d.outgoing} />
        )}
      </div>
    </div>
  );
}

function RefList({
  label,
  refs,
}: {
  label: string;
  refs: { id: string; name: string; kind: string; file: string; line?: number | null }[];
}) {
  return (
    <div>
      <div className="text-[10px] text-text-4 uppercase tracking-[0.06em] mb-2">
        {label}
      </div>
      {refs.length === 0 ? (
        <span className="text-[11px] text-text-4">No references</span>
      ) : (
        refs.map((r) => (
          <Link
            key={r.id}
            to={`/symbol/${encodeURIComponent(r.id)}`}
            className="flex items-center gap-2 py-1.5 border-b border-border last:border-b-0 no-underline hover:no-underline"
          >
            <KindDot kind={r.kind} size={6} />
            <span className="font-mono text-[11px] text-text-1 hover:text-cyan flex-1">
              {r.name}
            </span>
            <FilePath path={r.file} line={r.line ?? undefined} />
          </Link>
        ))
      )}
    </div>
  );
}

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [kindFilter, setKindFilter] = useState("");
  const [fileFilter, setFileFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<SearchHit | null>(null);

  const dq = useDebounce(query, 250);
  const dFile = useDebounce(fileFilter, 250);

  const hasQuery = dq.length > 0 || kindFilter !== "" || dFile.length > 0;

  const { data, isFetching } = useQuery({
    enabled: hasQuery,
    queryKey: ["search", dq, kindFilter, dFile, offset],
    queryFn: () =>
      api.search({
        q: dq || "*",
        kind: kindFilter || undefined,
        file: dFile || undefined,
        offset,
        limit: PAGE,
      }),
  });

  const clearAll = () => {
    setQuery("");
    setKindFilter("");
    setFileFilter("");
    setOffset(0);
  };

  return (
    <div className="flex flex-col gap-3 h-full">
      {/* Search bar */}
      <div className="glass rounded-[10px] px-4 py-3 flex gap-2.5 items-center">
        <Icon name="search" size={14} className="text-text-4 shrink-0" />
        <input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOffset(0);
          }}
          placeholder="Search symbols — names, qualified paths, doc terms…"
          autoFocus
          className="flex-1 bg-transparent outline-none border-none font-mono text-[13px] text-text-1 placeholder:text-text-4"
        />
        <select
          value={kindFilter}
          onChange={(e) => {
            setKindFilter(e.target.value);
            setOffset(0);
          }}
          className="bg-surface border border-border rounded-md text-text-2 text-[12px] px-2 py-1 outline-none cursor-pointer"
        >
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {k || "All kinds"}
            </option>
          ))}
        </select>
        <input
          value={fileFilter}
          onChange={(e) => {
            setFileFilter(e.target.value);
            setOffset(0);
          }}
          placeholder="file glob…"
          className="w-36 bg-surface border border-border rounded-md text-text-2 font-mono text-[12px] px-2.5 py-1 outline-none"
        />
        {(query || kindFilter || fileFilter) && (
          <button
            type="button"
            onClick={clearAll}
            className="text-text-4 hover:text-text-2 p-0.5"
          >
            <Icon name="x" size={13} />
          </button>
        )}
      </div>

      {/* Two-pane */}
      <div className="flex-1 flex gap-3 min-h-0">
        {/* Results list */}
        <div className="w-[320px] shrink-0 glass rounded-[10px] flex flex-col overflow-hidden">
          <div className="px-3.5 py-2.5 border-b border-border flex items-center justify-between">
            <span className="text-[11px] text-text-4">
              {hasQuery && data
                ? `${data.count} result${data.count !== 1 ? "s" : ""}`
                : hasQuery
                  ? "Searching…"
                  : "Enter a query"}
            </span>
            {hasQuery && (dq || kindFilter || dFile) && (
              <Badge tone="default">{dq || kindFilter || dFile}</Badge>
            )}
          </div>

          <div className="flex-1 overflow-y-auto">
            {!hasQuery && (
              <EmptyState
                icon={<Icon name="search" size={20} />}
                title="Start typing to search"
                hint='Try "GraphDB", "function", or a file path'
              />
            )}

            {hasQuery && !data && isFetching && (
              <div className="p-4 space-y-2">
                <Skeleton /> <Skeleton /> <Skeleton /> <Skeleton />
              </div>
            )}

            {data && data.hits.length === 0 && (
              <EmptyState
                icon={<Icon name="search" size={20} />}
                title="No matches"
                hint="Try relaxing the kind filter or broadening your query"
              />
            )}

            {data?.hits.map((h) => {
              const active = selected?.id === h.id;
              return (
                <button
                  key={h.id}
                  type="button"
                  onClick={() => setSelected(h)}
                  className={
                    "w-full text-left px-3.5 py-2.5 border-b border-border transition-colors border-l-2 " +
                    (active
                      ? "border-l-cyan bg-cyan/[0.05]"
                      : "border-l-transparent hover:bg-white/[0.02]")
                  }
                >
                  <div className="flex items-center gap-1.5 mb-1">
                    <KindDot kind={h.kind} size={7} />
                    <span
                      className={`font-mono text-[12px] font-semibold flex-1 truncate ${
                        active ? "text-cyan" : "text-text-1"
                      }`}
                    >
                      {h.name}
                    </span>
                    <KindBadge kind={h.kind} />
                  </div>
                  <div className="font-mono text-[10px] text-text-3 truncate">
                    {h.file}
                  </div>
                </button>
              );
            })}
          </div>

          {/* Pagination */}
          {data && data.count > PAGE && (
            <div className="px-3.5 py-2 border-t border-border flex gap-2 items-center">
              <button
                type="button"
                className="btn-ghost !text-[11px] !px-2.5 !py-1"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE))}
              >
                ← Prev
              </button>
              <span className="flex-1 text-center text-[10px] text-text-4 font-mono">
                {offset + 1}–{Math.min(offset + PAGE, data.count)} / {data.count}
              </span>
              <button
                type="button"
                className="btn-ghost !text-[11px] !px-2.5 !py-1"
                disabled={!data.has_more}
                onClick={() => setOffset(data.next_offset ?? offset + PAGE)}
              >
                Next →
              </button>
            </div>
          )}
        </div>

        {/* Detail pane */}
        <DetailPane hit={selected} />
      </div>
    </div>
  );
}
