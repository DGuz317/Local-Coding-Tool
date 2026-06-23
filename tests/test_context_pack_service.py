from __future__ import annotations

import json
from textwrap import dedent

from typer.testing import CliRunner

from repolens.cli import app
from repolens.context_pack import get_task_context
from repolens.context_pack_contract import CONTEXT_PACK_VERSION, DEFAULT_CONTEXT_PACK_BUDGET
from repolens.indexer import index_repository
from repolens.mcp_server import RepoLensMcpTools

runner = CliRunner()


def test_get_task_context_returns_deterministic_context_pack_contract(tmp_path):
    _write_context_fixture_repo(tmp_path)
    index_repository(tmp_path)

    first = get_task_context(tmp_path, "Fix API_TOKEN=abc123 login validation")
    second = get_task_context(tmp_path, "Fix API_TOKEN=abc123 login validation")

    assert first == second
    assert first["ok"] is True
    assert first["confidence"] == "medium"
    assert first["limits"] == DEFAULT_CONTEXT_PACK_BUDGET

    pack = first["data"]
    assert pack["context_pack_version"] == CONTEXT_PACK_VERSION
    assert pack["context_pack_id"].startswith("cp_")
    assert pack["task"] == "Fix API_TOKEN login validation"
    assert pack["task_fingerprint"].startswith("task_")
    assert "abc123" not in json.dumps(first)
    assert pack["budget"]["max_first_read_files"] == 5
    assert pack["freshness"]["canonical_graph_hash"]
    assert pack["truncation"] == {"fields": [], "truncated": False}

    assert [item["path"] for item in pack["first_read_files"]] == [
        "src/auth/login.ts",
        "README.md",
    ]
    first_read = pack["first_read_files"][0]
    assert first_read["kind"] == "first_read_file"
    assert first_read["rank"] == 1
    assert first_read["handle"].startswith("item_")
    assert first_read["symbols"]
    assert first_read["relationships"] == []
    assert first_read["related_tests"] == ["tests/login.test.ts"]

    assert [item["path"] for item in pack["likely_tests"]] == ["tests/login.test.ts"]
    assert pack["candidate_verification_commands"] == []
    assert [handle["handle"] for handle in pack["expansion_handles"]] == [
        item["handle"] for item in pack["first_read_files"]
    ]
    assert all(
        handle["context_pack_id"] == pack["context_pack_id"] for handle in pack["expansion_handles"]
    )


def test_context_pack_cli_and_mcp_use_same_service(tmp_path):
    _write_context_fixture_repo(tmp_path)
    index_repository(tmp_path)

    cli_result = runner.invoke(
        app,
        ["context", str(tmp_path), "Add validation to login flow tests", "--json"],
    )
    mcp_result = RepoLensMcpTools(tmp_path).get_task_context("Add validation to login flow tests")

    assert cli_result.exit_code == 0
    cli_envelope = json.loads(cli_result.output)
    assert cli_envelope == mcp_result
    assert cli_envelope["data"]["first_read_files"][0]["path"] == "src/auth/login.ts"

    human_result = runner.invoke(
        app, ["context", str(tmp_path), "Add validation to login flow tests"]
    )

    assert human_result.exit_code == 0
    assert "Context Pack" in human_result.output
    assert "First-Read Files" in human_result.output
    assert "src/auth/login.ts" in human_result.output
    assert "Lower-priority context to inspect later" in human_result.output


def _write_context_fixture_repo(root) -> None:
    _write_text(
        root / "package.json",
        dedent(
            """
            {
              "name": "auth-demo",
              "scripts": {"test": "vitest run tests/login.test.ts"}
            }
            """
        ).lstrip(),
    )
    _write_text(
        root / "README.md",
        dedent(
            """
            # Auth Demo

            The login flow is implemented in `src/auth/login.ts`.
            """
        ).lstrip(),
    )
    _write_text(
        root / "src" / "auth" / "login.ts",
        dedent(
            """
            export function validateLogin(input: { user: string }) {
              return input.user.length > 0;
            }

            export function loginFlow(input: { user: string }) {
              return validateLogin(input);
            }
            """
        ).lstrip(),
    )
    _write_text(
        root / "tests" / "login.test.ts",
        dedent(
            """
            import { validateLogin } from "../src/auth/login";

            test("validates login", () => {
              expect(validateLogin({ user: "demo" })).toBe(true);
            });
            """
        ).lstrip(),
    )


def _write_text(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
