import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import ForceGraph2D from "react-force-graph-2d";
import { useNavigate } from "react-router-dom";
import { api, type GraphNode } from "../api";
import { KIND_COLOR, Skeleton } from "../components/ui";
import { Icon } from "../components/Icon";

// Node augmented with centrality + simulation coordinates the force layout injects.
type VizNode = GraphNode & { val?: number; x?: number; y?: number };
type VizLink = { source: string | VizNode; target: string | VizNode; kind: string; confidence?: string };

type FGMethods = {
  zoomToFit: (ms?: number, padding?: number) => void;
  centerAt: (x?: number, y?: number, ms?: number) => void;
  zoom: (k?: number, ms?: number) => void;
};

function nodeId(end: string | VizNode): string {
  return typeof end === "string" ? end : end.id;
}

function colorFor(node: GraphNode, byCommunity: boolean): string {
  if (byCommunity && node.community_id) {
    const hash = Array.from(node.community_id).reduce(
      (acc, ch) => (acc * 33 + ch.charCodeAt(0)) >>> 0,
      0,
    );
    return `hsl(${hash % 360} 70% 60%)`;
  }
  return KIND_COLOR[node.kind] ?? "#71717a";
}

const KIND_ORDER = ["function", "method", "class", "interface", "module", "variable", "type"];

export default function GraphPage() {
  const [fileFilter, setFileFilter] = useState("");
  const [byCommunity, setByCommunity] = useState(true);
  const [limit, setLimit] = useState(2000);
  const [nameQuery, setNameQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const navigate = useNavigate();
  const fgRef = useRef<FGMethods | undefined>(undefined);

  const { data, isLoading } = useQuery({
    queryKey: ["graph", fileFilter, byCommunity, limit],
    queryFn: () =>
      api.graph({ file_filter: fileFilter || undefined, communities: byCommunity, limit }),
  });

  // PageRank centrality drives node size + glow. Fetched separately and merged
  // by id so we don't change the graph endpoint.
  const { data: ranking } = useQuery({
    queryKey: ["pagerank", limit],
    queryFn: () => api.pagerank({ limit: 500 }),
  });

  const scoreById = useMemo(() => {
    const map = new Map<string, number>();
    const top = ranking?.ranking ?? [];
    const max = top.reduce((m, r) => Math.max(m, r.score), 0) || 1;
    for (const r of top) map.set(r.id, r.score / max);
    return map;
  }, [ranking]);

  const graphData = useMemo(() => {
    if (!data) return { nodes: [] as VizNode[], links: [] as VizLink[] };
    // Degree is the fallback weight for nodes outside the PageRank top-N.
    const degree = new Map<string, number>();
    for (const l of data.links) {
      degree.set(l.source, (degree.get(l.source) ?? 0) + 1);
      degree.set(l.target, (degree.get(l.target) ?? 0) + 1);
    }
    const maxDeg = Math.max(1, ...degree.values());
    const nodes: VizNode[] = data.nodes.map((n) => ({
      ...n,
      val: scoreById.get(n.id) ?? (degree.get(n.id) ?? 0) / maxDeg,
    }));
    return { nodes, links: data.links.map((l) => ({ ...l })) as VizLink[] };
  }, [data, scoreById]);

  // Adjacency for blast-radius highlighting on click.
  const adjacency = useMemo(() => {
    const map = new Map<string, Set<string>>();
    for (const l of graphData.links) {
      const s = nodeId(l.source);
      const t = nodeId(l.target);
      map.set(s, (map.get(s) ?? new Set()).add(t));
      map.set(t, (map.get(t) ?? new Set()).add(s));
    }
    return map;
  }, [graphData]);

  const highlightNodes = useMemo(() => {
    if (!selectedId) return null;
    const set = new Set<string>([selectedId]);
    for (const n of adjacency.get(selectedId) ?? []) set.add(n);
    return set;
  }, [selectedId, adjacency]);

  const nameMatches = useMemo(() => {
    const q = nameQuery.trim().toLowerCase();
    if (!q) return null;
    return new Set(
      graphData.nodes.filter((n) => n.name.toLowerCase().includes(q)).map((n) => n.id),
    );
  }, [nameQuery, graphData]);

  // Zoom to the first search match.
  useEffect(() => {
    if (!nameMatches || nameMatches.size === 0) return;
    const first = graphData.nodes.find((n) => nameMatches.has(n.id));
    if (first && first.x != null && first.y != null) {
      fgRef.current?.centerAt(first.x, first.y, 600);
      fgRef.current?.zoom(4, 600);
    }
  }, [nameMatches, graphData]);

  const selectedNode = selectedId ? graphData.nodes.find((n) => n.id === selectedId) : null;

  return (
    <div className="flex flex-col gap-3 h-full min-h-0">
      <div className="glass rounded-[10px] px-4 py-3 flex flex-wrap gap-3 items-center">
        <div className="flex items-center gap-2 flex-1 min-w-[200px]">
          <Icon name="search" size={13} className="text-text-4 shrink-0" />
          <input
            value={nameQuery}
            onChange={(e) => setNameQuery(e.target.value)}
            placeholder="Find a symbol by name…"
            className="flex-1 bg-transparent border-none outline-none font-mono text-[12px] text-text-1 placeholder:text-text-4"
          />
        </div>
        <input
          value={fileFilter}
          onChange={(e) => setFileFilter(e.target.value)}
          placeholder="File prefix filter"
          className="w-[200px] bg-surface border border-border rounded-md px-2 py-1 font-mono text-[12px] text-text-1 outline-none focus:border-cyan/50"
        />
        <label className="flex items-center gap-2 text-[12px] text-text-2 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={byCommunity}
            onChange={(e) => setByCommunity(e.target.checked)}
            className="accent-cyan"
          />
          Color by community
        </label>
        <label className="flex items-center gap-2 text-[11px] text-text-4 uppercase tracking-[0.06em]">
          Limit
          <input
            type="number"
            min={100}
            max={10000}
            step={100}
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="w-20 bg-surface border border-border rounded-md px-2 py-1 font-mono text-[12px] text-text-1 outline-none focus:border-cyan/50"
          />
        </label>
        {data && (
          <span className="text-[11px] text-text-4 font-mono">
            {data.nodes.length} nodes · {data.links.length} links
          </span>
        )}
        {data?.truncated && (
          <span className="text-[11px] text-amber bg-amber/10 border border-amber/30 rounded px-2 py-[2px]">
            Truncated — narrow filter
          </span>
        )}
      </div>

      <div className="flex-1 flex gap-3 min-h-0">
        <div className="flex-1 glass rounded-[10px] overflow-hidden relative">
          {isLoading ? (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-[12px] text-text-4">Loading graph…</div>
            </div>
          ) : (
            <ForceGraph2D
              ref={fgRef as never}
              graphData={graphData}
              nodeRelSize={4}
              onBackgroundClick={() => setSelectedId(null)}
              onNodeClick={(n: VizNode) => setSelectedId(n.id === selectedId ? null : n.id)}
              linkColor={(l: VizLink) => {
                if (highlightNodes) {
                  const on = highlightNodes.has(nodeId(l.source)) && highlightNodes.has(nodeId(l.target));
                  return on ? "rgba(0,240,255,0.45)" : "rgba(255,255,255,0.03)";
                }
                return "rgba(255,255,255,0.08)";
              }}
              linkDirectionalArrowLength={3}
              linkDirectionalArrowRelPos={1}
              backgroundColor="transparent"
              nodeCanvasObject={(node: VizNode, ctx: CanvasRenderingContext2D, scale: number) => {
                const x = node.x ?? 0;
                const y = node.y ?? 0;
                const radius = 2 + (node.val ?? 0) * 7;
                const dim =
                  (highlightNodes && !highlightNodes.has(node.id)) ||
                  (nameMatches && !nameMatches.has(node.id));
                const color = colorFor(node, byCommunity);
                // Glow for high-centrality or matched/selected nodes.
                if (!dim && (node.val ?? 0) > 0.5) {
                  ctx.beginPath();
                  ctx.arc(x, y, radius + 3, 0, 2 * Math.PI);
                  ctx.fillStyle = color.replace(")", " / 0.18)").replace("hsl", "hsla").replace("rgb", "rgba");
                  ctx.fill();
                }
                ctx.beginPath();
                ctx.arc(x, y, radius, 0, 2 * Math.PI);
                ctx.fillStyle = dim ? "rgba(120,120,130,0.25)" : color;
                ctx.fill();
                if (node.id === selectedId || (nameMatches && nameMatches.has(node.id))) {
                  ctx.lineWidth = 1.5 / scale;
                  ctx.strokeStyle = "#ffffff";
                  ctx.stroke();
                }
                // Labels appear when zoomed in, or always for the selected/matched node.
                const showLabel =
                  scale > 2.5 || node.id === selectedId || (nameMatches?.has(node.id) ?? false);
                if (showLabel && !dim) {
                  ctx.font = `${11 / scale}px ui-sans-serif, system-ui`;
                  ctx.fillStyle = "rgba(230,230,240,0.9)";
                  ctx.fillText(node.name, x + radius + 1.5 / scale, y + 3 / scale);
                }
              }}
            />
          )}
        </div>

        <aside className="w-[210px] shrink-0 glass rounded-[10px] p-4 flex flex-col gap-3">
          {selectedNode ? (
            <div className="border-b border-border pb-3">
              <div className="text-[10px] text-text-4 uppercase tracking-[0.06em] mb-1">Selected</div>
              <div className="font-mono text-[12px] text-text-1 break-words">
                {selectedNode.name}
              </div>
              <div className="text-[11px] text-text-3 mt-0.5">{selectedNode.kind}</div>
              <div className="text-[11px] text-text-4 mt-1">
                {(highlightNodes?.size ?? 1) - 1} direct connections highlighted
              </div>
              <button
                onClick={() => navigate(`/symbol/${encodeURIComponent(selectedNode.id)}`)}
                className="mt-2 text-[11px] text-cyan hover:underline"
              >
                Open symbol →
              </button>
            </div>
          ) : null}
          <div>
            <div className="text-[10px] text-text-4 uppercase tracking-[0.06em] mb-2">Legend</div>
            <ul className="text-[11px] text-text-3 leading-relaxed space-y-1.5">
              <li>• Node size = PageRank centrality</li>
              <li>• Color = {byCommunity ? "community" : "symbol kind"}</li>
              <li>• Glow = high-importance node</li>
            </ul>
            {!byCommunity ? (
              <div className="flex flex-col gap-1 mt-2">
                {KIND_ORDER.map((k) => (
                  <div key={k} className="flex items-center gap-2 text-[11px]">
                    <span
                      className="w-2.5 h-2.5 rounded-full shrink-0"
                      style={{ backgroundColor: KIND_COLOR[k] ?? "#71717a" }}
                    />
                    <span className="text-text-2 capitalize">{k}</span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
          <div className="border-t border-border pt-3">
            <div className="text-[10px] text-text-4 uppercase tracking-[0.06em] mb-2">Tips</div>
            {isLoading ? (
              <div className="space-y-2">
                <Skeleton /> <Skeleton w="70%" />
              </div>
            ) : (
              <ul className="text-[11px] text-text-3 leading-relaxed space-y-1.5">
                <li>• Click a node → blast radius</li>
                <li>• Search to zoom to a symbol</li>
                <li>• Scroll to zoom · drag to pan</li>
              </ul>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
