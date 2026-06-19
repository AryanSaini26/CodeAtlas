"""Static data-lineage extraction for dbt, Airflow, SQL, and OpenLineage export."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any, Literal

LineageFormat = Literal["text", "json", "openlineage"]


def build_lineage_graph(repo_path: str | Path) -> dict[str, Any]:
    """Build a lightweight static lineage graph from common data-engineering files."""
    root = Path(repo_path)
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []

    def add_node(node_id: str, kind: str, **attrs: Any) -> None:
        nodes.setdefault(node_id, {"id": node_id, "kind": kind, **attrs})

    def add_edge(source: str, target: str, kind: str) -> None:
        edge = {"source": source, "target": target, "kind": kind}
        if edge not in edges:
            edges.append(edge)

    _extract_dbt_manifest(root, add_node, add_edge)
    _extract_airflow_dags(root, add_node, add_edge)
    _extract_sql_files(root, add_node, add_edge)

    return {
        "repo": str(root),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": sorted(nodes.values(), key=lambda item: item["id"]),
        "edges": sorted(edges, key=lambda item: (item["source"], item["target"], item["kind"])),
    }


def lineage_impact(graph: dict[str, Any], query: str) -> dict[str, Any]:
    """Return downstream nodes reachable from a dataset/model/job name."""
    node_ids = [node["id"] for node in graph["nodes"]]
    query_lower = query.lower()
    seeds = [node_id for node_id in node_ids if node_id.lower() == query_lower]
    if not seeds:
        seeds = [node_id for node_id in node_ids if query_lower in node_id.lower()]
    adjacency: dict[str, list[str]] = {}
    for edge in graph["edges"]:
        adjacency.setdefault(edge["source"], []).append(edge["target"])

    seen: set[str] = set()
    queue = list(seeds)
    while queue:
        current = queue.pop(0)
        for target in adjacency.get(current, []):
            if target not in seen:
                seen.add(target)
                queue.append(target)

    return {
        "query": query,
        "matched": seeds,
        "downstream_count": len(seen),
        "downstream": sorted(seen),
    }


def render_lineage_text(graph: dict[str, Any]) -> str:
    lines = [
        "# CodeAtlas Data Lineage",
        "",
        f"- Nodes: {graph['node_count']}",
        f"- Edges: {graph['edge_count']}",
        "",
        "## Nodes",
    ]
    for node in graph["nodes"][:100]:
        lines.append(f"- `{node['id']}` ({node['kind']})")
    lines.extend(["", "## Edges"])
    for edge in graph["edges"][:150]:
        lines.append(f"- `{edge['source']}` --{edge['kind']}--> `{edge['target']}`")
    return "\n".join(lines)


def export_openlineage(graph: dict[str, Any]) -> dict[str, Any]:
    """Render static design lineage in an OpenLineage-inspired JobEvent shape."""
    events = []
    dataset_nodes = {
        node["id"]: node
        for node in graph["nodes"]
        if node["kind"] in {"dbt_model", "dbt_source", "sql_table", "sql_view", "dataset"}
    }
    for node in graph["nodes"]:
        if node["kind"] not in {"dbt_model", "airflow_task", "sql_query", "job"}:
            continue
        inputs = [
            _openlineage_dataset(edge["source"], dataset_nodes.get(edge["source"]))
            for edge in graph["edges"]
            if edge["target"] == node["id"] and edge["source"] in dataset_nodes
        ]
        outputs = [
            _openlineage_dataset(edge["target"], dataset_nodes.get(edge["target"]))
            for edge in graph["edges"]
            if edge["source"] == node["id"] and edge["target"] in dataset_nodes
        ]
        events.append(
            {
                "eventType": "JOB",
                "job": {
                    "namespace": "codeatlas.static",
                    "name": node["id"],
                    "facets": {
                        "sourceCodeLocation": {
                            "_producer": "codeatlas",
                            "_schemaURL": "https://openlineage.io/spec/facets/1-0-0/SourceCodeLocationJobFacet.json",
                            "type": "git",
                            "url": node.get("file", graph["repo"]),
                        }
                    },
                },
                "inputs": inputs,
                "outputs": outputs,
            }
        )
    return {
        "producer": "codeatlas",
        "schemaURL": "https://openlineage.io/spec/2-0-2/OpenLineage.json",
        "events": events,
    }


def _openlineage_dataset(name: str, node: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "namespace": "codeatlas.static",
        "name": name,
        "facets": {"schema": {"fields": node.get("columns", []) if node else []}},
    }


def _extract_dbt_manifest(root: Path, add_node: Any, add_edge: Any) -> None:
    for manifest in [root / "target" / "manifest.json", root / "manifest.json"]:
        if not manifest.exists():
            continue
        try:
            data = json.loads(manifest.read_text())
        except json.JSONDecodeError:
            continue
        resources = {}
        for section in ("nodes", "sources", "exposures", "metrics"):
            raw = data.get(section, {})
            if isinstance(raw, dict):
                resources.update(raw)
        for unique_id, item in resources.items():
            name = str(item.get("name", unique_id))
            resource_type = str(item.get("resource_type", "resource"))
            node_id = f"dbt:{resource_type}:{name}"
            add_node(
                node_id,
                f"dbt_{resource_type}",
                file=item.get("original_file_path"),
                owner=item.get("owner"),
            )
        for _unique_id, item in resources.items():
            source = f"dbt:{item.get('resource_type', 'resource')}:{item.get('name', _unique_id)}"
            depends_on = item.get("depends_on", {}).get("nodes", [])
            for dep in depends_on:
                dep_item = resources.get(dep)
                if dep_item:
                    target = f"dbt:{dep_item.get('resource_type', 'resource')}:{dep_item.get('name', dep)}"
                    add_edge(target, source, "depends_on")


def _extract_airflow_dags(root: Path, add_node: Any, add_edge: Any) -> None:
    for path in root.rglob("*.py"):
        if any(part in {".git", ".venv", "venv", "__pycache__"} for part in path.parts):
            continue
        try:
            tree = ast.parse(path.read_text())
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        dag_ids: set[str] = set()
        task_ids: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _call_name(node.func)
                if name == "DAG":
                    dag_id = _keyword_or_first_string(node, "dag_id", allow_first_arg=True)
                    if dag_id:
                        dag_ids.add(dag_id)
                        add_node(f"airflow:dag:{dag_id}", "airflow_dag", file=str(path))
                task_id = _keyword_or_first_string(node, "task_id", allow_first_arg=False)
                if task_id:
                    task_ids.add(task_id)
                    add_node(f"airflow:task:{task_id}", "airflow_task", file=str(path))
        for dag_id in dag_ids:
            for task_id in task_ids:
                add_edge(f"airflow:dag:{dag_id}", f"airflow:task:{task_id}", "contains")


def _extract_sql_files(root: Path, add_node: Any, add_edge: Any) -> None:
    table_re = re.compile(r"\b(?:from|join)\s+([a-zA-Z_][\w.]+)", re.IGNORECASE)
    create_re = re.compile(
        r"\bcreate\s+(?:or\s+replace\s+)?(?:table|view)\s+([a-zA-Z_][\w.]+)", re.IGNORECASE
    )
    for path in root.rglob("*.sql"):
        if ".git" in path.parts:
            continue
        try:
            text = path.read_text()
        except OSError:
            continue
        query_id = f"sql:query:{path.relative_to(root)}"
        add_node(query_id, "sql_query", file=str(path))
        for table in sorted(set(table_re.findall(text))):
            dataset = f"sql:table:{table}"
            add_node(dataset, "sql_table")
            add_edge(dataset, query_id, "reads")
        for table in sorted(set(create_re.findall(text))):
            dataset = f"sql:table:{table}"
            add_node(dataset, "sql_table")
            add_edge(query_id, dataset, "writes")


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _keyword_or_first_string(node: ast.Call, keyword: str, *, allow_first_arg: bool) -> str | None:
    for kw in node.keywords:
        if (
            kw.arg == keyword
            and isinstance(kw.value, ast.Constant)
            and isinstance(kw.value.value, str)
        ):
            return kw.value.value
    if (
        allow_first_arg
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ):
        return node.args[0].value
    return None
