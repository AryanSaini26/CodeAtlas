import { useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import ForceGraph2D from "react-force-graph-2d";
import { useNavigate } from "react-router-dom";
import { api, type GraphNode } from "../api";
import { KIND_COLOR, Skeleton } from "../components/ui";
import { Icon } from "../components/Icon";

function colorFor(node: GraphNode, byCommunity: boolean) {
  if (byCommunity && node.community_id) {
    const hash = Array.from(node.community_id).reduce(
      (acc, ch) => (acc * 33 + ch.charCodeAt(0)) >>> 0,
      0,
    );
    const hue = hash % 360;
    return `hsl(${hue} 70% 60%)`;
  }
  return KIND_COLOR[node.kind] ?? "#71717a";
}

const KIND_ORDER = [
  "function",
  "method",
  "class",
  "interface",
  "module",
  "variable",
  "type",
];

export default function GraphPage() {
  const [fileFilter, setFileFilter] = useState("");
  const [byCommunity, setByCommunity] = useState(false);
  const [limit, setLimit] = useState(2000);
  const navigate = useNavigate();
  const fgRef = useRef<unknown>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["graph", fileFilter, byCommunity, limit],
    queryFn: () =>
      api.graph({
        file_filter: fileFilter || undefined,
        communities: byCommunity,
        limit,
      }),
  });

  const graphData = useMemo(() => {
    if (!data) return { nodes: [], links: [] };
    return {
      nodes: data.nodes.map((n) => ({ ...n })),
      links: data.links.map((l) => ({ ...l })),
    };
  }, [data]);

  return (
    <div className="flex flex-col gap-3 h-full min-h-0">
      <div className="glass rounded-[10px] px-4 py-3 flex flex-wrap gap-3 items-center">
        <div className="flex items-center gap-2 flex-1 min-w-[240px]">
          <Icon name="search" size={13} className="text-text-4 shrink-0" />
          <input
            value={fileFilter}
            onChange={(e) => setFileFilter(e.target.value)}
            placeholder="File prefix — e.g. src/codeatlas/"
            className="flex-1 bg-transparent border-none outline-none font-mono text-[12px] text-text-1 placeholder:text-text-4"
          />
        </div>

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
            Truncated — narrow filter to see more
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
              nodeLabel={(n: GraphNode) => `${n.qualified_name} (${n.kind})`}
              nodeColor={(n: GraphNode) => colorFor(n, byCommunity)}
              nodeRelSize={4}
              linkColor={() => "rgba(255,255,255,0.10)"}
              linkDirectionalArrowLength={3}
              linkDirectionalArrowRelPos={1}
              onNodeClick={(n: GraphNode) =>
                navigate(`/symbol/${encodeURIComponent(n.id)}`)
              }
              backgroundColor="transparent"
            />
          )}
        </div>

        <aside className="w-[200px] shrink-0 glass rounded-[10px] p-4 flex flex-col gap-3">
          <div>
            <div className="text-[10px] text-text-4 uppercase tracking-[0.06em] mb-2">
              Legend
            </div>
            <div className="flex flex-col gap-1.5">
              {byCommunity ? (
                <span className="text-[11px] text-text-3 leading-relaxed">
                  Colors show strongly-connected communities detected via
                  Louvain modularity.
                </span>
              ) : (
                KIND_ORDER.map((k) => (
                  <div key={k} className="flex items-center gap-2 text-[11px]">
                    <span
                      className="w-2.5 h-2.5 rounded-full shrink-0"
                      style={{ backgroundColor: KIND_COLOR[k] ?? "#71717a" }}
                    />
                    <span className="text-text-2 capitalize">{k}</span>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="border-t border-border pt-3">
            <div className="text-[10px] text-text-4 uppercase tracking-[0.06em] mb-2">
              Tips
            </div>
            {isLoading ? (
              <div className="space-y-2">
                <Skeleton /> <Skeleton w="70%" /> <Skeleton w="85%" />
              </div>
            ) : (
              <ul className="text-[11px] text-text-3 leading-relaxed space-y-1.5">
                <li>• Drag nodes to rearrange</li>
                <li>• Click to open a symbol</li>
                <li>• Scroll to zoom</li>
                <li>• Narrow with file prefix filter</li>
              </ul>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
