from __future__ import annotations

import json
import sqlite3

from typer.testing import CliRunner

from repolens.cli import app
from repolens.indexer import ARTIFACT_GITIGNORE_CONTENT

runner = CliRunner()

GRAPH_ARTIFACTS = (
    "graph.sqlite",
    "graph.json",
    "graph-lite.json",
    "graph-report.md",
    "graph-index.md",
    "graph-status.json",
)


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


def test_index_creates_graph_store_and_exports(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")

    result = runner.invoke(app, ["index", str(tmp_path)])

    assert result.exit_code == 0
    assert "Graph store: .repolens/graph.sqlite" in result.output
    for artifact in GRAPH_ARTIFACTS:
        assert (tmp_path / ".repolens" / artifact).exists(), artifact


def test_graph_sqlite_contains_schema_and_minimum_facts(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (tmp_path / ".env").write_text("TOKEN=secret\n", encoding="utf-8")

    result = runner.invoke(app, ["index", str(tmp_path)])

    assert result.exit_code == 0

    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        metadata = dict(connection.execute("SELECT key, value FROM metadata ORDER BY key"))
        repositories = list(
            connection.execute("SELECT id, analysis_root, name FROM repositories ORDER BY id")
        )
        directories = list(
            connection.execute("SELECT path, node_id, parent_path FROM directories ORDER BY path")
        )
        files = list(
            connection.execute("SELECT path, directory_path, size_bytes FROM files ORDER BY path")
        )
        skipped_paths = dict(
            connection.execute("SELECT path, reason FROM skipped_paths ORDER BY path")
        )
        run = connection.execute(
            """
            SELECT file_count, directory_count, skipped_path_count, scan_policy_version
            FROM runs
            WHERE id = 1
            """
        ).fetchone()

    assert metadata["schema_name"] == "repolens_graph"
    assert metadata["schema_version"] == "1"
    assert repositories == [("repository:.", ".", tmp_path.name)]
    assert directories == [
        (".", "directory:.", None),
        ("docs", "directory:docs", "."),
        ("src", "directory:src", "."),
    ]
    assert files == [
        ("docs/guide.md", "docs", 8),
        ("src/app.py", "src", 12),
    ]
    assert skipped_paths[".env"] == "secret_path"
    assert skipped_paths[".repolens"] == "repolens_artifact_dir"
    assert run == (2, 3, 2, 1)


def test_index_exports_are_deterministic_except_allowed_run_timestamp(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Fixture\n", encoding="utf-8")

    first_result = runner.invoke(app, ["index", str(tmp_path)])
    assert first_result.exit_code == 0
    first_exports = _stable_export_content(tmp_path)

    second_result = runner.invoke(app, ["index", str(tmp_path)])
    assert second_result.exit_code == 0

    assert _stable_export_content(tmp_path) == first_exports


def test_graph_exports_do_not_mirror_source_code(tmp_path):
    source_body = "THIS_SOURCE_BODY_MUST_NOT_BE_MIRRORED"
    (tmp_path / "app.py").write_text(
        f"def app():\n    return {source_body!r}\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["index", str(tmp_path)])

    assert result.exit_code == 0
    for artifact in GRAPH_ARTIFACTS:
        artifact_text = (tmp_path / ".repolens" / artifact).read_text(
            encoding="utf-8", errors="ignore"
        )
        assert source_body not in artifact_text, artifact


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


def _stable_export_content(repo_path):
    artifact_dir = repo_path / ".repolens"
    return {
        "graph.json": _without_volatile_json_fields(artifact_dir / "graph.json"),
        "graph-lite.json": _without_volatile_json_fields(artifact_dir / "graph-lite.json"),
        "graph-report.md": _without_volatile_markdown_fields(artifact_dir / "graph-report.md"),
        "graph-index.md": _without_volatile_markdown_fields(artifact_dir / "graph-index.md"),
        "graph-status.json": _without_volatile_json_fields(artifact_dir / "graph-status.json"),
    }


def _without_volatile_json_fields(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return _remove_keys(data, {"indexed_at_utc"})


def _remove_keys(value, volatile_keys):
    if isinstance(value, dict):
        return {
            key: _remove_keys(child, volatile_keys)
            for key, child in value.items()
            if key not in volatile_keys
        }
    if isinstance(value, list):
        return [_remove_keys(child, volatile_keys) for child in value]
    return value


def _without_volatile_markdown_fields(path):
    return "\n".join(
        "Indexed at UTC: <volatile>" if line.startswith("Indexed at UTC:") else line
        for line in path.read_text(encoding="utf-8").splitlines()
    )
