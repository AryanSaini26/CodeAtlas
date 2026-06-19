"""Tests for static data-lineage extraction."""

import json
from pathlib import Path

from codeatlas.data_lineage import (
    build_lineage_graph,
    export_openlineage,
    lineage_impact,
    render_lineage_text,
)


def test_build_lineage_graph_from_dbt_manifest_sql_and_airflow(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "manifest.json").write_text(
        json.dumps(
            {
                "nodes": {
                    "model.demo.orders": {
                        "name": "orders",
                        "resource_type": "model",
                        "depends_on": {"nodes": ["source.demo.raw_orders"]},
                        "original_file_path": "models/orders.sql",
                    }
                },
                "sources": {
                    "source.demo.raw_orders": {
                        "name": "raw_orders",
                        "resource_type": "source",
                    }
                },
                "exposures": {
                    "exposure.demo.dashboard": {
                        "name": "revenue_dashboard",
                        "resource_type": "exposure",
                        "depends_on": {"nodes": ["model.demo.orders"]},
                    }
                },
            }
        )
    )
    (tmp_path / "query.sql").write_text("create table mart.orders as select * from raw.orders")
    (tmp_path / "dag.py").write_text(
        "from airflow import DAG\n"
        "with DAG('daily_orders') as dag:\n"
        "    extract = object(task_id='extract_orders')\n"
    )

    graph = build_lineage_graph(tmp_path)
    node_ids = {node["id"] for node in graph["nodes"]}
    assert "dbt:model:orders" in node_ids
    assert "dbt:source:raw_orders" in node_ids
    assert "airflow:dag:daily_orders" in node_ids
    assert "sql:table:mart.orders" in node_ids
    assert graph["edge_count"] >= 3
    assert "dbt:model:orders" in lineage_impact(graph, "raw_orders")["downstream"]
    assert "CodeAtlas Data Lineage" in render_lineage_text(graph)


def test_export_openlineage_has_events(tmp_path: Path) -> None:
    (tmp_path / "query.sql").write_text("create table analytics.users as select * from raw.users")
    graph = build_lineage_graph(tmp_path)
    payload = export_openlineage(graph)
    assert payload["producer"] == "codeatlas"
    assert payload["events"]
    assert payload["events"][0]["eventType"] == "JOB"
