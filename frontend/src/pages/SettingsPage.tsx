import { useEffect, useState } from "react";
import { api, ReindexResponse } from "../api";
import {
  Badge,
  Card,
  CardBody,
  CardHeader,
} from "../components/ui";
import { Icon } from "../components/Icon";

const LS_API_BASE = "codeatlas.apiBase";
const LS_API_KEY = "codeatlas.apiKey";

function SettingRow({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-4 py-3 border-b border-border last:border-b-0">
      <div className="w-44 shrink-0">
        <div className="text-[12px] text-text-2 font-medium">{label}</div>
        {hint && <div className="text-[11px] text-text-4 mt-0.5">{hint}</div>}
      </div>
      <div className="flex-1 min-w-0">{children}</div>
    </div>
  );
}

export default function SettingsPage() {
  const [apiBase, setApiBase] = useState(
    () => localStorage.getItem(LS_API_BASE) ?? "/api/v1",
  );
  const [apiKey, setApiKey] = useState(
    () => localStorage.getItem(LS_API_KEY) ?? "",
  );
  const [showKey, setShowKey] = useState(false);
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
    <div className="flex flex-col gap-4 max-w-3xl">
      <Card>
        <CardHeader
          title="Connection"
          subtitle="Saved in your browser only — these settings never leave this machine."
        />
        <CardBody className="!py-1">
          <SettingRow
            label="API base URL"
            hint="Where the backend lives"
          >
            <input
              value={apiBase}
              onChange={(e) => setApiBase(e.target.value)}
              placeholder="/api/v1"
              className="w-full bg-surface border border-border rounded-md px-3 py-1.5 font-mono text-[12px] text-text-1 outline-none focus:border-cyan/50"
            />
          </SettingRow>
          <SettingRow
            label="X-API-Key"
            hint="Required on protected servers"
          >
            <div className="flex items-center gap-2">
              <input
                type={showKey ? "text" : "password"}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="Leave blank for open servers"
                className="flex-1 bg-surface border border-border rounded-md px-3 py-1.5 font-mono text-[12px] text-text-1 outline-none focus:border-cyan/50"
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="btn-ghost !text-[11px] !px-2 !py-1.5"
              >
                {showKey ? "Hide" : "Show"}
              </button>
            </div>
          </SettingRow>
          <div className="pt-3 flex items-center gap-2 text-[11px] text-text-4">
            <Icon name="info" size={11} /> Changes take effect on next page reload.
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Reindex"
          subtitle="Trigger an incremental or full re-parse of the working repo"
        />
        <CardBody className="space-y-3">
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => triggerReindex(true)}
              disabled={reindexing}
              className="btn-primary !text-[12px] flex items-center gap-1.5"
            >
              <Icon name="refresh" size={12} />
              {reindexing ? "Running…" : "Incremental reindex"}
            </button>
            <button
              type="button"
              onClick={() => triggerReindex(false)}
              disabled={reindexing}
              className="btn-ghost !text-[12px] flex items-center gap-1.5"
            >
              <Icon name="refresh" size={12} />
              Full reindex
            </button>
          </div>

          {error ? (
            <div className="text-[12px] text-bad bg-bad/10 border border-bad/30 rounded-md px-3 py-2">
              {error}
            </div>
          ) : null}

          {lastResult ? (
            <div className="bg-surface border border-border rounded-md px-3.5 py-2.5">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge tone="success">{lastResult.mode}</Badge>
                <Stat label="parsed" value={lastResult.parsed} color="#22c55e" />
                <Stat label="skipped" value={lastResult.skipped} />
                <Stat
                  label="errors"
                  value={lastResult.errors}
                  color={lastResult.errors > 0 ? "#ef4444" : undefined}
                />
                <span className="ml-auto font-mono text-[11px] text-text-4">
                  {lastResult.duration_ms} ms
                </span>
              </div>
            </div>
          ) : null}
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="About"
          subtitle="CodeAtlas — tree-sitter code knowledge graph"
        />
        <CardBody className="!py-1">
          <SettingRow label="Version">
            <span className="font-mono text-[12px] text-text-1">1.0.0</span>
          </SettingRow>
          <SettingRow label="Docs">
            <a
              href="https://github.com/AryanSaini26/CodeAtlas"
              target="_blank"
              rel="noreferrer"
              className="text-cyan text-[12px] inline-flex items-center gap-1 no-underline hover:no-underline"
            >
              <Icon name="externalLink" size={11} /> github.com/AryanSaini26/CodeAtlas
            </a>
          </SettingRow>
        </CardBody>
      </Card>
    </div>
  );
}

function Stat({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color?: string;
}) {
  return (
    <span className="text-[11px] text-text-3 font-mono">
      <span className="text-text-4">{label} </span>
      <span style={color ? { color } : undefined} className={color ? "" : "text-text-1"}>
        {value}
      </span>
    </span>
  );
}
