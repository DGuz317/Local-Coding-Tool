from __future__ import annotations

import json
import sqlite3

from typer.testing import CliRunner

from repolens.cli import app
from repolens.context_pack import get_task_context
from repolens.indexer import index_repository
from repolens.semantic_artifact import SEMANTIC_STORE_PATH, inspect_semantic_artifact

runner = CliRunner()


def test_experimental_semantic_artifact_records_source_free_metadata(tmp_path):
    (tmp_path / "app.py").write_text(
        "def run():\n    return 'do-not-disclose-source'\n",
        encoding="utf-8",
    )

    result = index_repository(tmp_path, experimental_semantic_artifact=True)

    assert result.semantic_artifact == SEMANTIC_STORE_PATH
    assert (tmp_path / ".repolens" / "semantic.sqlite").is_file()
    with sqlite3.connect(tmp_path / ".repolens" / "semantic.sqlite") as connection:
        connection.row_factory = sqlite3.Row
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        rows = list(
            connection.execute(
                """
                SELECT
                    source_path,
                    source_language,
                    semantic_backend,
                    parser_backend,
                    provenance_json,
                    confidence,
                    evidence_labels_json,
                    experimental_status
                FROM semantic_sources
                """
            )
        )

    assert metadata["schema_version"] == "1"
    assert metadata["semantic_backend"] == "semantic_skeleton"
    assert metadata["parser_backend"] == "tree_sitter_js_ts"
    assert metadata["experimental_status"] == "experimental"
    assert len(rows) == 1
    row = rows[0]
    assert row["source_path"] == "app.py"
    assert row["source_language"] == "python"
    assert row["semantic_backend"] == "semantic_skeleton"
    assert row["parser_backend"] == "tree_sitter_js_ts"
    assert json.loads(row["provenance_json"])["semantic_backend"] == "semantic_skeleton"
    assert row["confidence"] == "candidate"
    assert json.loads(row["evidence_labels_json"]) == [
        "scanner:eligible_file",
        "semantic:skeleton",
    ]
    assert row["experimental_status"] == "experimental"
    assert (
        b"do-not-disclose-source" not in (tmp_path / ".repolens" / "semantic.sqlite").read_bytes()
    )


def test_experimental_semantic_artifact_excluded_from_stable_identity(tmp_path):
    (tmp_path / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")

    index_repository(tmp_path)
    stable_hash = _canonical_graph_hash(tmp_path)
    stable_pack_id = get_task_context(tmp_path, "change run")["data"]["context_pack_id"]

    index_repository(tmp_path, experimental_semantic_artifact=True)

    assert _canonical_graph_hash(tmp_path) == stable_hash
    assert get_task_context(tmp_path, "change run")["data"]["context_pack_id"] == stable_pack_id
    graph_payload = (tmp_path / ".repolens" / "graph.json").read_text(encoding="utf-8")
    assert "semantic_skeleton" not in graph_payload
    assert "semantic:skeleton" not in graph_payload


def test_semantic_artifact_status_reports_missing_present_stale_and_unsupported(tmp_path):
    (tmp_path / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")

    assert inspect_semantic_artifact(tmp_path).status == "missing"

    index_repository(tmp_path, experimental_semantic_artifact=True)
    present = inspect_semantic_artifact(tmp_path)
    assert present.status == "present"
    assert present.reason == "semantic_artifact_current"

    (tmp_path / "app.py").write_text("def run():\n    return 100\n", encoding="utf-8")
    stale = inspect_semantic_artifact(tmp_path)
    assert stale.status == "stale"
    assert stale.reason == "semantic_source_fingerprint_changed"

    with sqlite3.connect(tmp_path / ".repolens" / "semantic.sqlite") as connection:
        connection.execute("UPDATE metadata SET value = '999' WHERE key = 'schema_version'")

    unsupported = inspect_semantic_artifact(tmp_path)
    assert unsupported.status == "unsupported"
    assert unsupported.reason == "semantic_schema_version_unsupported"
    assert unsupported.detected_schema_version == "999"


def test_cli_can_enable_semantic_artifact_and_status_reports_it(tmp_path):
    (tmp_path / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")

    result = runner.invoke(
        app, ["index", str(tmp_path), "--experimental-semantic-artifact", "--json"]
    )

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    assert envelope["data"]["semantic_artifact"] == ".repolens/semantic.sqlite"

    status_result = runner.invoke(app, ["status", str(tmp_path), "--json"])

    assert status_result.exit_code == 0
    status_envelope = json.loads(status_result.output)
    assert status_envelope["data"]["semantic_artifact"]["status"] == "present"


def _canonical_graph_hash(root) -> str:
    with sqlite3.connect(root / ".repolens" / "graph.sqlite") as connection:
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'canonical_graph_hash'"
        ).fetchone()
    assert row is not None
    return str(row[0])
