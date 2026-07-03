"""Shared Context Pack service for CLI and MCP surfaces."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from repolens.context_pack_contract import (
    ASSISTANT_PREFLIGHT_VERSION,
    CONTEXT_PACK_VERSION,
    DEFAULT_CONTEXT_PACK_BUDGET,
    HUMAN_LOWER_PRIORITY_LABEL,
    guard_context_pack_output,
)
from repolens.mcp_envelope import (
    mcp_error,
    mcp_from_query_envelope,
    mcp_success,
    truncation_metadata,
)
from repolens.query import GraphQueryService
from repolens.redaction import redact_text

_TEST_PATH_RE = re.compile(r"(^|/)(tests?|__tests__)/|[._-](test|spec)\.", re.IGNORECASE)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b([A-Z0-9_.-]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API[_-]?KEY|AUTH|PRIVATE[_-]?KEY)"
    r"[A-Z0-9_.-]*)\b\s*[:=]\s*[^\s,;]+"
)
_SOURCE_KINDS = {
    "AsyncFunction",
    "AsyncMethod",
    "Class",
    "Function",
    "JavaScriptArrowFunction",
    "JavaScriptClass",
    "JavaScriptFunction",
    "JavaScriptInterface",
    "JavaScriptTypeAlias",
    "Method",
    "PythonModule",
    "JavaScriptModule",
}
_BROAD_TASK_TOKENS = {"app", "application", "codebase", "project", "repo", "repository"}
_TEST_TASK_TOKENS = {"spec", "specs", "test", "tests"}
_AGENT_GUIDANCE_NAMES = {"agents.md", "claude.md"}
_CONFIG_NAMES = {
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "setup.py",
    "setup.cfg",
    "tox.ini",
    "tsconfig.json",
    "jsconfig.json",
}
_EXPAND_CONTEXT_MAX_DEPTH = 2
_EXPAND_CONTEXT_DEFAULT_DEPTH = 1
_EXPAND_CONTEXT_DEFAULT_ITEMS_PER_KIND = 3
_EXPAND_CONTEXT_DEFAULT_TOTAL_ITEMS = 10
_EXPAND_CONTEXT_GROUPS = (
    "direct_affected_files",
    "dependencies",
    "dependents",
    "likely_tests",
    "related_docs",
    "related_configs",
    "risk_signals",
    "candidate_verification_commands",
)


def expand_context(
    repo_path: Path | str,
    task: str,
    context_pack_id: str,
    item_handle: str,
    *,
    focus_hints: Sequence[str] = (),
    budget: Mapping[str, int] | None = None,
    depth: int = _EXPAND_CONTEXT_DEFAULT_DEPTH,
    max_items_per_kind: int = _EXPAND_CONTEXT_DEFAULT_ITEMS_PER_KIND,
    max_total_items: int = _EXPAND_CONTEXT_DEFAULT_TOTAL_ITEMS,
) -> dict[str, Any]:
    """Expand one item returned in a specific Context Pack without session state."""
    capped_depth = min(max(1, int(depth)), _EXPAND_CONTEXT_MAX_DEPTH)
    limits = _expansion_limits(max_items_per_kind, max_total_items)
    validated = _validated_pack_item(
        repo_path,
        task,
        context_pack_id,
        item_handle,
        focus_hints=focus_hints,
        budget=budget,
        limits=limits,
    )
    if not validated["ok"]:
        return validated["envelope"]

    pack = validated["pack"]
    item = validated["item"]
    item_path = str(item.get("path", ""))
    if not item_path:
        return _context_pack_followup_error(
            code="context_pack_item_not_expandable",
            message="Context Pack item cannot be expanded because it has no graph path.",
            limits=limits,
            freshness=pack.get("freshness"),
        )

    impact = GraphQueryService(repo_path).impact_analysis(
        item_path,
        depth=capped_depth,
        max_results=max(limits["max_items_per_kind"], limits["max_total_items"]),
    )
    if not impact.get("ok", False):
        return mcp_from_query_envelope(impact)

    impact_data = _mapping(impact.get("data"))
    expanded_context, truncated_fields = _expanded_context_groups(
        impact_data,
        context_pack_id=context_pack_id,
        freshness=_mapping(pack.get("freshness")),
        max_items_per_kind=limits["max_items_per_kind"],
        max_total_items=limits["max_total_items"],
    )
    data = {
        "context_pack_id": context_pack_id,
        "depth": capped_depth,
        "expanded_context": expanded_context,
        "item": _followup_item_summary(item),
        "item_handle": item_handle,
        "item_kind": item.get("kind"),
        "truncation": truncation_metadata(fields=truncated_fields),
    }
    return guard_context_pack_output(
        mcp_success(
            data=guard_context_pack_output(data),
            confidence=str(item.get("confidence", impact.get("confidence", "low"))),
            evidence=item.get("evidence", []),
            freshness=_mapping(pack.get("freshness")),
            limits=limits,
            truncation=truncation_metadata(fields=truncated_fields),
            warnings=impact.get("warnings", []),
        )
    )


def explain_relevance(
    repo_path: Path | str,
    task: str,
    context_pack_id: str,
    item_handle: str,
    *,
    focus_hints: Sequence[str] = (),
    budget: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Explain why one returned Context Pack item appeared in that pack."""
    limits = {"max_depth": 0, "max_items_per_kind": 0, "max_total_items": 1}
    validated = _validated_pack_item(
        repo_path,
        task,
        context_pack_id,
        item_handle,
        focus_hints=focus_hints,
        budget=budget,
        limits=limits,
    )
    if not validated["ok"]:
        return validated["envelope"]

    item = validated["item"]
    data = {
        "confidence": str(item.get("confidence", "low")),
        "context_pack_id": context_pack_id,
        "evidence": _safe_evidence(item.get("evidence", [])),
        "freshness": _mapping(item.get("freshness")),
        "item_handle": item_handle,
        "item_kind": item.get("kind"),
        "path": item.get("path", ""),
        "reason": str(item.get("reason", "Graph-derived task match.")),
    }
    return guard_context_pack_output(
        mcp_success(
            data=guard_context_pack_output(data),
            confidence=data["confidence"],
            evidence=data["evidence"],
            freshness=data["freshness"],
            limits=limits,
            truncation=truncation_metadata(),
            warnings=[],
        )
    )


def get_task_context(
    repo_path: Path | str,
    task: str,
    *,
    focus_hints: Sequence[str] = (),
    budget: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Return a deterministic v0.3 Context Pack envelope for a natural-language task."""
    active_budget = _context_budget(budget)
    repo_root = Path(repo_path).resolve()
    focus_error = _outside_focus_hint_error(repo_root, focus_hints, active_budget)
    if focus_error is not None:
        return focus_error

    query = GraphQueryService(repo_path)
    status = query.graph_status()
    reading = query.suggest_reading_order(
        task,
        max_files=active_budget["max_first_read_files"]
        + active_budget["max_items_per_support_group"],
    )
    if not reading.get("ok", False):
        return mcp_from_query_envelope(reading)
    reading = _apply_focus_hint_resolution(reading, focus_hints=focus_hints, repo_root=repo_root)

    hardening_warnings = _hardening_warnings(
        reading,
        task=task,
        focus_hints=focus_hints,
        repo_root=repo_root,
    )
    warnings = [*reading.get("warnings", []), *hardening_warnings]
    confidence = str(reading.get("confidence", "low"))
    if hardening_warnings and any(
        "focus hint" in warning.lower() for warning in hardening_warnings
    ):
        confidence = "low"

    pack = _build_context_pack(
        reading,
        file_metadata=_context_pack_file_metadata(query, reading, active_budget),
        support_context=_support_context(query, reading, active_budget),
        status=status,
        task=task,
        focus_hints=focus_hints,
        budget=active_budget,
    )
    guarded_pack = guard_context_pack_output(pack)
    truncation = dict(guarded_pack["truncation"])
    return guard_context_pack_output(
        mcp_success(
            data=guarded_pack,
            confidence=confidence,
            evidence=reading.get("evidence", []),
            freshness=guarded_pack["freshness"],
            limits=active_budget,
            truncation=truncation,
            warnings=warnings,
        )
    )


def get_assistant_preflight(
    repo_path: Path | str,
    task: str,
    *,
    focus_hints: Sequence[str] = (),
    budget: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Return the v0.5 Assistant Preflight contract shared by CLI and MCP."""
    context_envelope = get_task_context(
        repo_path,
        task,
        focus_hints=focus_hints,
        budget=budget,
    )
    if not context_envelope.get("ok", False):
        return context_envelope

    context_pack = _mapping(context_envelope.get("data"))
    active_budget = _context_budget(budget)
    normalized_focus_hints = [redact_text(str(hint)) for hint in focus_hints]
    data = {
        "assistant_preflight_version": ASSISTANT_PREFLIGHT_VERSION,
        "ambiguity": _sequence(context_pack.get("ambiguity")),
        "budget_controls": _preflight_budget_controls(context_pack, active_budget),
        "candidate_verification_commands": _sequence(
            context_pack.get("candidate_verification_commands")
        ),
        "confidence": str(context_envelope.get("confidence", "low")),
        "context_pack_id": context_pack.get("context_pack_id", ""),
        "context_pack_version": context_pack.get("context_pack_version", CONTEXT_PACK_VERSION),
        "evidence": _safe_evidence(context_envelope.get("evidence", [])),
        "first_read_files": _sequence(context_pack.get("first_read_files")),
        "focus_hints": {
            "items": normalized_focus_hints,
            "max_items": active_budget["max_items_per_support_group"],
            "resolution": "resolved_or_warned_by_context_pack",
        },
        "freshness": _mapping(context_envelope.get("freshness")),
        "likely_tests": _sequence(context_pack.get("likely_tests")),
        "limits": _mapping(context_envelope.get("limits")),
        "task_context": {
            "display_task": context_pack.get("task", ""),
            "fingerprint": context_pack.get("task_fingerprint", ""),
            "scope": "graph_bounded_orientation",
        },
        "truncation": _mapping(context_envelope.get("truncation")),
        "warnings": _sequence(context_envelope.get("warnings")),
    }
    data = guard_context_pack_output(data)
    return guard_context_pack_output(
        mcp_success(
            data=data,
            confidence=data["confidence"],
            evidence=data["evidence"],
            freshness=data["freshness"],
            limits=data["limits"],
            truncation=data["truncation"],
            warnings=data["warnings"],
        )
    )


def _build_context_pack(
    reading: Mapping[str, Any],
    *,
    file_metadata: Mapping[str, Any],
    support_context: Mapping[str, Any],
    status: Mapping[str, Any],
    task: str,
    focus_hints: Sequence[str],
    budget: dict[str, int],
) -> dict[str, Any]:
    data = _mapping(reading.get("data"))
    freshness = _freshness(reading, status)
    task_fingerprint = _task_fingerprint(task)
    normalized_focus_hints = tuple(sorted(redact_text(str(hint)) for hint in focus_hints))
    context_pack_id = _hash_id(
        "cp",
        {
            "budget": budget,
            "context_pack_version": CONTEXT_PACK_VERSION,
            "focus_hints": normalized_focus_hints,
            "graph_hash": freshness.get("canonical_graph_hash"),
            "task_fingerprint": task_fingerprint,
        },
    )

    reading_items = [_mapping(item) for item in _sequence(data.get("reading_order"))]
    likely_tests_raw = [item for item in reading_items if _is_test_path(str(item.get("path", "")))]
    supporting_docs_raw = [
        item for item in reading_items if _is_doc_path(str(item.get("path", "")))
    ]
    supporting_configs_raw = [
        item for item in reading_items if _is_config_path(str(item.get("path", "")))
    ]
    support_paths = {
        str(item.get("path", ""))
        for item in [*supporting_docs_raw, *supporting_configs_raw]
        if item.get("path")
    }
    if not _is_test_focused_task(task):
        support_paths.update(
            str(item.get("path", "")) for item in likely_tests_raw if item.get("path")
        )
    first_read_raw = [
        item for item in reading_items if str(item.get("path", "")) not in support_paths
    ]
    related_tests_by_source = _related_tests_by_source(likely_tests_raw)

    first_read_files = [
        _first_read_item(
            item,
            context_pack_id=context_pack_id,
            rank=index + 1,
            related_tests=related_tests_by_source.get(str(item.get("path", "")), []),
            file_metadata=file_metadata,
            freshness=freshness,
        )
        for index, item in enumerate(first_read_raw[: budget["max_first_read_files"]])
    ]
    likely_tests = [
        _support_item(
            item,
            context_pack_id=context_pack_id,
            kind="likely_test",
            freshness=freshness,
        )
        for item in likely_tests_raw[: budget["max_items_per_support_group"]]
    ]
    supporting_docs = [
        _support_item(
            item,
            context_pack_id=context_pack_id,
            kind="supporting_doc",
            freshness=freshness,
            file_metadata=file_metadata,
        )
        for item in _dedupe_support_items(
            [*supporting_docs_raw, *_sequence(support_context.get("supporting_docs"))]
        )[: budget["max_items_per_support_group"]]
    ]
    supporting_configs = [
        _support_item(
            item,
            context_pack_id=context_pack_id,
            kind="supporting_config",
            freshness=freshness,
            file_metadata=file_metadata,
        )
        for item in _dedupe_support_items(
            [*supporting_configs_raw, *_sequence(support_context.get("supporting_configs"))]
        )[: budget["max_items_per_support_group"]]
    ]
    agent_guidance = [
        _agent_guidance_item(item, context_pack_id=context_pack_id, freshness=freshness)
        for item in _sequence(support_context.get("agent_guidance"))[
            : budget["max_agent_guidance_items"]
        ]
    ]
    risk_signals = [
        _risk_signal_item(item, context_pack_id=context_pack_id, freshness=freshness)
        for item in _sequence(support_context.get("risk_signals"))[: budget["max_risk_signals"]]
    ]
    lower_priority_context = [
        _support_item(
            item,
            context_pack_id=context_pack_id,
            kind="lower_priority_context",
            freshness=freshness,
            file_metadata=file_metadata,
        )
        for item in _sequence(support_context.get("lower_priority_context"))[
            : budget["max_items_per_support_group"]
        ]
    ]
    candidate_commands = [
        _command_item(command, context_pack_id=context_pack_id, freshness=freshness)
        for command in _dedupe_commands(
            [
                *_sequence(data.get("candidate_verification_commands")),
                *_sequence(support_context.get("candidate_verification_commands")),
            ]
        )[: budget["max_candidate_verification_commands"]]
    ]
    ambiguity = [
        _ambiguity_item(candidate, context_pack_id=context_pack_id, freshness=freshness)
        for candidate in _sequence(data.get("candidates"))[: budget["max_items_per_support_group"]]
    ]
    expandable_items = [
        *first_read_files,
        *likely_tests,
        *supporting_docs,
        *supporting_configs,
        *agent_guidance,
        *candidate_commands,
        *risk_signals,
        *lower_priority_context,
        *ambiguity,
    ]
    expansion_handles = [
        {
            "context_pack_id": context_pack_id,
            "handle": item["handle"],
            "item_kind": item["kind"],
            "max_depth": _EXPAND_CONTEXT_DEFAULT_DEPTH,
            "reason": "Expand this returned item with bounded graph context.",
        }
        for item in expandable_items
    ]

    pack = {
        "agent_guidance": [],
        "ambiguity": ambiguity,
        "budget": _budget_metadata(
            budget,
            first_read_files,
            likely_tests,
            candidate_commands,
            supporting_docs,
            supporting_configs,
            agent_guidance,
            risk_signals,
            lower_priority_context,
        ),
        "candidate_verification_commands": candidate_commands,
        "context_pack_id": context_pack_id,
        "context_pack_version": CONTEXT_PACK_VERSION,
        "expansion_handles": expansion_handles,
        "first_read_files": first_read_files,
        "freshness": freshness,
        "likely_tests": likely_tests,
        "lower_priority_context": lower_priority_context,
        "next_actions": _next_actions(first_read_files),
        "risk_signals": risk_signals,
        "supporting_configs": supporting_configs,
        "supporting_docs": supporting_docs,
        "task": _display_task(task),
        "task_fingerprint": task_fingerprint,
        "truncation": truncation_metadata(),
    }
    pack["agent_guidance"] = agent_guidance
    return _apply_character_budget(pack, budget["max_total_chars"])


def _first_read_item(
    item: Mapping[str, Any],
    *,
    context_pack_id: str,
    rank: int,
    related_tests: list[str],
    file_metadata: Mapping[str, Any],
    freshness: Mapping[str, Any],
) -> dict[str, Any]:
    node = _mapping(item.get("node"))
    path = str(item.get("path", ""))
    result = {
        **_base_item(
            item,
            context_pack_id=context_pack_id,
            kind="first_read_file",
            freshness=freshness,
        ),
        "rank": rank,
        "relationships": [],
        "related_tests": related_tests,
        "symbols": _symbols_for_item(node),
    }
    _attach_file_metadata(result, path=path, file_metadata=file_metadata, freshness=freshness)
    return result


def _context_pack_file_metadata(
    query: GraphQueryService,
    reading: Mapping[str, Any],
    budget: Mapping[str, int],
) -> dict[str, Any]:
    data = _mapping(reading.get("data"))
    paths = [
        str(item.get("path")) for item in _sequence(data.get("reading_order")) if item.get("path")
    ][: budget["max_first_read_files"] + budget["max_items_per_support_group"]]
    metadata = query.context_pack_file_metadata(paths)
    if not metadata.get("ok", False):
        return {}
    return _mapping(metadata.get("data"))


def _support_context(
    query: GraphQueryService,
    reading: Mapping[str, Any],
    budget: Mapping[str, int],
) -> dict[str, list[dict[str, Any]]]:
    data = _mapping(reading.get("data"))
    source_paths = [
        str(item.get("path"))
        for item in _sequence(data.get("reading_order"))
        if item.get("path")
        and not _is_test_path(str(item.get("path")))
        and not _is_doc_path(str(item.get("path")))
        and not _is_config_path(str(item.get("path")))
    ][: budget["max_first_read_files"]]
    support: dict[str, list[dict[str, Any]]] = {
        "agent_guidance": _agent_guidance_context(query, budget),
        "candidate_verification_commands": [],
        "lower_priority_context": [],
        "risk_signals": [],
        "supporting_configs": [],
        "supporting_docs": [],
    }
    first_read_paths = set(source_paths)
    support_paths: set[str] = set()
    for path in source_paths:
        impact = query.impact_analysis(
            path,
            max_results=max(
                budget["max_items_per_support_group"],
                budget["max_candidate_verification_commands"],
                budget["max_risk_signals"],
            ),
        )
        if not impact.get("ok", False):
            continue
        impact_data = _mapping(impact.get("data"))
        support["supporting_docs"].extend(_sequence(impact_data.get("related_docs")))
        support["supporting_configs"].extend(_sequence(impact_data.get("related_configs")))
        support["candidate_verification_commands"].extend(
            _sequence(impact_data.get("candidate_verification_commands"))
        )
        support["risk_signals"].extend(
            _risk_context_item(item) for item in _sequence(impact_data.get("risk_comments"))
        )
        support_paths.update(
            str(item.get("path"))
            for item in [
                *_sequence(impact_data.get("related_docs")),
                *_sequence(impact_data.get("related_configs")),
            ]
            if _mapping(item).get("path")
        )
        for group_name in ("dependencies", "dependents"):
            for item in _sequence(impact_data.get(group_name)):
                mapped = _mapping(item)
                item_path = str(mapped.get("path", ""))
                if (
                    not item_path
                    or item_path in first_read_paths
                    or item_path in support_paths
                    or _is_test_path(item_path)
                    or _is_doc_path(item_path)
                    or _is_config_path(item_path)
                ):
                    continue
                support["lower_priority_context"].append(
                    {
                        **mapped,
                        "reason": "Evidence-backed related context to inspect later if needed.",
                    }
                )
    support["supporting_docs"] = _dedupe_support_items(support["supporting_docs"])
    support["supporting_configs"] = _dedupe_support_items(support["supporting_configs"])
    support["candidate_verification_commands"] = _dedupe_commands(
        support["candidate_verification_commands"]
    )
    support["risk_signals"] = _dedupe_risk_signals(support["risk_signals"])
    support["lower_priority_context"] = _dedupe_support_items(support["lower_priority_context"])
    return support


def _agent_guidance_context(
    query: GraphQueryService, budget: Mapping[str, int]
) -> list[dict[str, Any]]:
    summary = query.repo_summary(max_important_files=budget["max_agent_guidance_items"])
    if not summary.get("ok", False):
        return []
    important_files = _sequence(_mapping(summary.get("data")).get("important_files"))
    guidance: list[dict[str, Any]] = []
    for item in important_files:
        mapped = _mapping(item)
        path = str(mapped.get("path", ""))
        if str(mapped.get("doc_kind", "")) != "agent_instructions" and not _is_agent_guidance_path(
            path
        ):
            continue
        guidance.append(
            {
                "confidence": "medium",
                "evidence": [{"path": path, "source": "documentation_files"}],
                "path": path,
                "reason": "Indexed Agent Guidance metadata is present.",
            }
        )
    return guidance


def _risk_context_item(item: Any) -> dict[str, Any]:
    mapped = _mapping(item)
    tag = str(mapped.get("tag") or "tagged_comment")
    line = mapped.get("line")
    path = str(mapped.get("path", ""))
    return {
        "category": tag,
        "confidence": str(mapped.get("confidence", "medium")),
        "evidence": [{"category": tag, "line": line, "path": path, "source": "tagged_comments"}],
        "line": line,
        "path": path,
        "reason": str(mapped.get("reason") or "tagged_comment_on_related_file"),
    }


def _support_item(
    item: Mapping[str, Any],
    *,
    context_pack_id: str,
    kind: str,
    freshness: Mapping[str, Any],
    file_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result = _base_item(item, context_pack_id=context_pack_id, kind=kind, freshness=freshness)
    if file_metadata is not None:
        _attach_file_metadata(
            result,
            path=str(item.get("path", "")),
            file_metadata=file_metadata,
            freshness=freshness,
        )
    return result


def _attach_file_metadata(
    item: dict[str, Any],
    *,
    path: str,
    file_metadata: Mapping[str, Any],
    freshness: Mapping[str, Any],
) -> None:
    summaries = _mapping(file_metadata.get("structural_summaries"))
    summary = _mapping(summaries.get(path))
    if summary:
        item["structural_summary"] = {**summary, "freshness": dict(freshness)}
    package_boundaries = _mapping(file_metadata.get("package_boundaries"))
    package_boundary = _mapping(package_boundaries.get(path))
    if package_boundary:
        item["package_boundary"] = package_boundary
    route_hints = _mapping(file_metadata.get("route_hints"))
    hints = _sequence(route_hints.get(path))
    if hints:
        item["route_hints"] = hints
    workspace_memberships = _mapping(file_metadata.get("workspace_memberships"))
    workspace_membership = _mapping(workspace_memberships.get(path))
    if workspace_membership:
        item["workspace_membership"] = workspace_membership
    relationship_candidates = _mapping(file_metadata.get("relationship_candidates"))
    candidates = _sequence(relationship_candidates.get(path))
    if candidates:
        item["relationship_candidates"] = candidates
        warning_codes = sorted(
            {
                str(_mapping(candidate).get("warning_code"))
                for candidate in candidates
                if _mapping(candidate).get("warning_code")
            }
        )
        if warning_codes:
            item["graph_quality_warning_codes"] = warning_codes


def _command_item(
    command: Any,
    *,
    context_pack_id: str,
    freshness: Mapping[str, Any],
) -> dict[str, Any]:
    item = _mapping(command)
    path = str(item.get("path") or item.get("group_source_path") or "")
    identity = {"kind": "candidate_verification_command", "name": item.get("name"), "path": path}
    return {
        "auto_run_recommended": False,
        "command": str(item.get("command", "")),
        "confidence": str(item.get("confidence", "high")),
        "evidence": [{"source": "config_commands"}],
        "found": True,
        "freshness": dict(freshness),
        "handle": _hash_id("item", {"context_pack_id": context_pack_id, "identity": identity}),
        "kind": "candidate_verification_command",
        "name": str(item.get("name", "")),
        "not_run": True,
        "path": path,
        "purpose": str(item.get("purpose", "unknown")),
        "reason": "Candidate verification command from repository config; not run.",
        "risk_bucket": str(item.get("risk_bucket", "unknown")),
        "run": False,
    }


def _agent_guidance_item(
    item: Any,
    *,
    context_pack_id: str,
    freshness: Mapping[str, Any],
) -> dict[str, Any]:
    mapped = _mapping(item)
    path = str(mapped.get("path", ""))
    identity = {"kind": "agent_guidance", "path": path}
    return {
        "confidence": str(mapped.get("confidence", "medium")),
        "evidence": _safe_evidence(mapped.get("evidence", [])),
        "freshness": dict(freshness),
        "handle": _hash_id("item", {"context_pack_id": context_pack_id, "identity": identity}),
        "kind": "agent_guidance",
        "path": path,
        "reason": str(mapped.get("reason") or "Indexed Agent Guidance metadata is present."),
    }


def _risk_signal_item(
    item: Any,
    *,
    context_pack_id: str,
    freshness: Mapping[str, Any],
) -> dict[str, Any]:
    mapped = _mapping(item)
    path = str(mapped.get("path", ""))
    category = str(mapped.get("category") or mapped.get("tag") or "tagged_comment")
    line = mapped.get("line")
    location: dict[str, Any] = {"path": path}
    if isinstance(line, int):
        location["line"] = line
    identity = {"category": category, "kind": "risk_signal", "line": line, "path": path}
    evidence = _safe_evidence(mapped.get("evidence", [])) or [
        {"category": category, "line": line, "path": path, "source": "tagged_comments"}
    ]
    return {
        "category": category,
        "confidence": str(mapped.get("confidence", "medium")),
        "evidence": evidence,
        "freshness": dict(freshness),
        "handle": _hash_id("item", {"context_pack_id": context_pack_id, "identity": identity}),
        "kind": "risk_signal",
        "location": location,
        "path": path,
        "reason": str(mapped.get("reason") or "Tagged comment metadata on related context."),
    }


def _ambiguity_item(
    candidate: Any,
    *,
    context_pack_id: str,
    freshness: Mapping[str, Any],
) -> dict[str, Any]:
    item = _mapping(candidate)
    node = _mapping(item.get("node"))
    path = str(node.get("path") or "")
    identity = {"kind": "ambiguity_candidate", "node_id": node.get("id"), "path": path}
    return {
        "confidence": str(item.get("confidence", "low")),
        "evidence": _safe_evidence(item.get("evidence", [])),
        "freshness": dict(freshness),
        "handle": _hash_id("item", {"context_pack_id": context_pack_id, "identity": identity}),
        "kind": "ambiguity_candidate",
        "path": path,
        "reason": "Task matched multiple graph candidates; inspect before choosing a target.",
    }


def _base_item(
    item: Mapping[str, Any],
    *,
    context_pack_id: str,
    kind: str,
    freshness: Mapping[str, Any],
) -> dict[str, Any]:
    path = str(item.get("path", ""))
    identity = {"kind": kind, "path": path, "reason": item.get("reason")}
    return {
        "confidence": str(item.get("confidence", "low")),
        "evidence": _safe_evidence(item.get("evidence", [])),
        "freshness": dict(freshness),
        "handle": _hash_id("item", {"context_pack_id": context_pack_id, "identity": identity}),
        "kind": kind,
        "path": path,
        "reason": str(
            item.get("ranking_reason") or item.get("reason") or "Graph-derived task match."
        ),
    }


def _symbols_for_item(node: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not node or str(node.get("kind", "")) not in _SOURCE_KINDS:
        return []
    metadata = _mapping(node.get("metadata"))
    symbol: dict[str, Any] = {
        "kind": str(node.get("kind", "")),
        "name": str(node.get("label", "")),
    }
    if metadata.get("qualified_name"):
        symbol["qualified_name"] = str(metadata["qualified_name"])
    if metadata.get("public") is not None:
        symbol["public"] = bool(metadata["public"])
    line_start = metadata.get("line_start") or metadata.get("start_line")
    line_end = metadata.get("line_end") or metadata.get("end_line")
    if isinstance(line_start, int) and isinstance(line_end, int):
        symbol["line_range"] = {"start": line_start, "end": line_end}
    return [symbol]


def _freshness(reading: Mapping[str, Any], status: Mapping[str, Any]) -> dict[str, Any]:
    source = _mapping(status.get("data"))
    if not source:
        status_text = "available"
        fresh = True
        for warning in _sequence(reading.get("warnings")):
            if "stale" in str(warning).lower():
                status_text = "stale"
                fresh = False
                break
        source = {"fresh": fresh, "status": status_text}
    evidence = _sequence(reading.get("evidence"))
    return {
        "canonical_graph_hash": _canonical_graph_hash(reading, source),
        "fresh": source.get("fresh", True),
        "status": source.get("status", "available"),
        "source": "graph_metadata",
        "source_evidence_count": len(evidence),
    }


def _canonical_graph_hash(reading: Mapping[str, Any], status_data: Mapping[str, Any]) -> str:
    status_hash = status_data.get("canonical_graph_hash")
    if status_hash:
        return str(status_hash)
    evidence = _sequence(reading.get("evidence"))
    return _hash_id("graph", evidence)


def _context_budget(overrides: Mapping[str, int] | None) -> dict[str, int]:
    budget = {key: int(value) for key, value in DEFAULT_CONTEXT_PACK_BUDGET.items()}
    for key, value in dict(overrides or {}).items():
        if key in budget:
            budget[key] = max(1, int(value))
    return budget


def _budget_metadata(
    budget: Mapping[str, int],
    first_read_files: Sequence[Mapping[str, Any]],
    likely_tests: Sequence[Mapping[str, Any]],
    candidate_commands: Sequence[Mapping[str, Any]],
    supporting_docs: Sequence[Mapping[str, Any]] = (),
    supporting_configs: Sequence[Mapping[str, Any]] = (),
    agent_guidance: Sequence[Mapping[str, Any]] = (),
    risk_signals: Sequence[Mapping[str, Any]] = (),
    lower_priority_context: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    serialized_chars = len(
        json.dumps(
            {
                "agent_guidance": agent_guidance,
                "candidate_verification_commands": candidate_commands,
                "first_read_files": first_read_files,
                "likely_tests": likely_tests,
                "lower_priority_context": lower_priority_context,
                "risk_signals": risk_signals,
                "supporting_configs": supporting_configs,
                "supporting_docs": supporting_docs,
            },
            sort_keys=True,
        )
    )
    return {
        **dict(budget),
        "approx_tokens": serialized_chars // budget["approx_token_estimate_divisor"] + 1,
        "used_chars": serialized_chars,
    }


def _preflight_budget_controls(
    context_pack: Mapping[str, Any], budget: Mapping[str, int]
) -> dict[str, Any]:
    pack_budget = _mapping(context_pack.get("budget"))
    return {
        "deterministic": True,
        "max_candidate_verification_commands": budget["max_candidate_verification_commands"],
        "max_first_read_files": budget["max_first_read_files"],
        "max_items_per_support_group": budget["max_items_per_support_group"],
        "max_total_chars": budget["max_total_chars"],
        "used_chars": int(pack_budget.get("used_chars", 0)),
        "units": ["items", "characters"],
    }


def _next_actions(first_read_files: Sequence[Mapping[str, Any]]) -> list[str]:
    actions = []
    if first_read_files:
        actions.append("Inspect the ranked First-Read Files before editing.")
    actions.append("Use expansion handles only for bounded follow-up context.")
    actions.append("Use explain relevance on returned items before broadening scope.")
    return actions[: DEFAULT_CONTEXT_PACK_BUDGET["max_next_actions"]]


def _apply_character_budget(pack: dict[str, Any], max_total_chars: int) -> dict[str, Any]:
    if len(json.dumps(pack, sort_keys=True)) <= max_total_chars:
        return pack
    pack = dict(pack)
    for group_name in ("supporting_docs", "supporting_configs", "lower_priority_context"):
        pack[group_name] = _strip_structural_summaries(_sequence(pack.get(group_name)))
    if len(json.dumps(pack, sort_keys=True)) <= max_total_chars:
        pack["truncation"] = truncation_metadata(fields=["structural_summaries"])
        return pack
    pack["lower_priority_context"] = []
    pack["supporting_docs"] = []
    pack["supporting_configs"] = []
    pack["truncation"] = truncation_metadata(fields=["character_budget"])
    return pack


def _strip_structural_summaries(items: Sequence[Any]) -> list[dict[str, Any]]:
    stripped = []
    for item in items:
        mapped = dict(_mapping(item))
        mapped.pop("structural_summary", None)
        stripped.append(mapped)
    return stripped


def _related_tests_by_source(tests: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    related: dict[str, list[str]] = {}
    for test in tests:
        source_path = test.get("source_path")
        path = test.get("path")
        if source_path is None:
            for evidence in _sequence(test.get("evidence")):
                evidence_source = _mapping(evidence).get("source_path") or _mapping(evidence).get(
                    "target_path"
                )
                if evidence_source:
                    source_path = evidence_source
                    break
        if source_path and path:
            related.setdefault(str(source_path), []).append(str(path))
    return {path: sorted(set(paths)) for path, paths in related.items()}


def _dedupe_support_items(items: Sequence[Any]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for item in items:
        mapped = _mapping(item)
        path = str(mapped.get("path", ""))
        if not path or path in deduped:
            continue
        deduped[path] = mapped
    return [deduped[path] for path in sorted(deduped)]


def _dedupe_commands(items: Sequence[Any]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in items:
        mapped = _mapping(item)
        key = (
            str(mapped.get("path", "")),
            str(mapped.get("name", "")),
            str(mapped.get("command", "")),
        )
        if key in deduped:
            continue
        deduped[key] = mapped
    return [deduped[key] for key in sorted(deduped)]


def _dedupe_risk_signals(items: Sequence[Any]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, Any], dict[str, Any]] = {}
    for item in items:
        mapped = _mapping(item)
        key = (str(mapped.get("path", "")), str(mapped.get("category", "")), mapped.get("line"))
        if key in deduped:
            continue
        deduped[key] = mapped
    return [deduped[key] for key in sorted(deduped, key=lambda key: (key[0], str(key[2]), key[1]))]


def _task_fingerprint(task: str) -> str:
    normalized = " ".join(_display_task(task).lower().split())
    return _hash_id("task", normalized)


def _display_task(task: str) -> str:
    return _SECRET_ASSIGNMENT_RE.sub(lambda match: match.group(1), redact_text(task))


def _outside_focus_hint_error(
    repo_root: Path, focus_hints: Sequence[str], budget: Mapping[str, int]
) -> dict[str, Any] | None:
    for hint in focus_hints:
        raw_hint = str(hint)
        if not _looks_like_path(raw_hint):
            continue
        hint_path = Path(raw_hint)
        resolved = (hint_path if hint_path.is_absolute() else repo_root / hint_path).resolve()
        if resolved == repo_root or repo_root in resolved.parents:
            continue
        return mcp_error(
            code="focus_hint_outside_root",
            message="Focus hints must stay inside the analysis root.",
            details={"focus_hint": "outside_analysis_root"},
            limits=budget,
            warnings=[],
            confidence="none",
            freshness={"fresh": False, "status": "invalid_focus_hint"},
        )
    return None


def _hardening_warnings(
    reading: Mapping[str, Any], *, task: str, focus_hints: Sequence[str], repo_root: Path
) -> list[str]:
    data = _mapping(reading.get("data"))
    warnings: list[str] = []
    if _is_broad_task(task):
        warnings.append(
            "Task is broad; Context Pack output is bounded and may omit lower-priority context."
        )
    if not _sequence(data.get("reading_order")) and not _sequence(data.get("candidates")):
        warnings.append("No useful graph matches found; returning a low-confidence bounded pack.")
    warnings.extend(
        _unresolved_focus_hint_warnings(data, focus_hints=focus_hints, repo_root=repo_root)
    )
    return list(dict.fromkeys(warnings))


def _apply_focus_hint_resolution(
    reading: Mapping[str, Any], *, focus_hints: Sequence[str], repo_root: Path
) -> dict[str, Any]:
    """Use an existing in-root focus path to disambiguate reading-order candidates."""
    data = _mapping(reading.get("data"))
    candidates = [_mapping(item) for item in _sequence(data.get("candidates"))]
    if not candidates or not focus_hints:
        return dict(reading)

    focus_paths: set[str] = set()
    for hint in focus_hints:
        raw_hint = str(hint)
        if not _looks_like_path(raw_hint):
            continue
        hint_path = Path(raw_hint)
        resolved = (hint_path if hint_path.is_absolute() else repo_root / hint_path).resolve()
        if resolved.exists() and (resolved == repo_root or repo_root in resolved.parents):
            focus_paths.add(resolved.relative_to(repo_root).as_posix())
    if not focus_paths:
        return dict(reading)

    focused = []
    for item in candidates:
        path = _candidate_path(item)
        if path in focus_paths:
            focused.append({**item, "path": path})
    if not focused:
        return dict(reading)

    updated_data = dict(data)
    updated_data["ambiguous"] = False
    updated_data["candidates"] = []
    updated_data["reading_order"] = focused
    updated_data["total_recommendations"] = len(focused)
    updated = dict(reading)
    updated["data"] = updated_data
    updated["confidence"] = "medium"
    return updated


def _candidate_path(item: Mapping[str, Any]) -> str:
    direct_path = str(item.get("path") or "")
    if direct_path:
        return direct_path
    return str(_mapping(item.get("node")).get("path") or "")


def _unresolved_focus_hint_warnings(
    data: Mapping[str, Any], *, focus_hints: Sequence[str], repo_root: Path
) -> list[str]:
    if not focus_hints:
        return []
    warnings: list[str] = []
    matched_text = _focus_match_text(data)
    for hint in focus_hints:
        raw_hint = str(hint)
        display_hint = _display_task(raw_hint)
        if _looks_like_path(raw_hint):
            hint_path = Path(raw_hint)
            resolved = (hint_path if hint_path.is_absolute() else repo_root / hint_path).resolve()
            if resolved.exists():
                continue
            warnings.append(f"Unresolved focus hint: {display_hint}; confidence downgraded.")
            continue
        if display_hint.lower() in matched_text:
            continue
        warnings.append(f"Unresolved focus hint: {display_hint}; confidence downgraded.")
    return warnings


def _focus_match_text(data: Mapping[str, Any]) -> str:
    chunks: list[str] = []
    for item in [*_sequence(data.get("reading_order")), *_sequence(data.get("candidates"))]:
        mapped = _mapping(item)
        node = _mapping(mapped.get("node"))
        metadata = _mapping(node.get("metadata"))
        chunks.extend(
            str(value)
            for value in (
                mapped.get("path"),
                node.get("label"),
                node.get("path"),
                metadata.get("qualified_name"),
            )
            if value
        )
    return "\n".join(chunks).lower()


def _is_broad_task(task: str) -> bool:
    tokens = re.findall(r"[A-Za-z0-9_./-]+", _display_task(task).lower())
    meaningful = [
        token
        for token in tokens
        if token not in {"across", "add", "change", "fix", "improve", "the", "to", "update"}
    ]
    return (
        bool(meaningful)
        and len(meaningful) <= 2
        and any(token in _BROAD_TASK_TOKENS for token in meaningful)
    )


def _is_test_focused_task(task: str) -> bool:
    return bool(
        set(re.findall(r"[A-Za-z0-9_./-]+", _display_task(task).lower())) & _TEST_TASK_TOKENS
    )


def _looks_like_path(value: str) -> bool:
    return "/" in value or "\\" in value or value.startswith(".") or bool(Path(value).suffix)


def _hash_id(prefix: str, value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _safe_evidence(value: Any) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for item in _sequence(value):
        mapped = _mapping(item)
        evidence.append({key: child for key, child in mapped.items() if key != "value"})
    return evidence[:3]


def _validated_pack_item(
    repo_path: Path | str,
    task: str,
    context_pack_id: str,
    item_handle: str,
    *,
    focus_hints: Sequence[str],
    budget: Mapping[str, int] | None,
    limits: Mapping[str, int],
) -> dict[str, Any]:
    envelope = get_task_context(repo_path, task, focus_hints=focus_hints, budget=budget)
    if not envelope.get("ok", False):
        return {"envelope": envelope, "ok": False}

    pack = _mapping(envelope.get("data"))
    freshness = _mapping(pack.get("freshness"))
    if freshness.get("fresh") is False:
        return {
            "envelope": _context_pack_followup_error(
                code="stale_context_pack",
                message="Context Pack is stale; request a fresh Context Pack before follow-up use.",
                limits=limits,
                freshness=freshness,
                warnings=envelope.get("warnings", []),
            ),
            "ok": False,
        }
    current_pack_id = str(pack.get("context_pack_id", ""))
    if current_pack_id != context_pack_id:
        return {
            "envelope": _context_pack_followup_error(
                code="context_pack_id_mismatch",
                message="Context Pack ID does not match current graph, task, focus, or budget.",
                limits=limits,
                freshness=freshness,
                details={"current_context_pack_id": current_pack_id},
            ),
            "ok": False,
        }

    item = _returned_pack_items(pack).get(item_handle)
    if item is None:
        return {
            "envelope": _context_pack_followup_error(
                code="context_pack_item_not_returned",
                message="Item handle was not returned in this Context Pack.",
                limits=limits,
                freshness=freshness,
            ),
            "ok": False,
        }
    return {"item": item, "ok": True, "pack": pack}


def _context_pack_followup_error(
    *,
    code: str,
    message: str,
    limits: Mapping[str, Any],
    freshness: Mapping[str, Any] | None = None,
    details: Mapping[str, Any] | None = None,
    warnings: Sequence[str] = (),
) -> dict[str, Any]:
    return guard_context_pack_output(
        mcp_error(
            code=code,
            message=message,
            details={"requires_new_pack": True, **dict(details or {})},
            limits=limits,
            warnings=warnings,
            freshness=freshness or {"fresh": None, "status": "unknown"},
        )
    )


def _returned_pack_items(pack: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    for group_name in (
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
        for item in _sequence(pack.get(group_name)):
            mapped = _mapping(item)
            handle = str(mapped.get("handle", ""))
            if handle:
                items[handle] = mapped
    return items


def _expansion_limits(max_items_per_kind: int, max_total_items: int) -> dict[str, int]:
    per_kind = max(1, int(max_items_per_kind))
    total = max(1, int(max_total_items))
    return {
        "max_depth": _EXPAND_CONTEXT_MAX_DEPTH,
        "max_items_per_kind": per_kind,
        "max_total_items": total,
    }


def _expanded_context_groups(
    impact_data: Mapping[str, Any],
    *,
    context_pack_id: str,
    freshness: Mapping[str, Any],
    max_items_per_kind: int,
    max_total_items: int,
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    groups: dict[str, list[dict[str, Any]]] = {group: [] for group in _EXPAND_CONTEXT_GROUPS}
    truncated_fields: list[str] = []
    remaining = max_total_items
    for group in _EXPAND_CONTEXT_GROUPS:
        raw_items = _sequence(
            impact_data.get("risk_comments") if group == "risk_signals" else impact_data.get(group)
        )
        if not raw_items:
            continue
        limited_raw = raw_items[: min(max_items_per_kind, remaining)]
        groups[group] = [
            _expanded_context_item(
                item,
                group=group,
                context_pack_id=context_pack_id,
                freshness=freshness,
            )
            for item in limited_raw
        ]
        remaining -= len(groups[group])
        if len(raw_items) > len(limited_raw):
            truncated_fields.append(group)
        if remaining <= 0:
            later_groups = _EXPAND_CONTEXT_GROUPS[_EXPAND_CONTEXT_GROUPS.index(group) + 1 :]
            truncated_fields.extend(
                later_group
                for later_group in later_groups
                if _sequence(
                    impact_data.get("risk_comments")
                    if later_group == "risk_signals"
                    else impact_data.get(later_group)
                )
            )
            break
    return groups, sorted(set(truncated_fields))


def _expanded_context_item(
    item: Any,
    *,
    group: str,
    context_pack_id: str,
    freshness: Mapping[str, Any],
) -> dict[str, Any]:
    mapped = _mapping(item)
    if group == "risk_signals":
        return _risk_signal_item(mapped, context_pack_id=context_pack_id, freshness=freshness)
    if group == "candidate_verification_commands":
        return _command_item(mapped, context_pack_id=context_pack_id, freshness=freshness)
    kind_by_group = {
        "dependencies": "lower_priority_context",
        "dependents": "lower_priority_context",
        "direct_affected_files": "first_read_file",
        "likely_tests": "likely_test",
        "related_configs": "supporting_config",
        "related_docs": "supporting_doc",
    }
    return _support_item(
        mapped,
        context_pack_id=context_pack_id,
        kind=kind_by_group.get(group, "lower_priority_context"),
        freshness=freshness,
    )


def _followup_item_summary(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "confidence": str(item.get("confidence", "low")),
        "evidence": _safe_evidence(item.get("evidence", [])),
        "freshness": _mapping(item.get("freshness")),
        "handle": str(item.get("handle", "")),
        "kind": str(item.get("kind", "")),
        "path": str(item.get("path", "")),
        "reason": str(item.get("reason", "Graph-derived task match.")),
    }


def _is_test_path(path: str) -> bool:
    return bool(_TEST_PATH_RE.search(path))


def _is_doc_path(path: str) -> bool:
    return Path(path).suffix.lower() in {".md", ".markdown", ".mdx"}


def _is_agent_guidance_path(path: str) -> bool:
    name = Path(path).name.lower()
    return name in _AGENT_GUIDANCE_NAMES or path.startswith("docs/agents/")


def _is_config_path(path: str) -> bool:
    name = Path(path).name.lower()
    if name in _CONFIG_NAMES:
        return True
    return name.endswith((".toml", ".yaml", ".yml", ".ini")) and not _is_doc_path(path)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def human_context_pack(envelope: Mapping[str, Any]) -> str:
    """Render a compact source-free Context Pack summary for humans."""
    if not envelope.get("ok"):
        error = _mapping(envelope.get("error"))
        return (
            f"Context Pack failed: {error.get('message') or error.get('code') or 'unknown error'}\n"
        )
    data = _mapping(envelope.get("data"))
    lines = [
        f"Context Pack: {data.get('context_pack_id')}",
        f"Task: {data.get('task')}",
        "First-Read Files:",
    ]
    first_read = _sequence(data.get("first_read_files"))
    if not first_read:
        lines.append("- none")
    for item in first_read:
        mapped = _mapping(item)
        lines.append(
            f"- {mapped.get('rank')}. {mapped.get('path')} "
            f"({mapped.get('confidence')}): {mapped.get('reason')}"
        )
    likely_tests = _sequence(data.get("likely_tests"))
    if likely_tests:
        lines.append("Likely Tests:")
        for item in likely_tests:
            mapped = _mapping(item)
            lines.append(f"- {mapped.get('path')} ({mapped.get('confidence')})")
    lines.append(
        f"{HUMAN_LOWER_PRIORITY_LABEL}: {len(_sequence(data.get('lower_priority_context')))}"
    )
    return "\n".join(lines) + "\n"


def human_assistant_preflight(envelope: Mapping[str, Any]) -> str:
    """Render a compact source-free Assistant Preflight summary for humans."""
    if not envelope.get("ok"):
        error = _mapping(envelope.get("error"))
        lines = [
            f"Assistant Preflight failed: {error.get('message') or error.get('code') or 'unknown error'}"
        ]
        if error.get("status"):
            lines.append(f"Status: {error.get('status')}")
        if error.get("recommended_action"):
            lines.append(f"Recommended action: {error.get('recommended_action')}")
        warnings = _sequence(envelope.get("warnings"))
        if warnings:
            lines.append("Warnings:")
            lines.extend(f"- {warning}" for warning in warnings)
        return "\n".join(lines) + "\n"
    data = _mapping(envelope.get("data"))
    task_context = _mapping(data.get("task_context"))
    budget_controls = _mapping(data.get("budget_controls"))
    lines = [
        f"Assistant Preflight: {data.get('context_pack_id')}",
        f"Task: {task_context.get('display_task')}",
        f"Freshness: {_mapping(data.get('freshness')).get('status')}",
        "First-Read Files:",
    ]
    first_read = _sequence(data.get("first_read_files"))
    if not first_read:
        lines.append("- none")
    for item in first_read:
        mapped = _mapping(item)
        lines.append(
            f"- {mapped.get('rank')}. {mapped.get('path')} "
            f"({mapped.get('confidence')}): {mapped.get('reason')}"
        )

    lines.append("Likely Tests:")
    likely_tests = _sequence(data.get("likely_tests"))
    if not likely_tests:
        lines.append("- none")
    for item in likely_tests:
        mapped = _mapping(item)
        lines.append(f"- {mapped.get('path')} ({mapped.get('confidence')}): {mapped.get('reason')}")

    lines.append("Candidate Verification Commands (discovered only; not run):")
    commands = _sequence(data.get("candidate_verification_commands"))
    if not commands:
        lines.append("- none")
    for item in commands:
        mapped = _mapping(item)
        lines.append(
            f"- {mapped.get('name')}: found={mapped.get('found')}, "
            f"run={mapped.get('run')}, risk={mapped.get('risk_bucket')}"
        )

    warnings = _sequence(data.get("warnings"))
    if warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in warnings)

    lines.extend(
        [
            f"Confidence: {data.get('confidence')}",
            f"Evidence: {len(_sequence(data.get('evidence')))} item(s)",
            "Budget Controls: "
            f"{budget_controls.get('max_first_read_files')} first-read files, "
            f"{budget_controls.get('max_items_per_support_group')} support items/group, "
            f"{budget_controls.get('max_candidate_verification_commands')} candidate commands, "
            f"{budget_controls.get('max_total_chars')} chars",
        ]
    )
    return "\n".join(lines) + "\n"
