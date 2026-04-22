import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, type SearchHit } from "../api";
import { Icon } from "./Icon";
import { FilePath, KindBadge, KindDot, Skeleton } from "./ui";

type NavItem = {
  kind: "nav";
  label: string;
  to: string;
  hint: string;
  icon: string;
};

const NAV_ITEMS: NavItem[] = [
  { kind: "nav", label: "Dashboard", to: "/", hint: "Go to overview", icon: "dashboard" },
  { kind: "nav", label: "Graph", to: "/graph", hint: "Interactive force graph", icon: "graph" },
  { kind: "nav", label: "Search", to: "/search", hint: "Full-text + semantic search", icon: "search" },
  { kind: "nav", label: "Analysis", to: "/analysis", hint: "PageRank, Hotspots, Communities", icon: "analysis" },
  { kind: "nav", label: "Diff", to: "/diff", hint: "Compare two git refs", icon: "diff" },
  { kind: "nav", label: "Settings", to: "/settings", hint: "API config + reindex", icon: "settings" },
];

function useDebounce<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function CommandPalette({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const dq = useDebounce(query.trim(), 150);

  useEffect(() => {
    if (open) {
      setQuery("");
      setCursor(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const { data, isFetching } = useQuery({
    enabled: open && dq.length > 0,
    queryKey: ["palette-search", dq],
    queryFn: () => api.search({ q: dq, limit: 8 }),
  });

  const filteredNav = useMemo(() => {
    if (!query) return NAV_ITEMS;
    const q = query.toLowerCase();
    return NAV_ITEMS.filter(
      (n) => n.label.toLowerCase().includes(q) || n.hint.toLowerCase().includes(q),
    );
  }, [query]);

  const hits = data?.hits ?? [];
  const items: Array<NavItem | { kind: "hit"; hit: SearchHit }> = useMemo(
    () => [
      ...filteredNav,
      ...hits.map((h) => ({ kind: "hit" as const, hit: h })),
    ],
    [filteredNav, hits],
  );

  useEffect(() => {
    setCursor(0);
  }, [dq, items.length]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setCursor((c) => Math.min(c + 1, items.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setCursor((c) => Math.max(c - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const item = items[cursor];
        if (!item) return;
        if (item.kind === "nav") {
          navigate(item.to);
        } else {
          navigate(`/symbol/${encodeURIComponent(item.hit.id)}`);
        }
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, items, cursor, navigate, onClose]);

  useEffect(() => {
    if (!listRef.current) return;
    const active = listRef.current.querySelector<HTMLElement>(
      '[data-active="true"]',
    );
    active?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh] px-4 animate-fade-up"
      style={{ backgroundColor: "rgba(5,5,5,0.75)" }}
      onClick={onClose}
    >
      <div
        className="glass rounded-[12px] w-full max-w-[640px] flex flex-col overflow-hidden shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
          <Icon name="search" size={15} className="text-text-3 shrink-0" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Type a symbol, qualified name, or doc term…"
            className="flex-1 bg-transparent outline-none border-none font-mono text-[13px] text-text-1 placeholder:text-text-4"
          />
          <kbd className="kbd">esc</kbd>
        </div>

        <div ref={listRef} className="max-h-[60vh] overflow-y-auto">
          {filteredNav.length > 0 && (
            <Section title="Navigate">
              {filteredNav.map((item, idx) => {
                const active = cursor === idx;
                return (
                  <Row
                    key={item.to}
                    active={active}
                    onMouseEnter={() => setCursor(idx)}
                    onClick={() => {
                      navigate(item.to);
                      onClose();
                    }}
                  >
                    <Icon name={item.icon} size={14} className="text-text-3" />
                    <span className="text-[12px] text-text-1 font-medium">
                      {item.label}
                    </span>
                    <span className="text-[11px] text-text-4 ml-2 truncate">
                      {item.hint}
                    </span>
                  </Row>
                );
              })}
            </Section>
          )}

          {dq.length > 0 && (
            <Section
              title={
                isFetching && !data
                  ? "Searching…"
                  : `Symbols${hits.length ? ` (${hits.length})` : ""}`
              }
            >
              {isFetching && !data && (
                <div className="px-4 py-2 space-y-2">
                  <Skeleton /> <Skeleton /> <Skeleton w="70%" />
                </div>
              )}
              {data && hits.length === 0 && (
                <div className="px-4 py-4 text-center text-[12px] text-text-4">
                  No symbols match "{dq}"
                </div>
              )}
              {hits.map((hit, i) => {
                const idx = filteredNav.length + i;
                const active = cursor === idx;
                return (
                  <Row
                    key={hit.id}
                    active={active}
                    onMouseEnter={() => setCursor(idx)}
                    onClick={() => {
                      navigate(`/symbol/${encodeURIComponent(hit.id)}`);
                      onClose();
                    }}
                  >
                    <KindDot kind={hit.kind} />
                    <span className="font-mono text-[12px] text-text-1 font-medium truncate">
                      {hit.name}
                    </span>
                    <KindBadge kind={hit.kind} />
                    <span className="flex-1" />
                    <FilePath path={hit.file} />
                  </Row>
                );
              })}
            </Section>
          )}

          {!dq && filteredNav.length === NAV_ITEMS.length && (
            <div className="px-4 py-3 text-[11px] text-text-4 border-t border-border">
              <span className="font-mono">
                Start typing to search symbols. Use <kbd className="kbd">↑</kbd>{" "}
                <kbd className="kbd">↓</kbd> to navigate,{" "}
                <kbd className="kbd">↵</kbd> to select.
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="px-4 pt-3 pb-1 text-[10px] text-text-4 uppercase tracking-[0.06em]">
        {title}
      </div>
      {children}
    </div>
  );
}

function Row({
  active,
  onMouseEnter,
  onClick,
  children,
}: {
  active: boolean;
  onMouseEnter?: () => void;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      data-active={active}
      onMouseEnter={onMouseEnter}
      onClick={onClick}
      className={
        "w-full flex items-center gap-2.5 px-4 py-2 text-left transition-colors border-l-2 " +
        (active
          ? "border-l-cyan bg-cyan/[0.06]"
          : "border-l-transparent hover:bg-white/[0.02]")
      }
    >
      {children}
    </button>
  );
}
