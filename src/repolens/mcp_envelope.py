"""Shared MCP response envelope helpers for RepoLens tools."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

MCP_MAX_EVIDENCE_ITEMS = 12
MCP_MAX_WARNING_ITEMS = 8
MCP_RESPONSE_MAX_BYTES = 512_000
MCP_GRAPH_UNAVAILABLE_CODES = frozenset(
    {
        "graph_store_is_symlink",
        "graph_store_unreadable",
        "missing_graph_artifacts",
        "unsupported_schema_version",
    }
)

_STALE_GRAPH_WARNING = "Graph artifacts may be stale; file metadata changed since indexing."


def mcp_success(
    *,
    data: Mapping[str, Any] | None = None,
    confidence: str = "high",
    evidence: Sequence[Mapping[str, Any]] = (),
    limits: Mapping[str, Any] | None = None,
    warnings: Sequence[str] = (),
    pagination: Mapping[str, Any] | None = None,
    freshness: Mapping[str, Any] | None = None,
    truncation: Mapping[str, Any] | None = None,
    max_response_bytes: int = MCP_RESPONSE_MAX_BYTES,
) -> dict[str, Any]:
    """Build a successful MCP tool response with bounded metadata."""
    envelope = _base_envelope(
        ok=True,
        data=dict(data or {}),
        confidence=confidence,
        evidence=evidence,
        limits=limits,
        warnings=warnings,
        freshness=freshness,
        truncation=truncation,
    )
    if pagination is not None:
        envelope["pagination"] = dict(pagination)
    return cap_mcp_response(envelope, max_response_bytes=max_response_bytes)


def mcp_error(
    *,
    code: str,
    message: str,
    details: Mapping[str, Any] | None = None,
    limits: Mapping[str, Any] | None = None,
    warnings: Sequence[str] = (),
    evidence: Sequence[Mapping[str, Any]] = (),
    confidence: str = "none",
    freshness: Mapping[str, Any] | None = None,
    truncation: Mapping[str, Any] | None = None,
    max_response_bytes: int = MCP_RESPONSE_MAX_BYTES,
) -> dict[str, Any]:
    """Build a structured MCP error response with the standard envelope shape."""
    error = {"code": code, "message": message}
    if details:
        error.update(details)
    return cap_mcp_response(
        _base_envelope(
            ok=False,
            data={},
            confidence=confidence,
            evidence=evidence,
            limits=limits,
            warnings=warnings,
            freshness=freshness,
            truncation=truncation,
            error=error,
        ),
        max_response_bytes=max_response_bytes,
    )


def mcp_graph_unavailable_error(
    *,
    code: str,
    missing_artifacts: Sequence[str] = (),
    recommended_action: str | None = None,
    status: str | None = None,
    limits: Mapping[str, Any] | None = None,
    warnings: Sequence[str] = (),
    evidence: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build the standardized actionable error for missing or unavailable graphs."""
    details: dict[str, Any] = {
        "missing_artifacts": list(missing_artifacts),
        "recommended_action": recommended_action,
        "status": status,
    }
    return mcp_error(
        code=code if code in MCP_GRAPH_UNAVAILABLE_CODES else "graph_unavailable",
        message=_graph_unavailable_message(code),
        details=details,
        limits=limits,
        warnings=warnings,
        evidence=evidence,
        freshness={"fresh": False, "status": status or "missing"},
    )


def mcp_from_query_envelope(
    envelope: Mapping[str, Any],
    *,
    cached: bool | None = None,
    status_ttl_seconds: float | None = None,
    max_response_bytes: int = MCP_RESPONSE_MAX_BYTES,
) -> dict[str, Any]:
    """Normalize a query-service envelope into the public MCP envelope contract."""
    result = dict(envelope)
    data = result.get("data")
    pagination = result.get("pagination")
    freshness = freshness_from_envelope(result)
    if cached is not None:
        freshness["status_cache"] = {
            "cached": cached,
            "ttl_seconds": status_ttl_seconds,
        }
    result["data"] = data if isinstance(data, dict) else {}
    result["evidence"] = _bounded_evidence(result.get("evidence", []))
    result["freshness"] = freshness
    result["limits"] = dict(result.get("limits", {}))
    result["ok"] = bool(result.get("ok", False))
    result["truncation"] = truncation_from_payload(data, pagination)
    result["warnings"] = _bounded_warnings(result.get("warnings", []))
    return cap_mcp_response(result, max_response_bytes=max_response_bytes)


def pagination_metadata(*, limit: int, offset: int, returned: int, total: int) -> dict[str, Any]:
    """Build standard MCP pagination metadata."""
    return {
        "limit": limit,
        "offset": offset,
        "returned": returned,
        "total": total,
        "truncated": offset + returned < total,
    }


def truncation_metadata(*, fields: Sequence[str] = ()) -> dict[str, Any]:
    """Build standard MCP truncation metadata."""
    normalized = sorted({field for field in fields if field})
    return {"fields": normalized, "truncated": bool(normalized)}


def truncation_from_payload(data: Any, pagination: Any) -> dict[str, Any]:
    """Derive standard truncation metadata from known query payload conventions."""
    fields: list[str] = []
    if isinstance(pagination, Mapping) and pagination.get("truncated") is True:
        fields.append("pagination")
    if isinstance(data, Mapping):
        data_truncated = data.get("truncated")
        if isinstance(data_truncated, bool):
            if data_truncated:
                fields.append("data")
        elif isinstance(data_truncated, Mapping):
            fields.extend(str(key) for key, value in data_truncated.items() if value)
    return truncation_metadata(fields=fields)


def freshness_from_envelope(envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Derive standard MCP freshness metadata from query data or graph errors."""
    data = envelope.get("data")
    if isinstance(data, Mapping) and ("fresh" in data or "status" in data):
        return {"fresh": data.get("fresh"), "status": data.get("status", "unknown")}
    error = envelope.get("error")
    if isinstance(error, Mapping) and error.get("code") in MCP_GRAPH_UNAVAILABLE_CODES:
        return {"fresh": False, "status": error.get("status", "missing")}
    warnings = envelope.get("warnings")
    if isinstance(warnings, Sequence) and not isinstance(warnings, (str, bytes)):
        if _STALE_GRAPH_WARNING in {str(warning) for warning in warnings}:
            return {"fresh": False, "status": "stale"}
    evidence = envelope.get("evidence")
    if isinstance(evidence, Sequence) and not isinstance(evidence, (str, bytes)):
        for item in evidence:
            if isinstance(item, Mapping) and item.get("source") == "sqlite_metadata":
                return {"fresh": True, "status": "available"}
    return {"fresh": None, "status": "unknown"}


def cap_mcp_response(
    envelope: Mapping[str, Any], *, max_response_bytes: int = MCP_RESPONSE_MAX_BYTES
) -> dict[str, Any]:
    """Ensure an MCP response cannot grow beyond the configured JSON byte cap."""
    result = dict(envelope)
    if _json_size(result) <= max_response_bytes:
        return result

    limits = dict(result.get("limits", {}))
    limits["response_max_bytes"] = max_response_bytes
    result["limits"] = limits

    warnings = _bounded_warnings(
        [*list(result.get("warnings", [])), "MCP response exceeded the response cap; data omitted."]
    )
    result["warnings"] = warnings
    result["data"] = {"omitted_due_to_response_cap": True}
    truncation = dict(result.get("truncation", truncation_metadata()))
    fields = list(truncation.get("fields", []))
    fields.append("response")
    result["truncation"] = truncation_metadata(fields=fields)

    if _json_size(result) <= max_response_bytes:
        return result

    return {
        "confidence": "none",
        "data": {},
        "error": {
            "code": "response_too_large",
            "message": "MCP response exceeded the response cap.",
        },
        "evidence": [],
        "freshness": {"fresh": None, "status": "unknown"},
        "limits": {"response_max_bytes": max_response_bytes},
        "ok": False,
        "truncation": truncation_metadata(fields=["response"]),
        "warnings": [],
    }


def _base_envelope(
    *,
    ok: bool,
    data: dict[str, Any],
    confidence: str,
    evidence: Sequence[Mapping[str, Any]],
    limits: Mapping[str, Any] | None,
    warnings: Sequence[str],
    freshness: Mapping[str, Any] | None,
    truncation: Mapping[str, Any] | None,
    error: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    envelope: dict[str, Any] = {
        "confidence": confidence,
        "data": data,
        "evidence": _bounded_evidence(evidence),
        "freshness": dict(freshness or {"fresh": None, "status": "unknown"}),
        "limits": dict(limits or {}),
        "ok": ok,
        "truncation": dict(truncation or truncation_metadata()),
        "warnings": _bounded_warnings(warnings),
    }
    if error is not None:
        envelope["error"] = dict(error)
    return envelope


def _bounded_warnings(warnings: Any) -> list[str]:
    if not isinstance(warnings, Sequence) or isinstance(warnings, (str, bytes)):
        return []
    bounded = [str(warning) for warning in warnings[:MCP_MAX_WARNING_ITEMS]]
    omitted = len(warnings) - len(bounded)
    if omitted > 0:
        bounded.append(f"{omitted} additional warnings omitted.")
    return bounded


def _bounded_evidence(evidence: Any) -> list[dict[str, Any]]:
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
        return []
    bounded = []
    for item in evidence[:MCP_MAX_EVIDENCE_ITEMS]:
        if isinstance(item, Mapping):
            bounded.append(dict(item))
    omitted = len(evidence) - len(bounded)
    if omitted > 0:
        bounded.append({"omitted": omitted, "reason": "mcp_metadata_limit"})
    return bounded


def _json_size(value: Mapping[str, Any]) -> int:
    try:
        return len(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    except TypeError:
        return len(str(value).encode("utf-8"))


def _graph_unavailable_message(code: str) -> str:
    if code == "missing_graph_artifacts":
        return "RepoLens graph artifacts are missing. Run repolens index for this repository."
    if code == "unsupported_schema_version":
        return "RepoLens graph schema is unsupported. Rebuild graph artifacts."
    return "RepoLens graph is unavailable. Rebuild graph artifacts."
