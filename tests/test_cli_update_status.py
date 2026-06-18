from __future__ import annotations

import json
import sqlite3
from textwrap import dedent

from typer.testing import CliRunner

from repolens.cli import app

runner = CliRunner()


def test_status_detects_blank_line_shift_without_mutating_artifacts(tmp_path):
    _write_text(
        tmp_path / "app.py",
        "import os\n\ndef run():\n    return os.getcwd()\n",
    )
    index_result = runner.invoke(app, ["index", str(tmp_path)])
    assert index_result.exit_code == 0
    before_status_export = (tmp_path / ".repolens" / "graph-status.json").read_text(
        encoding="utf-8"
    )

    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        stored_hashes = connection.execute(
            """
            SELECT raw_hash, normalized_hash, graph_hash, dependency_hash, symbol_hash, line_range_hash
            FROM files
            WHERE path = 'app.py'
            """
        ).fetchone()

    _write_text(
        tmp_path / "app.py",
        "import os\n\n\ndef run():\n    return os.getcwd()\n",
    )

    result = runner.invoke(app, ["status", str(tmp_path), "--json"])

    assert result.exit_code == 0
    assert (tmp_path / ".repolens" / "graph-status.json").read_text(
        encoding="utf-8"
    ) == before_status_export
    envelope = json.loads(result.output)
    freshness = envelope["data"]["freshness"]
    files = {file["path"]: file for file in freshness["files"]}
    app_change = files["app.py"]

    assert envelope["data"]["status"] == "stale"
    assert envelope["data"]["reason"] == "file_changes_detected"
    assert freshness["fresh"] is False
    assert freshness["change_counts"]["content_only_change"] == 1
    assert app_change["change_type"] == "content_only_change"
    assert app_change["hashes"]["raw"]["old"] == stored_hashes[0]
    assert app_change["hashes"]["normalized"]["old"] == stored_hashes[1]
    assert app_change["hashes"]["graph"]["old"] == stored_hashes[2]
    assert (
        app_change["hashes"]["normalized"]["old"] == app_change["hashes"]["normalized"]["current"]
    )
    assert app_change["hashes"]["graph"]["old"] == app_change["hashes"]["graph"]["current"]
    assert app_change["hashes"]["dependency"]["old"] == stored_hashes[3]
    assert app_change["hashes"]["symbol"]["old"] == stored_hashes[4]
    assert app_change["hashes"]["line_range"]["old"] == stored_hashes[5]
    assert app_change["secondary_signals"] == {
        "dependency_changed": False,
        "graph_changed": False,
        "line_range_changed": True,
        "normalized_content_changed": False,
        "raw_content_changed": True,
        "symbol_changed": False,
    }


def test_status_classifies_primary_file_changes(tmp_path):
    _write_text(tmp_path / "dep.py", "import os\n\nVALUE = 1\n")
    _write_text(tmp_path / "struct.py", "def old_name():\n    return 1\n")
    _write_text(tmp_path / "broken.py", "def ok():\n    return 1\n")
    _write_text(tmp_path / "deleted.py", "def gone():\n    return 1\n")
    _write_text(tmp_path / "same.py", "def same():\n    return 1\n")

    index_result = runner.invoke(app, ["index", str(tmp_path)])
    assert index_result.exit_code == 0

    _write_text(tmp_path / "dep.py", "import sys\n\nVALUE = 1\n")
    _write_text(tmp_path / "struct.py", "def new_name():\n    return 1\n")
    _write_text(tmp_path / "broken.py", "def broken(:\n    pass\n")
    (tmp_path / "deleted.py").unlink()
    _write_text(tmp_path / "new.py", "def created():\n    return 1\n")

    result = runner.invoke(app, ["status", str(tmp_path), "--json"])

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    changes = {file["path"]: file["change_type"] for file in envelope["data"]["freshness"]["files"]}
    assert changes["dep.py"] == "dependency_change"
    assert changes["struct.py"] == "structural_change"
    assert changes["broken.py"] == "parse_error"
    assert changes["deleted.py"] == "deleted"
    assert changes["new.py"] == "new"
    assert changes["same.py"] == "no_change"
    assert envelope["warnings"] == ["Parser errors detected in the live graph overlay."]


def test_update_bootstraps_missing_graph_and_records_latest_changes(tmp_path):
    _write_text(tmp_path / "app.py", "def app():\n    return 1\n")

    first_result = runner.invoke(app, ["update", str(tmp_path), "--json"])

    assert first_result.exit_code == 0
    first_envelope = json.loads(first_result.output)
    assert first_envelope["data"]["mode"] == "initialized"
    assert first_envelope["data"]["initialized"] is True
    assert (tmp_path / ".repolens" / "graph.sqlite").exists()

    _write_text(tmp_path / "app.py", "def renamed():\n    return 1\n")
    second_result = runner.invoke(app, ["update", str(tmp_path), "--json"])

    assert second_result.exit_code == 0
    second_envelope = json.loads(second_result.output)
    assert second_envelope["data"]["mode"] == "updated"
    assert second_envelope["data"]["initialized"] is False
    assert second_envelope["data"]["freshness"]["change_counts"]["structural_change"] == 1

    graph_status = json.loads(
        (tmp_path / ".repolens" / "graph-status.json").read_text(encoding="utf-8")
    )
    assert graph_status["freshness"]["fresh"] is True
    assert graph_status["freshness"]["status"] == "available"
    assert graph_status["changes"]["change_counts"]["structural_change"] == 1
    assert graph_status["changes"]["changed_files"] == [
        {
            "change_type": "structural_change",
            "path": "app.py",
            "secondary_signals": {
                "dependency_changed": False,
                "graph_changed": True,
                "line_range_changed": False,
                "normalized_content_changed": True,
                "raw_content_changed": True,
                "symbol_changed": True,
            },
        }
    ]

    status_result = runner.invoke(app, ["status", str(tmp_path), "--json"])
    assert status_result.exit_code == 0
    status_envelope = json.loads(status_result.output)
    assert status_envelope["data"]["fresh"] is True
    assert status_envelope["data"]["freshness"]["changed_files"] == []


def test_update_warns_about_parser_errors_without_failing(tmp_path):
    _write_text(tmp_path / "broken.py", "def ok():\n    return 1\n")
    index_result = runner.invoke(app, ["index", str(tmp_path)])
    assert index_result.exit_code == 0
    _write_text(tmp_path / "broken.py", "def broken(:\n    pass\n")

    result = runner.invoke(app, ["update", str(tmp_path), "--json"])

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    assert envelope["data"]["freshness"]["change_counts"]["parse_error"] == 1
    assert envelope["warnings"] == ["Parser errors detected in the live graph overlay."]


def test_status_detects_git_metadata_changes(tmp_path):
    _write_text(tmp_path / "app.py", "def app():\n    return 1\n")
    git_dir = tmp_path / ".git"
    (git_dir / "refs" / "heads").mkdir(parents=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git_dir / "refs" / "heads" / "main").write_text("a" * 40 + "\n", encoding="utf-8")
    index_result = runner.invoke(app, ["index", str(tmp_path)])
    assert index_result.exit_code == 0

    (git_dir / "refs" / "heads" / "main").write_text("b" * 40 + "\n", encoding="utf-8")
    result = runner.invoke(app, ["status", str(tmp_path), "--json"])

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    assert envelope["data"]["status"] == "stale"
    assert envelope["data"]["reason"] == "git_metadata_changed"
    assert envelope["data"]["freshness"]["git"]["indexed"]["commit"] == "a" * 40
    assert envelope["data"]["freshness"]["git"]["current"]["commit"] == "b" * 40


def test_status_requires_rebuild_for_extractor_or_config_hash_changes(tmp_path):
    _write_text(tmp_path / "app.py", "def app():\n    return 1\n")
    index_result = runner.invoke(app, ["index", str(tmp_path)])
    assert index_result.exit_code == 0

    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        current_metadata = dict(connection.execute("SELECT key, value FROM metadata ORDER BY key"))
        connection.execute(
            "UPDATE metadata SET value = 'old-extractor' WHERE key = 'exporter_version'"
        )

    extractor_result = runner.invoke(app, ["status", str(tmp_path), "--json"])

    assert extractor_result.exit_code == 0
    extractor_envelope = json.loads(extractor_result.output)
    assert extractor_envelope["data"]["status"] == "rebuild_required"
    assert extractor_envelope["data"]["reason"] == "extractor_version_changed"
    assert extractor_envelope["data"]["freshness"]["full_reparse_required"] is True

    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        connection.execute(
            "UPDATE metadata SET value = ? WHERE key = 'exporter_version'",
            (current_metadata["exporter_version"],),
        )
        connection.execute(
            "UPDATE metadata SET value = 'old-config' WHERE key = 'effective_config_hash'"
        )

    config_result = runner.invoke(app, ["status", str(tmp_path), "--json"])

    assert config_result.exit_code == 0
    config_envelope = json.loads(config_result.output)
    assert config_envelope["data"]["status"] == "rebuild_required"
    assert config_envelope["data"]["reason"] == "effective_config_changed"
    assert config_envelope["data"]["freshness"]["full_reparse_required"] is True


def _write_text(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        dedent(content).lstrip() if content.startswith("\n") else content, encoding="utf-8"
    )
