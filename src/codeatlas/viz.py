"""Self-contained interactive graph visualization using D3.js."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codeatlas.graph.store import GraphStore

VIZ_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CodeAtlas — Knowledge Graph</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
         background: #0d1117; color: #c9d1d9; overflow: hidden; }
  #toolbar { position: fixed; top: 0; left: 0; right: 0; z-index: 10;
             background: #161b22; border-bottom: 1px solid #30363d;
             padding: 8px 16px; display: flex; align-items: center; gap: 12px; }
  #toolbar h1 { font-size: 16px; font-weight: 600; color: #58a6ff; }
  #toolbar .stats { font-size: 13px; color: #8b949e; }
  #search { background: #0d1117; border: 1px solid #30363d; border-radius: 6px;
            color: #c9d1d9; padding: 4px 10px; font-size: 13px; width: 220px; }
  #search:focus { outline: none; border-color: #58a6ff; }
  #search::placeholder { color: #484f58; }
  .legend { display: flex; gap: 10px; margin-left: auto; }
  .legend-item { display: flex; align-items: center; gap: 4px; font-size: 12px; color: #8b949e; }
  .legend-dot { width: 10px; height: 10px; border-radius: 50%; }
  svg { width: 100vw; height: 100vh; }
  .link { stroke-opacity: 0.4; }
  .link:hover { stroke-opacity: 1; }
  .node circle { stroke: #0d1117; stroke-width: 1.5px; cursor: pointer; }
  .node text { font-size: 10px; fill: #c9d1d9; pointer-events: none; }
  .node.dimmed circle { opacity: 0.15; }
  .node.dimmed text { opacity: 0.1; }
  .link.dimmed { stroke-opacity: 0.04; }
  #tooltip { position: fixed; background: #1c2128; border: 1px solid #30363d;
             border-radius: 8px; padding: 10px 14px; font-size: 12px;
             pointer-events: none; display: none; z-index: 20;
             max-width: 360px; box-shadow: 0 4px 12px rgba(0,0,0,0.4); }
  #tooltip .tt-name { font-weight: 600; color: #58a6ff; font-size: 13px; }
  #tooltip .tt-kind { color: #8b949e; margin-left: 6px; }
  #tooltip .tt-file { color: #7ee787; margin-top: 4px; }
</style>
</head>
<body>
<div id="toolbar">
  <h1>CodeAtlas</h1>
  <input id="search" type="text" placeholder="Search symbols…">
  <span class="stats" id="stats"></span>
  <div class="legend">
    <div class="legend-item"><div class="legend-dot" style="background:#58a6ff"></div>class</div>
    <div class="legend-item"><div class="legend-dot" style="background:#7ee787"></div>function</div>
    <div class="legend-item"><div class="legend-dot" style="background:#d2a8ff"></div>interface</div>
    <div class="legend-item"><div class="legend-dot" style="background:#ffa657"></div>import</div>
    <div class="legend-item"><div class="legend-dot" style="background:#f78166"></div>enum</div>
    <div class="legend-item"><div class="legend-dot" style="background:#8b949e"></div>other</div>
  </div>
</div>
<div id="tooltip">
  <span class="tt-name"></span><span class="tt-kind"></span>
  <div class="tt-file"></div>
</div>
<svg></svg>
<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
const graphData = __GRAPH_JSON__;

const kindColor = {
  "class": "#58a6ff", "method": "#7ee787", "function": "#7ee787",
  "interface": "#d2a8ff", "import": "#ffa657", "module": "#ffa657",
  "enum": "#f78166", "constant": "#f97583", "variable": "#f97583",
  "type_alias": "#d2a8ff", "namespace": "#79c0ff"
};
const defaultColor = "#8b949e";

const edgeColor = {
  "calls": "#3fb950", "imports": "#58a6ff", "inherits": "#f85149",
  "implements": "#bc8cff", "decorates": "#d29922", "references": "#39d2e0"
};

const svg = d3.select("svg");
const width = window.innerWidth;
const height = window.innerHeight;

document.getElementById("stats").textContent =
  `${graphData.nodes.length} symbols · ${graphData.links.length} relationships`;

const simulation = d3.forceSimulation(graphData.nodes)
  .force("link", d3.forceLink(graphData.links).id(d => d.id).distance(80))
  .force("charge", d3.forceManyBody().strength(-120))
  .force("center", d3.forceCenter(width / 2, height / 2))
  .force("collision", d3.forceCollide().radius(20));

const g = svg.append("g");

// Zoom
svg.call(d3.zoom().scaleExtent([0.1, 8]).on("zoom", (e) => {
  g.attr("transform", e.transform);
}));

const link = g.append("g")
  .selectAll("line")
  .data(graphData.links)
  .join("line")
  .attr("class", "link")
  .attr("stroke", d => edgeColor[d.kind] || "#30363d")
  .attr("stroke-width", 1);

const node = g.append("g")
  .selectAll("g")
  .data(graphData.nodes)
  .join("g")
  .attr("class", "node")
  .call(d3.drag()
    .on("start", (e, d) => { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
    .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
    .on("end", (e, d) => { if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
  );

node.append("circle")
  .attr("r", d => {
    const deg = graphData.links.filter(l => l.source.id === d.id || l.target.id === d.id).length;
    return Math.max(4, Math.min(deg * 1.5 + 4, 18));
  })
  .attr("fill", d => kindColor[d.kind] || defaultColor);

node.append("text")
  .attr("dx", 12).attr("dy", 4)
  .text(d => d.name);

const tooltip = document.getElementById("tooltip");

node.on("mouseover", (e, d) => {
  tooltip.style.display = "block";
  tooltip.querySelector(".tt-name").textContent = d.qualified_name || d.name;
  tooltip.querySelector(".tt-kind").textContent = `(${d.kind})`;
  tooltip.querySelector(".tt-file").textContent = d.file || "";

  // Highlight connected
  const connected = new Set();
  connected.add(d.id);
  graphData.links.forEach(l => {
    const sid = typeof l.source === "object" ? l.source.id : l.source;
    const tid = typeof l.target === "object" ? l.target.id : l.target;
    if (sid === d.id) connected.add(tid);
    if (tid === d.id) connected.add(sid);
  });
  node.classed("dimmed", n => !connected.has(n.id));
  link.classed("dimmed", l => {
    const sid = typeof l.source === "object" ? l.source.id : l.source;
    const tid = typeof l.target === "object" ? l.target.id : l.target;
    return sid !== d.id && tid !== d.id;
  });
}).on("mousemove", (e) => {
  tooltip.style.left = (e.clientX + 14) + "px";
  tooltip.style.top = (e.clientY + 14) + "px";
}).on("mouseout", () => {
  tooltip.style.display = "none";
  node.classed("dimmed", false);
  link.classed("dimmed", false);
});

simulation.on("tick", () => {
  link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
      .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
  node.attr("transform", d => `translate(${d.x},${d.y})`);
});

// Search
document.getElementById("search").addEventListener("input", (e) => {
  const q = e.target.value.toLowerCase();
  if (!q) { node.classed("dimmed", false); link.classed("dimmed", false); return; }
  const matched = new Set();
  graphData.nodes.forEach(n => {
    if ((n.name || "").toLowerCase().includes(q) || (n.qualified_name || "").toLowerCase().includes(q)) {
      matched.add(n.id);
    }
  });
  // Also show their direct connections
  const expanded = new Set(matched);
  graphData.links.forEach(l => {
    const sid = typeof l.source === "object" ? l.source.id : l.source;
    const tid = typeof l.target === "object" ? l.target.id : l.target;
    if (matched.has(sid)) expanded.add(tid);
    if (matched.has(tid)) expanded.add(sid);
  });
  node.classed("dimmed", n => !expanded.has(n.id));
  link.classed("dimmed", l => {
    const sid = typeof l.source === "object" ? l.source.id : l.source;
    const tid = typeof l.target === "object" ? l.target.id : l.target;
    return !expanded.has(sid) && !expanded.has(tid);
  });
});
</script>
</body>
</html>"""


def render_graph_html(graph_json: str) -> str:
    """Inject graph JSON data into the visualization HTML template."""
    return VIZ_HTML_TEMPLATE.replace("__GRAPH_JSON__", graph_json)


def generate_viz(store: GraphStore, file_filter: str | None = None) -> str:
    """Generate a self-contained HTML visualization from a GraphStore."""
    from codeatlas.graph.export import ExportOptions, export_json

    opts = ExportOptions(file_filter=file_filter)
    graph_json = export_json(store, opts)
    return render_graph_html(graph_json)
