const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api/v1";
const HOSTED_API_BASE =
  (import.meta.env.VITE_HOSTED_API_BASE as string | undefined) ??
  "/api/hosted/v1";
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

async function hostedReq<T>(
  path: string,
  params?: Record<string, unknown>,
  init?: RequestInit,
): Promise<T> {
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
  const token =
    typeof window !== "undefined"
      ? window.localStorage.getItem("codeatlas.hostedToken")
      : null;
  const headers: Record<string, string> = {
    ...(init?.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (init?.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const resp = await fetch(HOSTED_API_BASE + path + qs, { ...init, headers });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`Hosted API ${resp.status}: ${body}`);
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

export type ImpactGroup = { depth: number; count: number; symbols: SymbolRef[] };
export type ImpactResponse = {
  symbol_id: string;
  max_depth: number;
  total_affected: number;
  by_depth: ImpactGroup[];
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

export type CommunitySummary = {
  community_id: string;
  size: number;
  sample_symbols: string[];
};

export type DiffSymbolEntry = {
  name: string;
  kind: string;
  file: string;
  old_line?: number | null;
  new_line?: number | null;
};

export type DiffResponse = {
  since: string;
  until: string;
  added: DiffSymbolEntry[];
  removed: DiffSymbolEntry[];
  modified: DiffSymbolEntry[];
};

export type ReindexResponse = {
  mode: string;
  parsed: number;
  skipped: number;
  errors: number;
  duration_ms: number;
};

export type HostedTeam = {
  id: string;
  slug: string;
  name: string;
  created_at: number;
};

export type HostedRepo = {
  id: string;
  team_id: string;
  name: string;
  local_path: string;
  graph_db_path: string;
  provider: string;
  provider_repo?: string | null;
  provider_repo_id?: string | null;
  provider_installation_id?: string | null;
  default_branch?: string | null;
  clone_url?: string | null;
  last_commit_sha?: string | null;
  last_indexed_at?: number | null;
  last_sync_status: string;
  last_error?: string | null;
  created_at: number;
  updated_at: number;
};

export type HostedSyncEvent = {
  id: string;
  repo_id: string;
  status: string;
  message: string;
  parsed: number;
  skipped: number;
  errors: number;
  duration_ms: number;
  commit_sha?: string | null;
  delivery_id?: string | null;
  created_at: number;
};

export type HostedGitHubApp = {
  brand: string;
  engine: string;
  configured: boolean;
  oauth_configured: boolean;
  webhook_configured: boolean;
  app_id?: string | null;
  client_id?: string | null;
  public_url?: string | null;
  setup_url?: string | null;
  repo_listing_source?: string | null;
};

export type HostedGitHubInstallation = {
  id: string;
  installation_id: string;
  team_id: string;
  account_login: string;
  account_type: string;
  account_id?: string | null;
  app_slug?: string | null;
  permissions: Record<string, unknown>;
  created_at: number;
  updated_at: number;
};

export type HostedGitHubRepository = {
  id: string;
  installation_id: string;
  provider_repo_id: string;
  full_name: string;
  name: string;
  owner: string;
  private: boolean;
  default_branch?: string | null;
  clone_url?: string | null;
  local_path?: string | null;
  activated_repo_id?: string | null;
  last_webhook_delivery_id?: string | null;
  last_webhook_event?: string | null;
  created_at: number;
  updated_at: number;
};

export type HostedBootstrapResponse = {
  user: { id: string; email: string; name: string; created_at: number };
  team: HostedTeam;
  token: string;
  token_record: {
    id: string;
    subject_type: string;
    subject_id: string;
    name: string;
    prefix: string;
    scopes: string[];
    created_at: number;
  };
};

export type HostedContextResponse = {
  query: string;
  mode: string;
  mode_effective: string;
  estimated_tokens: number;
  result_count: number;
  results: Array<{
    score: number;
    symbol: {
      id: string;
      name: string;
      qualified_name: string;
      kind: string;
      file: string;
      line: number;
    };
  }>;
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
  impact: (id: string, maxDepth = 5) =>
    req<ImpactResponse>(`/symbols/${encodeURIComponent(id)}/impact`, { max_depth: maxDepth }),
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
  communities: () =>
    req<{ count: number; communities: CommunitySummary[] }>("/communities"),
  diff: (params: { since: string; until?: string; repo_path?: string }) =>
    req<DiffResponse>("/diff", params),
  reindex: async (params?: { repo_path?: string; incremental?: boolean }) => {
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
    const resp = await fetch(API_BASE + "/reindex" + qs, {
      method: "POST",
      headers,
    });
    if (!resp.ok) throw new Error(`API ${resp.status}: ${await resp.text()}`);
    return (await resp.json()) as ReindexResponse;
  },
  streamUrl: () => API_BASE + "/stream",
};

export type HostedEvalRow = {
  mode: string;
  mode_effective?: string;
  recall_at_k: number;
  mrr: number;
  ndcg_at_k: number;
  avg_context_savings: number;
  [key: string]: unknown;
};

export type HostedEvalSummary = {
  kind: string;
  task_count: number;
  comparison: HostedEvalRow[];
  generated_at: number;
  note?: string;
} | null;

export type HostedLineageGraph = {
  repo: string;
  node_count: number;
  edge_count: number;
  nodes: { id: string; kind: string }[];
  edges: { source: string; target: string; kind: string }[];
};

export type HostedSavings = {
  query: string;
  with_context_tokens: number;
  without_context_tokens: number;
  savings_pct: number;
  files: string[];
  file_count: number;
  result_count: number;
};

export type HostedContextQuery = {
  id: string;
  query: string;
  mode: string;
  source: string;
  tokens: number;
  result_count: number;
  latency_ms: number;
  security_status: string;
  created_at: number;
};

export const hostedOAuthLoginUrl = () => HOSTED_API_BASE + "/github/oauth/login";

export const hostedApi = {
  bootstrap: () =>
    hostedReq<HostedBootstrapResponse>("/dev/bootstrap", undefined, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  teams: () => hostedReq<{ teams: HostedTeam[] }>("/teams"),
  repos: () => hostedReq<{ repos: HostedRepo[] }>("/repos"),
  createRepo: (payload: {
    team_slug: string;
    name: string;
    local_path: string;
    provider?: string;
    provider_repo?: string;
    provider_repo_id?: string;
    provider_installation_id?: string;
    default_branch?: string;
    clone_url?: string;
  }) =>
    hostedReq<{ repo: HostedRepo }>("/repos", undefined, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  syncRepo: (repoId: string) =>
    hostedReq<{ repo: HostedRepo; event: HostedSyncEvent }>(
      `/repos/${encodeURIComponent(repoId)}/sync`,
      undefined,
      { method: "POST" },
    ),
  repoStats: (repoId: string) =>
    hostedReq<{ repo: HostedRepo; stats: StatsResponse }>(
      `/repos/${encodeURIComponent(repoId)}/stats`,
    ),
  syncEvents: (repoId: string) =>
    hostedReq<{ events: HostedSyncEvent[] }>(
      `/repos/${encodeURIComponent(repoId)}/sync-events`,
    ),
  latestEval: (repoId: string) =>
    hostedReq<{ eval: HostedEvalSummary }>(`/repos/${encodeURIComponent(repoId)}/eval`),
  lineage: (repoId: string) =>
    hostedReq<{ lineage: HostedLineageGraph }>(`/repos/${encodeURIComponent(repoId)}/lineage`),
  contextQueries: (repoId: string) =>
    hostedReq<{ queries: HostedContextQuery[] }>(
      `/repos/${encodeURIComponent(repoId)}/context-queries`,
    ),
  contextSavings: (repoId: string, q: string) =>
    hostedReq<{ savings: HostedSavings }>(
      `/repos/${encodeURIComponent(repoId)}/context-savings`,
      { q },
    ),
  runEval: (repoId: string) =>
    hostedReq<{ eval: HostedEvalSummary }>(
      `/repos/${encodeURIComponent(repoId)}/eval`,
      undefined,
      { method: "POST", body: JSON.stringify({}) },
    ),
  context: (repoId: string, params: { q: string; budget?: number; mode?: string }) =>
    hostedReq<HostedContextResponse>(
      `/repos/${encodeURIComponent(repoId)}/context`,
      params,
    ),
  connection: (repoId: string) =>
    hostedReq<{
      status: string;
      context_endpoint: string;
      auth_header: string;
      mcp_note: string;
      local_mcp_config: object;
    }>(`/repos/${encodeURIComponent(repoId)}/connection`),
  createRepoToken: (repoId: string) =>
    hostedReq<{
      token: string;
      token_record: { prefix: string; scopes: string[]; name: string };
    }>(`/repos/${encodeURIComponent(repoId)}/tokens`, undefined, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  githubApp: () => hostedReq<HostedGitHubApp>("/github/app"),
  demoInfo: () =>
    hostedReq<{ enabled: boolean; token?: string; repo_id?: string }>("/demo-info"),
  githubInstallations: () =>
    hostedReq<{ installations: HostedGitHubInstallation[] }>(
      "/github/installations",
    ),
  githubRepos: (installationId: string, params?: { refresh?: boolean }) =>
    hostedReq<{ source: string; repositories: HostedGitHubRepository[] }>(
      `/github/installations/${encodeURIComponent(installationId)}/repos`,
      params,
    ),
  activateGithubRepo: (
    providerRepoId: string,
    payload: { local_path?: string; hosted_name?: string },
  ) =>
    hostedReq<{ repo: HostedRepo }>(
      `/github/repos/${encodeURIComponent(providerRepoId)}/activate`,
      undefined,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  syncGithubRepo: (providerRepoId: string) =>
    hostedReq<{ repo: HostedRepo; event: HostedSyncEvent }>(
      `/github/repos/${encodeURIComponent(providerRepoId)}/sync`,
      undefined,
      { method: "POST" },
    ),
};
