import { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Icon } from "./Icon";
import { PulseDot } from "./ui";
import { api } from "../api";

type NavItem = { to: string; label: string; icon: string; end?: boolean };

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: "dashboard", end: true },
  { to: "/graph", label: "Graph", icon: "graph" },
  { to: "/search", label: "Search", icon: "search" },
  { to: "/analysis", label: "Analysis", icon: "analysis" },
  { to: "/diff", label: "Diff", icon: "diff" },
  { to: "/settings", label: "Settings", icon: "settings" },
];

function LogoMark() {
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" fill="none" className="shrink-0">
      <rect width="28" height="28" rx="7" fill="rgba(0,240,255,0.08)" />
      <rect x="1" y="1" width="26" height="26" rx="6" stroke="rgba(0,240,255,0.3)" strokeWidth="1" />
      <circle cx="14" cy="14" r="4" fill="none" stroke="#00f0ff" strokeWidth="1.5" />
      <circle cx="7" cy="9" r="1.5" fill="#00f0ff" opacity="0.7" />
      <circle cx="21" cy="9" r="1.5" fill="#bd00ff" opacity="0.7" />
      <circle cx="7" cy="19" r="1.5" fill="#00f0ff" opacity="0.7" />
      <circle cx="21" cy="19" r="1.5" fill="#bd00ff" opacity="0.7" />
      <line x1="8.2" y1="9.8" x2="11" y2="12" stroke="rgba(0,240,255,0.4)" strokeWidth="1" />
      <line x1="19.8" y1="9.8" x2="17" y2="12" stroke="rgba(189,0,255,0.4)" strokeWidth="1" />
      <line x1="8.2" y1="18.2" x2="11" y2="16" stroke="rgba(0,240,255,0.4)" strokeWidth="1" />
      <line x1="19.8" y1="18.2" x2="17" y2="16" stroke="rgba(189,0,255,0.4)" strokeWidth="1" />
    </svg>
  );
}

function Sidebar({
  collapsed,
  setCollapsed,
}: {
  collapsed: boolean;
  setCollapsed: (v: boolean) => void;
}) {
  return (
    <aside
      className="h-full flex flex-col border-r border-border overflow-hidden transition-[width] duration-200 z-10 shrink-0"
      style={{
        width: collapsed ? 52 : 220,
        background: "rgba(19,19,19,0.7)",
        backdropFilter: "blur(20px)",
      }}
    >
      <div
        className={`flex items-center gap-2.5 border-b border-border ${
          collapsed ? "py-4 justify-center" : "px-4 pt-4 pb-3.5"
        }`}
      >
        <LogoMark />
        {!collapsed && (
          <div>
            <div className="font-head font-bold text-[15px] text-text-1 leading-none tracking-tight">
              CodeAtlas
            </div>
            <div className="text-[10px] text-text-4 font-mono mt-0.5">
              v1.0 · local
            </div>
          </div>
        )}
      </div>

      <nav className="flex-1 py-2 overflow-y-auto">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              "flex items-center gap-2.5 w-full text-[13px] font-sans transition-all border-l-2 " +
              (collapsed ? "py-2.5 justify-center" : "px-3.5 py-2.5") +
              " " +
              (isActive
                ? "border-cyan bg-cyan/[0.06] text-cyan font-medium"
                : "border-transparent text-text-3 hover:text-text-1 hover:bg-white/[0.03]")
            }
          >
            <Icon name={item.icon} size={15} />
            {!collapsed && <span>{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      <button
        type="button"
        onClick={() => setCollapsed(!collapsed)}
        className={`flex items-center border-t border-border py-2.5 text-text-4 hover:text-text-2 transition-colors w-full ${
          collapsed ? "justify-center" : "justify-end px-3.5"
        }`}
      >
        <Icon name={collapsed ? "chevronR" : "chevronL"} size={13} />
      </button>
    </aside>
  );
}

function TopBar({ title }: { title: string }) {
  const connected = true;
  const statusColor = connected ? "#22c55e" : "#ef4444";
  const statusLabel = connected ? "Connected" : "Disconnected";

  return (
    <header
      className="h-[46px] shrink-0 flex items-center gap-3 px-5 border-b border-border"
      style={{
        background: "rgba(19,19,19,0.6)",
        backdropFilter: "blur(20px)",
      }}
    >
      <span className="font-head font-bold text-[14px] text-text-1">
        {title}
      </span>
      <div className="flex-1" />
      <div
        className="flex items-center gap-1.5 rounded-full border px-2.5 py-[3px] text-[11px]"
        style={{
          backgroundColor: `${statusColor}14`,
          borderColor: `${statusColor}40`,
          color: statusColor,
        }}
      >
        <PulseDot color={statusColor} size={6} />
        {statusLabel}
      </div>
      <a
        href="https://github.com/AryanSaini26/CodeAtlas"
        target="_blank"
        rel="noreferrer"
        className="text-text-4 hover:text-text-2 text-[11px] no-underline hover:no-underline flex items-center gap-1"
      >
        <Icon name="externalLink" size={12} /> GitHub
      </a>
    </header>
  );
}

function StatusFooter() {
  const stats = useQuery({ queryKey: ["stats"], queryFn: () => api.stats() });
  const s = stats.data;
  return (
    <footer
      className="h-8 shrink-0 flex items-center gap-4 px-4 border-t border-border"
      style={{ background: "rgba(13,13,13,0.8)" }}
    >
      {s ? (
        <>
          <Stat label="Files" value={s.files.toLocaleString()} />
          <Sep />
          <Stat label="Symbols" value={s.symbols.toLocaleString()} />
          <Sep />
          <Stat label="Relationships" value={s.relationships.toLocaleString()} />
        </>
      ) : (
        <span className="text-[11px] text-text-4">Loading stats…</span>
      )}
      <div className="flex-1" />
      <span className="text-[10px] text-text-4 font-mono">
        http://127.0.0.1:8080
      </span>
    </footer>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <span className="text-[11px] text-text-3">
      <span className="text-text-4">{label} </span>
      <span className="font-mono text-text-2">{value}</span>
    </span>
  );
}

function Sep() {
  return <span className="w-px h-3 bg-border" />;
}

export function Layout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();
  const active = NAV.find(
    (n) => (n.end ? location.pathname === n.to : location.pathname.startsWith(n.to)),
  );
  const isGraph = location.pathname.startsWith("/graph");
  return (
    <div className="flex flex-col h-screen">
      <TopBar title={active?.label ?? "CodeAtlas"} />
      <div className="flex-1 flex min-h-0">
        <Sidebar collapsed={collapsed} setCollapsed={setCollapsed} />
        <main
          className={`flex-1 flex flex-col bg-bg ${
            isGraph ? "overflow-hidden p-3" : "overflow-y-auto p-4"
          }`}
        >
          <div className={`flex-1 ${isGraph ? "h-full" : ""}`}>{children}</div>
        </main>
      </div>
      <StatusFooter />
    </div>
  );
}
