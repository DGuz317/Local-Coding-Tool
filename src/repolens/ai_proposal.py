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
from repolens.redaction import REDACTION_POLICY_VERSION, redact_payload, redact_text

AI_PROPOSAL_VERSION = "0.8.ai_proposal.v1"
AI_INPUT_PACKER_VERSION = "0.8.context_pack_summary_input.v1"
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

    if normalized_kind != "context_pack_summary":
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
                "Only context_pack_summary has a configured provider path in this slice; "
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
        evidence.append({"source": "context_pack_summary_proposal", "issue": 204})
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
