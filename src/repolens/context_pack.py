"""Shared Context Pack service for CLI and MCP surfaces."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from repolens.context_pack_contract import (
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


def _build_context_pack(
    reading: Mapping[str, Any],
    *,
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
    first_read_raw = [item for item in reading_items if item not in likely_tests_raw]
    related_tests_by_source = _related_tests_by_source(likely_tests_raw)

    first_read_files = [
        _first_read_item(
            item,
            context_pack_id=context_pack_id,
            rank=index + 1,
            related_tests=related_tests_by_source.get(str(item.get("path", "")), []),
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
    candidate_commands = [
        _command_item(command, context_pack_id=context_pack_id, freshness=freshness)
        for command in _sequence(data.get("candidate_verification_commands"))[
            : budget["max_candidate_verification_commands"]
        ]
    ]
    ambiguity = [
        _ambiguity_item(candidate, context_pack_id=context_pack_id, freshness=freshness)
        for candidate in _sequence(data.get("candidates"))[: budget["max_items_per_support_group"]]
    ]
    expansion_handles = [
        {
            "context_pack_id": context_pack_id,
            "handle": item["handle"],
            "item_kind": item["kind"],
            "max_depth": 1,
            "reason": "Expand this returned item with bounded graph context.",
        }
        for item in first_read_files
    ]

    pack = {
        "agent_guidance": [],
        "ambiguity": ambiguity,
        "budget": _budget_metadata(budget, first_read_files, likely_tests, candidate_commands),
        "candidate_verification_commands": candidate_commands,
        "context_pack_id": context_pack_id,
        "context_pack_version": CONTEXT_PACK_VERSION,
        "expansion_handles": expansion_handles,
        "first_read_files": first_read_files,
        "freshness": freshness,
        "likely_tests": likely_tests,
        "lower_priority_context": [],
        "next_actions": _next_actions(first_read_files, likely_tests),
        "risk_signals": [],
        "supporting_configs": [],
        "supporting_docs": [],
        "task": _display_task(task),
        "task_fingerprint": task_fingerprint,
        "truncation": truncation_metadata(),
    }
    return _apply_character_budget(pack, budget["max_total_chars"])


def _first_read_item(
    item: Mapping[str, Any],
    *,
    context_pack_id: str,
    rank: int,
    related_tests: list[str],
    freshness: Mapping[str, Any],
) -> dict[str, Any]:
    node = _mapping(item.get("node"))
    return {
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


def _support_item(
    item: Mapping[str, Any],
    *,
    context_pack_id: str,
    kind: str,
    freshness: Mapping[str, Any],
) -> dict[str, Any]:
    return _base_item(item, context_pack_id=context_pack_id, kind=kind, freshness=freshness)


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
        "auto_run_recommended": bool(item.get("auto_run_recommended", False)),
        "command": str(item.get("command", "")),
        "confidence": str(item.get("confidence", "high")),
        "evidence": [{"source": "config_commands"}],
        "freshness": dict(freshness),
        "handle": _hash_id("item", {"context_pack_id": context_pack_id, "identity": identity}),
        "kind": "candidate_verification_command",
        "name": str(item.get("name", "")),
        "not_run": bool(item.get("not_run", True)),
        "path": path,
        "reason": "Candidate verification command from repository config; not run.",
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
        symbol["line_range"] = {"end": line_end, "start": line_start}
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
) -> dict[str, Any]:
    serialized_chars = len(
        json.dumps(
            {
                "candidate_verification_commands": candidate_commands,
                "first_read_files": first_read_files,
                "likely_tests": likely_tests,
            },
            sort_keys=True,
        )
    )
    return {
        **dict(budget),
        "approx_tokens": serialized_chars // budget["approx_token_estimate_divisor"] + 1,
        "used_chars": serialized_chars,
    }


def _next_actions(
    first_read_files: Sequence[Mapping[str, Any]], likely_tests: Sequence[Mapping[str, Any]]
) -> list[str]:
    actions = []
    if first_read_files:
        actions.append("Inspect the ranked First-Read Files before editing.")
    if likely_tests:
        actions.append("Inspect likely related tests for expected behavior.")
    actions.append("Use expansion handles only for bounded follow-up context.")
    return actions[: DEFAULT_CONTEXT_PACK_BUDGET["max_next_actions"]]


def _apply_character_budget(pack: dict[str, Any], max_total_chars: int) -> dict[str, Any]:
    if len(json.dumps(pack, sort_keys=True)) <= max_total_chars:
        return pack
    pack = dict(pack)
    pack["lower_priority_context"] = []
    pack["supporting_docs"] = []
    pack["supporting_configs"] = []
    pack["truncation"] = truncation_metadata(fields=["character_budget"])
    return pack


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
        token for token in tokens if token not in {"add", "change", "fix", "the", "to", "update"}
    ]
    return (
        bool(meaningful)
        and len(meaningful) <= 2
        and any(token in _BROAD_TASK_TOKENS for token in meaningful)
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


def _is_test_path(path: str) -> bool:
    return bool(_TEST_PATH_RE.search(path))


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
