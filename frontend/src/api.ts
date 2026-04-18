const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api/v1";
const API_KEY = import.meta.env.VITE_API_KEY as string | undefined;

async function req<T>(path: string, params?: Record<string, unknown>): Promise<T> {
  const qs = params
    ? "?" +
      Object.entries(params)
        .filter(([, v]) => v !== undefined && v !== null && v !== "")
        .map(
          ([k, v]) =>
            encodeURIComponent(k) + "=" + encodeURIComponent(String(v))
        )
        .join("&")
    : "";
  const headers: Record<string, string> = {};
  if (API_KEY) headers["X-API-Key"] = API_KEY;
  const resp = await fetch(API_BASE + path + qs, { headers });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`API ${resp.status}: ${body}`);
  }
  return (await resp.json()) as T;
}

export type GraphNode = {
  id: string;
  name: string;
  qualified_name: string;
  kind: string;
  file: string;
  community_id?: string | null;
};

export type GraphLink = {
  source: string;
  target: string;
  kind: string;
  confidence: string;
};

export type GraphResponse = {
  nodes: GraphNode[];
  links: GraphLink[];
  truncated: boolean;
};

export type StatsResponse = {
  files: number;
  symbols: number;
  relationships: number;
  languages: Record<string, number>;
  kinds: Record<string, number>;
};

export type SymbolRef = {
  id: string;
  name: string;
  qualified_name: string;
  kind: string;
  file: string;
  line?: number | null;
};

export type SymbolDetails = {
  id: string;
  name: string;
  qualified_name: string;
  kind: string;
  file: string;
  start_line: number;
  end_line: number;
  signature?: string | null;
  docstring?: string | null;
  incoming: SymbolRef[];
  outgoing: SymbolRef[];
};

export type SearchHit = {
  id: string;
  name: string;
  qualified_name: string;
  kind: string;
  file: string;
  score?: number | null;
};

export type SearchResponse = {
  query: string;
  count: number;
  offset: number;
  has_more: boolean;
  next_offset: number | null;
  hits: SearchHit[];
};

export type PageRankEntry = {
  id: string;
  name: string;
  qualified_name: string;
  kind: string;
  file: string;
  score: number;
};

export type HotspotEntry = {
  file: string;
  churn: number;
  in_degree: number;
  score: number;
};

export type CoverageGapEntry = {
  id: string;
  name: string;
  qualified_name: string;
  kind: string;
  file: string;
  line: number;
};

export const api = {
  stats: () => req<StatsResponse>("/stats"),
  graph: (params?: {
    file_filter?: string;
    communities?: boolean;
    limit?: number;
  }) => req<GraphResponse>("/graph", params),
  symbol: (id: string) =>
    req<SymbolDetails>(`/symbols/${encodeURIComponent(id)}`),
  search: (params: {
    q: string;
    kind?: string;
    file?: string;
    limit?: number;
    offset?: number;
  }) => req<SearchResponse>("/search", params),
  pagerank: (params?: { limit?: number; kind?: string }) =>
    req<{ count: number; ranking: PageRankEntry[] }>("/pagerank", params),
  hotspots: (params?: { repo_path?: string; limit?: number }) =>
    req<{ count: number; hotspots: HotspotEntry[] }>("/hotspots", params),
  coverageGaps: (params?: {
    file_filter?: string;
    limit?: number;
    offset?: number;
  }) =>
    req<{
      count: number;
      offset: number;
      has_more: boolean;
      next_offset: number | null;
      gaps: CoverageGapEntry[];
    }>("/coverage-gaps", params),
};
