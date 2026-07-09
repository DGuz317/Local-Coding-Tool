from __future__ import annotations

import json
from textwrap import dedent

from typer.testing import CliRunner

from repolens.artifact_audit import ARTIFACT_AUDIT_VERSION, audit_artifacts
from repolens.cli import app
from repolens.indexer import index_repository

runner = CliRunner()


def test_audit_artifacts_json_passes_for_indexed_fixture(tmp_path):
    _write_audit_fixture_repo(tmp_path)
    index_repository(tmp_path)

    result = runner.invoke(app, ["audit-artifacts", str(tmp_path), "--json"])

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    data = envelope["data"]
    assert envelope["ok"] is True
    assert data["artifact_audit_version"] == ARTIFACT_AUDIT_VERSION
    assert data["summary"]["passed"] is True
    assert data["summary"]["violation_count"] == 0
    assert ".repolens/graph.json" in data["audited_artifacts"]
    assert data["checks"]["call_chain_facts_source_free"] is True
    assert data["checks"]["candidate_commands_not_run"] is True


def test_audit_artifacts_human_output_summarizes_failures(tmp_path):
    _write_audit_fixture_repo(tmp_path)
    index_repository(tmp_path)
    _write_negative_artifact(tmp_path)

    result = runner.invoke(app, ["audit-artifacts", str(tmp_path)])

    assert result.exit_code == 1
    assert "RepoLens Artifact Audit:" in result.output
    assert "Status: failed" in result.output
    assert "Failures:" in result.output
    assert "source_snippet_leakage" in result.output
    assert "candidate_commands_not_run" in result.output


def test_audit_artifacts_reports_negative_fixture_failures_clearly(tmp_path):
    _write_audit_fixture_repo(tmp_path)
    index_repository(tmp_path)
    _write_negative_artifact(tmp_path)

    envelope = audit_artifacts(tmp_path, max_artifact_bytes=8)

    assert envelope["ok"] is False
    violations = envelope["data"]["violations"]
    checks = {violation["check"] for violation in violations}
    assert {
        "absolute_host_paths",
        "candidate_commands_not_run",
        "mcp_contract",
        "oversized_artifacts",
        "raw_agent_guidance_mirroring",
        "raw_secret_like_values",
        "source_snippet_leakage",
    }.issubset(checks)
    assert all(str(violation["location"]).startswith(".repolens/") for violation in violations)
    assert any("required MCP envelope field" in violation["message"] for violation in violations)
    assert any("must remain discovered-only" in violation["message"] for violation in violations)


def test_audit_artifacts_detects_source_bearing_semantic_jsonl_fields(tmp_path):
    _write_audit_fixture_repo(tmp_path)
    index_repository(tmp_path)
    _write_text(
        tmp_path / ".repolens" / "semantic.jsonl",
        json.dumps(
            {
                "source_path": "src/auth/login.ts",
                "raw_condition_text": "input.user.trim().toLowerCase().length > 0",
                "function_signature": "validateLogin(input)",
                "raw_value": f"{tmp_path.as_posix()}/src/auth/login.ts",
            },
            sort_keys=True,
        )
        + "\n",
    )

    envelope = audit_artifacts(tmp_path)

    assert envelope["ok"] is False
    checks = {violation["check"] for violation in envelope["data"]["violations"]}
    assert "semantic_outputs_source_free" in checks
    assert "absolute_host_paths" in checks


def _write_negative_artifact(root) -> None:
    payload = {
        "ok": True,
        "data": {
            "candidate_verification_commands": [
                {
                    "auto_run_recommended": True,
                    "command": "npm test",
                    "found": True,
                    "kind": "candidate_verification_command",
                    "not_run": False,
                    "run": True,
                }
            ],
            "raw_agent_guidance": (
                "Instructions from: AGENTS.md\n"
                "Non-Negotiable Product Boundaries must not be mirrored as raw guidance. "
                "This deliberately long fixture text simulates an unsafe assistant-facing dump "
                "of instruction material rather than compact metadata."
            ),
            "snippet": "function leakedSource() { return true; }",
            "unsafe_absolute_path": f"{root.as_posix()}/src/auth/login.ts",
            "unsafe_secret": "API_TOKEN=abc123",
        },
    }
    _write_text(root / ".repolens" / "negative-audit.json", json.dumps(payload, sort_keys=True))


def _write_audit_fixture_repo(root) -> None:
    _write_text(
        root / "package.json",
        dedent(
            """
            {
              "name": "audit-demo",
              "scripts": {
                "test": "vitest run tests/login.test.ts"
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
              return input.user.trim().toLowerCase().length > 0;
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
