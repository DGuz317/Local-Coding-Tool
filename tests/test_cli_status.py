from __future__ import annotations

import json
import sqlite3

from typer.testing import CliRunner

from repolens.cli import app

runner = CliRunner()


def test_status_reports_missing_graph_in_text_without_mutating_repo(tmp_path):
    result = runner.invoke(app, ["status", str(tmp_path)])

    assert result.exit_code == 0
    assert "Graph status: stale" in result.output
    assert "Reason: missing graph artifacts" in result.output
    assert "Recommended action: repolens index" in result.output
    assert ".repolens/graph.sqlite" in result.output
    assert not (tmp_path / ".repolens").exists()


def test_status_reports_missing_graph_as_json_envelope(tmp_path):
    result = runner.invoke(app, ["status", str(tmp_path), "--json"])

    assert result.exit_code == 0
    envelope = json.loads(result.output)

    assert envelope["ok"] is True
    assert envelope["data"]["status"] == "stale"
    assert envelope["data"]["reason"] == "missing_graph_artifacts"
    assert envelope["data"]["fresh"] is False
    assert envelope["data"]["artifact_dir"] == ".repolens"
    assert ".repolens/graph.sqlite" in envelope["data"]["missing_artifacts"]
    assert envelope["data"]["recommended_action"].startswith("repolens index ")
    assert envelope["warnings"] == ["Graph artifacts are missing."]
    assert envelope["limits"] == {}
    assert not (tmp_path / ".repolens").exists()


def test_status_reports_existing_graph_artifacts_after_index(tmp_path):
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    index_result = runner.invoke(app, ["index", str(tmp_path)])
    assert index_result.exit_code == 0

    result = runner.invoke(app, ["status", str(tmp_path), "--json"])

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    assert envelope["ok"] is True
    assert envelope["data"]["status"] == "available"
    assert envelope["data"]["reason"] == "graph_current"
    assert envelope["data"]["fresh"] is True
    assert envelope["data"]["missing_artifacts"] == []
    assert envelope["data"]["recommended_action"] is None
    assert envelope["data"]["detected_schema_version"] == "15"
    assert envelope["data"]["freshness"]["changed_files"] == []
    assert all(warning.startswith("parser_backend:") for warning in envelope["warnings"])


def test_status_reports_unsupported_schema_version_when_detectable(tmp_path):
    artifact_dir = tmp_path / ".repolens"
    artifact_dir.mkdir()
    with sqlite3.connect(artifact_dir / "graph.sqlite") as connection:
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO metadata(key, value) VALUES ('schema_version', '999')")
    for artifact in (
        "graph.json",
        "graph-lite.json",
        "graph-report.md",
        "graph-index.md",
        "graph-status.json",
    ):
        (artifact_dir / artifact).write_text("{}\n", encoding="utf-8")

    result = runner.invoke(app, ["status", str(tmp_path), "--json"])

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    assert envelope["ok"] is True
    assert envelope["data"]["status"] == "rebuild_required"
    assert envelope["data"]["reason"] == "unsupported_schema_version"
    assert envelope["data"]["fresh"] is False
    assert envelope["data"]["missing_artifacts"] == []
    assert envelope["data"]["detected_schema_version"] == "999"
    assert envelope["data"]["supported_schema_version"] == 15
    assert envelope["data"]["recommended_action"].startswith("repolens index ")
    assert envelope["warnings"] == ["Graph schema version is unsupported. Rebuild required."]
