"""Graph export to DOT (Graphviz), JSON (D3.js), and Mermaid formats."""

import json
import re
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


def export_mermaid(store: GraphStore, options: ExportOptions | None = None) -> str:
    """Export the class/interface hierarchy as a Mermaid classDiagram.

    Renders classes, interfaces, enums, and their inheritance/implementation
    edges. Methods are listed inside each class block (up to 6 per class).
    """
    opts = options or ExportOptions()
    conn = store._conn

    params: list[str] = []
    sym_query = """
        SELECT id, name, qualified_name, kind, file_path
        FROM symbols
        WHERE kind IN ('class', 'interface', 'struct', 'enum')
    """
    if opts.file_filter:
        sym_query += " AND file_path LIKE ?"
        params.append(f"{opts.file_filter}%")
    symbols = conn.execute(sym_query, params).fetchall()
    symbol_ids = {row["id"] for row in symbols}

    # Map qualified_name → methods (up to 6)
    method_params: list[str] = []
    method_query = """
        SELECT name, qualified_name, kind, signature
        FROM symbols
        WHERE kind = 'method'
    """
    if opts.file_filter:
        method_query += " AND file_path LIKE ?"
        method_params.append(f"{opts.file_filter}%")
    method_rows = conn.execute(method_query, method_params).fetchall()

    class_to_methods: dict[str, list[str]] = {}
    for mr in method_rows:
        qn = mr["qualified_name"] or ""
        if "." in qn:
            parent_qn = qn.rsplit(".", 1)[0]
            display = mr["signature"] or mr["name"]
            # Trim long signatures to keep diagram readable
            if len(display) > 60:
                display = display[:57] + "..."
            class_to_methods.setdefault(parent_qn, []).append(display)

    lines = ["classDiagram"]

    for row in symbols:
        safe = _mermaid_id(row["name"])
        kind = row["kind"]
        lines.append(f"    class {safe} {{")
        if kind == "interface":
            lines.append("        <<interface>>")
        elif kind == "enum":
            lines.append("        <<enumeration>>")
        for sig in class_to_methods.get(row["qualified_name"], [])[:6]:
            lines.append(f"        +{_mermaid_safe(sig)}")
        lines.append("    }")

    # Inheritance / implements edges
    rels = conn.execute(
        "SELECT source_id, target_id, kind FROM relationships WHERE kind IN ('inherits', 'implements')"
    ).fetchall()
    id_to_name: dict[str, str] = {row["id"]: row["name"] for row in symbols}
    for r in rels:
        src_id = r["source_id"]
        tgt_id = r["target_id"]
        if src_id not in symbol_ids:
            continue
        if tgt_id in id_to_name:
            tgt_name = id_to_name[tgt_id]
        elif tgt_id.startswith("<unresolved>::") or tgt_id.startswith("<external>::"):
            tgt_name = tgt_id.split("::")[-1]
        else:
            continue
        src_name = id_to_name[src_id]
        arrow = "<|--" if r["kind"] == "inherits" else "<|.."
        lines.append(f"    {_mermaid_id(tgt_name)} {arrow} {_mermaid_id(src_name)}")

    return "\n".join(lines)


def _mermaid_id(name: str) -> str:
    """Strip non-identifier characters for Mermaid node names."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def _mermaid_safe(text: str) -> str:
    """Escape characters that would break a Mermaid class member line."""
    return text.replace("{", "(").replace("}", ")").replace('"', "'").replace("\n", " ")


def _dot_id(symbol_id: str) -> str:
    """Convert a symbol ID to a valid DOT node identifier."""
    return '"' + _dot_escape(symbol_id) + '"'


def _dot_escape(s: str) -> str:
    """Escape special characters for DOT format."""
    return s.replace("\\", "\\\\").replace('"', '\\"')
