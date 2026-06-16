from __future__ import annotations

import json

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
