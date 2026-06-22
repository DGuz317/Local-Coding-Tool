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

    assert metadata["schema_version"] == "12"
    assert len(metadata["canonical_graph_hash"]) == 64
    assert {"confidence", "resolution_strategy", "evidence_json"} <= edge_columns
    assert len(import_edges) == 1

    edge = import_edges[0]
    assert (
        edge[0] == "edge:IMPORTS:javascript_module:src/app.ts->javascript_package:third_party:react"
    )
    assert edge[4] == "high"
    assert edge[5] == "external_import"
    evidence = json.loads(edge[6])
    assert sorted(item["line"] for item in evidence) == [1, 2]
    assert {item["specifier"] for item in evidence} == {"react"}
    assert all(item["kind"] == "javascript_import" for item in evidence)
    assert all(item["resolution_status"] == "external" for item in evidence)
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
    assert sorted(item["line"] for item in exported_edge["evidence"]) == [1, 2]
    assert {item["specifier"] for item in exported_edge["evidence"]} == {"react"}


def test_python_local_imports_resolve_to_unique_scanner_approved_modules(tmp_path):
    (tmp_path / "src" / "acme").mkdir(parents=True)
    (tmp_path / "acme").mkdir()
    (tmp_path / "src" / "acme" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "acme" / "helpers.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "src" / "acme" / "models.py").write_text(
        "class Model:\n    pass\n", encoding="utf-8"
    )
    (tmp_path / "src" / "acme" / "ambiguous.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "acme" / "ambiguous.py").write_text("VALUE = 2\n", encoding="utf-8")
    (tmp_path / "src" / "acme" / "service.py").write_text(
        "import acme.helpers\nfrom .models import Model\nimport acme.ambiguous\nimport requests\n",
        encoding="utf-8",
    )
    scan = scan_repository(tmp_path)

    build_graph_store(tmp_path, scan)
    export_graph_artifacts(tmp_path)

    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        import_edges = list(
            connection.execute(
                """
                SELECT target_id, confidence, resolution_strategy, evidence_json, metadata_json
                FROM edges
                WHERE source_id = 'python_module:src/acme/service.py'
                  AND kind = 'IMPORTS'
                ORDER BY target_id
                """
            )
        )

    module_edges = {edge[0]: edge for edge in import_edges if edge[0].startswith("python_module:")}
    assert set(module_edges) == {
        "python_module:src/acme/helpers.py",
        "python_module:src/acme/models.py",
    }
    helpers_edge = module_edges["python_module:src/acme/helpers.py"]
    models_edge = module_edges["python_module:src/acme/models.py"]
    assert helpers_edge[1] == "high"
    assert helpers_edge[2] == "local_import"
    helpers_evidence = json.loads(helpers_edge[3])
    assert helpers_evidence[0]["import_id"].startswith("python_import:src/acme/service.py:")
    assert helpers_evidence == [
        {
            "import_id": helpers_evidence[0]["import_id"],
            "imported_name": None,
            "kind": "python_import",
            "line": 1,
            "module": "acme.helpers",
            "resolved_path": "src/acme/helpers.py",
        }
    ]
    assert json.loads(helpers_edge[4])["resolved_path"] == "src/acme/helpers.py"
    assert models_edge[2] == "local_import"
    assert json.loads(models_edge[4])["resolved_path"] == "src/acme/models.py"
    assert not any(edge[0] == "python_module:src/acme/ambiguous.py" for edge in import_edges)
    assert not any(edge[0] == "python_module:acme/ambiguous.py" for edge in import_edges)
    assert not any(
        edge[0].startswith("python_module:") and "requests" in edge[0] for edge in import_edges
    )

    graph_json = json.loads((tmp_path / ".repolens" / "graph.json").read_text(encoding="utf-8"))
    assert any(
        edge["target_id"] == "python_module:src/acme/models.py"
        and edge["confidence"] == "high"
        and edge["resolution_strategy"] == "local_import"
        for edge in graph_json["edges"]
    )


def test_javascript_relative_import_edges_store_strategy_and_bounded_evidence(tmp_path):
    (tmp_path / "src" / "app").mkdir(parents=True)
    (tmp_path / "src" / "lib").mkdir(parents=True)
    (tmp_path / "src" / "lib" / "format.ts").write_text(
        "export const format = () => 'ok';\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "app" / "main.ts").write_text(
        "import { format } from '../lib/format';\nconst again = require('../lib/format');\n",
        encoding="utf-8",
    )
    scan = scan_repository(tmp_path)

    build_graph_store(tmp_path, scan)
    export_graph_artifacts(tmp_path)

    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        edge = connection.execute(
            """
            SELECT target_id, confidence, resolution_strategy, evidence_json, metadata_json
            FROM edges
            WHERE source_id = 'javascript_module:src/app/main.ts'
              AND kind = 'IMPORTS'
            """
        ).fetchone()

    assert edge[0] == "javascript_module:src/lib/format.ts"
    assert edge[1] == "high"
    assert edge[2] == "local_import"
    evidence = json.loads(edge[3])
    assert sorted(item["line"] for item in evidence) == [1, 2]
    assert {item["specifier"] for item in evidence} == {"../lib/format"}
    assert all(item["kind"] == "javascript_import" for item in evidence)
    assert all(item["resolution_status"] == "resolved_relative" for item in evidence)
    assert json.loads(edge[4])["resolved_path"] == "src/lib/format.ts"


def test_javascript_alias_import_edges_use_canonical_strategy(tmp_path):
    (tmp_path / "src" / "shared").mkdir(parents=True)
    (tmp_path / "tsconfig.json").write_text(
        '{"compilerOptions":{"paths":{"@/*":["src/*"]}}}\n',
        encoding="utf-8",
    )
    (tmp_path / "src" / "shared" / "format.ts").write_text(
        "export const format = () => 'ok';\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "main.ts").write_text(
        "import { format } from '@/shared/format';\n",
        encoding="utf-8",
    )
    scan = scan_repository(tmp_path)

    build_graph_store(tmp_path, scan)

    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        edge = connection.execute(
            """
            SELECT target_id, confidence, resolution_strategy, evidence_json, metadata_json
            FROM edges
            WHERE source_id = 'javascript_module:src/main.ts'
              AND kind = 'IMPORTS'
            """
        ).fetchone()

    assert edge[0] == "javascript_module:src/shared/format.ts"
    assert edge[1] == "medium"
    assert edge[2] == "path_alias_import"
    evidence = json.loads(edge[3])
    assert evidence[0]["resolution_status"] == "resolved_alias"
    assert json.loads(edge[4])["resolved_path"] == "src/shared/format.ts"


def test_graph_store_exports_redacted_config_metadata_and_commands(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"name":"token-tools","scripts":{"test":"TOKEN=abc vitest --token xyz"},'
        '"token":"should-not-leak","dependencies":{"secret-sauce":"^1.0.0"}}\n',
        encoding="utf-8",
    )
    scan = scan_repository(tmp_path)

    build_graph_store(tmp_path, scan)
    export_graph_artifacts(tmp_path)

    graph_json = json.loads((tmp_path / ".repolens" / "graph.json").read_text(encoding="utf-8"))
    output = json.dumps(graph_json, sort_keys=True)

    assert "should-not-leak" not in output
    assert "TOKEN=<redacted> vitest --token <redacted>" in output
    assert "token-tools" in output
    assert "secret-sauce" in output


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
