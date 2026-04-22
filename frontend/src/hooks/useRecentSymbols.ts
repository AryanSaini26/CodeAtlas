import { useCallback, useEffect, useState } from "react";

export type RecentSymbol = {
  id: string;
  name: string;
  qualified_name: string;
  kind: string;
  file: string;
  visitedAt: number;
};

const STORAGE_KEY = "codeatlas.recentSymbols.v1";
const MAX_ENTRIES = 20;

function readStorage(): RecentSymbol[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (e): e is RecentSymbol =>
        !!e && typeof e.id === "string" && typeof e.visitedAt === "number",
    );
  } catch {
    return [];
  }
}

function writeStorage(entries: RecentSymbol[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    /* ignore quota / disabled storage */
  }
}

export function useRecentSymbols(): {
  recent: RecentSymbol[];
  record: (entry: Omit<RecentSymbol, "visitedAt">) => void;
  clear: () => void;
} {
  const [recent, setRecent] = useState<RecentSymbol[]>(() => readStorage());

  useEffect(() => {
    if (typeof window === "undefined") return;
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) setRecent(readStorage());
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const record = useCallback((entry: Omit<RecentSymbol, "visitedAt">) => {
    setRecent((prev) => {
      const without = prev.filter((p) => p.id !== entry.id);
      const next = [{ ...entry, visitedAt: Date.now() }, ...without].slice(
        0,
        MAX_ENTRIES,
      );
      writeStorage(next);
      return next;
    });
  }, []);

  const clear = useCallback(() => {
    writeStorage([]);
    setRecent([]);
  }, []);

  return { recent, record, clear };
}
