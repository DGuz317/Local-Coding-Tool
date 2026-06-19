from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from repolens.graph import (
    GraphExportError,
    GraphStoreError,
    build_graph_store,
    export_graph_artifacts,
)
from repolens.scanner import scan_repository


def test_edges_store_contract_and_merge_duplicate_import_evidence(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.ts").write_text(
        "import React from 'react';\nimport { useState } from 'react';\n",
        encoding="utf-8",
    )
    scan = scan_repository(tmp_path)

    build_graph_store(tmp_path, scan)
    export_graph_artifacts(tmp_path)

    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        metadata = dict(connection.execute("SELECT key, value FROM metadata ORDER BY key"))
        edge_columns = {row[1] for row in connection.execute("PRAGMA table_info(edges)")}
        import_edges = list(
            connection.execute(
                """
                SELECT
                    id,
                    source_id,
                    target_id,
                    kind,
                    confidence,
                    resolution_strategy,
                    evidence_json,
                    metadata_json
                FROM edges
                WHERE source_id = 'javascript_module:src/app.ts'
                  AND target_id = 'javascript_package:third_party:react'
                  AND kind = 'IMPORTS'
                """
            )
        )

    assert metadata["schema_version"] == "10"
    assert len(metadata["canonical_graph_hash"]) == 64
    assert {"confidence", "resolution_strategy", "evidence_json"} <= edge_columns
    assert len(import_edges) == 1

    edge = import_edges[0]
    assert (
        edge[0] == "edge:IMPORTS:javascript_module:src/app.ts->javascript_package:third_party:react"
    )
    assert edge[4] == "high"
    assert edge[5] == "external_import"
    assert json.loads(edge[6]) == [
        {"kind": "line", "line": 1},
        {"kind": "line", "line": 2},
    ]
    assert json.loads(edge[7])["lines"] == [1, 2]

    graph_json = json.loads((tmp_path / ".repolens" / "graph.json").read_text(encoding="utf-8"))
    exported_edge = next(
        edge
        for edge in graph_json["edges"]
        if edge["id"]
        == "edge:IMPORTS:javascript_module:src/app.ts->javascript_package:third_party:react"
    )
    assert exported_edge["confidence"] == "high"
    assert exported_edge["resolution_strategy"] == "external_import"
    assert exported_edge["evidence"] == [
        {"kind": "line", "line": 1},
        {"kind": "line", "line": 2},
    ]


def test_graph_store_rebuild_leaves_existing_database_when_replace_fails(tmp_path, monkeypatch):
    (tmp_path / ".repolens").mkdir()
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    scan = scan_repository(tmp_path)
    build_graph_store(tmp_path, scan)
    graph_store = tmp_path / ".repolens" / "graph.sqlite"
    original_store = graph_store.read_bytes()
    real_replace = os.replace

    def fail_graph_store_replace(source, target):
        if Path(target).name == "graph.sqlite":
            raise OSError("simulated replace failure")
        real_replace(source, target)

    monkeypatch.setattr("repolens.graph.os.replace", fail_graph_store_replace)

    with pytest.raises(GraphStoreError, match="graph_store_rebuild_failed"):
        build_graph_store(tmp_path, scan)

    assert graph_store.read_bytes() == original_store


def test_graph_export_leaves_existing_artifact_when_replace_fails(tmp_path, monkeypatch):
    (tmp_path / ".repolens").mkdir()
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    scan = scan_repository(tmp_path)
    build_graph_store(tmp_path, scan)
    export_graph_artifacts(tmp_path)
    graph_export = tmp_path / ".repolens" / "graph.json"
    original_export = graph_export.read_text(encoding="utf-8")
    real_replace = os.replace

    def fail_graph_json_replace(source, target):
        if Path(target).name == "graph.json":
            raise OSError("simulated replace failure")
        real_replace(source, target)

    monkeypatch.setattr("repolens.graph.os.replace", fail_graph_json_replace)

    with pytest.raises(GraphExportError, match="graph_export_write_failed"):
        export_graph_artifacts(tmp_path)

    assert graph_export.read_text(encoding="utf-8") == original_export
