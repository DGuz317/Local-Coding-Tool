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
    plan_selective_update,
)
from repolens.graph_store import GRAPH_STORE_PATH, SqliteGraphStore
from repolens.query import GraphQueryService
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

    assert metadata["schema_version"] == "16"
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
    assert all(item["outcome_class"] == "resolved_edge" for item in evidence)
    assert all(item["evidence_labels"] == ["javascript_import_specifier"] for item in evidence)
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


def test_javascript_call_chains_are_metadata_facts_not_call_edges(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "query.ts").write_text(
        "export function loadUsers() {\n  return db.select().from().where();\n}\n",
        encoding="utf-8",
    )
    scan = scan_repository(tmp_path)

    build_graph_store(tmp_path, scan)
    export_graph_artifacts(tmp_path)

    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        chain_rows = list(
            connection.execute(
                """
                SELECT path, receiver_shape, method_names_json, parser_evidence_labels_json
                FROM javascript_call_chains
                ORDER BY path, start_line, id
                """
            )
        )
        call_edges = list(connection.execute("SELECT id FROM edges WHERE kind = 'CALLS'"))

    assert len(chain_rows) == 1
    assert chain_rows[0][0] == "src/query.ts"
    assert chain_rows[0][1] == "identifier"
    assert json.loads(chain_rows[0][2]) == ["select", "from", "where"]
    assert json.loads(chain_rows[0][3]) == [
        "line_local_member_call_sequence",
        "source_free_shape",
    ]
    assert call_edges == []

    graph_json = json.loads((tmp_path / ".repolens" / "graph.json").read_text(encoding="utf-8"))
    assert graph_json["counts"]["javascript_call_chains"] == 1
    assert graph_json["javascript"]["call_chains"][0]["method_names"] == [
        "select",
        "from",
        "where",
    ]
    assert "db.select" not in json.dumps(graph_json, sort_keys=True)

    metadata = GraphQueryService(tmp_path).context_pack_file_metadata(["src/query.ts"])
    chains = metadata["data"]["structural_summaries"]["src/query.ts"]["call_chains"]
    assert chains == [
        {
            "evidence": [
                {
                    "line_range": {"end": 2, "start": 2},
                    "source": "javascript_call_chains",
                }
            ],
            "line_range": {"end": 2, "start": 2},
            "method_names": ["select", "from", "where"],
            "parser_evidence_labels": [
                "line_local_member_call_sequence",
                "source_free_shape",
            ],
            "receiver_shape": "identifier",
        }
    ]


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


def test_ambiguous_workspace_package_imports_create_candidates_not_edges(tmp_path):
    (tmp_path / "packages" / "app" / "src").mkdir(parents=True)
    (tmp_path / "packages" / "shared-a" / "src").mkdir(parents=True)
    (tmp_path / "packages" / "shared-b" / "src").mkdir(parents=True)
    (tmp_path / "package.json").write_text(
        '{"name":"repo","workspaces":["packages/*"]}\n', encoding="utf-8"
    )
    (tmp_path / "packages" / "app" / "package.json").write_text(
        '{"name":"app","dependencies":{"@acme/shared":"workspace:*"}}\n',
        encoding="utf-8",
    )
    (tmp_path / "packages" / "shared-a" / "package.json").write_text(
        '{"name":"@acme/shared","main":"src/index.ts"}\n', encoding="utf-8"
    )
    (tmp_path / "packages" / "shared-b" / "package.json").write_text(
        '{"name":"@acme/shared","main":"src/index.ts"}\n', encoding="utf-8"
    )
    (tmp_path / "packages" / "app" / "src" / "index.ts").write_text(
        "import { shared } from '@acme/shared';\n", encoding="utf-8"
    )
    (tmp_path / "packages" / "shared-a" / "src" / "index.ts").write_text(
        "export const shared = 'a';\n", encoding="utf-8"
    )
    (tmp_path / "packages" / "shared-b" / "src" / "index.ts").write_text(
        "export const shared = 'b';\n", encoding="utf-8"
    )

    build_graph_store(tmp_path, scan_repository(tmp_path))
    export_graph_artifacts(tmp_path)

    source_id = "javascript_module:packages/app/src/index.ts"
    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        connection.row_factory = sqlite3.Row
        import_edges = list(
            connection.execute(
                """
                SELECT target_id
                FROM edges
                WHERE source_id = ?
                  AND kind = 'IMPORTS'
                ORDER BY target_id
                """,
                (source_id,),
            )
        )
        candidates = list(
            connection.execute(
                """
                SELECT
                    target_id,
                    outcome_class,
                    confidence,
                    resolution_strategy,
                    evidence_label,
                    evidence_json,
                    metadata_json
                FROM relationship_candidates
                WHERE source_id = ?
                  AND kind = 'IMPORTS'
                ORDER BY target_id
                """,
                (source_id,),
            )
        )
        warnings = json.loads(
            connection.execute(
                "SELECT value FROM metadata WHERE key = 'graph_quality_warnings'"
            ).fetchone()[0]
        )

    assert import_edges == []
    assert [candidate["outcome_class"] for candidate in candidates] == [
        "relationship_candidate",
        "relationship_candidate",
    ]
    assert {candidate["target_id"] for candidate in candidates} == {
        "config_package_root:javascript:@acme/shared:packages/shared-a",
        "config_package_root:javascript:@acme/shared:packages/shared-b",
    }
    assert {candidate["confidence"] for candidate in candidates} == {"low"}
    assert {candidate["resolution_strategy"] for candidate in candidates} == {
        "workspace_package_import"
    }
    assert {candidate["evidence_label"] for candidate in candidates} == {
        "package_manifest_identity"
    }
    assert all(
        {item["evidence_label"] for item in json.loads(candidate["evidence_json"])}
        >= {
            "javascript_import_specifier",
            "package_manifest_dependency",
            "package_manifest_identity",
            "workspace_declaration",
        }
        for candidate in candidates
    )
    assert all(
        json.loads(candidate["metadata_json"])["package_name"] == "@acme/shared"
        for candidate in candidates
    )
    assert "graph_quality:ambiguous_workspace_package_import:count=1" in warnings

    graph_json = json.loads((tmp_path / ".repolens" / "graph.json").read_text(encoding="utf-8"))
    assert graph_json["counts"]["relationship_candidates"] == 2
    assert len(graph_json["relationship_candidates"]) == 2


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
    assert all(item["outcome_class"] == "resolved_edge" for item in evidence)
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
    assert evidence[0]["evidence_labels"] == [
        "javascript_import_specifier",
        "typescript_path_alias",
    ]
    assert json.loads(edge[4])["resolved_path"] == "src/shared/format.ts"


def test_javascript_imports_persist_outcomes_candidates_and_warnings(tmp_path):
    (tmp_path / "src" / "lib").mkdir(parents=True)
    (tmp_path / "src" / "app").mkdir(parents=True)
    (tmp_path / "src" / "lib" / "ambiguous.ts").write_text("export const value = 1;\n")
    (tmp_path / "src" / "lib" / "ambiguous.tsx").write_text("export const value = 2;\n")
    (tmp_path / "src" / "app" / "main.ts").write_text(
        "import ambiguous from '../lib/ambiguous';\n",
        encoding="utf-8",
    )

    build_graph_store(tmp_path, scan_repository(tmp_path))
    export_graph_artifacts(tmp_path)

    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT outcome_class, evidence_labels_json, candidate_paths_json, resolution_status
            FROM javascript_imports
            WHERE specifier = '../lib/ambiguous'
            """
        ).fetchone()
        warnings = json.loads(
            connection.execute(
                "SELECT value FROM metadata WHERE key = 'graph_quality_warnings'"
            ).fetchone()[0]
        )

    assert row["outcome_class"] == "relationship_candidate"
    assert json.loads(row["evidence_labels_json"]) == ["javascript_import_specifier"]
    assert json.loads(row["candidate_paths_json"]) == [
        "src/lib/ambiguous.ts",
        "src/lib/ambiguous.tsx",
    ]
    assert row["resolution_status"] == "unresolved_ambiguous_relative"
    assert "graph_quality:javascript_unresolved_import_relationships:count=1" in warnings

    graph_json = json.loads((tmp_path / ".repolens" / "graph.json").read_text(encoding="utf-8"))
    [import_fact] = graph_json["javascript"]["imports"]
    assert import_fact["outcome_class"] == "relationship_candidate"
    assert import_fact["candidate_paths"] == [
        "src/lib/ambiguous.ts",
        "src/lib/ambiguous.tsx",
    ]


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


def test_sqlite_graph_store_replaces_artifacts_through_seam(tmp_path):
    (tmp_path / "app.py").write_text("def first():\n    return 1\n", encoding="utf-8")
    graph_store = SqliteGraphStore(tmp_path)

    graph_store.rebuild(scan_repository(tmp_path))
    graph_store.export_artifacts()
    original_store = (tmp_path / GRAPH_STORE_PATH).read_bytes()

    (tmp_path / "app.py").write_text("def second():\n    return 2\n", encoding="utf-8")
    previous_status = graph_store.inspect()
    scan = scan_repository(tmp_path)
    plan = plan_selective_update(previous_status, scan)

    exports = graph_store.replace_selectively(
        scan,
        plan,
        file_changes=previous_status.file_changes,
    )

    assert graph_store.graph_store_path == ".repolens/graph.sqlite"
    assert exports == graph_store.graph_export_paths
    assert (tmp_path / GRAPH_STORE_PATH).read_bytes() != original_store
    assert GraphQueryService(tmp_path, graph_store=graph_store).search_graph("second")["ok"] is True
