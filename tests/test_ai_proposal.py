from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from textwrap import dedent

from repolens.ai_proposal import create_ai_proposal
from repolens.context_pack import get_task_context
from repolens.context_pack_contract import CONTEXT_PACK_VERSION
from repolens.graph import GRAPH_SCHEMA_VERSION
from repolens.indexer import index_repository
from repolens.redaction import REDACTION_POLICY_VERSION

TEST_PROVIDER = "test"
TEST_MODEL = "context-pack-summary-v1"
TASK = "Summarize auth login context without exposing API_TOKEN=task-secret-204"

FORBIDDEN_DISCLOSURES = (
    "SOURCE_BODY_SENTINEL_204",
    "RAW_COMMENT_SENTINEL_204",
    "RAW_AGENT_GUIDANCE_SENTINEL_204",
    "source-secret-204",
    "env-secret-204",
    "task-secret-204",
)


def test_context_pack_summary_test_provider_returns_available_contract_without_source_disclosure(
    tmp_path,
):
    _write_ai_proposal_fixture_repo(tmp_path)
    index_repository(tmp_path)

    envelope = create_ai_proposal(
        tmp_path,
        kind="context_pack_summary",
        task=TASK,
        enable_ai=True,
        provider=TEST_PROVIDER,
        model=TEST_MODEL,
    )

    proposal = _assert_available_context_pack_summary(envelope, tmp_path)
    deterministic_evidence = proposal["deterministic_evidence"]
    ai_interpretation = proposal["ai_interpretation"]

    assert deterministic_evidence != ai_interpretation
    assert deterministic_evidence["context_pack_id"].startswith("cp_")
    assert [item["path"] for item in deterministic_evidence["first_read_files"]] == [
        "src/auth/login.ts"
    ]
    assert ai_interpretation["summary"]
    assert proposal["evidence_refs"]
    _assert_no_forbidden_disclosures(envelope)


def test_context_pack_summary_input_digest_is_stable_and_changes_with_bounded_metadata(
    tmp_path,
):
    _write_ai_proposal_fixture_repo(tmp_path)
    index_repository(tmp_path)

    first = create_ai_proposal(
        tmp_path,
        kind="context_pack_summary",
        task=TASK,
        enable_ai=True,
        provider=TEST_PROVIDER,
        model=TEST_MODEL,
    )
    second = create_ai_proposal(
        tmp_path,
        kind="context_pack_summary",
        task=TASK,
        enable_ai=True,
        provider=TEST_PROVIDER,
        model=TEST_MODEL,
    )

    first_digest = _proposal(first)["input_digest"]
    assert second == first
    assert _proposal(second)["input_digest"] == first_digest

    _write_text(
        tmp_path / "src" / "auth" / "login.ts",
        dedent(
            """
            // RAW_COMMENT_SENTINEL_204 must stay out of proposals.
            export function validateLogin(input: { user: string }) {
              const marker = "SOURCE_BODY_SENTINEL_204";
              return input.user.length > 0 && marker.length > 0;
            }

            export function loginFlow(input: { user: string }) {
              return validateLogin(input);
            }

            export function describeLoginBoundary() {
              return "metadata changed without disclosing source bodies";
            }
            """
        ).lstrip(),
    )
    index_repository(tmp_path)

    changed = create_ai_proposal(
        tmp_path,
        kind="context_pack_summary",
        task=TASK,
        enable_ai=True,
        provider=TEST_PROVIDER,
        model=TEST_MODEL,
    )

    assert _proposal(changed)["input_digest"] != first_digest
    _assert_no_forbidden_disclosures(changed)


def test_context_pack_summary_creation_does_not_mutate_context_pack_graph_artifacts_or_user_files(
    tmp_path,
):
    _write_ai_proposal_fixture_repo(tmp_path)
    index_repository(tmp_path)
    before_pack = get_task_context(tmp_path, TASK)["data"]
    before_first_read_paths = [item["path"] for item in before_pack["first_read_files"]]
    before_graph_hash = _metadata_value(tmp_path, "canonical_graph_hash")
    before_artifacts = _artifact_bytes(tmp_path)
    before_user_files = _user_file_bytes(tmp_path)

    envelope = create_ai_proposal(
        tmp_path,
        kind="context_pack_summary",
        task=TASK,
        enable_ai=True,
        provider=TEST_PROVIDER,
        model=TEST_MODEL,
    )

    _assert_available_context_pack_summary(envelope, tmp_path)
    after_pack = get_task_context(tmp_path, TASK)["data"]
    assert after_pack["context_pack_id"] == before_pack["context_pack_id"]
    assert [item["path"] for item in after_pack["first_read_files"]] == before_first_read_paths
    assert _metadata_value(tmp_path, "canonical_graph_hash") == before_graph_hash
    assert _artifact_bytes(tmp_path) == before_artifacts
    assert _user_file_bytes(tmp_path) == before_user_files


def test_architecture_explanation_returns_metadata_only_target_explanation(tmp_path):
    _write_architecture_fixture_repo(tmp_path)
    index_repository(tmp_path)
    before_graph_hash = _metadata_value(tmp_path, "canonical_graph_hash")
    before_artifacts = _artifact_bytes(tmp_path)

    envelope = create_ai_proposal(
        tmp_path,
        kind="architecture_explanation",
        target="src/app/main.ts",
        enable_ai=True,
        provider=TEST_PROVIDER,
        model="architecture-explanation-v1",
    )

    assert envelope["ok"] is True
    data = envelope["data"]
    assert data["status"] == "available"
    assert data["kind"] == "architecture_explanation"
    proposal = data["proposal"]
    assert isinstance(proposal, Mapping)
    assert proposal["kind"] == "architecture_explanation"
    assert proposal["input_packer_version"] == "0.8.architecture_explanation_input.v1"
    assert proposal["input_digest"].startswith("sha256:")
    assert proposal["graph_schema_version"] == GRAPH_SCHEMA_VERSION
    assert proposal["evidence_refs"]
    assert proposal["deterministic_evidence"]["target_node"]["path"] == "src/app/main.ts"
    assert proposal["ai_interpretation"]["responsibilities"]
    assert any("Semantic fact types" in item for item in proposal["limitations"])
    assert any("No ownership" in item for item in proposal["limitations"])
    _assert_boundary_excludes_source_material(proposal)
    assert _metadata_value(tmp_path, "canonical_graph_hash") == before_graph_hash
    assert _artifact_bytes(tmp_path) == before_artifacts


def test_architecture_explanation_surfaces_relationship_candidates_and_warnings(tmp_path):
    _write_architecture_fixture_repo(tmp_path)
    index_repository(tmp_path)

    envelope = create_ai_proposal(
        tmp_path,
        kind="architecture_explanation",
        target="src/app/main.ts",
        enable_ai=True,
        provider=TEST_PROVIDER,
        model="architecture-explanation-v1",
    )

    proposal = _proposal(envelope)
    deterministic = proposal["deterministic_evidence"]
    assert deterministic["relationship_candidates"]
    assert "graph_quality:ambiguous_import_relationship" in deterministic["graph_quality_warnings"]
    assert any(
        "graph_quality:javascript_unresolved_import_relationships" in warning
        for warning in proposal["warnings"]
    )


def test_architecture_explanation_validates_missing_target(tmp_path):
    _write_architecture_fixture_repo(tmp_path)
    index_repository(tmp_path)

    envelope = create_ai_proposal(
        tmp_path,
        kind="architecture_explanation",
        enable_ai=True,
        provider=TEST_PROVIDER,
        model="architecture-explanation-v1",
    )

    assert envelope["ok"] is True
    assert envelope["data"]["status"] == "unavailable"
    assert envelope["data"]["reason"]["code"] == "missing_target"
    assert envelope["data"]["proposal"] is None


def test_context_pack_summary_provider_error_is_structured_and_redacted(tmp_path):
    _write_ai_proposal_fixture_repo(tmp_path)
    index_repository(tmp_path)

    envelope = create_ai_proposal(
        tmp_path,
        kind="context_pack_summary",
        task="Summarize auth context with API_TOKEN=provider-error-secret-204",
        enable_ai=True,
        provider=TEST_PROVIDER,
        model="raise-provider-error",
    )

    assert envelope["ok"] is True
    data = envelope["data"]
    assert data["status"] == "unavailable"
    assert data["kind"] == "context_pack_summary"
    assert data["reason"]["code"] == "provider_error"
    provider = data["provider"]
    assert provider["configured"] is True
    assert provider["name"] == TEST_PROVIDER
    assert provider["model"] == "raise-provider-error"
    assert data["proposal"] is None
    assert any("provider error" in warning.lower() for warning in envelope["warnings"])

    serialized = json.dumps(envelope, sort_keys=True)
    assert "provider-error-secret-204" not in serialized
    assert "RAW_PROVIDER_ERROR_PAYLOAD" not in serialized
    assert "Traceback" not in serialized
    assert "test-provider-api-key" not in serialized

    assert "provider-secret" not in serialized
    assert "raw-provider-secret" not in serialized
    assert "<redacted>" in serialized


def _assert_available_context_pack_summary(
    envelope: Mapping[str, object], root: Path
) -> Mapping[str, object]:
    assert envelope["ok"] is True
    data = envelope["data"]
    assert isinstance(data, Mapping)
    assert data["status"] == "available"
    assert data["kind"] == "context_pack_summary"
    provider = data["provider"]
    assert provider["configured"] is True
    assert provider["name"] == TEST_PROVIDER
    assert provider["model"] == TEST_MODEL

    proposal = data["proposal"]
    assert isinstance(proposal, Mapping)
    assert proposal.keys() >= {
        "ai_interpretation",
        "canonical_graph_hash",
        "confidence",
        "context_pack_version",
        "deterministic_evidence",
        "evidence_refs",
        "graph_schema_version",
        "input_boundary",
        "input_digest",
        "input_packer_version",
        "kind",
        "limitations",
        "proposal_schema_version",
        "provider",
        "redaction_policy_version",
        "source_disclosure",
        "warnings",
    }
    assert proposal["kind"] == "context_pack_summary"
    proposal_provider = proposal["provider"]
    assert proposal_provider["name"] == TEST_PROVIDER
    assert proposal_provider["model"] == TEST_MODEL
    assert proposal["redaction_policy_version"] == REDACTION_POLICY_VERSION
    assert proposal["context_pack_version"] == CONTEXT_PACK_VERSION
    assert proposal["graph_schema_version"] == GRAPH_SCHEMA_VERSION
    assert proposal["canonical_graph_hash"] == _metadata_value(root, "canonical_graph_hash")
    assert proposal["input_digest"].startswith("sha256:")

    _assert_boundary_excludes_source_material(proposal)
    return proposal


def _proposal(envelope: Mapping[str, object]) -> Mapping[str, object]:
    proposal = envelope["data"]["proposal"]
    assert isinstance(proposal, Mapping)
    return proposal


def _assert_no_forbidden_disclosures(envelope: Mapping[str, object]) -> None:
    serialized = json.dumps(envelope, sort_keys=True)
    for forbidden in FORBIDDEN_DISCLOSURES:
        assert forbidden not in serialized


def _assert_boundary_excludes_source_material(proposal: Mapping[str, object]) -> None:
    boundary = proposal["input_boundary"]
    assert isinstance(boundary, Mapping)
    assert boundary["default_scope"] == "bounded_repolens_metadata"
    assert boundary["source_text_included"] is False
    assert boundary["raw_prompt_persisted"] is False
    assert set(boundary["excluded_material"]) >= {
        "source_bodies",
        "raw_comments",
        "raw_secrets",
        "raw_agent_guidance_text",
        "credential_values",
        "raw_provider_error_payloads",
    }

    disclosure = proposal["source_disclosure"]
    assert isinstance(disclosure, Mapping)
    assert disclosure["source_text_included"] is False
    assert disclosure["raw_comments_included"] is False
    assert disclosure["raw_secrets_included"] is False
    assert disclosure["raw_agent_guidance_text_included"] is False
    assert disclosure["credential_values_included"] is False
    assert disclosure["provider_error_payload_included"] is False


def _write_architecture_fixture_repo(root: Path) -> None:
    _write_text(root / "package.json", '{"name":"architecture-demo"}\n')
    _write_text(root / "src" / "lib" / "ambiguous.ts", "export const value = 1;\n")
    _write_text(root / "src" / "lib" / "ambiguous.tsx", "export const value = 2;\n")
    _write_text(
        root / "src" / "app" / "main.ts",
        "import ambiguous from '../lib/ambiguous';\nexport const app = ambiguous;\n",
    )


def _write_ai_proposal_fixture_repo(root: Path) -> None:
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
        root / "AGENTS.md",
        "# Agent Notes\n\nRAW_AGENT_GUIDANCE_SENTINEL_204 must not appear in proposals.\n",
    )
    _write_text(root / ".env", "API_TOKEN=env-secret-204\n")
    _write_text(
        root / "README.md",
        "# Auth Demo\n\nLogin validation lives in `src/auth/login.ts`.\n",
    )
    _write_text(
        root / "src" / "auth" / "login.ts",
        dedent(
            """
            // RAW_COMMENT_SENTINEL_204 must stay out of proposals.
            export function validateLogin(input: { user: string }) {
              const marker = "SOURCE_BODY_SENTINEL_204";
              const token = "API_TOKEN=source-secret-204";
              return input.user.length > 0 && marker.length > 0 && token.length > 0;
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


def _artifact_bytes(root: Path) -> dict[str, bytes]:
    artifact_root = root / ".repolens"
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(artifact_root.rglob("*"))
        if path.is_file()
    }


def _user_file_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".repolens" not in path.relative_to(root).parts
    }


def _metadata_value(root: Path, key: str) -> str:
    with sqlite3.connect(root / ".repolens" / "graph.sqlite") as connection:
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = ?",
            (key,),
        ).fetchone()
    assert row is not None
    return str(row[0])


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
