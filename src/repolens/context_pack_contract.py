"""Context Pack v0.3 contracts and disclosure guard.

This module is intentionally data-oriented. Later Context Pack services should import
these constants instead of redefining response shapes, budgets, or safety rules.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from repolens.redaction import redact_payload, redact_text

CONTEXT_PACK_VERSION = "0.3.contract.v1"
ASSISTANT_PREFLIGHT_VERSION = "0.5.preflight.v1"

CONFIDENCE_LEVELS = ("high", "medium", "low", "none")

CONTEXT_PACK_REQUIRED_TOP_LEVEL_FIELDS = (
    "context_pack_id",
    "context_pack_version",
    "task",
    "task_fingerprint",
    "budget",
    "freshness",
    "first_read_files",
    "likely_tests",
    "supporting_docs",
    "supporting_configs",
    "agent_guidance",
    "candidate_verification_commands",
    "risk_signals",
    "lower_priority_context",
    "ambiguity",
    "expansion_handles",
    "next_actions",
    "truncation",
)

MCP_ENVELOPE_REQUIRED_FIELDS = (
    "ok",
    "data",
    "confidence",
    "evidence",
    "freshness",
    "limits",
    "truncation",
    "warnings",
)

ASSISTANT_PREFLIGHT_REQUIRED_TOP_LEVEL_FIELDS = (
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
)

ASSISTANT_PREFLIGHT_CONTRACT = {
    "purpose": "bounded_assistant_orientation_before_broad_repository_reads",
    "shared_surfaces": ("cli_preflight", "mcp_assistant_preflight"),
    "budget_units": ("items", "characters"),
    "forbidden_budget_units": ("model_specific_tokens",),
    "default_context_pack_enrichment": "none",
    "opt_in_enrichment_reserved_for_later": True,
    "opt_in_enrichment_option": "include_experimental_semantic_hints",
}

CONTEXT_PACK_ITEM_KINDS = (
    "first_read_file",
    "likely_test",
    "supporting_doc",
    "supporting_config",
    "agent_guidance",
    "candidate_verification_command",
    "risk_signal",
    "lower_priority_context",
    "ambiguity_candidate",
)

CONTEXT_PACK_ITEM_REQUIRED_FIELDS = (
    "handle",
    "kind",
    "path",
    "reason",
    "confidence",
    "evidence",
    "freshness",
)

FIRST_READ_FILE_REQUIRED_FIELDS = (
    *CONTEXT_PACK_ITEM_REQUIRED_FIELDS,
    "rank",
    "symbols",
    "relationships",
    "related_tests",
)

EXPANSION_HANDLE_REQUIRED_FIELDS = (
    "handle",
    "item_kind",
    "context_pack_id",
    "reason",
    "max_depth",
)

SUPPORT_GROUPS = (
    "likely_tests",
    "supporting_docs",
    "supporting_configs",
    "agent_guidance",
    "candidate_verification_commands",
    "risk_signals",
    "lower_priority_context",
    "ambiguity",
)

DEFAULT_CONTEXT_PACK_BUDGET = {
    "max_first_read_files": 5,
    "max_items_per_support_group": 5,
    "max_next_actions": 3,
    "max_agent_guidance_items": 3,
    "max_candidate_verification_commands": 5,
    "max_risk_signals": 5,
    "max_total_chars": 12_000,
    "approx_token_estimate_divisor": 4,
}

TRUNCATION_REQUIRED_FIELDS = ("truncated", "fields")

RANKING_CONTRACT = {
    "inputs": (
        "canonical_graph_hash",
        "context_pack_version",
        "normalized_redacted_task_fingerprint",
        "focus_hints",
        "budget_parameters",
        "graph_relationships",
        "indexed_symbols_docs_configs_commands",
        "freshness_metadata",
    ),
    "scoring_categories": (
        "direct_path_or_symbol_match",
        "focus_hint_match",
        "graph_relationship_strength",
        "task_token_match",
        "related_test_or_config_evidence",
        "freshness_penalty",
        "ambiguity_penalty",
    ),
    "confidence_treatment": (
        "high_confidence_items_sort_before_medium_when_scores_tie",
        "medium_confidence_items_sort_before_low_when_scores_tie",
        "low_confidence_items_may_appear_as_candidates_or_lower_priority_context",
        "none_confidence_is_reserved_for unavailable_or_unusable_context",
    ),
    "stable_tie_breakers": (
        "item_kind_priority",
        "repo_relative_posix_path",
        "qualified_symbol_name",
        "line_range_start",
        "stable_graph_node_id",
        "handle",
    ),
    "broad_task_behavior": "return_bounded_pack_with_breadth_warning_not_repository_dump",
    "no_match_behavior": "return_successful_low_confidence_pack_without_broad_dump",
    "ambiguous_task_behavior": "return_candidates_instead_of_silently_selecting_one",
}

ID_AND_HANDLE_RULES = {
    "must_be_deterministic": True,
    "must_be_pack_scoped": True,
    "allowed_inputs": (
        "canonical_graph_hash",
        "context_pack_version",
        "normalized_redacted_task_fingerprint",
        "focus_hints",
        "budget_parameters",
        "stable_item_identity",
    ),
    "forbidden_material": (
        "raw_task_text",
        "secret_like_task_fragments",
        "absolute_paths",
        "source_snippets",
        "serialized_source_derived_payloads",
        "assistant_session_state",
    ),
}

HUMAN_LOWER_PRIORITY_LABEL = "Lower-priority context to inspect later"

FORBIDDEN_CONTEXT_PACK_FIELD_NAMES = frozenset(
    {
        "absolute_path",
        "body",
        "code",
        "code_body",
        "comment_text",
        "contents",
        "file_contents",
        "function_body",
        "function_signature",
        "method_body",
        "method_signature",
        "paragraph_excerpt",
        "raw_agent_guidance",
        "raw_comment_text",
        "raw_source",
        "raw_task_text",
        "serialized_source_payload",
        "session_id",
        "signature",
        "snippet",
        "snippets",
        "source_code",
        "source_text",
        "task_text",
    }
)

_ABSOLUTE_PATH_RE = re.compile(r"^(?:/|[A-Za-z]:[\\/])")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b[A-Z0-9_.-]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API[_-]?KEY|AUTH|PRIVATE[_-]?KEY)"
    r"[A-Z0-9_.-]*\b\s*[:=]\s*[^\s,;]+"
)
_CODE_BODY_RE = re.compile(r"(?s)(?:^|\n)\s*(?:def|class|function|const|let|var)\s+[^\n]+[{:]")


class ContextPackDisclosureError(ValueError):
    """Raised when Context Pack output contains forbidden source-bearing material."""

    def __init__(self, violations: Sequence[str]):
        self.violations = tuple(violations)
        super().__init__("Context Pack output failed No Whole-Source Disclosure guard.")


def guard_context_pack_output(
    payload: Mapping[str, Any], *, sanitize: bool = False
) -> dict[str, Any]:
    """Apply the central No Whole-Source Disclosure guard to Context Pack output.

    By default the guard rejects unsafe output. With ``sanitize=True`` it omits
    forbidden fields and redacts secret-looking text while preserving safe metadata.
    """
    sanitized, violations = _guard_value(redact_payload(dict(payload)), path="$", sanitize=sanitize)
    if violations and not sanitize:
        raise ContextPackDisclosureError(violations)
    if isinstance(sanitized, dict):
        return sanitized
    return {}


def _guard_value(value: Any, *, path: str, sanitize: bool) -> tuple[Any, list[str]]:
    violations: list[str] = []
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if path == "$.error" and key_text == "code":
                result[key_text] = child
                continue
            if key_text in FORBIDDEN_CONTEXT_PACK_FIELD_NAMES:
                violations.append(f"{child_path}: forbidden field")
                if sanitize:
                    continue
            guarded_child, child_violations = _guard_value(
                child, path=child_path, sanitize=sanitize
            )
            violations.extend(child_violations)
            result[key_text] = guarded_child
        return result, violations
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = []
        for index, child in enumerate(value):
            guarded_child, child_violations = _guard_value(
                child, path=f"{path}[{index}]", sanitize=sanitize
            )
            violations.extend(child_violations)
            items.append(guarded_child)
        return items, violations
    if isinstance(value, str):
        string_violations = _string_violations(value, path=path)
        violations.extend(string_violations)
        if sanitize and string_violations:
            return redact_text(value), violations
    return value, violations


def _string_violations(value: str, *, path: str) -> list[str]:
    violations: list[str] = []
    if not path.endswith(".route_path") and _ABSOLUTE_PATH_RE.match(value):
        violations.append(f"{path}: absolute path")
    if _SECRET_ASSIGNMENT_RE.search(value):
        violations.append(f"{path}: secret-like text")
    if _CODE_BODY_RE.search(value):
        violations.append(f"{path}: source-like body")
    return violations
