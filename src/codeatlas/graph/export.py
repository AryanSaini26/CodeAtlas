"""Graph export to DOT (Graphviz) and JSON (D3.js) formats."""

import json
from dataclasses import dataclass

from codeatlas.graph.store import GraphStore


@dataclass
class ExportOptions:
    include_externals: bool = False
    max_depth: int = 0
    file_filter: str | None = None


def export_dot(store: GraphStore, options: ExportOptions | None = None) -> str:
    """Export the knowledge graph to Graphviz DOT format."""
    opts = options or ExportOptions()
    conn = store._conn

    lines = [
        "digraph codeatlas {",
        "    rankdir=LR;",
        '    node [shape=box, fontname="Helvetica"];',
    ]

    # Collect symbols
    query = "SELECT id, name, qualified_name, kind, file_path FROM symbols"
    params: list[str] = []
    if opts.file_filter:
        query += " WHERE file_path LIKE ?"
        params.append(f"{opts.file_filter}%")

    symbols = conn.execute(query, params).fetchall()
    symbol_ids = {row["id"] for row in symbols}

    # Style map
    kind_styles = {
        "function": 'shape=ellipse, style=filled, fillcolor="#d4edda"',
        "method": 'shape=ellipse, style=filled, fillcolor="#d4edda"',
        "class": 'shape=box, style=filled, fillcolor="#cce5ff"',
        "interface": 'shape=box, style="filled,dashed", fillcolor="#e2e3e5"',
        "module": 'shape=folder, style=filled, fillcolor="#fff3cd"',
        "constant": 'shape=diamond, style=filled, fillcolor="#f8d7da"',
        "variable": 'shape=diamond, style=filled, fillcolor="#fce4ec"',
        "enum": 'shape=box, style=filled, fillcolor="#e8daef"',
        "type_alias": 'shape=box, style="filled,rounded", fillcolor="#d5f5e3"',
        "import": 'shape=note, style=filled, fillcolor="#fdebd0"',
        "namespace": 'shape=tab, style=filled, fillcolor="#d6eaf8"',
    }

    for row in symbols:
        node_id = _dot_id(row["id"])
        style = kind_styles.get(row["kind"], "")
        label = row["qualified_name"]
        lines.append(f'    {node_id} [label="{_dot_escape(label)}", {style}];')

    # Collect relationships
    rel_query = "SELECT source_id, target_id, kind FROM relationships"
    rel_params: list[str] = []
    if opts.file_filter:
        rel_query += " WHERE file_path LIKE ?"
        rel_params.append(f"{opts.file_filter}%")

    relationships = conn.execute(rel_query, rel_params).fetchall()

    edge_styles = {
        "calls": 'color="#28a745"',
        "imports": 'color="#007bff", style=dashed',
        "inherits": 'color="#dc3545", arrowhead=empty',
        "implements": 'color="#6f42c1", style=dashed, arrowhead=empty',
        "decorates": 'color="#fd7e14", style=dotted',
        "defines": 'color="#6c757d"',
        "references": 'color="#17a2b8", style=dotted',
    }

    for row in relationships:
        src = row["source_id"]
        tgt = row["target_id"]

        if not opts.include_externals:
            if tgt.startswith("<external>::") or tgt.startswith("<unresolved>::"):
                continue
            if src not in symbol_ids or tgt not in symbol_ids:
                continue

        style = edge_styles.get(row["kind"], "")
        lines.append(f'    {_dot_id(src)} -> {_dot_id(tgt)} [{style}, label="{row["kind"]}"];')

    lines.append("}")
    return "\n".join(lines)


def export_json(store: GraphStore, options: ExportOptions | None = None) -> str:
    """Export the knowledge graph to D3.js-compatible JSON format."""
    opts = options or ExportOptions()
    conn = store._conn

    query = "SELECT id, name, qualified_name, kind, file_path FROM symbols"
    params: list[str] = []
    if opts.file_filter:
        query += " WHERE file_path LIKE ?"
        params.append(f"{opts.file_filter}%")

    symbols = conn.execute(query, params).fetchall()
    symbol_ids = {row["id"] for row in symbols}

    nodes = []
    for row in symbols:
        nodes.append(
            {
                "id": row["id"],
                "name": row["name"],
                "qualified_name": row["qualified_name"],
                "kind": row["kind"],
                "file": row["file_path"],
            }
        )

    rel_query = "SELECT source_id, target_id, kind FROM relationships"
    rel_params: list[str] = []
    if opts.file_filter:
        rel_query += " WHERE file_path LIKE ?"
        rel_params.append(f"{opts.file_filter}%")

    relationships = conn.execute(rel_query, rel_params).fetchall()

    links = []
    for row in relationships:
        src = row["source_id"]
        tgt = row["target_id"]

        if not opts.include_externals:
            if tgt.startswith("<external>::") or tgt.startswith("<unresolved>::"):
                continue
            if src not in symbol_ids or tgt not in symbol_ids:
                continue

        links.append(
            {
                "source": src,
                "target": tgt,
                "kind": row["kind"],
            }
        )

    data = {"nodes": nodes, "links": links}
    return json.dumps(data, indent=2)


def _dot_id(symbol_id: str) -> str:
    """Convert a symbol ID to a valid DOT node identifier."""
    return '"' + _dot_escape(symbol_id) + '"'


def _dot_escape(s: str) -> str:
    """Escape special characters for DOT format."""
    return s.replace("\\", "\\\\").replace('"', '\\"')
