import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api";

export type LiveStatus = "idle" | "connecting" | "open" | "closed";

export function useLiveStats(): { status: LiveStatus; lastEventAt: number | null } {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<LiveStatus>("idle");
  const [lastEventAt, setLastEventAt] = useState<number | null>(null);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (typeof window === "undefined" || typeof EventSource === "undefined") {
      return;
    }

    setStatus("connecting");
    const es = new EventSource(api.streamUrl());
    sourceRef.current = es;

    const onOpen = () => setStatus("open");
    const onError = () => setStatus("closed");
    const onStats = () => {
      setLastEventAt(Date.now());
      queryClient.invalidateQueries({ queryKey: ["stats"] });
    };

    es.addEventListener("open", onOpen);
    es.addEventListener("error", onError);
    es.addEventListener("stats", onStats);

    return () => {
      es.removeEventListener("open", onOpen);
      es.removeEventListener("error", onError);
      es.removeEventListener("stats", onStats);
      es.close();
      sourceRef.current = null;
    };
  }, [queryClient]);

  return { status, lastEventAt };
}
