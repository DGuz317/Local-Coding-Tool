from __future__ import annotations

import json
import sqlite3
from textwrap import dedent

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
    assert metadata["schema_version"] == "3"
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


def test_index_writes_python_facts_to_sqlite_and_exports(tmp_path):
    _write_text(tmp_path / "pyproject.toml", '[project]\nname = "acme"\n')
    _write_text(tmp_path / "src" / "acme" / "__init__.py", "")
    _write_text(
        tmp_path / "src" / "acme" / "service.py",
        dedent(
            '''
            """Service module. Extra details are not exported as a full docstring."""

            import os
            import requests
            from acme import models
            from .helpers import helper as imported_helper

            # TODO: replace fixture service
            @registry.register
            class Child(Base):
                """Child handles work. Extra class details."""

                @classmethod
                def build(cls):
                    return helper()

            @decorated
            def helper():
                return Child()

            async def async_worker():
                helper()

            def caller():
                # SECURITY: keep permission checks
                helper()
                Child()
                os.getcwd()
            '''
        ).lstrip(),
    )

    result = runner.invoke(app, ["index", str(tmp_path)])

    assert result.exit_code == 0
    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        modules = list(
            connection.execute(
                """
                SELECT path, module_name, parser_status, docstring_summary
                FROM python_modules
                ORDER BY path
                """
            )
        )
        symbols = list(
            connection.execute(
                """
                SELECT kind, qualified_name, decorators_json, bases_json, docstring_summary
                FROM python_symbols
                WHERE path = 'src/acme/service.py'
                ORDER BY qualified_name
                """
            )
        )
        imports = list(
            connection.execute(
                """
                SELECT module, imported_name, root_name, classification
                FROM python_imports
                WHERE path = 'src/acme/service.py'
                ORDER BY module, imported_name
                """
            )
        )
        packages = list(
            connection.execute(
                """
                SELECT name, classification
                FROM python_packages
                ORDER BY classification, name
                """
            )
        )
        comments = list(
            connection.execute(
                """
                SELECT tag, text
                FROM python_tagged_comments
                ORDER BY tag, text
                """
            )
        )
        calls = list(
            connection.execute(
                """
                SELECT callee_name, confidence
                FROM python_calls
                ORDER BY callee_name, line
                """
            )
        )

    assert modules == [
        ("src/acme/__init__.py", "acme", "parsed", None),
        ("src/acme/service.py", "acme.service", "parsed", "Service module."),
    ]
    assert ("class", "Child", '["registry.register"]', '["Base"]', "Child handles work.") in symbols
    assert ("function", "helper", '["decorated"]', "[]", None) in symbols
    assert ("async_function", "async_worker", "[]", "[]", None) in symbols
    assert ("method", "Child.build", '["classmethod"]', "[]", None) in symbols
    assert ("os", None, "os", "stdlib") in imports
    assert ("requests", None, "requests", "third_party") in imports
    assert ("acme", "models", "acme", "local") in imports
    assert ("helpers", "helper", "helpers", "local") in imports
    assert ("acme", "local") in packages
    assert ("os", "stdlib") in packages
    assert ("requests", "third_party") in packages
    assert ("TODO", "replace fixture service") in comments
    assert ("SECURITY", "keep permission checks") in comments
    assert ("Child", "high") in calls
    assert ("helper", "high") in calls

    graph_json = json.loads((tmp_path / ".repolens" / "graph.json").read_text())
    graph_lite = json.loads((tmp_path / ".repolens" / "graph-lite.json").read_text())
    report = (tmp_path / ".repolens" / "graph-report.md").read_text(encoding="utf-8")
    graph_index = (tmp_path / ".repolens" / "graph-index.md").read_text(encoding="utf-8")

    assert any(
        symbol["qualified_name"] == "Child" and symbol["bases"] == ["Base"]
        for symbol in graph_json["python"]["symbols"]
    )
    assert any(
        import_fact["root_name"] == "requests" and import_fact["classification"] == "third_party"
        for import_fact in graph_json["python"]["imports"]
    )
    assert any(
        comment["tag"] == "SECURITY" and comment["text"] == "keep permission checks"
        for comment in graph_lite["python"]["tagged_comments"]
    )
    assert "## Python Symbols" in report
    assert "`Child`" in report
    assert "third_party" in report
    assert "SECURITY" in report
    assert "## Python Imports" in graph_index
    assert "requests" in graph_index


def test_index_records_python_syntax_errors_nonfatally_and_removes_stale_facts(tmp_path):
    target = tmp_path / "broken.py"
    _write_text(target, "def valid():\n    return 1\n")
    first_result = runner.invoke(app, ["index", str(tmp_path)])
    assert first_result.exit_code == 0

    _write_text(target, "# FIXME: repair parser fixture\ndef broken(:\n    pass\n")
    second_result = runner.invoke(app, ["index", str(tmp_path)])

    assert second_result.exit_code == 0
    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        file_status = connection.execute(
            "SELECT parser_status FROM files WHERE path = 'broken.py'"
        ).fetchone()
        parse_errors = list(
            connection.execute("SELECT path, message FROM python_parse_errors ORDER BY path")
        )
        symbols = list(
            connection.execute("SELECT qualified_name FROM python_symbols WHERE path = 'broken.py'")
        )
        comments = list(
            connection.execute("SELECT tag, text FROM python_tagged_comments ORDER BY tag")
        )

    assert file_status == ("parse_error",)
    assert parse_errors == [("broken.py", "invalid syntax")]
    assert symbols == []
    assert comments == [("FIXME", "repair parser fixture")]

    graph_json = json.loads((tmp_path / ".repolens" / "graph.json").read_text())
    graph_lite = json.loads((tmp_path / ".repolens" / "graph-lite.json").read_text())
    report = (tmp_path / ".repolens" / "graph-report.md").read_text(encoding="utf-8")
    graph_index = (tmp_path / ".repolens" / "graph-index.md").read_text(encoding="utf-8")

    assert graph_json["python"]["parse_errors"][0]["path"] == "broken.py"
    assert graph_lite["python"]["parse_errors"][0]["message"] == "invalid syntax"
    assert "parse_error" in report
    assert "broken.py" in graph_index


def test_index_writes_javascript_import_facts_to_sqlite_and_exports(tmp_path):
    _write_text(
        tmp_path / "src" / "app.ts",
        dedent(
            """
            import React from "react";
            import { map } from "lodash/fp";
            import * as path from "node:path";
            import "zone.js";
            const fs = require("fs");
            const scoped = require("@scope/pkg/sub/path");
            const local = require("./local");
            const dynamic = import("kleur/colors");
            """
        ).lstrip(),
    )

    result = runner.invoke(app, ["index", str(tmp_path)])

    assert result.exit_code == 0
    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        file_status = connection.execute(
            "SELECT parser_status FROM files WHERE path = 'src/app.ts'"
        ).fetchone()
        modules = list(
            connection.execute(
                """
                SELECT path, module_name, extension, parser_status
                FROM javascript_modules
                ORDER BY path
                """
            )
        )
        imports = list(
            connection.execute(
                """
                SELECT kind, specifier, root_name, classification
                FROM javascript_imports
                ORDER BY line, id
                """
            )
        )
        packages = list(
            connection.execute(
                """
                SELECT name, classification
                FROM javascript_packages
                ORDER BY classification, name
                """
            )
        )

    assert file_status == ("parsed",)
    assert modules == [("src/app.ts", "src/app", ".ts", "parsed")]
    assert ("default_import", "react", "react", "third_party") in imports
    assert ("named_import", "lodash/fp", "lodash", "third_party") in imports
    assert ("namespace_import", "node:path", "path", "node_builtin") in imports
    assert ("side_effect_import", "zone.js", "zone.js", "third_party") in imports
    assert ("require", "fs", "fs", "node_builtin") in imports
    assert ("require", "@scope/pkg/sub/path", "@scope/pkg", "third_party") in imports
    assert ("require", "./local", None, "local_unresolved") in imports
    assert ("dynamic_import", "kleur/colors", "kleur", "third_party") in imports
    assert ("path", "node_builtin") in packages
    assert ("fs", "node_builtin") in packages
    assert ("@scope/pkg", "third_party") in packages
    assert ("lodash", "third_party") in packages

    graph_json = json.loads((tmp_path / ".repolens" / "graph.json").read_text())
    graph_lite = json.loads((tmp_path / ".repolens" / "graph-lite.json").read_text())
    report = (tmp_path / ".repolens" / "graph-report.md").read_text(encoding="utf-8")
    graph_index = (tmp_path / ".repolens" / "graph-index.md").read_text(encoding="utf-8")

    assert any(
        import_fact["specifier"] == "lodash/fp"
        and import_fact["root_name"] == "lodash"
        and import_fact["classification"] == "third_party"
        for import_fact in graph_json["javascript"]["imports"]
    )
    assert any(
        import_fact["specifier"] == "./local"
        and import_fact["root_name"] is None
        and import_fact["classification"] == "local_unresolved"
        for import_fact in graph_lite["javascript"]["imports"]
    )
    assert "## JavaScript Imports" in report
    assert "lodash/fp" in report
    assert "node_builtin" in report
    assert "## JavaScript Packages" in graph_index
    assert "@scope/pkg" in graph_index


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


def _write_text(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
