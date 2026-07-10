from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

from typer.testing import CliRunner

from repolens.cli import app
from repolens.indexer import index_repository

runner = CliRunner()


def test_create_ai_proposal_cli_json_matches_service_and_does_not_write_artifacts(tmp_path):
    _write_text(tmp_path / "src" / "app.py", "def alpha():\n    return 1\n")
    before_paths = _repo_paths(tmp_path)
    task = "Summarize the bounded context pack"

    result = runner.invoke(
        app,
        [
            "create-ai-proposal",
            str(tmp_path),
            "context_pack_summary",
            task,
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    cli_envelope = json.loads(result.output)
    from repolens.ai_proposal import create_ai_proposal

    service_envelope = create_ai_proposal(
        tmp_path,
        kind="context_pack_summary",
        task=task,
    )
    assert cli_envelope == service_envelope
    assert cli_envelope["ok"] is True
    assert cli_envelope["data"]["status"] == "disabled"
    assert cli_envelope["data"]["kind"] == "context_pack_summary"
    assert cli_envelope["data"]["provider"] == {
        "configured": False,
        "name": None,
        "model": None,
    }
    assert cli_envelope["data"]["safety"] == {
        "provider_called": False,
        "network_accessed": False,
        "file_written": False,
        "command_executed": False,
        "patch_applied": False,
        "remote_posted": False,
    }
    assert _repo_paths(tmp_path) == before_paths
    assert not (tmp_path / ".repolens").exists()


def test_create_ai_proposal_cli_json_returns_configured_test_provider_success_after_indexing(
    tmp_path,
):
    _write_context_summary_fixture_repo(tmp_path)
    index_repository(tmp_path)
    task = "Summarize auth login context without exposing API_TOKEN=cli-secret-204"

    result = runner.invoke(
        app,
        [
            "create-ai-proposal",
            str(tmp_path),
            "context_pack_summary",
            task,
            "--enable-ai",
            "--provider",
            "test",
            "--model",
            "context-pack-summary-v1",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    cli_envelope = json.loads(result.output)
    from repolens.ai_proposal import create_ai_proposal

    service_envelope = create_ai_proposal(
        tmp_path,
        kind="context_pack_summary",
        task=task,
        enable_ai=True,
        provider="test",
        model="context-pack-summary-v1",
    )
    assert cli_envelope == service_envelope
    assert cli_envelope["ok"] is True
    assert cli_envelope["data"]["status"] == "available"
    provider = cli_envelope["data"]["provider"]
    assert provider["configured"] is True
    assert provider["name"] == "test"
    assert provider["model"] == "context-pack-summary-v1"

    proposal = cli_envelope["data"]["proposal"]
    assert proposal["kind"] == "context_pack_summary"
    proposal_provider = proposal["provider"]
    assert proposal_provider["name"] == "test"
    assert proposal_provider["model"] == "context-pack-summary-v1"
    assert proposal["input_boundary"]["default_scope"] == "bounded_repolens_metadata"
    assert set(proposal["input_boundary"]["excluded_material"]) >= {
        "source_bodies",
        "raw_comments",
        "raw_secrets",
        "raw_agent_guidance_text",
        "credential_values",
    }
    assert proposal["source_disclosure"]["source_text_included"] is False
    assert proposal["source_disclosure"]["raw_comments_included"] is False
    assert proposal["source_disclosure"]["raw_secrets_included"] is False
    assert proposal["source_disclosure"]["raw_agent_guidance_text_included"] is False
    assert proposal["deterministic_evidence"]["first_read_files"][0]["path"] == (
        "src/auth/login.ts"
    )
    assert proposal["ai_interpretation"]["summary"]
    serialized = json.dumps(cli_envelope, sort_keys=True)
    assert "cli-secret-204" not in serialized
    assert "CLI_SOURCE_BODY_SENTINEL_204" not in serialized
    assert "CLI_RAW_COMMENT_SENTINEL_204" not in serialized


def test_create_ai_proposal_cli_json_returns_architecture_explanation(tmp_path):
    _write_architecture_fixture_repo(tmp_path)
    index_repository(tmp_path)

    result = runner.invoke(
        app,
        [
            "create-ai-proposal",
            str(tmp_path),
            "architecture_explanation",
            "--target",
            "src/app/main.ts",
            "--enable-ai",
            "--provider",
            "test",
            "--model",
            "architecture-explanation-v1",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    cli_envelope = json.loads(result.output)
    assert cli_envelope["ok"] is True
    assert cli_envelope["data"]["status"] == "available"
    proposal = cli_envelope["data"]["proposal"]
    assert proposal["kind"] == "architecture_explanation"
    assert proposal["deterministic_evidence"]["target_node"]["path"] == "src/app/main.ts"
    assert proposal["evidence_refs"]


def _write_architecture_fixture_repo(root: Path) -> None:
    _write_text(root / "package.json", '{"name":"architecture-demo"}\n')
    _write_text(root / "src" / "lib" / "ambiguous.ts", "export const value = 1;\n")
    _write_text(root / "src" / "lib" / "ambiguous.tsx", "export const value = 2;\n")
    _write_text(
        root / "src" / "app" / "main.ts",
        "import ambiguous from '../lib/ambiguous';\nexport const app = ambiguous;\n",
    )


def _write_context_summary_fixture_repo(root: Path) -> None:
    _write_text(
        root / "package.json",
        dedent(
            """
            {
              "name": "auth-demo",
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
            // CLI_RAW_COMMENT_SENTINEL_204 must not leave the bounded metadata path.
            export function validateLogin(input: { user: string }) {
              return input.user.length > 0 && "CLI_SOURCE_BODY_SENTINEL_204".length > 0;
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


def _repo_paths(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in root.rglob("*")}


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
