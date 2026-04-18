import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";

export default function SearchPage() {
  const [q, setQ] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [offset, setOffset] = useState(0);

  const { data, isFetching } = useQuery({
    enabled: submitted.length > 0,
    queryKey: ["search", submitted, offset],
    queryFn: () => api.search({ q: submitted, offset, limit: 25 }),
  });

  return (
    <div className="flex flex-col gap-4">
      <form
        className="card flex gap-3 items-center"
        onSubmit={(e) => {
          e.preventDefault();
          setOffset(0);
          setSubmitted(q);
        }}
      >
        <input
          className="input flex-1"
          placeholder="Search symbols (FTS5 — try names, qualified paths, doc terms)"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          autoFocus
        />
        <button type="submit" className="btn-primary">
          Search
        </button>
      </form>

      {isFetching && <p className="text-slate-500 text-sm">Searching…</p>}

      {data && (
        <div className="card">
          <p className="text-xs text-slate-500 mb-3">
            {data.count} result{data.count === 1 ? "" : "s"} for{" "}
            <span className="text-slate-200">{data.query}</span>
            {data.has_more && " — more available, use Next"}
          </p>
          <ul className="divide-y divide-border/60">
            {data.hits.map((h) => (
              <li key={h.id} className="py-2">
                <Link
                  to={`/symbol/${encodeURIComponent(h.id)}`}
                  className="font-bold"
                >
                  {h.qualified_name}
                </Link>
                <span className="text-xs text-slate-500 ml-2">{h.kind}</span>
                <div className="text-xs text-slate-500">{h.file}</div>
              </li>
            ))}
            {data.hits.length === 0 && (
              <li className="py-2 text-slate-500 text-sm">No matches.</li>
            )}
          </ul>
          <div className="flex justify-between mt-3 text-xs">
            <button
              className="btn"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 25))}
            >
              ← Prev
            </button>
            <span className="text-slate-500 self-center">
              offset {data.offset}
            </span>
            <button
              className="btn"
              disabled={!data.has_more}
              onClick={() => setOffset(data.next_offset ?? offset + 25)}
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
