import { useEffect, useState } from "react";
import { api, ReindexResponse } from "../api";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  Input,
} from "../components/ui";

const LS_API_BASE = "codeatlas.apiBase";
const LS_API_KEY = "codeatlas.apiKey";

export default function SettingsPage() {
  const [apiBase, setApiBase] = useState(
    () => localStorage.getItem(LS_API_BASE) ?? "/api/v1",
  );
  const [apiKey, setApiKey] = useState(
    () => localStorage.getItem(LS_API_KEY) ?? "",
  );
  const [reindexing, setReindexing] = useState(false);
  const [lastResult, setLastResult] = useState<ReindexResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    localStorage.setItem(LS_API_BASE, apiBase);
  }, [apiBase]);
  useEffect(() => {
    if (apiKey) localStorage.setItem(LS_API_KEY, apiKey);
    else localStorage.removeItem(LS_API_KEY);
  }, [apiKey]);

  const triggerReindex = async (incremental: boolean) => {
    setReindexing(true);
    setError(null);
    try {
      const res = await api.reindex({ incremental });
      setLastResult(res);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setReindexing(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Connection"
          subtitle="Saved in your browser only — these settings never leave this machine."
        />
        <CardBody className="space-y-3">
          <label className="block text-xs text-slate-400">
            API base URL
            <Input
              className="mt-1"
              value={apiBase}
              onChange={(e) => setApiBase(e.target.value)}
              placeholder="/api/v1 or http://localhost:8080/api/v1"
            />
          </label>
          <label className="block text-xs text-slate-400">
            X-API-Key (if required)
            <Input
              className="mt-1"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="Leave blank for open servers"
            />
          </label>
          <p className="text-xs text-slate-500">
            Changes take effect on next page reload.
          </p>
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Reindex"
          subtitle="Trigger an incremental or full re-parse of the working repo."
        />
        <CardBody className="space-y-3">
          <div className="flex gap-2">
            <Button
              onClick={() => triggerReindex(true)}
              disabled={reindexing}
            >
              {reindexing ? "Running…" : "Incremental reindex"}
            </Button>
            <Button
              variant="ghost"
              onClick={() => triggerReindex(false)}
              disabled={reindexing}
            >
              Full reindex
            </Button>
          </div>
          {error ? (
            <div className="text-sm text-rose-400">{error}</div>
          ) : null}
          {lastResult ? (
            <div className="text-sm text-slate-300 flex flex-wrap gap-2 items-center">
              <Badge tone="success">{lastResult.mode}</Badge>
              <span>parsed {lastResult.parsed}</span>
              <span>skipped {lastResult.skipped}</span>
              <span>errors {lastResult.errors}</span>
              <span className="ml-auto text-xs text-slate-500">
                {lastResult.duration_ms} ms
              </span>
            </div>
          ) : null}
        </CardBody>
      </Card>
    </div>
  );
}
