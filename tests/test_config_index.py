from __future__ import annotations

from textwrap import dedent

from repolens.config_index import extract_config_index
from repolens.scanner import scan_repository


def test_config_index_extracts_python_packaging_dependencies_roots_and_entrypoints(tmp_path):
    _write_text(
        tmp_path / "pyproject.toml",
        dedent(
            """
            [build-system]
            requires = ["hatchling>=1.26"]
            build-backend = "hatchling.build"

            [project]
            name = "acme-service"
            version = "1.2.3"
            requires-python = ">=3.11"
            dependencies = ["requests>=2", "uvicorn[standard]"]

            [project.optional-dependencies]
            dev = ["pytest>=8"]

            [project.scripts]
            acme = "acme.cli:main"
            """
        ).lstrip(),
    )
    _write_text(tmp_path / "requirements.txt", "flask>=3\n# ignored\n-r other.txt\n")
    _write_text(
        tmp_path / "setup.cfg",
        dedent(
            """
            [metadata]
            name = legacy-acme

            [options]
            install_requires =
                click>=8
            """
        ).lstrip(),
    )
    _write_text(
        tmp_path / "setup.py",
        "setup(name='setup-acme', install_requires=['rich>=13'])\n",
    )
    _write_text(tmp_path / "uv.lock", "version = 1\n")
    _write_text(tmp_path / "src" / "acme_service" / "__init__.py", "")
    _write_text(
        tmp_path / "src" / "acme_service" / "__main__.py",
        "if __name__ == '__main__':\n    main()\n",
    )
    _write_text(tmp_path / "tools" / "worker", "#!/usr/bin/env python\nprint('ok')\n")

    config_index = extract_config_index(tmp_path, scan_repository(tmp_path).files)

    config_files = {config.path: config for config in config_index.config_files}
    assert config_files["pyproject.toml"].parser_status == "parsed"
    assert config_files["pyproject.toml"].top_level_keys == ("build-system", "project")
    assert config_files["uv.lock"].parser_status == "detected"

    packages = {
        (package.ecosystem, package.classification, package.name, package.dependency_type)
        for package in config_index.packages
    }
    assert ("python", "local", "acme-service", "project") in packages
    assert ("python", "external", "requests", "project.dependencies") in packages
    assert ("python", "external", "pytest", "project.optional-dependencies.dev") in packages
    assert ("python", "external", "flask", "requirements") in packages
    assert ("python", "external", "click", "install_requires") in packages
    assert ("python", "external", "rich", "install_requires") in packages

    managers = {(manager.ecosystem, manager.name) for manager in config_index.package_managers}
    assert ("python", "uv") in managers
    assert ("python", "pip") in managers
    assert ("python", "setuptools") in managers

    roots = {(root.ecosystem, root.name, root.path) for root in config_index.package_roots}
    assert ("python", "acme-service", "src/acme_service") in roots

    entrypoints = {
        (entrypoint.kind, entrypoint.name, entrypoint.target)
        for entrypoint in config_index.entrypoints
    }
    assert ("python_console_script", "acme", "acme.cli:main") in entrypoints
    assert (
        "python_main_guard",
        "src/acme_service/__main__.py",
        "src/acme_service/__main__.py",
    ) in entrypoints
    assert ("shebang", "tools/worker", "tools/worker") in entrypoints


def test_config_index_extracts_javascript_manifests_lockfiles_commands_and_entrypoints(tmp_path):
    _write_text(
        tmp_path / "package.json",
        dedent(
            r"""
            {
              "name": "web-app",
              "version": "0.2.0",
              "packageManager": "pnpm@9.0.0",
              "dependencies": {"react": "^19.0.0"},
              "devDependencies": {"vitest": "^3.0.0"},
              "scripts": {
                "test": "VITE_TOKEN=abc vitest --run --token super-secret",
                "lint": "eslint .",
                "deploy": "npm publish --otp 123456",
                "start": "vite --host 0.0.0.0"
              },
              "bin": {"web-app": "./bin/cli.js"},
              "main": "dist/index.js"
            }
            """
        ).lstrip(),
    )
    _write_text(tmp_path / "pnpm-lock.yaml", "lockfileVersion: '9.0'\n")
    _write_text(tmp_path / "package-lock.json", '{"lockfileVersion": 3}\n')

    config_index = extract_config_index(tmp_path, scan_repository(tmp_path).files)

    packages = {
        (package.ecosystem, package.classification, package.name, package.dependency_type)
        for package in config_index.packages
    }
    assert ("javascript", "local", "web-app", "package") in packages
    assert ("javascript", "external", "react", "dependencies") in packages
    assert ("javascript", "external", "vitest", "devDependencies") in packages

    managers = {(manager.ecosystem, manager.name) for manager in config_index.package_managers}
    assert ("javascript", "pnpm") in managers
    assert ("javascript", "npm") in managers

    lockfiles = {(lockfile.manager, lockfile.path) for lockfile in config_index.lockfiles}
    assert ("pnpm", "pnpm-lock.yaml") in lockfiles
    assert ("npm", "package-lock.json") in lockfiles

    commands = {command.name: command for command in config_index.commands}
    assert commands["test"].purpose == "test"
    assert commands["test"].not_run is True
    assert "super-secret" not in commands["test"].command
    assert "abc" not in commands["test"].command
    assert "<redacted>" in commands["test"].command
    assert commands["deploy"].purpose == "deploy"
    assert commands["deploy"].auto_run_recommended is False
    assert "123456" not in commands["deploy"].command

    entrypoints = {
        (entrypoint.kind, entrypoint.name, entrypoint.target)
        for entrypoint in config_index.entrypoints
    }
    assert ("package_bin", "web-app", "./bin/cli.js") in entrypoints
    assert ("package_main", "main", "dist/index.js") in entrypoints
    assert ("package_script", "start", "vite --host 0.0.0.0") in entrypoints


def test_config_index_redacts_commands_and_metadata_without_losing_useful_facts(tmp_path):
    _write_text(
        tmp_path / "package.json",
        dedent(
            r"""
            {
              "name": "token-tools",
              "version": "1.0.0",
              "dependencies": {"secret-sauce": "^1.2.3"},
              "scripts": {
                "test": "AUTH_TOKEN=abc vitest --api-key xyz",
                "start": "vite --host 127.0.0.1"
              },
              "token": "should-not-leak"
            }
            """
        ).lstrip(),
    )

    config_index = extract_config_index(tmp_path, scan_repository(tmp_path).files)

    packages = {(package.name, package.classification) for package in config_index.packages}
    assert ("token-tools", "local") in packages
    assert ("secret-sauce", "external") in packages
    commands = {command.name: command.command for command in config_index.commands}
    assert commands["test"] == "AUTH_TOKEN=<redacted> vitest --api-key <redacted>"
    assert commands["start"] == "vite --host 127.0.0.1"
    assert "should-not-leak" not in str(config_index.config_files)
    metadata = {config.path: config.metadata for config in config_index.config_files}
    assert metadata["package.json"]["top_level_types"]["token"] == "redacted"


def test_config_index_extracts_docker_make_ci_precommit_and_task_commands(tmp_path):
    _write_text(
        tmp_path / "Dockerfile",
        'FROM python:3.12\nCMD ["python", "-m", "acme"]\nENTRYPOINT ./entrypoint.sh\n',
    )
    _write_text(
        tmp_path / "Makefile",
        dedent(
            """
            test:
	uv run pytest

            deploy-prod:
	./scripts/deploy.sh
            """
        ).lstrip(),
    )
    _write_text(
        tmp_path / ".github" / "workflows" / "ci.yml",
        dedent(
            """
            name: CI
            jobs:
              test:
                steps:
                  - run: uv run pytest
                  - run: uv run ruff check .
            """
        ).lstrip(),
    )
    _write_text(
        tmp_path / ".pre-commit-config.yaml",
        dedent(
            """
            repos:
              - repo: local
                hooks: []
            """
        ).lstrip(),
    )
    _write_text(
        tmp_path / "Taskfile.yml",
        dedent(
            """
            version: '3'
            tasks:
              test:
                cmds:
                  - uv run pytest
              lint:
                cmds:
                  - uv run ruff check .
            """
        ).lstrip(),
    )

    config_index = extract_config_index(tmp_path, scan_repository(tmp_path).files)

    command_facts = {
        (command.source, command.name, command.purpose) for command in config_index.commands
    }
    assert ("make_target", "test", "test") in command_facts
    assert ("make_target", "deploy-prod", "deploy") in command_facts
    assert ("github_actions", "ci:1", "test") in command_facts
    assert ("github_actions", "ci:2", "lint") in command_facts
    assert ("pre_commit", "pre-commit", "lint") in command_facts
    assert ("taskfile", "test", "test") in command_facts
    assert ("taskfile", "lint", "lint") in command_facts
    assert all(command.not_run for command in config_index.commands)

    entrypoints = {(entrypoint.kind, entrypoint.target) for entrypoint in config_index.entrypoints}
    assert ("docker_cmd", '["python", "-m", "acme"]') in entrypoints
    assert ("docker_entrypoint", "./entrypoint.sh") in entrypoints


def test_config_index_records_malformed_configs_nonfatally_and_sanitizes_metadata(tmp_path):
    _write_text(tmp_path / "bad.json", "{not-json\n")
    _write_text(tmp_path / "bad.toml", "[broken\n")
    _write_text(tmp_path / "bad.yml", "value: !Unsafe tagged\n")
    _write_text(
        tmp_path / "service.yaml",
        dedent(
            """
            name: service
            token: should-not-be-exported
            features:
              - api
            """
        ).lstrip(),
    )

    config_index = extract_config_index(tmp_path, scan_repository(tmp_path).files)

    statuses = {config.path: config.parser_status for config in config_index.config_files}
    assert statuses["bad.json"] == "parse_error"
    assert statuses["bad.toml"] == "parse_error"
    assert statuses["bad.yml"] == "parse_error"
    assert statuses["service.yaml"] == "parsed"

    parse_errors = {error.path: error.message for error in config_index.parse_errors}
    assert parse_errors["bad.json"] == "invalid_json"
    assert parse_errors["bad.toml"] == "invalid_toml"
    assert parse_errors["bad.yml"] == "unsupported_yaml_tag"

    metadata = {config.path: config.metadata for config in config_index.config_files}
    assert metadata["service.yaml"]["top_level_types"] == {
        "features": "sequence",
        "name": "scalar",
        "token": "redacted",
    }
    assert "should-not-be-exported" not in str(metadata["service.yaml"])


def test_config_index_groups_monorepo_commands_by_nearest_explicit_package_root(tmp_path):
    _write_text(
        tmp_path / "package.json",
        dedent(
            r"""
            {
              "name": "workspace-root",
              "packageManager": "pnpm@9.0.0",
              "workspaces": ["packages/*"],
              "scripts": {"test": "pnpm -r test"}
            }
            """
        ).lstrip(),
    )
    _write_text(tmp_path / "pnpm-workspace.yaml", "packages:\n  - packages/*\n")
    _write_text(
        tmp_path / "packages" / "api" / "package.json",
        '{"name":"@acme/api","scripts":{"test":"vitest --run"}}\n',
    )
    _write_text(
        tmp_path / "packages" / "api" / "Makefile",
        "lint:\n\teslint .\n",
    )
    _write_text(
        tmp_path / "packages" / "worker" / "pyproject.toml",
        dedent(
            """
            [project]
            name = "acme-worker"
            version = "0.1.0"
            """
        ).lstrip(),
    )
    _write_text(tmp_path / "packages" / "worker" / "src" / "acme_worker" / "__init__.py", "")
    _write_text(tmp_path / "packages" / "docs" / "src" / "index.ts", "export {}\n")

    config_index = extract_config_index(tmp_path, scan_repository(tmp_path).files)

    roots = {(root.ecosystem, root.name, root.path) for root in config_index.package_roots}
    assert ("javascript", "workspace-root", ".") in roots
    assert ("javascript", "@acme/api", "packages/api") in roots
    assert ("python", "acme-worker", "packages/worker/src/acme_worker") in roots
    assert not any(root.path == "packages/docs" for root in config_index.package_roots)

    workspaces = {
        (workspace.ecosystem, workspace.path, workspace.pattern, workspace.source_path)
        for workspace in config_index.workspaces
    }
    assert ("javascript", "packages/*", "packages/*", "package.json") in workspaces
    assert ("javascript", "packages/*", "packages/*", "pnpm-workspace.yaml") in workspaces

    commands = {(command.path, command.name): command for command in config_index.commands}
    assert commands[("package.json", "test")].group_path == "."
    assert commands[("package.json", "test")].group_kind == "package_root"
    assert commands[("packages/api/package.json", "test")].group_path == "packages/api"
    assert commands[("packages/api/Makefile", "lint")].group_path == "packages/api"
    assert (
        commands[("packages/api/Makefile", "lint")].group_source_path == "packages/api/package.json"
    )


def test_config_index_detects_common_nested_package_manager_evidence(tmp_path):
    _write_text(
        tmp_path / "apps" / "web" / "package.json",
        '{"name":"web","scripts":{"test":"npm test"}}\n',
    )
    _write_text(tmp_path / "apps" / "web" / "yarn.lock", "# lock\n")
    _write_text(
        tmp_path / "services" / "api" / "pyproject.toml",
        '[project]\nname = "api"\nversion = "0.1.0"\n',
    )
    _write_text(tmp_path / "services" / "api" / "uv.lock", "version = 1\n")
    _write_text(tmp_path / "services" / "api" / "api" / "__init__.py", "")

    config_index = extract_config_index(tmp_path, scan_repository(tmp_path).files)

    managers = {
        (manager.ecosystem, manager.name, manager.source_path, manager.evidence_kind)
        for manager in config_index.package_managers
    }
    assert ("javascript", "yarn", "apps/web/yarn.lock", "lockfile") in managers
    assert ("python", "uv", "services/api/uv.lock", "lockfile") in managers

    roots = {(root.ecosystem, root.name, root.path) for root in config_index.package_roots}
    assert ("javascript", "web", "apps/web") in roots
    assert ("python", "api", "services/api/api") in roots


def _write_text(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
