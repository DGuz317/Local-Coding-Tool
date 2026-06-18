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
    assert metadata["schema_version"] == "8"
    assert "effective_config_hash" in metadata
    assert "git_branch" in metadata
    assert "git_commit" in metadata
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


def test_index_writes_javascript_symbol_export_and_commonjs_facts_to_artifacts(tmp_path):
    _write_text(
        tmp_path / "src" / "component.tsx",
        dedent(
            """
            export function handler() {
              return "handler result";
            }

            export const view = () => "view result";
            export const version = "1.0.0";
            const internal = async () => "internal result";

            export class Service {}
            export interface ServiceProps { name: string }
            export type ServiceMode = "fast" | "safe";

            export default handler;
            export { Service as PublicService };

            module.exports = handler;
            exports.view = view;
            """
        ).lstrip(),
    )

    result = runner.invoke(app, ["index", str(tmp_path)])

    assert result.exit_code == 0
    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        symbols = list(
            connection.execute(
                """
                SELECT kind, qualified_name, start_line, end_line
                FROM javascript_symbols
                ORDER BY kind, qualified_name
                """
            )
        )
        exports = list(
            connection.execute(
                """
                SELECT kind, exported_name, local_name
                FROM javascript_exports
                ORDER BY kind, exported_name
                """
            )
        )
        commonjs_assignments = list(
            connection.execute(
                """
                SELECT kind, exported_name, assigned_name
                FROM javascript_commonjs_assignments
                ORDER BY kind, exported_name
                """
            )
        )

    assert ("function", "handler", 1, 1) in symbols
    assert ("arrow_function", "view", 5, 5) in symbols
    assert ("arrow_function", "internal", 7, 7) in symbols
    assert ("class", "Service", 9, 9) in symbols
    assert ("interface", "ServiceProps", 10, 10) in symbols
    assert ("type_alias", "ServiceMode", 11, 11) in symbols
    assert exports == [
        ("class_export", "Service", "Service"),
        ("const_export", "version", "version"),
        ("const_export", "view", "view"),
        ("default_export", "default", "handler"),
        ("function_export", "handler", "handler"),
        ("named_export", "PublicService", "Service"),
    ]
    assert commonjs_assignments == [
        ("exports_property", "view", "view"),
        ("module_exports", "module.exports", "handler"),
    ]

    graph_json = json.loads((tmp_path / ".repolens" / "graph.json").read_text())
    graph_lite = json.loads((tmp_path / ".repolens" / "graph-lite.json").read_text())
    report = (tmp_path / ".repolens" / "graph-report.md").read_text(encoding="utf-8")
    graph_index = (tmp_path / ".repolens" / "graph-index.md").read_text(encoding="utf-8")

    assert any(
        symbol["kind"] == "interface" and symbol["qualified_name"] == "ServiceProps"
        for symbol in graph_json["javascript"]["symbols"]
    )
    assert any(
        export["kind"] == "default_export" and export["local_name"] == "handler"
        for export in graph_lite["javascript"]["exports"]
    )
    assert any(
        assignment["kind"] == "exports_property" and assignment["exported_name"] == "view"
        for assignment in graph_json["javascript"]["commonjs_assignments"]
    )
    assert "## JavaScript Symbols" in report
    assert "ServiceProps" in report
    assert "## JavaScript Exports" in report
    assert "default_export" in report
    assert "## JavaScript CommonJS Assignments" in graph_index
    assert "module.exports" in graph_index


def test_index_writes_mixed_javascript_typescript_alias_facts_to_artifacts(tmp_path):
    _write_text(
        tmp_path / "tsconfig.json",
        dedent(
            """
            {
              "compilerOptions": {
                "baseUrl": ".",
                "paths": {
                  "@/*": ["src/*"],
                  "@ambiguous/*": ["src/*", "lib/*"]
                }
              }
            }
            """
        ).lstrip(),
    )
    _write_text(tmp_path / "src" / "lib" / "run.ts", "export const run = () => 'done';\n")
    _write_text(tmp_path / "src" / "components" / "App.tsx", "export const App = () => null;\n")
    _write_text(
        tmp_path / "src" / "main.tsx",
        dedent(
            """
            import React from "react";
            import { run } from "@/lib/run";
            import { App } from "@/components/App";
            import maybe from "@ambiguous/maybe";

            export { App };
            export default App;
            """
        ).lstrip(),
    )

    result = runner.invoke(app, ["index", str(tmp_path)])

    assert result.exit_code == 0
    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        metadata = dict(connection.execute("SELECT key, value FROM metadata ORDER BY key"))
        imports = list(
            connection.execute(
                """
                SELECT specifier, root_name, classification, resolved_path, resolution_status
                FROM javascript_imports
                ORDER BY specifier
                """
            )
        )
        import_edges = list(
            connection.execute(
                """
                SELECT source_id, target_id, kind, metadata_json
                FROM edges
                WHERE source_id = 'javascript_module:src/main.tsx'
                ORDER BY target_id
                """
            )
        )

    assert metadata["schema_version"] == "8"
    assert (
        "@/components/App",
        None,
        "local_resolved",
        "src/components/App.tsx",
        "resolved_alias",
    ) in imports
    assert ("@/lib/run", None, "local_resolved", "src/lib/run.ts", "resolved_alias") in imports
    assert (
        "@ambiguous/maybe",
        None,
        "local_unresolved",
        None,
        "unresolved_complex_alias",
    ) in imports
    assert ("react", "react", "third_party", None, "external") in imports

    assert any(
        target_id == "javascript_module:src/lib/run.ts"
        and kind == "IMPORTS"
        and '"resolved_path":"src/lib/run.ts"' in metadata_json
        for _, target_id, kind, metadata_json in import_edges
    )
    assert not any("@ambiguous/maybe" in metadata_json for *_, metadata_json in import_edges)

    graph_json = json.loads((tmp_path / ".repolens" / "graph.json").read_text())
    graph_lite = json.loads((tmp_path / ".repolens" / "graph-lite.json").read_text())
    report = (tmp_path / ".repolens" / "graph-report.md").read_text(encoding="utf-8")
    graph_index = (tmp_path / ".repolens" / "graph-index.md").read_text(encoding="utf-8")

    assert any(
        import_fact["specifier"] == "@/lib/run"
        and import_fact["resolved_path"] == "src/lib/run.ts"
        and import_fact["resolution_status"] == "resolved_alias"
        for import_fact in graph_json["javascript"]["imports"]
    )
    assert any(
        import_fact["specifier"] == "@ambiguous/maybe"
        and import_fact["resolved_path"] is None
        and import_fact["resolution_status"] == "unresolved_complex_alias"
        for import_fact in graph_lite["javascript"]["imports"]
    )
    assert any(
        edge["target_id"] == "javascript_module:src/components/App.tsx"
        and edge["kind"] == "IMPORTS"
        for edge in graph_json["edges"]
    )
    assert "## JavaScript Imports" in report
    assert "resolved_alias" in report
    assert "src/lib/run.ts" in report
    assert "## JavaScript Exports" in graph_index
    assert "default_export" in graph_index


def test_index_writes_config_command_package_and_entrypoint_facts_to_artifacts(tmp_path):
    _write_text(
        tmp_path / "pyproject.toml",
        dedent(
            """
            [project]
            name = "acme-service"
            version = "0.1.0"
            dependencies = ["requests>=2"]

            [project.scripts]
            acme = "acme.cli:main"
            """
        ).lstrip(),
    )
    _write_text(
        tmp_path / "package.json",
        dedent(
            r"""
            {
              "name": "web-app",
              "packageManager": "npm@10.0.0",
              "dependencies": {"react": "^19.0.0"},
              "scripts": {
                "test": "vitest --run --token super-secret",
                "deploy": "npm publish --otp 123456",
                "start": "vite --host 0.0.0.0"
              },
              "bin": {"web-app": "./bin/cli.js"}
            }
            """
        ).lstrip(),
    )
    _write_text(tmp_path / "package-lock.json", '{"lockfileVersion": 3}\n')
    _write_text(tmp_path / "src" / "acme_service" / "__init__.py", "")
    _write_text(
        tmp_path / "src" / "acme_service" / "__main__.py",
        "if __name__ == '__main__':\n    main()\n",
    )
    _write_text(tmp_path / "Dockerfile", 'FROM node:22\nCMD ["npm", "start"]\n')
    _write_text(tmp_path / "Makefile", "test:\n\tuv run pytest\n")

    result = runner.invoke(app, ["index", str(tmp_path)])

    assert result.exit_code == 0
    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        metadata = dict(connection.execute("SELECT key, value FROM metadata ORDER BY key"))
        config_files = list(
            connection.execute(
                """
                SELECT path, config_kind, format, parser_status
                FROM config_files
                ORDER BY path
                """
            )
        )
        packages = list(
            connection.execute(
                """
                SELECT ecosystem, classification, name, dependency_type
                FROM config_packages
                ORDER BY ecosystem, classification, name, dependency_type
                """
            )
        )
        commands = list(
            connection.execute(
                """
                SELECT source, name, purpose, command, not_run, auto_run_recommended
                FROM config_commands
                ORDER BY source, name
                """
            )
        )
        entrypoints = list(
            connection.execute(
                """
                SELECT kind, name, target
                FROM config_entrypoints
                ORDER BY kind, name
                """
            )
        )
        lockfiles = list(
            connection.execute("SELECT manager, path FROM config_lockfiles ORDER BY path")
        )

    assert metadata["schema_version"] == "8"
    assert ("package.json", "package_manifest", "json", "parsed") in config_files
    assert ("pyproject.toml", "python_package", "toml", "parsed") in config_files
    assert ("package-lock.json", "lockfile", "json", "detected") in config_files
    assert ("python", "local", "acme-service", "project") in packages
    assert ("python", "external", "requests", "project.dependencies") in packages
    assert ("javascript", "local", "web-app", "package") in packages
    assert ("javascript", "external", "react", "dependencies") in packages
    assert ("npm", "package-lock.json") in lockfiles
    assert any(
        source == "package_script"
        and name == "test"
        and purpose == "test"
        and "super-secret" not in command
        and not_run == 1
        for source, name, purpose, command, not_run, _ in commands
    )
    assert any(
        source == "package_script"
        and name == "deploy"
        and purpose == "deploy"
        and auto_run_recommended == 0
        and "123456" not in command
        for source, name, purpose, command, _, auto_run_recommended in commands
    )
    assert ("python_console_script", "acme", "acme.cli:main") in entrypoints
    assert (
        "python_main_guard",
        "src/acme_service/__main__.py",
        "src/acme_service/__main__.py",
    ) in entrypoints
    assert ("docker_cmd", "CMD", '["npm", "start"]') in entrypoints

    graph_json = json.loads((tmp_path / ".repolens" / "graph.json").read_text())
    graph_lite = json.loads((tmp_path / ".repolens" / "graph-lite.json").read_text())
    report = (tmp_path / ".repolens" / "graph-report.md").read_text(encoding="utf-8")
    graph_index = (tmp_path / ".repolens" / "graph-index.md").read_text(encoding="utf-8")

    assert any(package["name"] == "react" for package in graph_json["config"]["packages"])
    assert any(command["name"] == "test" for command in graph_lite["config"]["commands"])
    assert "## Config Packages" in report
    assert "react" in report
    assert "## Config Entrypoints" in graph_index
    assert "docker_cmd" in graph_index


def test_index_writes_documentation_comment_and_skill_facts_to_artifacts(tmp_path):
    _write_text(tmp_path / "src" / "app.py", "def app():\n    return 1\n")
    _write_text(
        tmp_path / "src" / "app.ts",
        dedent(
            """
            // TODO: handle browser fallback
            export const app = () => true;
            /* SECURITY: keep auth check close */
            """
        ).lstrip(),
    )
    _write_text(tmp_path / "docs" / "guide.md", "# Guide\n")
    _write_text(tmp_path / "AGENTS.md", "# AGENTS.md\n\nUse repo-specific workflow.\n")
    _write_text(
        tmp_path / ".agents" / "skills" / "review" / "SKILL.md",
        dedent(
            """
            ---
            name: review
            description: Review repository changes for regressions.
            ---

            # Review
            """
        ).lstrip(),
    )
    _write_text(
        tmp_path / "README.md",
        dedent(
            """
            # RepoLens

            RepoLens maps local repositories. Extra details are not mirrored.

            ## Setup
            See [Guide](docs/guide.md), `src/app.py`, and AGENTS.md.

            ```python
            SECRET_CODE_FENCE_BODY = "must not be exported"
            ```

            ## Setup
            """
        ).lstrip(),
    )

    result = runner.invoke(app, ["index", str(tmp_path)])

    assert result.exit_code == 0
    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        metadata = dict(connection.execute("SELECT key, value FROM metadata ORDER BY key"))
        markdown_files = list(
            connection.execute(
                """
                SELECT path, doc_kind, importance, title, intro
                FROM documentation_files
                ORDER BY path
                """
            )
        )
        headings = list(
            connection.execute(
                """
                SELECT path, heading_id, text, line
                FROM markdown_headings
                WHERE path = 'README.md'
                ORDER BY line
                """
            )
        )
        links = list(
            connection.execute(
                """
                SELECT path, label, target_path
                FROM markdown_links
                ORDER BY path, label
                """
            )
        )
        mentions = list(
            connection.execute(
                """
                SELECT path, mentioned_path, target_path
                FROM markdown_path_mentions
                ORDER BY path, mentioned_path
                """
            )
        )
        fences = list(
            connection.execute(
                """
                SELECT path, language, info_string
                FROM markdown_code_fences
                ORDER BY path, start_line
                """
            )
        )
        tagged_comments = list(
            connection.execute(
                """
                SELECT tag, text, language
                FROM documentation_tagged_comments
                ORDER BY tag, text
                """
            )
        )
        skills = list(
            connection.execute("SELECT name, description, path FROM skills ORDER BY name")
        )

    assert metadata["schema_version"] == "8"
    assert (
        "README.md",
        "readme",
        "important",
        "RepoLens",
        "RepoLens maps local repositories.",
    ) in markdown_files
    assert ("AGENTS.md", "agent_instructions", "important", "AGENTS.md", None) in markdown_files
    assert ("README.md", "repolens", "RepoLens", 1) in headings
    assert ("README.md", "setup", "Setup", 5) in headings
    assert ("README.md", "setup-1", "Setup", 12) in headings
    assert ("README.md", "Guide", "docs/guide.md") in links
    assert ("README.md", "src/app.py", "src/app.py") in mentions
    assert ("README.md", "AGENTS.md", "AGENTS.md") in mentions
    assert ("README.md", "python", "python") in fences
    assert ("SECURITY", "keep auth check close", "javascript") in tagged_comments
    assert ("TODO", "handle browser fallback", "javascript") in tagged_comments
    assert (
        "review",
        "Review repository changes for regressions.",
        ".agents/skills/review/SKILL.md",
    ) in skills

    graph_json = json.loads((tmp_path / ".repolens" / "graph.json").read_text())
    graph_lite = json.loads((tmp_path / ".repolens" / "graph-lite.json").read_text())
    report = (tmp_path / ".repolens" / "graph-report.md").read_text(encoding="utf-8")
    graph_index = (tmp_path / ".repolens" / "graph-index.md").read_text(encoding="utf-8")

    assert any(
        file["doc_kind"] == "agent_instructions" for file in graph_json["documentation"]["files"]
    )
    assert any(skill["name"] == "review" for skill in graph_lite["documentation"]["skills"])
    assert "## Markdown Headings" in report
    assert "setup-1" in report
    assert "## Skills" in graph_index
    assert "review" in graph_index

    for artifact in GRAPH_ARTIFACTS:
        artifact_text = (tmp_path / ".repolens" / artifact).read_text(
            encoding="utf-8", errors="ignore"
        )
        assert "SECRET_CODE_FENCE_BODY" not in artifact_text, artifact


def test_index_exports_are_deterministic_except_allowed_run_timestamp(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    _write_text(tmp_path / "src" / "widget.ts", "export const widget = () => 'ok';\n")
    (tmp_path / "README.md").write_text("# Fixture\n", encoding="utf-8")

    first_result = runner.invoke(app, ["index", str(tmp_path)])
    assert first_result.exit_code == 0
    first_exports = _stable_export_content(tmp_path)

    second_result = runner.invoke(app, ["index", str(tmp_path)])
    assert second_result.exit_code == 0

    assert _stable_export_content(tmp_path) == first_exports


def test_graph_exports_do_not_mirror_source_code(tmp_path):
    source_body = "THIS_PYTHON_SOURCE_BODY_MUST_NOT_BE_MIRRORED"
    javascript_source_body = "THIS_JS_SOURCE_BODY_MUST_NOT_BE_MIRRORED"
    (tmp_path / "app.py").write_text(
        f"def app():\n    return {source_body!r}\n",
        encoding="utf-8",
    )
    _write_text(
        tmp_path / "src" / "app.ts",
        f"export const app = () => {javascript_source_body!r};\n",
    )

    result = runner.invoke(app, ["index", str(tmp_path)])

    assert result.exit_code == 0
    for artifact in GRAPH_ARTIFACTS:
        artifact_text = (tmp_path / ".repolens" / artifact).read_text(
            encoding="utf-8", errors="ignore"
        )
        assert source_body not in artifact_text, artifact
        assert javascript_source_body not in artifact_text, artifact


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
