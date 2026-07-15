from __future__ import annotations

import json
from textwrap import dedent

from typer.testing import CliRunner

from repolens.cli import app
from repolens.indexer import index_repository

runner = CliRunner()


def test_preflight_json_returns_bounded_cli_contract(tmp_path):
    _write_preflight_fixture_repo(tmp_path)
    index_repository(tmp_path)

    result = runner.invoke(
        app,
        [
            "preflight",
            str(tmp_path),
            "Fix API_TOKEN=abc123 login validation",
            "--focus-hint",
            "src/auth/login.ts",
            "--max-first-read-files",
            "1",
            "--max-items-per-support-group",
            "1",
            "--max-candidate-verification-commands",
            "1",
            "--max-total-chars",
            "8000",
            "--json",
        ],
    )

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    data = envelope["data"]
    assert envelope["ok"] is True
    assert data["assistant_preflight_version"] == "0.5.preflight.v1"
    assert data["task_context"]["display_task"] == "Fix API_TOKEN login validation"
    assert data["focus_hints"]["items"] == ["src/auth/login.ts"]
    assert data["budget_controls"]["max_first_read_files"] == 1
    assert data["freshness"]["fresh"] is True
    assert [item["path"] for item in data["first_read_files"]] == ["src/auth/login.ts"]
    assert [item["path"] for item in data["likely_tests"]] == ["tests/login.test.ts"]
    assert data["candidate_verification_commands"]
    assert all(command["found"] is True for command in data["candidate_verification_commands"])
    assert all(command["run"] is False for command in data["candidate_verification_commands"])
    assert all(command["not_run"] is True for command in data["candidate_verification_commands"])
    assert "abc123" not in result.output
    assert "return input.user" not in result.output


def test_preflight_human_output_includes_actionable_orientation_sections(tmp_path):
    _write_preflight_fixture_repo(tmp_path)
    index_repository(tmp_path)

    result = runner.invoke(
        app, ["preflight", str(tmp_path), "Fix API_TOKEN=abc123 login validation"]
    )

    assert result.exit_code == 0
    assert "Assistant Preflight:" in result.output
    assert "Freshness: available" in result.output
    assert "First-Read Files:" in result.output
    assert "Likely Tests:" in result.output
    assert "Candidate Verification Commands (discovered only; not run):" in result.output
    assert "run=False" in result.output
    assert "Confidence:" in result.output
    assert "Evidence:" in result.output
    assert "Budget Controls:" in result.output
    assert "return input.user" not in result.output


def test_preflight_missing_graph_is_initialized_automatically(tmp_path):
    _write_preflight_fixture_repo(tmp_path)

    json_result = runner.invoke(app, ["preflight", str(tmp_path), "Fix login validation", "--json"])
    human_result = runner.invoke(app, ["preflight", str(tmp_path), "Fix login validation"])

    assert json_result.exit_code == 0
    envelope = json.loads(json_result.output)
    assert envelope["ok"] is True
    assert envelope["freshness"]["fresh"] is True
    assert (tmp_path / ".repolens" / "graph.sqlite").is_file()
    assert human_result.exit_code == 0
    assert "Assistant Preflight:" in human_result.output
    assert "Freshness: available" in human_result.output


def test_preflight_refreshes_stale_graph_automatically(tmp_path):
    _write_preflight_fixture_repo(tmp_path)
    index_repository(tmp_path)
    _write_text(tmp_path / "src" / "auth" / "login.ts", "export const changed = true;\n")

    result = runner.invoke(app, ["preflight", str(tmp_path), "Fix login validation", "--json"])

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    assert envelope["ok"] is True
    assert envelope["freshness"]["fresh"] is True
    assert envelope["data"]["freshness"]["status"] == "available"
    assert envelope["data"]["graph_lifecycle"]["detected_state"] == "changed"
    assert envelope["data"]["graph_lifecycle"]["update"]["mode"] == "selective"
    assert "Graph artifacts may be stale" not in " ".join(envelope["warnings"])


def _write_preflight_fixture_repo(root) -> None:
    _write_text(
        root / "package.json",
        dedent(
            """
            {
              "name": "auth-demo",
              "scripts": {
                "test": "vitest run tests/login.test.ts",
                "lint": "eslint src/auth/login.ts"
              }
            }
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
