"""Read-only AI Proposal paths for RepoLens v0.8."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from repolens.context_pack import get_task_context
from repolens.context_pack_contract import CONTEXT_PACK_VERSION
from repolens.graph import GRAPH_SCHEMA_VERSION
from repolens.mcp_envelope import mcp_success, truncation_metadata
from repolens.query import GraphQueryService
from repolens.redaction import REDACTION_POLICY_VERSION, redact_payload, redact_text

AI_PROPOSAL_VERSION = "0.8.ai_proposal.v1"
AI_INPUT_PACKER_VERSION = "0.8.context_pack_summary_input.v1"
AI_ARCHITECTURE_INPUT_PACKER_VERSION = "0.8.architecture_explanation_input.v1"
AI_TEST_PROVIDER_NAME = "test"
AI_TEST_PROVIDER_ENV_VAR = "REPOLENS_AI_TEST_PROVIDER_TOKEN"
AI_TEST_PROVIDER_ERROR_MODEL = "raise-provider-error"
AI_PROPOSAL_SUPPORTED_KINDS = frozenset(
    {
        "architecture_explanation",
        "context_pack_summary",
        "patch_plan",
    }
)

_NO_ACTION_SAFETY_FLAGS = {
    "provider_called": False,
    "network_accessed": False,
    "file_written": False,
    "command_executed": False,
    "patch_applied": False,
    "remote_posted": False,
}
_TEST_PROVIDER_SAFETY_FLAGS = {
    **_NO_ACTION_SAFETY_FLAGS,
    "provider_called": True,
}
_SOURCE_DISCLOSURE = {
    "source_text_included": False,
    "raw_comments_included": False,
    "raw_secrets_included": False,
    "raw_agent_guidance_text_included": False,
    "large_raw_documents_included": False,
    "credential_values_included": False,
    "provider_error_payload_included": False,
}
_INPUT_EXCLUDED_MATERIAL = (
    "source_bodies",
    "raw_comments",
    "raw_secrets",
    "raw_agent_guidance_text",
    "large_raw_documents",
    "credential_values",
    "raw_provider_error_payloads",
)
_INPUT_BOUNDARY = {
    "default_scope": "bounded_repolens_metadata",
    "source_text_included": False,
    "raw_prompt_persisted": False,
    "excluded_material": _INPUT_EXCLUDED_MATERIAL,
}
_PROPOSAL_LIMITATIONS = [
    "AI interpretation is outside the trusted deterministic graph.",
    "The proposal does not change Context Pack ranking, resolver behavior, or graph artifacts.",
    "The test provider is local and deterministic; it does not prove external model quality.",
]


class _AIProviderError(Exception):
    """Provider failure carrying a raw payload that must not cross output boundaries."""


def create_ai_proposal(
    repo_path: Path | str,
    kind: str,
    *,
    task: str | None = None,
    context_pack_id: str | None = None,
    target: str | None = None,
    enable_ai: bool = False,
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Return a v0.8 AI Proposal envelope without hidden provider fallback."""
    repo_root = Path(repo_path)
    normalized_kind = _normalize_kind(kind)
    provider_config = _provider_config(enable_ai=enable_ai, provider=provider, model=model)

    if normalized_kind not in AI_PROPOSAL_SUPPORTED_KINDS:
        return _proposal_envelope(
            repo_root=repo_root,
            kind=normalized_kind,
            status="unsupported_kind",
            reason="unsupported_kind",
            provider_config=provider_config,
            task=task,
            context_pack_id=context_pack_id,
            target=target,
            warnings=[
                "Unsupported AI Proposal kind; no provider fallback or provider call was attempted."
            ],
        )

    if not enable_ai:
        return _proposal_envelope(
            repo_root=repo_root,
            kind=normalized_kind,
            status="disabled",
            reason="ai_disabled",
            provider_config=provider_config,
            task=task,
            context_pack_id=context_pack_id,
            target=target,
            warnings=["AI Proposal requests are disabled by default."],
        )

    if not provider_config["configured"]:
        return _proposal_envelope(
            repo_root=repo_root,
            kind=normalized_kind,
            status="unavailable",
            reason="provider_unconfigured",
            provider_config=provider_config,
            task=task,
            context_pack_id=context_pack_id,
            target=target,
            warnings=["AI Proposal requests require explicit provider and model configuration."],
        )

    if normalized_kind not in {"architecture_explanation", "context_pack_summary"}:
        return _proposal_envelope(
            repo_root=repo_root,
            kind=normalized_kind,
            status="unavailable",
            reason="provider_execution_unavailable",
            provider_config=provider_config,
            task=task,
            context_pack_id=context_pack_id,
            target=target,
            warnings=[
                "This AI Proposal kind has no configured provider path in this slice; "
                "no provider fallback was attempted."
            ],
        )

    if provider_config["name"] != AI_TEST_PROVIDER_NAME:
        return _proposal_envelope(
            repo_root=repo_root,
            kind=normalized_kind,
            status="unavailable",
            reason="provider_unsupported",
            provider_config=provider_config,
            task=task,
            context_pack_id=context_pack_id,
            target=target,
            warnings=["Configured provider is not supported by this local RepoLens slice."],
        )

    if normalized_kind == "architecture_explanation":
        return _create_architecture_explanation_proposal(
            repo_root,
            task=task,
            context_pack_id=context_pack_id,
            target=target,
            provider_config=provider_config,
        )

    if not task:
        return _proposal_envelope(
            repo_root=repo_root,
            kind=normalized_kind,
            status="unavailable",
            reason="missing_task",
            provider_config=provider_config,
            task=task,
            context_pack_id=context_pack_id,
            target=target,
            warnings=["Context Pack Summary Proposals require a task to rebuild bounded input."],
        )

    context_envelope = get_task_context(repo_root, task)
    if not context_envelope.get("ok", False):
        return _proposal_envelope(
            repo_root=repo_root,
            kind=normalized_kind,
            status="unavailable",
            reason="context_pack_unavailable",
            provider_config=provider_config,
            task=task,
            context_pack_id=context_pack_id,
            target=target,
            warnings=[
                "Context Pack metadata is unavailable; run repolens index before requesting "
                "a Context Pack Summary Proposal."
            ],
        )

    context_pack = _mapping(context_envelope.get("data"))
    generated_pack_id = str(context_pack.get("context_pack_id", ""))
    if context_pack_id and context_pack_id != generated_pack_id:
        return _proposal_envelope(
            repo_root=repo_root,
            kind=normalized_kind,
            status="unavailable",
            reason="context_pack_id_mismatch",
            provider_config=provider_config,
            task=task,
            context_pack_id=context_pack_id,
            target=target,
            warnings=[
                "Requested Context Pack ID does not match the deterministic pack rebuilt "
                "from the supplied task."
            ],
        )

    packed_input = _pack_context_pack_summary_input(context_envelope)
    input_digest = _input_digest(packed_input)
    try:
        proposal = _test_provider_context_pack_summary(
            packed_input,
            provider_config=provider_config,
            input_digest=input_digest,
        )
    except _AIProviderError as exc:
        return _proposal_envelope(
            repo_root=repo_root,
            kind=normalized_kind,
            status="unavailable",
            reason="provider_error",
            provider_config=provider_config,
            task=task,
            context_pack_id=context_pack_id or generated_pack_id,
            target=target,
            warnings=[
                "AI provider returned an error; raw provider payload was redacted.",
                f"Redacted provider error: {redact_text(str(exc))}",
            ],
            safety=_TEST_PROVIDER_SAFETY_FLAGS,
        )

    return _proposal_envelope(
        repo_root=repo_root,
        kind=normalized_kind,
        status="available",
        reason="proposal_available",
        provider_config=provider_config,
        task=task,
        context_pack_id=context_pack_id or generated_pack_id,
        target=target,
        warnings=list(proposal["warnings"]),
        proposal=proposal,
        context_freshness=_mapping(context_envelope.get("freshness")),
        context_limits=_mapping(context_envelope.get("limits")),
        context_truncation=_mapping(context_envelope.get("truncation")),
        safety=_TEST_PROVIDER_SAFETY_FLAGS,
    )


def human_ai_proposal(envelope: Mapping[str, Any]) -> str:
    """Render a compact human summary for the CLI."""
    if not envelope.get("ok", False):
        error = envelope.get("error")
        message = "unknown error"
        if isinstance(error, Mapping):
            message = str(error.get("message", message))
        return f"AI Proposal request failed: {message}\n"

    data = envelope.get("data")
    if not isinstance(data, Mapping):
        return "AI Proposal request returned no data.\n"

    provider = data.get("provider")
    provider_configured = False
    if isinstance(provider, Mapping):
        provider_configured = bool(provider.get("configured"))
    lines = [
        "AI Proposal request",
        f"Kind: {data.get('kind', '')}",
        f"Status: {data.get('status', '')}",
        f"Reason: {_reason_code(data.get('reason'))}",
        f"Provider configured: {str(provider_configured).lower()}",
    ]
    proposal = data.get("proposal")
    if isinstance(proposal, Mapping):
        lines.extend(
            [
                f"Input digest: {proposal.get('input_digest', '')}",
                f"Canonical graph hash: {proposal.get('canonical_graph_hash', '')}",
            ]
        )
    lines.append(
        "No network call, command execution, file write, patch application, or remote post "
        "was performed."
    )
    lines.append("")
    return "\n".join(lines)


def _proposal_envelope(
    *,
    repo_root: Path,
    kind: str,
    status: str,
    reason: str,
    provider_config: Mapping[str, Any],
    task: str | None,
    context_pack_id: str | None,
    target: str | None,
    warnings: list[str],
    proposal: Mapping[str, Any] | None = None,
    context_freshness: Mapping[str, Any] | None = None,
    context_limits: Mapping[str, Any] | None = None,
    context_truncation: Mapping[str, Any] | None = None,
    safety: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    data = {
        "ai_proposal_version": AI_PROPOSAL_VERSION,
        "kind": kind,
        "status": status,
        "reason": {"code": reason},
        "proposal": dict(proposal) if proposal is not None else None,
        "provider": dict(provider_config),
        "request": {
            "kind": kind,
            "repo_path": _repo_display_path(repo_root),
            "task": redact_text(task or "") if task else None,
            "context_pack_id": redact_text(context_pack_id or "") if context_pack_id else None,
            "target": redact_text(target or "") if target else None,
            "metadata_only": True,
        },
        "input_boundary": _public_input_boundary(),
        "source_disclosure": dict(_SOURCE_DISCLOSURE),
        "safety": dict(safety or _NO_ACTION_SAFETY_FLAGS),
        "supported_kinds": sorted(AI_PROPOSAL_SUPPORTED_KINDS),
    }
    confidence = "medium" if proposal is not None else "none"
    evidence = [{"source": "v0.8_ai_provider_boundary", "issue": 203}]
    if proposal is not None:
        evidence.append(
            {
                "source": f"{kind}_proposal",
                "issue": 205 if kind == "architecture_explanation" else 204,
            }
        )
    return mcp_success(
        data=data,
        confidence=confidence,
        evidence=evidence,
        freshness=context_freshness,
        limits={
            "supported_kinds": sorted(AI_PROPOSAL_SUPPORTED_KINDS),
            **dict(context_limits or {}),
        },
        truncation=context_truncation or truncation_metadata(),
        warnings=warnings,
    )


def _create_architecture_explanation_proposal(
    repo_root: Path,
    *,
    task: str | None,
    context_pack_id: str | None,
    target: str | None,
    provider_config: Mapping[str, Any],
) -> dict[str, Any]:
    if not target and not task:
        return _proposal_envelope(
            repo_root=repo_root,
            kind="architecture_explanation",
            status="unavailable",
            reason="missing_target",
            provider_config=provider_config,
            task=task,
            context_pack_id=context_pack_id,
            target=target,
            warnings=[
                "Architecture Explanation Proposals require a target or a task-backed Context Pack."
            ],
        )
    if context_pack_id and not task:
        return _proposal_envelope(
            repo_root=repo_root,
            kind="architecture_explanation",
            status="unavailable",
            reason="missing_task",
            provider_config=provider_config,
            task=task,
            context_pack_id=context_pack_id,
            target=target,
            warnings=["Context Pack targets require the task used to rebuild bounded metadata."],
        )

    context_envelope: Mapping[str, Any] | None = None
    if task:
        context_envelope = get_task_context(repo_root, task)
        if not context_envelope.get("ok", False):
            return _proposal_envelope(
                repo_root=repo_root,
                kind="architecture_explanation",
                status="unavailable",
                reason="context_pack_unavailable",
                provider_config=provider_config,
                task=task,
                context_pack_id=context_pack_id,
                target=target,
                warnings=[
                    "Context Pack metadata is unavailable; run repolens index before requesting "
                    "an Architecture Explanation Proposal."
                ],
            )
        generated_pack_id = str(_mapping(context_envelope.get("data")).get("context_pack_id", ""))
        if context_pack_id and context_pack_id != generated_pack_id:
            return _proposal_envelope(
                repo_root=repo_root,
                kind="architecture_explanation",
                status="unavailable",
                reason="context_pack_id_mismatch",
                provider_config=provider_config,
                task=task,
                context_pack_id=context_pack_id,
                target=target,
                warnings=[
                    "Requested Context Pack ID does not match the deterministic pack rebuilt "
                    "from the supplied task."
                ],
            )
        context_pack_id = context_pack_id or generated_pack_id

    packed_input = _pack_architecture_explanation_input(
        repo_root,
        task=task,
        context_envelope=context_envelope,
        target=target,
    )
    if packed_input.get("target_resolution", {}).get("status") in {"unresolved", "ambiguous"}:
        return _proposal_envelope(
            repo_root=repo_root,
            kind="architecture_explanation",
            status="unavailable",
            reason="target_unresolved",
            provider_config=provider_config,
            task=task,
            context_pack_id=context_pack_id,
            target=target,
            warnings=["Architecture Explanation target could not be resolved unambiguously."],
        )

    input_digest = _input_digest(packed_input)
    proposal = _test_provider_architecture_explanation(
        packed_input,
        provider_config=provider_config,
        input_digest=input_digest,
    )
    return _proposal_envelope(
        repo_root=repo_root,
        kind="architecture_explanation",
        status="available",
        reason="proposal_available",
        provider_config=provider_config,
        task=task,
        context_pack_id=context_pack_id,
        target=target,
        warnings=list(proposal["warnings"]),
        proposal=proposal,
        safety=_TEST_PROVIDER_SAFETY_FLAGS,
    )


def _pack_architecture_explanation_input(
    repo_root: Path,
    *,
    task: str | None,
    context_envelope: Mapping[str, Any] | None,
    target: str | None,
) -> dict[str, Any]:
    query = GraphQueryService(repo_root)
    context_pack = _mapping(context_envelope.get("data")) if context_envelope else {}
    target_ref = _clean_optional(target) or _first_context_path(context_pack) or "."
    node_envelope = query.get_node(reference=target_ref)
    node_data = _mapping(node_envelope.get("data"))
    node = _mapping(node_data.get("node"))
    resolution_status = (
        "resolved" if node else "ambiguous" if node_data.get("ambiguous") else "unresolved"
    )
    neighbors_envelope: Mapping[str, Any] = {}
    impact_envelope: Mapping[str, Any] = {}
    if node:
        node_id = str(node.get("id", target_ref))
        neighbors_envelope = query.get_neighbors(node_id=node_id, depth=1, max_results=12)
        impact_envelope = query.impact_analysis(node_id, depth=1, max_results=12)
    paths = _architecture_paths(node=node, context_pack=context_pack)
    file_metadata = query.context_pack_file_metadata(paths) if paths else {}
    packed = {
        "input_packer_version": AI_ARCHITECTURE_INPUT_PACKER_VERSION,
        "redaction_policy_version": REDACTION_POLICY_VERSION,
        "proposal_kind": "architecture_explanation",
        "request": {"task": task or "", "target": target_ref},
        "context_pack": _pack_architecture_context_pack(context_pack),
        "target_resolution": {
            "status": resolution_status,
            "reference": target_ref,
            "node": _pack_node(node),
            "candidates": [
                _pack_node(_mapping(candidate.get("node")))
                for candidate in _sequence(node_data.get("candidates"))
            ],
        },
        "neighbors": _pack_neighbors(_mapping(neighbors_envelope.get("data"))),
        "impact": _pack_impact(_mapping(impact_envelope.get("data"))),
        "file_metadata": _pack_file_metadata(_mapping(file_metadata.get("data"))),
        "envelope": {
            "evidence": _safe_evidence_refs(_sequence(node_envelope.get("evidence"))),
            "warnings": sorted(
                set(
                    str(warning)
                    for warning in [
                        *_sequence(node_envelope.get("warnings")),
                        *_sequence(neighbors_envelope.get("warnings")),
                        *_sequence(impact_envelope.get("warnings")),
                        *_sequence(file_metadata.get("warnings")),
                    ]
                )
            ),
        },
        "input_boundary": _public_input_boundary(),
        "source_disclosure": dict(_SOURCE_DISCLOSURE),
    }
    return redact_payload(packed)


def _test_provider_architecture_explanation(
    packed_input: Mapping[str, Any],
    *,
    provider_config: Mapping[str, Any],
    input_digest: str,
) -> dict[str, Any]:
    target_resolution = _mapping(packed_input.get("target_resolution"))
    node = _mapping(target_resolution.get("node"))
    neighbors = [
        _mapping(item) for item in _sequence(_mapping(packed_input.get("neighbors")).get("items"))
    ]
    file_metadata = _mapping(packed_input.get("file_metadata"))
    relationship_candidates = _flatten_relationship_candidates(file_metadata)
    graph_quality_warnings = sorted(
        set(
            str(code)
            for candidate in relationship_candidates
            for code in [candidate.get("warning_code")]
            if code
        )
    )
    warnings = [
        *[
            str(warning)
            for warning in _sequence(_mapping(packed_input.get("envelope")).get("warnings"))
        ],
        *graph_quality_warnings,
        "Generated by configured local test provider from bounded architecture metadata.",
    ]
    path = str(node.get("path") or node.get("id") or target_resolution.get("reference") or "")
    neighbor_labels = [str(item.get("label") or item.get("id")) for item in neighbors[:5]]
    evidence_refs = _architecture_evidence_refs(packed_input)
    return {
        "kind": "architecture_explanation",
        "proposal_schema_version": AI_PROPOSAL_VERSION,
        "provider": {"name": provider_config.get("name"), "model": provider_config.get("model")},
        "provenance": {
            "provider": provider_config.get("name"),
            "model": provider_config.get("model"),
            "environment": _mapping(provider_config.get("environment")),
        },
        "input_boundary": _public_input_boundary(),
        "source_disclosure": dict(_SOURCE_DISCLOSURE),
        "evidence_refs": evidence_refs,
        "confidence": "medium",
        "warnings": list(dict.fromkeys(warnings)),
        "limitations": [
            *_PROPOSAL_LIMITATIONS,
            "Semantic fact types may be unavailable; this explanation uses indexed metadata only.",
            "No ownership, dependency, route, runtime behavior, or graph facts are created.",
        ],
        "input_packer_version": AI_ARCHITECTURE_INPUT_PACKER_VERSION,
        "redaction_policy_version": REDACTION_POLICY_VERSION,
        "input_digest": input_digest,
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "target": {"reference": target_resolution.get("reference"), "node": node},
        "deterministic_evidence": {
            "label": "deterministic_architecture_metadata",
            "target_node": node,
            "neighboring_areas": neighbors,
            "relationship_candidates": relationship_candidates,
            "graph_quality_warnings": graph_quality_warnings,
        },
        "ai_interpretation": {
            "label": "ai_interpretation_not_graph_fact",
            "responsibilities": _architecture_responsibilities(path, node, neighbor_labels),
            "neighboring_areas": neighbor_labels,
            "limitations": "Explanation is bounded to RepoLens metadata and does not assert runtime behavior.",
        },
    }


def _pack_context_pack_summary_input(context_envelope: Mapping[str, Any]) -> dict[str, Any]:
    context_pack = _mapping(context_envelope.get("data"))
    freshness = _mapping(context_pack.get("freshness"))
    packed = {
        "input_packer_version": AI_INPUT_PACKER_VERSION,
        "redaction_policy_version": REDACTION_POLICY_VERSION,
        "proposal_kind": "context_pack_summary",
        "context_pack": {
            "context_pack_id": context_pack.get("context_pack_id", ""),
            "context_pack_version": context_pack.get("context_pack_version", CONTEXT_PACK_VERSION),
            "task": context_pack.get("task", ""),
            "task_fingerprint": context_pack.get("task_fingerprint", ""),
            "freshness": {
                "canonical_graph_hash": freshness.get("canonical_graph_hash", ""),
                "fresh": freshness.get("fresh"),
                "source": freshness.get("source", ""),
                "status": freshness.get("status", ""),
            },
            "budget": _mapping(context_pack.get("budget")),
            "first_read_files": [
                _pack_context_item(item) for item in _sequence(context_pack.get("first_read_files"))
            ],
            "likely_tests": [
                _pack_context_item(item) for item in _sequence(context_pack.get("likely_tests"))
            ],
            "supporting_docs": [
                _pack_context_item(item) for item in _sequence(context_pack.get("supporting_docs"))
            ],
            "supporting_configs": [
                _pack_context_item(item)
                for item in _sequence(context_pack.get("supporting_configs"))
            ],
            "agent_guidance": [
                _pack_context_item(item) for item in _sequence(context_pack.get("agent_guidance"))
            ],
            "candidate_verification_commands": [
                _pack_context_item(item)
                for item in _sequence(context_pack.get("candidate_verification_commands"))
            ],
            "risk_signals": [
                _pack_context_item(item) for item in _sequence(context_pack.get("risk_signals"))
            ],
            "lower_priority_context": [
                _pack_context_item(item)
                for item in _sequence(context_pack.get("lower_priority_context"))
            ],
            "ambiguity": [
                _pack_context_item(item) for item in _sequence(context_pack.get("ambiguity"))
            ],
            "next_actions": [str(action) for action in _sequence(context_pack.get("next_actions"))],
            "truncation": _mapping(context_pack.get("truncation")),
        },
        "envelope": {
            "confidence": str(context_envelope.get("confidence", "low")),
            "evidence": _safe_evidence_refs(_sequence(context_envelope.get("evidence"))),
            "limits": _mapping(context_envelope.get("limits")),
            "warnings": [str(warning) for warning in _sequence(context_envelope.get("warnings"))],
        },
        "input_boundary": _public_input_boundary(),
        "source_disclosure": dict(_SOURCE_DISCLOSURE),
    }
    return redact_payload(packed)


def _test_provider_context_pack_summary(
    packed_input: Mapping[str, Any],
    *,
    provider_config: Mapping[str, Any],
    input_digest: str,
) -> dict[str, Any]:
    if provider_config.get("model") == AI_TEST_PROVIDER_ERROR_MODEL:
        raise _AIProviderError(
            "test provider failure payload API_TOKEN=provider-secret "
            "{'password':'raw-provider-secret'}"
        )

    context_pack = _mapping(packed_input.get("context_pack"))
    freshness = _mapping(context_pack.get("freshness"))
    first_read_files = [_mapping(item) for item in _sequence(context_pack.get("first_read_files"))]
    likely_tests = [_mapping(item) for item in _sequence(context_pack.get("likely_tests"))]
    task = str(context_pack.get("task", ""))
    first_paths = [str(item.get("path", "")) for item in first_read_files if item.get("path")]
    test_paths = [str(item.get("path", "")) for item in likely_tests if item.get("path")]
    evidence_refs = _proposal_evidence_refs(context_pack)
    warnings = [
        str(warning)
        for warning in _sequence(_mapping(packed_input.get("envelope")).get("warnings"))
    ]
    warnings.append(
        "Generated by configured local test provider from bounded Context Pack metadata."
    )

    return {
        "kind": "context_pack_summary",
        "proposal_schema_version": AI_PROPOSAL_VERSION,
        "provider": {
            "name": provider_config.get("name"),
            "model": provider_config.get("model"),
        },
        "provenance": {
            "provider": provider_config.get("name"),
            "model": provider_config.get("model"),
            "environment": _mapping(provider_config.get("environment")),
        },
        "input_boundary": _public_input_boundary(),
        "source_disclosure": dict(_SOURCE_DISCLOSURE),
        "evidence_refs": evidence_refs,
        "confidence": "medium",
        "warnings": warnings,
        "limitations": list(_PROPOSAL_LIMITATIONS),
        "input_packer_version": AI_INPUT_PACKER_VERSION,
        "redaction_policy_version": REDACTION_POLICY_VERSION,
        "input_digest": input_digest,
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "canonical_graph_hash": freshness.get("canonical_graph_hash", ""),
        "context_pack_id": context_pack.get("context_pack_id", ""),
        "context_pack_version": context_pack.get("context_pack_version", CONTEXT_PACK_VERSION),
        "deterministic_evidence": {
            "label": "deterministic_context_pack_metadata",
            "context_pack_id": context_pack.get("context_pack_id", ""),
            "first_read_files": [_deterministic_item_evidence(item) for item in first_read_files],
            "likely_tests": [_deterministic_item_evidence(item) for item in likely_tests],
            "candidate_verification_commands": [
                _deterministic_item_evidence(item)
                for item in _sequence(context_pack.get("candidate_verification_commands"))
            ],
            "warnings": warnings[:-1],
        },
        "ai_interpretation": {
            "label": "ai_interpretation_not_structural_summary",
            "summary": _summary_sentence(task, first_paths, test_paths),
            "first_read_focus": first_paths,
            "likely_test_focus": test_paths,
            "next_actions": [str(action) for action in _sequence(context_pack.get("next_actions"))],
        },
    }


def _first_context_path(context_pack: Mapping[str, Any]) -> str | None:
    for group in ("first_read_files", "lower_priority_context", "supporting_docs"):
        for item in _sequence(context_pack.get(group)):
            path = _mapping(item).get("path")
            if path:
                return str(path)
    return None


def _architecture_paths(*, node: Mapping[str, Any], context_pack: Mapping[str, Any]) -> list[str]:
    paths: list[str] = []
    if node.get("path"):
        paths.append(str(node["path"]))
    for group in ("first_read_files", "likely_tests", "supporting_docs", "supporting_configs"):
        for item in _sequence(context_pack.get(group)):
            path = _mapping(item).get("path")
            if path:
                paths.append(str(path))
    return sorted(dict.fromkeys(paths))[:20]


def _pack_architecture_context_pack(context_pack: Mapping[str, Any]) -> dict[str, Any]:
    if not context_pack:
        return {}
    return {
        "context_pack_id": context_pack.get("context_pack_id", ""),
        "context_pack_version": context_pack.get("context_pack_version", CONTEXT_PACK_VERSION),
        "task_fingerprint": context_pack.get("task_fingerprint", ""),
        "first_read_files": [
            _pack_context_item(item) for item in _sequence(context_pack.get("first_read_files"))
        ],
        "likely_tests": [
            _pack_context_item(item) for item in _sequence(context_pack.get("likely_tests"))
        ],
        "ambiguity": [
            _pack_context_item(item) for item in _sequence(context_pack.get("ambiguity"))
        ],
        "truncation": _mapping(context_pack.get("truncation")),
    }


def _pack_node(node: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: node.get(key)
        for key in ("id", "kind", "label", "path", "line_range", "metadata")
        if key in node and node.get(key) not in (None, "")
    }


def _pack_neighbors(data: Mapping[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for item in _sequence(data.get("neighbors"))[:12]:
        mapped = _mapping(item)
        node = _mapping(mapped.get("node"))
        edge = _mapping(mapped.get("edge"))
        items.append(
            {
                "id": node.get("id"),
                "kind": node.get("kind"),
                "label": node.get("label"),
                "path": node.get("path"),
                "edge_kind": edge.get("kind"),
                "direction": mapped.get("direction"),
                "confidence": edge.get("confidence"),
                "evidence": _safe_evidence_refs(_sequence(edge.get("evidence"))),
            }
        )
    return {"items": items, "truncated": bool(data.get("truncated", False))}


def _pack_impact(data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: data.get(key)
        for key in (
            "target",
            "resolved_target",
            "direct_dependents",
            "direct_dependencies",
            "candidate_verification_commands",
            "candidates",
        )
        if key in data
    }


def _pack_file_metadata(data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "package_boundaries": data.get("package_boundaries", {}),
        "relationship_candidates": data.get("relationship_candidates", {}),
        "route_hints": data.get("route_hints", {}),
        "structural_summaries": data.get("structural_summaries", {}),
        "workspace_memberships": data.get("workspace_memberships", {}),
    }


def _flatten_relationship_candidates(file_metadata: Mapping[str, Any]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for path, candidates in sorted(_mapping(file_metadata.get("relationship_candidates")).items()):
        for candidate in _sequence(candidates):
            mapped = _mapping(candidate)
            if mapped:
                flattened.append({"path": path, **mapped})
    return flattened[:20]


def _architecture_evidence_refs(packed_input: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    target = _mapping(_mapping(packed_input.get("target_resolution")).get("node"))
    if target.get("id"):
        refs.append(f"node:{target['id']}")
    for neighbor in _sequence(_mapping(packed_input.get("neighbors")).get("items")):
        mapped = _mapping(neighbor)
        if mapped.get("id"):
            refs.append(f"neighbor:{mapped['id']}:{mapped.get('edge_kind', '')}")
    for candidate in _flatten_relationship_candidates(_mapping(packed_input.get("file_metadata"))):
        refs.append(
            f"relationship_candidate:{candidate.get('path', '')}:{candidate.get('warning_code', '')}"
        )
    return list(dict.fromkeys(refs))[:12]


def _architecture_responsibilities(
    path: str, node: Mapping[str, Any], neighbor_labels: Sequence[str]
) -> list[str]:
    kind = str(node.get("kind", "target"))
    label = str(node.get("label") or path or "the target")
    responsibilities = [
        f"{label} is represented as a {kind} in indexed RepoLens metadata.",
    ]
    if path:
        responsibilities.append(f"The explanation is scoped to repository metadata for {path}.")
    if neighbor_labels:
        responsibilities.append(
            "Neighboring areas are inferred from recorded graph edges: "
            + ", ".join(neighbor_labels[:5])
            + "."
        )
    return responsibilities


def _pack_context_item(value: Any) -> dict[str, Any]:
    item = _mapping(value)
    packed: dict[str, Any] = {
        "handle": item.get("handle", ""),
        "kind": item.get("kind", ""),
        "path": item.get("path", ""),
        "reason": item.get("reason", ""),
        "confidence": item.get("confidence", ""),
        "evidence": _safe_evidence_refs(_sequence(item.get("evidence"))),
        "freshness": _mapping(item.get("freshness")),
    }
    for optional_key in (
        "rank",
        "symbols",
        "relationships",
        "related_tests",
        "command",
        "risk_category",
        "package",
        "line_range",
    ):
        if optional_key in item:
            packed[optional_key] = item[optional_key]
    return redact_payload(packed)


def _proposal_evidence_refs(context_pack: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    pack_id = str(context_pack.get("context_pack_id", ""))
    for group in (
        "first_read_files",
        "likely_tests",
        "supporting_docs",
        "supporting_configs",
        "agent_guidance",
        "candidate_verification_commands",
        "risk_signals",
        "lower_priority_context",
        "ambiguity",
    ):
        for item in _sequence(context_pack.get(group)):
            mapped = _mapping(item)
            handle = str(mapped.get("handle", ""))
            if handle:
                refs.append(f"{pack_id}:{group}:{handle}")
    return refs[:12]


def _deterministic_item_evidence(item: Any) -> dict[str, Any]:
    mapped = _mapping(item)
    return {
        "handle": mapped.get("handle", ""),
        "path": mapped.get("path", ""),
        "kind": mapped.get("kind", ""),
        "reason": mapped.get("reason", ""),
        "confidence": mapped.get("confidence", ""),
        "evidence_refs": _safe_evidence_refs(_sequence(mapped.get("evidence"))),
    }


def _summary_sentence(task: str, first_paths: Sequence[str], test_paths: Sequence[str]) -> str:
    task_text = task or "the requested task"
    primary = ", ".join(first_paths[:3]) if first_paths else "no first-read file"
    tests = ", ".join(test_paths[:3]) if test_paths else "no likely test"
    return (
        f"For {task_text}, the bounded Context Pack prioritizes {primary} and surfaces "
        f"{tests}; this is an AI interpretation of deterministic metadata, not a "
        "Structural Summary or graph fact."
    )


def _input_digest(packed_input: Mapping[str, Any]) -> str:
    payload = json.dumps(packed_input, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _provider_config(*, enable_ai: bool, provider: str | None, model: str | None) -> dict[str, Any]:
    provider_name = _clean_optional(provider)
    model_name = _clean_optional(model)
    environment = None
    if provider_name == AI_TEST_PROVIDER_NAME:
        environment = {
            "variable": AI_TEST_PROVIDER_ENV_VAR,
            "present": AI_TEST_PROVIDER_ENV_VAR in os.environ,
        }
    result: dict[str, Any] = {
        "configured": bool(enable_ai and provider_name and model_name),
        "name": provider_name,
        "model": model_name,
    }
    if environment is not None:
        result["environment"] = environment
    return result


def _public_input_boundary() -> dict[str, Any]:
    return {
        "default_scope": _INPUT_BOUNDARY["default_scope"],
        "source_text_included": _INPUT_BOUNDARY["source_text_included"],
        "raw_prompt_persisted": _INPUT_BOUNDARY["raw_prompt_persisted"],
        "excluded_material": list(_INPUT_EXCLUDED_MATERIAL),
    }


def _safe_evidence_refs(evidence: Sequence[Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for item in evidence[:5]:
        mapped = _mapping(item)
        if mapped:
            refs.append(redact_payload(mapped))
    return refs


def _reason_code(reason: Any) -> str:
    if isinstance(reason, Mapping):
        return str(reason.get("code", ""))
    return str(reason or "")


def _normalize_kind(kind: str) -> str:
    return kind.strip().lower().replace("-", "_")


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _repo_display_path(repo_root: Path) -> str:
    if not repo_root.is_absolute():
        return repo_root.as_posix()
    return repo_root.name or "."


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []
