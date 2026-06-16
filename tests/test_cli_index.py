from __future__ import annotations

import json

from typer.testing import CliRunner

from repolens.cli import app
from repolens.indexer import ARTIFACT_GITIGNORE_CONTENT

runner = CliRunner()


def test_index_bootstraps_scan_artifacts_for_non_git_root(tmp_path):
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")

    result = runner.invoke(app, ["index", str(tmp_path)])

    assert result.exit_code == 0
    assert "Eligible files: 1" in result.output
    assert "Artifact directory: .repolens" in result.output
    assert "Scan summary: .repolens/scan.json" in result.output
    assert not (tmp_path / ".gitignore").exists()
    assert (tmp_path / ".repolens" / ".gitignore").read_text(
        encoding="utf-8"
    ) == ARTIFACT_GITIGNORE_CONTENT

    scan_artifact = json.loads((tmp_path / ".repolens" / "scan.json").read_text())
    assert scan_artifact["analysis_root"] == "."
    assert scan_artifact["files"] == [{"path": "app.py", "size_bytes": 12}]
    assert scan_artifact["skipped_paths"] == [
        {"path": ".repolens", "reason": "repolens_artifact_dir"}
    ]


def test_index_honors_gitignore_and_only_creates_repolens_for_git_root(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (tmp_path / "kept.py").write_text("print('kept')\n", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("print('ignored')\n", encoding="utf-8")
    before_children = {path.name for path in tmp_path.iterdir()}

    result = runner.invoke(app, ["index", str(tmp_path), "--json"])

    assert result.exit_code == 0
    assert {path.name for path in tmp_path.iterdir()} == before_children | {".repolens"}

    envelope = json.loads(result.output)
    assert envelope["ok"] is True
    assert envelope["data"]["artifact_dir"] == ".repolens"
    assert envelope["data"]["scan_artifact"] == ".repolens/scan.json"
    assert envelope["data"]["eligible_files"] == [
        {"path": ".gitignore", "size_bytes": 11},
        {"path": "kept.py", "size_bytes": 14},
    ]
    assert {item["path"]: item["reason"] for item in envelope["data"]["skipped_paths"]} == {
        ".git": "excluded_directory",
        ".repolens": "repolens_artifact_dir",
        "ignored.py": "gitignore",
    }


def test_index_reports_safe_error_when_artifact_dir_is_symlink(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".repolens").symlink_to(outside, target_is_directory=True)

    result = runner.invoke(app, ["index", str(tmp_path), "--json"])

    assert result.exit_code == 1
    envelope = json.loads(result.output)
    assert envelope["ok"] is False
    assert envelope["error"] == {"message": "artifact_dir_is_symlink"}
    assert not (outside / ".gitignore").exists()
