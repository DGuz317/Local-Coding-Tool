"""Read-only AI Proposal safety paths for RepoLens v0.8."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from repolens.mcp_envelope import mcp_success
from repolens.redaction import redact_text

AI_PROPOSAL_VERSION = "0.8.ai_proposal.v1"
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
    """Return the v0.8 AI Proposal safety envelope without making provider calls."""
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
            "Provider execution is not implemented in this safety slice; no provider call was made."
        ],
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
    return "\n".join(
        [
            "AI Proposal request",
            f"Kind: {data.get('kind', '')}",
            f"Status: {data.get('status', '')}",
            f"Reason: {_reason_code(data.get('reason'))}",
            f"Provider configured: {str(provider_configured).lower()}",
            "No provider call, network call, command execution, file write, patch application, or remote post was performed.",
            "",
        ]
    )


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
) -> dict[str, Any]:
    data = {
        "ai_proposal_version": AI_PROPOSAL_VERSION,
        "kind": kind,
        "status": status,
        "reason": {"code": reason},
        "proposal": None,
        "provider": dict(provider_config),
        "request": {
            "kind": kind,
            "repo_path": _repo_display_path(repo_root),
            "task": redact_text(task or "") if task else None,
            "context_pack_id": redact_text(context_pack_id or "") if context_pack_id else None,
            "target": redact_text(target or "") if target else None,
            "metadata_only": True,
        },
        "input_boundary": {
            "default_scope": "bounded_repolens_metadata",
            "source_text_included": False,
            "raw_prompt_persisted": False,
        },
        "safety": dict(_NO_ACTION_SAFETY_FLAGS),
        "supported_kinds": sorted(AI_PROPOSAL_SUPPORTED_KINDS),
    }
    return mcp_success(
        data=data,
        confidence="none",
        evidence=[{"source": "v0.8_ai_provider_boundary", "issue": 203}],
        limits={"supported_kinds": sorted(AI_PROPOSAL_SUPPORTED_KINDS)},
        warnings=warnings,
    )


def _provider_config(*, enable_ai: bool, provider: str | None, model: str | None) -> dict[str, Any]:
    provider_name = _clean_optional(provider)
    model_name = _clean_optional(model)
    return {
        "configured": bool(enable_ai and provider_name and model_name),
        "name": provider_name,
        "model": model_name,
    }


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
