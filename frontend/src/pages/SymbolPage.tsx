import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, type SymbolRef } from "../api";

export default function SymbolPage() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading, isError, error } = useQuery({
    enabled: !!id,
    queryKey: ["symbol", id],
    queryFn: () => api.symbol(id!),
  });

  if (isLoading) return <p className="text-slate-500 text-sm">Loading…</p>;
  if (isError)
    return (
      <div className="card">
        <p className="text-red-400 text-sm">
          {(error as Error).message || "Not found"}
        </p>
        <Link to="/search" className="btn mt-3 inline-block">
          ← Back to search
        </Link>
      </div>
    );
  if (!data) return null;

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <section className="card md:col-span-2">
        <p className="text-xs text-slate-500 uppercase">{data.kind}</p>
        <h1 className="text-xl font-bold break-all">{data.qualified_name}</h1>
        <p className="text-sm text-slate-400 mt-1">
          {data.file}:{data.start_line}-{data.end_line}
        </p>
        {data.signature && (
          <pre className="mt-4 bg-bg/60 border border-border rounded-md p-3 text-sm overflow-x-auto">
            {data.signature}
          </pre>
        )}
        {data.docstring && (
          <article className="mt-4 text-sm whitespace-pre-wrap text-slate-300">
            {data.docstring}
          </article>
        )}
      </section>
      <aside className="card flex flex-col gap-4">
        <RefList title="Outgoing" refs={data.outgoing} />
        <RefList title="Incoming" refs={data.incoming} />
      </aside>
    </div>
  );
}

function RefList({ title, refs }: { title: string; refs: SymbolRef[] }) {
  return (
    <div>
      <h2 className="text-sm text-slate-400 uppercase tracking-wide mb-2">
        {title} ({refs.length})
      </h2>
      {refs.length === 0 ? (
        <p className="text-slate-500 text-xs">None.</p>
      ) : (
        <ul className="space-y-1 text-sm">
          {refs.slice(0, 50).map((r) => (
            <li key={r.id} className="truncate">
              <Link
                to={`/symbol/${encodeURIComponent(r.id)}`}
                className="font-bold"
              >
                {r.qualified_name}
              </Link>
              <span className="text-xs text-slate-500 ml-2">{r.kind}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
