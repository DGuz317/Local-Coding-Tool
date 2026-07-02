from __future__ import annotations

import json
from pathlib import Path

import pytest

from repolens.context_pack_contract import (
    ASSISTANT_PREFLIGHT_CONTRACT,
    ASSISTANT_PREFLIGHT_REQUIRED_TOP_LEVEL_FIELDS,
    ASSISTANT_PREFLIGHT_VERSION,
    CONTEXT_PACK_ITEM_REQUIRED_FIELDS,
    CONTEXT_PACK_REQUIRED_TOP_LEVEL_FIELDS,
    DEFAULT_CONTEXT_PACK_BUDGET,
    HUMAN_LOWER_PRIORITY_LABEL,
    ID_AND_HANDLE_RULES,
    MCP_ENVELOPE_REQUIRED_FIELDS,
    RANKING_CONTRACT,
    SUPPORT_GROUPS,
    ContextPackDisclosureError,
    guard_context_pack_output,
)


def test_context_pack_schema_contract_names_required_pack_and_mcp_fields():
    assert "context_pack_id" in CONTEXT_PACK_REQUIRED_TOP_LEVEL_FIELDS
    assert "first_read_files" in CONTEXT_PACK_REQUIRED_TOP_LEVEL_FIELDS
    assert "expansion_handles" in CONTEXT_PACK_REQUIRED_TOP_LEVEL_FIELDS
    assert "confidence" in CONTEXT_PACK_ITEM_REQUIRED_FIELDS
    assert "evidence" in CONTEXT_PACK_ITEM_REQUIRED_FIELDS
    assert set(MCP_ENVELOPE_REQUIRED_FIELDS) == {
        "ok",
        "data",
        "confidence",
        "evidence",
        "freshness",
        "limits",
        "truncation",
        "warnings",
    }


def test_assistant_preflight_schema_contract_is_bounded_and_shared():
    assert ASSISTANT_PREFLIGHT_VERSION == "0.5.preflight.v1"
    assert set(ASSISTANT_PREFLIGHT_REQUIRED_TOP_LEVEL_FIELDS) == {
        "assistant_preflight_version",
        "context_pack_id",
        "context_pack_version",
        "task_context",
        "focus_hints",
        "budget_controls",
        "freshness",
        "first_read_files",
        "likely_tests",
        "candidate_verification_commands",
        "ambiguity",
        "warnings",
        "evidence",
        "confidence",
        "limits",
        "truncation",
    }
    assert ASSISTANT_PREFLIGHT_CONTRACT["budget_units"] == ("items", "characters")
    assert "model_specific_tokens" in ASSISTANT_PREFLIGHT_CONTRACT["forbidden_budget_units"]
    assert ASSISTANT_PREFLIGHT_CONTRACT["default_context_pack_enrichment"] == "none"
    assert ASSISTANT_PREFLIGHT_CONTRACT["opt_in_enrichment_reserved_for_later"] is True


def test_context_pack_budget_contract_sets_explicit_support_group_caps():
    assert DEFAULT_CONTEXT_PACK_BUDGET == {
        "max_first_read_files": 5,
        "max_items_per_support_group": 5,
        "max_next_actions": 3,
        "max_agent_guidance_items": 3,
        "max_candidate_verification_commands": 5,
        "max_risk_signals": 5,
        "max_total_chars": 12_000,
        "approx_token_estimate_divisor": 4,
    }
    assert "agent_guidance" in SUPPORT_GROUPS
    assert "lower_priority_context" in SUPPORT_GROUPS


def test_ranking_and_handle_contracts_are_deterministic_and_safe():
    assert "canonical_graph_hash" in RANKING_CONTRACT["inputs"]
    assert "stable_graph_node_id" in RANKING_CONTRACT["stable_tie_breakers"]
    assert RANKING_CONTRACT["broad_task_behavior"].endswith("not_repository_dump")
    assert RANKING_CONTRACT["no_match_behavior"].endswith("without_broad_dump")
    assert RANKING_CONTRACT["ambiguous_task_behavior"].startswith("return_candidates")
    assert ID_AND_HANDLE_RULES["must_be_deterministic"] is True
    assert "raw_task_text" in ID_AND_HANDLE_RULES["forbidden_material"]
    assert "absolute_paths" in ID_AND_HANDLE_RULES["forbidden_material"]
    assert "assistant_session_state" in ID_AND_HANDLE_RULES["forbidden_material"]


def test_human_contract_uses_lower_priority_wording_not_ignore_language():
    assert HUMAN_LOWER_PRIORITY_LABEL == "Lower-priority context to inspect later"
    assert "ignore" not in HUMAN_LOWER_PRIORITY_LABEL.lower()
    assert "irrelevant" not in HUMAN_LOWER_PRIORITY_LABEL.lower()
    assert "safe to skip" not in HUMAN_LOWER_PRIORITY_LABEL.lower()


def test_context_pack_disclosure_guard_rejects_forbidden_source_bearing_fields():
    payload = {
        "data": {
            "context_pack_id": "cp_123",
            "first_read_files": [
                {
                    "path": "src/repolens/query.py",
                    "snippet": "def leak():\n    return 'source'",
                }
            ],
        }
    }

    with pytest.raises(ContextPackDisclosureError) as exc_info:
        guard_context_pack_output(payload)

    assert "$.data.first_read_files[0].snippet: forbidden field" in exc_info.value.violations


def test_context_pack_disclosure_guard_redacts_or_omits_when_sanitizing():
    payload = {
        "data": {
            "handle": "item_1",
            "raw_task_text": "Fix API_TOKEN=abc123",
            "reason": "TOKEN=abc123 relates to src/auth.py",
        }
    }

    guarded = guard_context_pack_output(payload, sanitize=True)

    assert "raw_task_text" not in guarded["data"]
    assert guarded["data"]["reason"] == "TOKEN=<redacted> relates to src/auth.py"
    assert "abc123" not in str(guarded)


def test_context_pack_disclosure_guard_rejects_absolute_paths_in_output():
    with pytest.raises(ContextPackDisclosureError) as exc_info:
        guard_context_pack_output({"data": {"path": "/home/user/project/src/app.py"}})

    assert "$.data.path: absolute path" in exc_info.value.violations


def test_context_pack_disclosure_guard_allows_standard_mcp_error_code():
    guarded = guard_context_pack_output(
        {
            "data": {},
            "error": {
                "code": "context_pack_id_mismatch",
                "message": "Request a fresh Context Pack.",
            },
        }
    )

    assert guarded["error"]["code"] == "context_pack_id_mismatch"


def test_context_pack_fixture_manifest_names_required_case_families():
    manifest_path = Path("tests/fixtures/context_pack/evaluation_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    release_categories = {
        case["category"]
        for case in manifest["cases"]
        if case.get("corpus", "release_blocking") == "release_blocking"
    }
    expanded_categories = {
        case["category"] for case in manifest["cases"] if case.get("corpus") == "expanded"
    }

    assert release_categories == {
        "happy_path",
        "test_focused",
        "documentation_config",
        "broad_task",
        "focal_ambiguity",
        "navigation_gap",
        "no_match",
        "focus_hint",
        "stale_graph",
        "secret_redaction",
        "stale_pack",
        "no_source_disclosure",
        "regression_v0_3_1",
        "package_workspace",
        "ambiguity",
        "command_classification",
    }
    assert expanded_categories == {"cli_export"}
    assert manifest["default_budget"] == DEFAULT_CONTEXT_PACK_BUDGET
    assert all("expected_outcomes" in case for case in manifest["cases"])
