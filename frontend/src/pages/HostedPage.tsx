import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  hostedApi,
  type HostedGitHubInstallation,
  type HostedGitHubRepository,
  type HostedRepo,
} from "../api";
import { Badge, Button, Card, CardBody, CardHeader, EmptyState, Input } from "../components/ui";
import { Icon } from "../components/Icon";

function fmtTime(ms?: number | null) {
  if (!ms) return "never";
  return new Date(ms).toLocaleString();
}

function statusTone(status: string): "default" | "success" | "warn" | "danger" | "cyan" {
  if (status === "success") return "success";
  if (status === "error") return "danger";
  if (status === "never") return "warn";
  return "cyan";
}

export default function HostedPage() {
  const qc = useQueryClient();
  const [tokenInput, setTokenInput] = useState(
    () => localStorage.getItem("codeatlas.hostedToken") ?? "",
  );
  const [repoName, setRepoName] = useState("codeatlas");
  const [repoPath, setRepoPath] = useState(".");
  const [selectedRepoId, setSelectedRepoId] = useState<string | null>(null);
  const [contextQuery, setContextQuery] = useState("auth flow");
  const [contextResult, setContextResult] = useState<string>("");
  const [connectionText, setConnectionText] = useState("");
  const [selectedInstallationId, setSelectedInstallationId] = useState<string | null>(null);
  const [githubLocalPath, setGithubLocalPath] = useState(".");

  const githubApp = useQuery({
    queryKey: ["hosted", "github", "app"],
    queryFn: () => hostedApi.githubApp(),
    retry: false,
  });

  const repos = useQuery({
    queryKey: ["hosted", "repos", tokenInput],
    queryFn: () => hostedApi.repos(),
    retry: false,
    enabled: !!tokenInput,
  });
  const teams = useQuery({
    queryKey: ["hosted", "teams", tokenInput],
    queryFn: () => hostedApi.teams(),
    retry: false,
    enabled: !!tokenInput,
  });
  const installations = useQuery({
    queryKey: ["hosted", "github", "installations", tokenInput],
    queryFn: () => hostedApi.githubInstallations(),
    retry: false,
    enabled: !!tokenInput,
  });

  const selectedInstallation = useMemo(() => {
    const list = installations.data?.installations ?? [];
    return (
      list.find((installation) => installation.id === selectedInstallationId) ?? list[0] ?? null
    );
  }, [installations.data?.installations, selectedInstallationId]);

  const githubRepos = useQuery({
    queryKey: ["hosted", "github", "repos", selectedInstallation?.id],
    queryFn: () => hostedApi.githubRepos(selectedInstallation!.id),
    retry: false,
    enabled: !!selectedInstallation,
  });

  const selectedRepo = useMemo(() => {
    const list = repos.data?.repos ?? [];
    return list.find((repo) => repo.id === selectedRepoId) ?? list[0] ?? null;
  }, [repos.data?.repos, selectedRepoId]);

  const events = useQuery({
    queryKey: ["hosted", "events", selectedRepo?.id],
    queryFn: () => hostedApi.syncEvents(selectedRepo!.id),
    enabled: !!selectedRepo,
    retry: false,
  });

  const stats = useQuery({
    queryKey: ["hosted", "stats", selectedRepo?.id],
    queryFn: () => hostedApi.repoStats(selectedRepo!.id),
    enabled: !!selectedRepo,
    retry: false,
  });

  const bootstrap = useMutation({
    mutationFn: () => hostedApi.bootstrap(),
    onSuccess: (data) => {
      localStorage.setItem("codeatlas.hostedToken", data.token);
      setTokenInput(data.token);
      void qc.invalidateQueries({ queryKey: ["hosted"] });
    },
  });

  const registerRepo = useMutation({
    mutationFn: () =>
      hostedApi.createRepo({
        team_slug: teams.data?.teams[0]?.slug ?? "default",
        name: repoName,
        local_path: repoPath,
      }),
    onSuccess: (data) => {
      setSelectedRepoId(data.repo.id);
      void qc.invalidateQueries({ queryKey: ["hosted"] });
    },
  });

  const syncRepo = useMutation({
    mutationFn: (repo: HostedRepo) => hostedApi.syncRepo(repo.id),
    onSuccess: (data) => {
      setSelectedRepoId(data.repo.id);
      void qc.invalidateQueries({ queryKey: ["hosted"] });
    },
  });
  const activateGithubRepo = useMutation({
    mutationFn: (repo: HostedGitHubRepository) =>
      hostedApi.activateGithubRepo(repo.provider_repo_id, {
        local_path: githubLocalPath,
        hosted_name: repo.full_name,
      }),
    onSuccess: (data) => {
      setSelectedRepoId(data.repo.id);
      void qc.invalidateQueries({ queryKey: ["hosted"] });
    },
  });

  const previewContext = useMutation({
    mutationFn: (repo: HostedRepo) =>
      hostedApi.context(repo.id, { q: contextQuery, budget: 1200, mode: "pagerank" }),
    onSuccess: (data) => {
      setContextResult(
        JSON.stringify(
          {
            query: data.query,
            mode_effective: data.mode_effective,
            estimated_tokens: data.estimated_tokens,
            results: data.results.slice(0, 5).map((entry) => ({
              symbol: entry.symbol.qualified_name,
              file: entry.symbol.file,
              line: entry.symbol.line,
              score: Number(entry.score.toFixed(3)),
            })),
          },
          null,
          2,
        ),
      );
    },
  });

  const loadConnection = useMutation({
    mutationFn: (repo: HostedRepo) => hostedApi.connection(repo.id),
    onSuccess: (data) => {
      setConnectionText(JSON.stringify(data, null, 2));
    },
  });

  const persistToken = () => {
    localStorage.setItem("codeatlas.hostedToken", tokenInput);
    void qc.invalidateQueries({ queryKey: ["hosted"] });
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-head text-[18px] font-bold text-text-1">Stratum Gateway</h1>
          <div className="mt-1 text-[12px] text-text-3">
            Hosted team context · powered by the CodeAtlas engine
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Input
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            placeholder="Bearer token"
            className="w-[320px] font-mono text-[11px]"
          />
          <Button variant="ghost" onClick={persistToken}>
            <Icon name="check" size={13} /> Use token
          </Button>
          <Button onClick={() => bootstrap.mutate()} disabled={bootstrap.isPending}>
            <Icon name="mcp" size={13} /> Bootstrap
          </Button>
        </div>
      </div>

      {repos.isError && tokenInput ? (
        <Card>
          <CardBody>
            <div className="text-bad text-[13px]">
              Hosted API unavailable or token rejected.
            </div>
          </CardBody>
        </Card>
      ) : null}

      <div className="grid grid-cols-1 xl:grid-cols-[360px_minmax(0,1fr)] gap-4">
        <div className="flex flex-col gap-4 min-w-0">
          <Card>
            <CardHeader
              title="GitHub App"
              subtitle={
                githubApp.data?.configured
                  ? "App credentials detected"
                  : "Dev metadata mode; credentials not set"
              }
            />
            <CardBody className="flex flex-col gap-3">
              <div className="grid grid-cols-3 gap-2">
                <StatusPill label="App" on={!!githubApp.data?.configured} />
                <StatusPill label="OAuth" on={!!githubApp.data?.oauth_configured} />
                <StatusPill label="Webhook" on={!!githubApp.data?.webhook_configured} />
              </div>
              <div className="font-mono text-[10px] text-text-4">
                {githubApp.data?.public_url ?? "STRATUM_PUBLIC_URL not set"}
              </div>
              <div className="flex flex-col gap-2">
                {(installations.data?.installations ?? []).map((installation) => (
                  <InstallationButton
                    key={installation.id}
                    installation={installation}
                    active={selectedInstallation?.id === installation.id}
                    onClick={() => setSelectedInstallationId(installation.id)}
                  />
                ))}
                {tokenInput && installations.data?.installations.length === 0 ? (
                  <EmptyState title="No installations" hint="Use webhook-test or API setup." />
                ) : null}
              </div>
              {selectedInstallation ? (
                <div className="flex flex-col gap-2">
                  <Input
                    value={githubLocalPath}
                    onChange={(e) => setGithubLocalPath(e.target.value)}
                    placeholder="Local checkout path for activation"
                  />
                  <div className="max-h-[220px] overflow-auto rounded-md border border-border">
                    {(githubRepos.data?.repositories ?? []).map((repo) => (
                      <button
                        type="button"
                        key={repo.id}
                        onClick={() => activateGithubRepo.mutate(repo)}
                        className="flex w-full items-center justify-between gap-2 border-b border-border px-3 py-2 text-left last:border-b-0 hover:bg-white/[0.04]"
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-[12px] text-text-1">
                            {repo.full_name}
                          </span>
                          <span className="block truncate font-mono text-[10px] text-text-4">
                            {repo.last_webhook_event ?? "no webhook"} ·{" "}
                            {repo.activated_repo_id ? "active" : "inactive"}
                          </span>
                        </span>
                        <Badge tone={repo.activated_repo_id ? "success" : "warn"}>
                          {repo.activated_repo_id ? "active" : "activate"}
                        </Badge>
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Repos" subtitle={teams.data?.teams[0]?.name ?? "No team loaded"} />
            <CardBody className="flex flex-col gap-3">
              <div className="grid grid-cols-1 gap-2">
                <Input value={repoName} onChange={(e) => setRepoName(e.target.value)} />
                <Input value={repoPath} onChange={(e) => setRepoPath(e.target.value)} />
                <Button
                  onClick={() => registerRepo.mutate()}
                  disabled={!tokenInput || registerRepo.isPending}
                >
                  <Icon name="check" size={13} /> Register repo
                </Button>
              </div>
              <div className="flex flex-col gap-2">
                {(repos.data?.repos ?? []).map((repo) => (
                  <button
                    type="button"
                    key={repo.id}
                    onClick={() => setSelectedRepoId(repo.id)}
                    className={`text-left rounded-md border px-3 py-2 transition-colors ${
                      selectedRepo?.id === repo.id
                        ? "border-cyan/50 bg-cyan/10"
                        : "border-border bg-white/[0.02] hover:bg-white/[0.04]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-text-1">{repo.name}</span>
                      <Badge tone={statusTone(repo.last_sync_status)}>
                        {repo.last_sync_status}
                      </Badge>
                    </div>
                    <div className="mt-1 truncate font-mono text-[10px] text-text-4">
                      {repo.provider === "github" ? repo.provider_repo : repo.local_path}
                    </div>
                  </button>
                ))}
                {tokenInput && repos.data?.repos.length === 0 ? (
                  <EmptyState title="No repos registered" hint="Register or activate a repo." />
                ) : null}
              </div>
            </CardBody>
          </Card>
        </div>

        <div className="flex flex-col gap-4 min-w-0">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Metric label="Files" value={stats.data?.stats.files ?? 0} />
            <Metric label="Symbols" value={stats.data?.stats.symbols ?? 0} />
            <Metric label="Relationships" value={stats.data?.stats.relationships ?? 0} />
          </div>

          <Card>
            <CardHeader
              title={selectedRepo?.name ?? "Repo"}
              subtitle={selectedRepo ? selectedRepo.graph_db_path : "Select a repo"}
              action={
                selectedRepo ? (
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => loadConnection.mutate(selectedRepo)}
                    >
                      <Icon name="copy" size={12} /> Connection
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => syncRepo.mutate(selectedRepo)}
                      disabled={syncRepo.isPending}
                    >
                      <Icon name="refresh" size={12} /> Sync
                    </Button>
                  </div>
                ) : null
              }
            />
            <CardBody>
              {selectedRepo ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-[12px]">
                  <Field label="Last indexed" value={fmtTime(selectedRepo.last_indexed_at)} />
                  <Field label="Last commit" value={selectedRepo.last_commit_sha ?? "unknown"} />
                  <Field label="Provider" value={selectedRepo.provider} />
                  <Field label="Provider repo" value={selectedRepo.provider_repo ?? "local"} />
                  <Field label="Status" value={selectedRepo.last_sync_status} />
                  {selectedRepo.last_error ? (
                    <div className="md:col-span-2 text-bad">{selectedRepo.last_error}</div>
                  ) : null}
                </div>
              ) : (
                <EmptyState title="No repo selected" hint="Bootstrap and register a repo." />
              )}
            </CardBody>
          </Card>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <Card>
              <CardHeader title="Context Preview" subtitle="Hosted repo context API" />
              <CardBody className="flex flex-col gap-3">
                <div className="flex gap-2">
                  <Input
                    value={contextQuery}
                    onChange={(e) => setContextQuery(e.target.value)}
                  />
                  <Button
                    onClick={() => selectedRepo && previewContext.mutate(selectedRepo)}
                    disabled={!selectedRepo || previewContext.isPending}
                  >
                    Run
                  </Button>
                </div>
                <pre className="min-h-[180px] overflow-auto rounded-md border border-border bg-black/20 p-3 text-[11px] text-text-2">
                  {contextResult || "No preview yet."}
                </pre>
              </CardBody>
            </Card>

            <Card>
              <CardHeader title="Recent Sync Events" subtitle="Latest hosted indexing runs" />
              <CardBody>
                <div className="flex flex-col gap-2">
                  {(events.data?.events ?? []).map((event) => (
                    <div
                      key={event.id}
                      className="rounded-md border border-border bg-white/[0.02] px-3 py-2"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <Badge tone={statusTone(event.status)}>{event.status}</Badge>
                        <span className="font-mono text-[10px] text-text-4">
                          {fmtTime(event.created_at)}
                        </span>
                      </div>
                      <div className="mt-1 text-[12px] text-text-2">{event.message}</div>
                      <div className="mt-1 font-mono text-[10px] text-text-4">
                        parsed {event.parsed} · skipped {event.skipped} · errors {event.errors} ·{" "}
                        {event.duration_ms}ms
                      </div>
                    </div>
                  ))}
                  {selectedRepo && events.data?.events.length === 0 ? (
                    <EmptyState title="No sync events" hint="Run sync for this repo." />
                  ) : null}
                </div>
              </CardBody>
            </Card>
          </div>

          {connectionText ? (
            <Card>
              <CardHeader title="Connection" subtitle="Hosted context and local MCP details" />
              <CardBody>
                <pre className="max-h-[260px] overflow-auto rounded-md border border-border bg-black/20 p-3 text-[11px] text-text-2">
                  {connectionText}
                </pre>
              </CardBody>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function StatusPill({ label, on }: { label: string; on: boolean }) {
  return (
    <div className="rounded-md border border-border bg-white/[0.02] px-2 py-2">
      <div className="text-[10px] uppercase tracking-[0.06em] text-text-4">{label}</div>
      <Badge tone={on ? "success" : "warn"}>{on ? "ready" : "stub"}</Badge>
    </div>
  );
}

function InstallationButton({
  installation,
  active,
  onClick,
}: {
  installation: HostedGitHubInstallation;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`text-left rounded-md border px-3 py-2 transition-colors ${
        active ? "border-cyan/50 bg-cyan/10" : "border-border bg-white/[0.02] hover:bg-white/[0.04]"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-text-1">{installation.account_login}</span>
        <Badge tone="cyan">{installation.account_type}</Badge>
      </div>
      <div className="mt-1 truncate font-mono text-[10px] text-text-4">
        installation {installation.installation_id}
      </div>
    </button>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <CardBody>
        <div className="text-[11px] uppercase tracking-[0.06em] text-text-3">{label}</div>
        <div className="mt-2 font-head text-[30px] font-bold leading-none text-text-1">
          {value.toLocaleString()}
        </div>
      </CardBody>
    </Card>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.06em] text-text-4">{label}</div>
      <div className="mt-1 break-all font-mono text-[11px] text-text-2">{value}</div>
    </div>
  );
}
