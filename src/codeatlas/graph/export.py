"""Graph export to DOT, JSON, Mermaid, GraphML, CSV, and Cypher formats."""

import csv
import io
import json
import re
from dataclasses import dataclass
from xml.sax.saxutils import escape as xml_escape

from codeatlas.graph.store import GraphStore


@dataclass
class ExportOptions:
    include_externals: bool = False
    max_depth: int = 0
    file_filter: str | None = None
    include_communities: bool = False


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

    communities = store.detect_communities() if opts.include_communities else {}

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
        if communities:
            cid = communities.get(row["id"], "")
            color = _community_color(cid)
            style = f'style=filled, fillcolor="{color}"'
        lines.append(f'    {node_id} [label="{_dot_escape(label)}", {style}];')

    # Collect relationships
    rel_query = "SELECT source_id, target_id, kind, confidence FROM relationships"
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
        confidence = row["confidence"] if "confidence" in row.keys() else "extracted"
        if confidence == "inferred":
            style += ", style=dashed"
        elif confidence == "ambiguous":
            style += ", style=dotted"
        label = f"{row['kind']} ({confidence})" if confidence != "extracted" else row["kind"]
        lines.append(f'    {_dot_id(src)} -> {_dot_id(tgt)} [{style}, label="{label}"];')

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

    communities = store.detect_communities() if opts.include_communities else {}

    nodes = []
    for row in symbols:
        node: dict[str, str | None] = {
            "id": row["id"],
            "name": row["name"],
            "qualified_name": row["qualified_name"],
            "kind": row["kind"],
            "file": row["file_path"],
        }
        if communities:
            node["community_id"] = communities.get(row["id"])
        nodes.append(node)

    rel_query = "SELECT source_id, target_id, kind, confidence FROM relationships"
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

        confidence = row["confidence"] if "confidence" in row.keys() else "extracted"
        links.append(
            {
                "source": src,
                "target": tgt,
                "kind": row["kind"],
                "confidence": confidence,
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


def export_graphml(store: GraphStore, options: ExportOptions | None = None) -> str:
    """Export the knowledge graph to GraphML (Gephi/yEd/Cytoscape)."""
    opts = options or ExportOptions()
    conn = store._conn

    sym_query = "SELECT id, name, qualified_name, kind, file_path FROM symbols"
    sym_params: list[str] = []
    if opts.file_filter:
        sym_query += " WHERE file_path LIKE ?"
        sym_params.append(f"{opts.file_filter}%")
    symbols = conn.execute(sym_query, sym_params).fetchall()
    symbol_ids = {row["id"] for row in symbols}

    communities = store.detect_communities() if opts.include_communities else {}

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
        '  <key id="name" for="node" attr.name="name" attr.type="string"/>',
        '  <key id="qualified_name" for="node" attr.name="qualified_name" attr.type="string"/>',
        '  <key id="kind" for="node" attr.name="kind" attr.type="string"/>',
        '  <key id="file" for="node" attr.name="file" attr.type="string"/>',
        '  <key id="community_id" for="node" attr.name="community_id" attr.type="string"/>',
        '  <key id="rel_kind" for="edge" attr.name="kind" attr.type="string"/>',
        '  <key id="confidence" for="edge" attr.name="confidence" attr.type="string"/>',
        '  <graph id="codeatlas" edgedefault="directed">',
    ]

    for row in symbols:
        node_id = xml_escape(row["id"], {'"': "&quot;"})
        lines.append(f'    <node id="{node_id}">')
        lines.append(f'      <data key="name">{xml_escape(row["name"])}</data>')
        lines.append(f'      <data key="qualified_name">{xml_escape(row["qualified_name"])}</data>')
        lines.append(f'      <data key="kind">{xml_escape(row["kind"])}</data>')
        lines.append(f'      <data key="file">{xml_escape(row["file_path"])}</data>')
        if communities:
            cid = communities.get(row["id"]) or ""
            lines.append(f'      <data key="community_id">{xml_escape(cid)}</data>')
        lines.append("    </node>")

    rel_query = "SELECT source_id, target_id, kind, confidence FROM relationships"
    rel_params: list[str] = []
    if opts.file_filter:
        rel_query += " WHERE file_path LIKE ?"
        rel_params.append(f"{opts.file_filter}%")
    relationships = conn.execute(rel_query, rel_params).fetchall()

    for idx, row in enumerate(relationships):
        src = row["source_id"]
        tgt = row["target_id"]
        if not opts.include_externals:
            if tgt.startswith("<external>::") or tgt.startswith("<unresolved>::"):
                continue
            if src not in symbol_ids or tgt not in symbol_ids:
                continue
        confidence = row["confidence"] if "confidence" in row.keys() else "extracted"
        esc_src = xml_escape(src, {'"': "&quot;"})
        esc_tgt = xml_escape(tgt, {'"': "&quot;"})
        lines.append(f'    <edge id="e{idx}" source="{esc_src}" target="{esc_tgt}">')
        lines.append(f'      <data key="rel_kind">{xml_escape(row["kind"])}</data>')
        lines.append(f'      <data key="confidence">{xml_escape(confidence)}</data>')
        lines.append("    </edge>")

    lines.append("  </graph>")
    lines.append("</graphml>")
    return "\n".join(lines)


def export_csv(store: GraphStore, options: ExportOptions | None = None) -> str:
    """Export the knowledge graph to CSV (Gephi-style nodes + edges sections)."""
    opts = options or ExportOptions()
    conn = store._conn

    sym_query = "SELECT id, name, qualified_name, kind, file_path FROM symbols"
    sym_params: list[str] = []
    if opts.file_filter:
        sym_query += " WHERE file_path LIKE ?"
        sym_params.append(f"{opts.file_filter}%")
    symbols = conn.execute(sym_query, sym_params).fetchall()
    symbol_ids = {row["id"] for row in symbols}

    communities = store.detect_communities() if opts.include_communities else {}

    buf = io.StringIO()
    buf.write("# nodes\n")
    node_fields = ["id", "name", "qualified_name", "kind", "file"]
    if communities:
        node_fields.append("community_id")
    writer = csv.DictWriter(buf, fieldnames=node_fields)
    writer.writeheader()
    for row in symbols:
        record = {
            "id": row["id"],
            "name": row["name"],
            "qualified_name": row["qualified_name"],
            "kind": row["kind"],
            "file": row["file_path"],
        }
        if communities:
            record["community_id"] = communities.get(row["id"]) or ""
        writer.writerow(record)

    rel_query = "SELECT source_id, target_id, kind, confidence FROM relationships"
    rel_params: list[str] = []
    if opts.file_filter:
        rel_query += " WHERE file_path LIKE ?"
        rel_params.append(f"{opts.file_filter}%")
    relationships = conn.execute(rel_query, rel_params).fetchall()

    buf.write("# edges\n")
    edge_writer = csv.DictWriter(buf, fieldnames=["source", "target", "kind", "confidence"])
    edge_writer.writeheader()
    for row in relationships:
        src = row["source_id"]
        tgt = row["target_id"]
        if not opts.include_externals:
            if tgt.startswith("<external>::") or tgt.startswith("<unresolved>::"):
                continue
            if src not in symbol_ids or tgt not in symbol_ids:
                continue
        confidence = row["confidence"] if "confidence" in row.keys() else "extracted"
        edge_writer.writerow(
            {"source": src, "target": tgt, "kind": row["kind"], "confidence": confidence}
        )

    return buf.getvalue()


def export_cypher(store: GraphStore, options: ExportOptions | None = None) -> str:
    """Export the knowledge graph as Neo4j Cypher CREATE statements."""
    opts = options or ExportOptions()
    conn = store._conn

    sym_query = "SELECT id, name, qualified_name, kind, file_path FROM symbols"
    sym_params: list[str] = []
    if opts.file_filter:
        sym_query += " WHERE file_path LIKE ?"
        sym_params.append(f"{opts.file_filter}%")
    symbols = conn.execute(sym_query, sym_params).fetchall()
    symbol_ids = {row["id"] for row in symbols}

    communities = store.detect_communities() if opts.include_communities else {}

    lines = []
    id_to_var: dict[str, str] = {}
    for idx, row in enumerate(symbols):
        var = f"n{idx}"
        id_to_var[row["id"]] = var
        label = _cypher_label(row["kind"])
        props = {
            "id": row["id"],
            "name": row["name"],
            "qualified_name": row["qualified_name"],
            "kind": row["kind"],
            "file": row["file_path"],
        }
        if communities:
            props["community_id"] = communities.get(row["id"]) or ""
        props_str = ", ".join(f"{k}: {_cypher_literal(v)}" for k, v in props.items())
        lines.append(f"CREATE ({var}:{label} {{{props_str}}})")

    rel_query = "SELECT source_id, target_id, kind, confidence FROM relationships"
    rel_params: list[str] = []
    if opts.file_filter:
        rel_query += " WHERE file_path LIKE ?"
        rel_params.append(f"{opts.file_filter}%")
    relationships = conn.execute(rel_query, rel_params).fetchall()

    for row in relationships:
        src = row["source_id"]
        tgt = row["target_id"]
        if not opts.include_externals:
            if tgt.startswith("<external>::") or tgt.startswith("<unresolved>::"):
                continue
            if src not in symbol_ids or tgt not in symbol_ids:
                continue
        src_var = id_to_var.get(src)
        tgt_var = id_to_var.get(tgt)
        if src_var is None or tgt_var is None:
            continue
        confidence = row["confidence"] if "confidence" in row.keys() else "extracted"
        rel_type = row["kind"].upper()
        lines.append(
            f"CREATE ({src_var})-[:{rel_type} "
            f"{{confidence: {_cypher_literal(confidence)}}}]->({tgt_var})"
        )

    return "\n".join(lines) + ("\n" if lines else "")


def _cypher_label(kind: str) -> str:
    """Convert a symbol kind to a Cypher node label (PascalCase)."""
    return "".join(part.capitalize() for part in kind.split("_")) or "Symbol"


def _cypher_literal(value: str) -> str:
    """Escape a string for safe inclusion as a Cypher literal."""
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


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


_COMMUNITY_PALETTE = [
    "#a6cee3",
    "#b2df8a",
    "#fb9a99",
    "#fdbf6f",
    "#cab2d6",
    "#ffff99",
    "#8dd3c7",
    "#fccde5",
    "#bc80bd",
    "#ccebc5",
]


def _community_color(community_id: str) -> str:
    """Deterministic pastel color for a community id."""
    if not community_id:
        return "#e0e0e0"
    idx = abs(hash(community_id)) % len(_COMMUNITY_PALETTE)
    return _COMMUNITY_PALETTE[idx]
