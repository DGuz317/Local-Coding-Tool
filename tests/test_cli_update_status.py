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
    assert second_envelope["data"]["mode"] == "selective"
    assert second_envelope["data"]["initialized"] is False
    assert second_envelope["data"]["freshness"]["change_counts"]["structural_change"] == 1
    assert second_envelope["data"]["selective_update"]["safe"] is True
    assert second_envelope["data"]["selective_update"]["reparse_paths"] == ["app.py"]
    assert second_envelope["data"]["selective_update"]["stale_cleanup_paths"] == []

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
    assert envelope["data"]["selective_update"]["parse_error_paths"] == ["broken.py"]
    assert envelope["data"]["selective_update"]["stale_cleanup_paths"] == ["broken.py"]
    assert envelope["warnings"] == ["Parser errors detected in the live graph overlay."]

    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        symbol_count = connection.execute(
            "SELECT COUNT(*) FROM python_symbols WHERE path = 'broken.py'"
        ).fetchone()[0]
        parse_error_count = connection.execute(
            "SELECT COUNT(*) FROM python_parse_errors WHERE path = 'broken.py'"
        ).fetchone()[0]

    assert symbol_count == 0
    assert parse_error_count == 1


def test_update_removes_stale_config_facts_when_config_becomes_unparseable(tmp_path):
    _write_text(
        tmp_path / "package.json",
        r"""
        {
          "name": "web-app",
          "dependencies": {"react": "^19.0.0"},
          "scripts": {"test": "vitest --run"}
        }
        """,
    )
    index_result = runner.invoke(app, ["index", str(tmp_path)])
    assert index_result.exit_code == 0

    _write_text(tmp_path / "package.json", "{not-json\n")
    result = runner.invoke(app, ["update", str(tmp_path), "--json"])

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    assert envelope["data"]["freshness"]["change_counts"]["parse_error"] == 1
    assert envelope["data"]["selective_update"]["parse_error_paths"] == ["package.json"]
    assert envelope["data"]["selective_update"]["stale_cleanup_paths"] == ["package.json"]

    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        config_status = connection.execute(
            "SELECT parser_status FROM config_files WHERE path = 'package.json'"
        ).fetchone()
        package_count = connection.execute(
            "SELECT COUNT(*) FROM config_packages WHERE source_path = 'package.json'"
        ).fetchone()[0]
        command_count = connection.execute(
            "SELECT COUNT(*) FROM config_commands WHERE path = 'package.json'"
        ).fetchone()[0]
        parse_error_count = connection.execute(
            "SELECT COUNT(*) FROM config_parse_errors WHERE path = 'package.json'"
        ).fetchone()[0]

    assert config_status == ("parse_error",)
    assert package_count == 0
    assert command_count == 0
    assert parse_error_count == 1


def test_update_plan_classifies_new_deleted_skipped_and_reused_files(tmp_path):
    _write_text(tmp_path / "changed.py", "def old():\n    return 1\n")
    _write_text(tmp_path / "deleted.py", "def gone():\n    return 1\n")
    _write_text(tmp_path / "same.py", "def same():\n    return 1\n")
    index_result = runner.invoke(app, ["index", str(tmp_path)])
    assert index_result.exit_code == 0

    _write_text(tmp_path / "changed.py", "def new():\n    return 1\n")
    (tmp_path / "deleted.py").unlink()
    _write_text(tmp_path / "new.py", "def created():\n    return 1\n")
    _write_text(tmp_path / ".env", "TOKEN=secret\n")

    result = runner.invoke(app, ["update", str(tmp_path), "--json"])

    assert result.exit_code == 0
    plan = json.loads(result.output)["data"]["selective_update"]
    assert plan["safe"] is True
    assert plan["changed_paths"] == ["changed.py", "deleted.py", "new.py"]
    assert plan["new_paths"] == ["new.py"]
    assert plan["deleted_paths"] == ["deleted.py"]
    assert plan["reused_paths"] == ["same.py"]
    assert plan["reparse_paths"] == ["changed.py", "new.py"]
    assert plan["stale_cleanup_paths"] == ["deleted.py"]
    assert plan["skipped_paths"] == [".env"]

    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        deleted_file_count = connection.execute(
            "SELECT COUNT(*) FROM files WHERE path = 'deleted.py'"
        ).fetchone()[0]
        deleted_symbol_count = connection.execute(
            "SELECT COUNT(*) FROM python_symbols WHERE path = 'deleted.py'"
        ).fetchone()[0]

    assert deleted_file_count == 0
    assert deleted_symbol_count == 0


def test_update_falls_back_to_full_rebuild_when_selective_update_is_unsafe(tmp_path):
    _write_text(tmp_path / "app.py", "def app():\n    return 1\n")
    index_result = runner.invoke(app, ["index", str(tmp_path)])
    assert index_result.exit_code == 0

    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        connection.execute("UPDATE metadata SET value = '0' WHERE key = 'schema_version'")

    result = runner.invoke(app, ["update", str(tmp_path), "--json"])

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    assert envelope["data"]["mode"] == "full_rebuild"
    assert envelope["data"]["selective_update"]["safe"] is False
    assert envelope["data"]["selective_update"]["reason"] == "unsupported_schema_version"

    status_result = runner.invoke(app, ["status", str(tmp_path), "--json"])
    assert status_result.exit_code == 0
    assert json.loads(status_result.output)["data"]["fresh"] is True


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

    update_result = runner.invoke(app, ["update", str(tmp_path), "--json"])

    assert update_result.exit_code == 0
    update_envelope = json.loads(update_result.output)
    assert update_envelope["data"]["mode"] == "full_rebuild"
    assert update_envelope["data"]["selective_update"]["safe"] is False
    assert update_envelope["data"]["selective_update"]["reason"] == "effective_config_changed"


def _write_text(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        dedent(content).lstrip() if content.startswith("\n") else content, encoding="utf-8"
    )
