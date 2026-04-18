import { useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import ForceGraph2D from "react-force-graph-2d";
import { useNavigate } from "react-router-dom";
import { api, type GraphNode } from "../api";

const KIND_COLORS: Record<string, string> = {
  function: "#7c8cff",
  method: "#57d6bf",
  class: "#f2b05c",
  interface: "#f07178",
  module: "#c792ea",
  variable: "#999999",
};

function colorFor(node: GraphNode, byCommunity: boolean) {
  if (byCommunity && node.community_id) {
    const hash = Array.from(node.community_id).reduce(
      (acc, ch) => (acc * 33 + ch.charCodeAt(0)) >>> 0,
      0
    );
    const hue = hash % 360;
    return `hsl(${hue} 65% 55%)`;
  }
  return KIND_COLORS[node.kind] ?? "#8892b0";
}

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
    <div className="flex flex-col gap-4">
      <div className="card flex flex-wrap gap-3 items-center">
        <input
          className="input max-w-xs"
          placeholder="File prefix filter (e.g. src/codeatlas/)"
          value={fileFilter}
          onChange={(e) => setFileFilter(e.target.value)}
        />
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={byCommunity}
            onChange={(e) => setByCommunity(e.target.checked)}
          />
          Color by community
        </label>
        <label className="flex items-center gap-2 text-sm">
          Limit
          <input
            type="number"
            className="input w-24"
            min={100}
            max={10000}
            step={100}
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
          />
        </label>
        {data?.truncated && (
          <span className="text-xs text-yellow-400">
            Truncated to {limit} nodes — narrow the file filter to see more.
          </span>
        )}
      </div>
      <div className="card h-[70vh] relative overflow-hidden p-0">
        {isLoading ? (
          <div className="absolute inset-0 flex items-center justify-center text-slate-500">
            Loading graph…
          </div>
        ) : (
          <ForceGraph2D
            ref={fgRef as never}
            graphData={graphData}
            nodeLabel={(n: GraphNode) => `${n.qualified_name} (${n.kind})`}
            nodeColor={(n: GraphNode) => colorFor(n, byCommunity)}
            nodeRelSize={4}
            linkColor={() => "rgba(255,255,255,0.12)"}
            linkDirectionalArrowLength={3}
            linkDirectionalArrowRelPos={1}
            onNodeClick={(n: GraphNode) =>
              navigate(`/symbol/${encodeURIComponent(n.id)}`)
            }
            backgroundColor="transparent"
          />
        )}
      </div>
    </div>
  );
}
