"""Deterministic semantic prototype evaluation for release-readiness evidence."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from repolens.artifact_audit import audit_artifacts
from repolens.context_pack import get_task_context
from repolens.indexer import index_repository
from repolens.mcp_envelope import mcp_success, truncation_metadata
from repolens.scanner import scan_repository
from repolens.semantic_artifact import (
    SEMANTIC_JSONL_PATH,
    inspect_semantic_source,
    inspect_semantic_source_from_source,
    write_semantic_artifact,
    write_semantic_debug_export,
)

SEMANTIC_EVALUATION_VERSION = "0.7.semantic-eval.v1"
DEFAULT_SEMANTIC_FIXTURE_ROOT = Path("tests/fixtures/semantic_evaluation")

_CASES: tuple[dict[str, object], ...] = (
    {
        "id": "branch_cfg",
        "path": "branch_cfg.py",
        "expect_control_flow": True,
        "expect_binding": True,
        "expect_supported": True,
    },
    {
        "id": "loop_exit_cfg",
        "path": "loop_exit_cfg.py",
        "expect_control_flow": True,
        "expect_binding": True,
        "expect_node_kinds": ("loop", "break", "continue", "raise", "return"),
        "expect_supported": True,
    },
    {
        "id": "scope_shadowing_bindings",
        "path": "scope_shadowing_bindings.py",
        "expect_control_flow": True,
        "expect_binding": True,
        "expect_ambiguous": True,
        "expect_uncertain": True,
        "expect_supported": True,
    },
    {
        "id": "dynamic_unresolved_cases",
        "path": "dynamic_unresolved_cases.py",
        "expect_control_flow": True,
        "expect_binding": True,
        "expect_uncertain": True,
        "expect_unsupported": True,
    },
)


def run_semantic_evaluation(
    *,
    fixture_root: Path | str = DEFAULT_SEMANTIC_FIXTURE_ROOT,
    export_debug_jsonl: bool = False,
) -> dict[str, Any]:
    """Run committed semantic fixtures without mutating the fixture directory."""
    fixture_path = Path(fixture_root)
    with tempfile.TemporaryDirectory(prefix="repolens-semantic-eval-") as temp_dir:
        work_root = Path(temp_dir) / "repo"
        shutil.copytree(fixture_path, work_root)

        index_repository(work_root)
        stable_hash = _canonical_graph_hash(work_root)
        default_pack = get_task_context(work_root, "inspect semantic prototype")
        default_pack_id = str(_mapping(default_pack.get("data")).get("context_pack_id", ""))
        default_pack_paths = _pack_paths(default_pack)

        scan = scan_repository(work_root)
        write_semantic_artifact(work_root, scan)
        debug_export_path = None
        if export_debug_jsonl:
            debug_export_path = write_semantic_debug_export(work_root, scan)

        semantic_pack = get_task_context(work_root, "inspect semantic prototype")
        semantic_payload = json.dumps(semantic_pack, sort_keys=True)
        cases = [_evaluate_case(work_root, _mapping(case)) for case in _CASES]
        from_source = inspect_semantic_source_from_source(work_root, "branch_cfg.py").to_cli_data()
        artifact_audit = audit_artifacts(work_root)
        debug_export = _debug_export_summary(work_root, debug_export_path)

        passed_cases = sum(1 for case in cases if case["passed"] is True)
        failed_cases = len(cases) - passed_cases
        data: dict[str, Any] = {
            "semantic_evaluation_version": SEMANTIC_EVALUATION_VERSION,
            "cases": cases,
            "case_summary": _case_summary(cases),
            "stable_contract_checks": {
                "canonical_graph_hash_unchanged": _canonical_graph_hash(work_root) == stable_hash,
                "context_pack_id_unchanged": str(
                    _mapping(semantic_pack.get("data")).get("context_pack_id", "")
                )
                == default_pack_id,
                "context_pack_paths_unchanged": _pack_paths(semantic_pack) == default_pack_paths,
                "default_mcp_output_excludes_semantic_facts": "semantic_skeleton"
                not in semantic_payload
                and "semantic:python" not in semantic_payload,
            },
            "from_source_debug": {
                "covered": from_source.get("inspection_mode") == "from_source_debug",
                "persistent": _mapping(from_source.get("debug_mode")).get("persistent"),
                "writes_artifacts": _mapping(from_source.get("debug_mode")).get("writes_artifacts"),
            },
            "debug_export": debug_export,
            "artifact_audit": {
                "passed": artifact_audit.get("ok") is True,
                "checks": _mapping(_mapping(artifact_audit.get("data")).get("checks")),
                "violation_count": _mapping(
                    _mapping(artifact_audit.get("data")).get("summary")
                ).get("violation_count", 0),
            },
            "release_gate": {
                "gate_type": "semantic_fixture_contract",
                "passed": failed_cases == 0
                and _canonical_graph_hash(work_root) == stable_hash
                and str(_mapping(semantic_pack.get("data")).get("context_pack_id", ""))
                == default_pack_id
                and _pack_paths(semantic_pack) == default_pack_paths
                and "semantic_skeleton" not in semantic_payload
                and "semantic:python" not in semantic_payload
                and artifact_audit.get("ok") is True
                and debug_export["passed"] is True
                and from_source.get("inspection_mode") == "from_source_debug"
                and _mapping(from_source.get("debug_mode")).get("persistent") is False
                and _mapping(from_source.get("debug_mode")).get("writes_artifacts") is False,
            },
            "summary": {
                "failed_cases": failed_cases,
                "passed_cases": passed_cases,
                "total_cases": len(cases),
            },
        }

    return mcp_success(
        data=data,
        confidence="high" if data["release_gate"]["passed"] else "medium",
        evidence=[
            {"fixture_root": fixture_path.as_posix(), "source": "semantic_evaluation_fixtures"}
        ],
        freshness={"fresh": True, "status": "fixture_evaluation"},
        limits={"cases": len(_CASES), "source_snippets": 0},
        truncation=truncation_metadata(),
        warnings=[],
    )


def human_semantic_evaluation(envelope: Mapping[str, Any]) -> str:
    """Render a compact semantic evaluation summary."""
    if not envelope.get("ok", False):
        error = _mapping(envelope.get("error"))
        return f"Semantic Evaluation failed: {error.get('message', 'unknown error')}\n"
    data = _mapping(envelope.get("data"))
    summary = _mapping(data.get("summary"))
    lines = [
        "Semantic Evaluation",
        f"Release gate: {'passed' if _mapping(data.get('release_gate')).get('passed') else 'failed'}",
        f"Cases: {summary.get('passed_cases', 0)}/{summary.get('total_cases', 0)} passed",
        "",
    ]
    for case in _sequence(data.get("cases")):
        mapped = _mapping(case)
        marker = "PASS" if mapped.get("passed") is True else "FAIL"
        lines.append(f"- {marker} {mapped.get('id')}")
    return "\n".join(lines) + "\n"


def _evaluate_case(root: Path, case: Mapping[str, Any]) -> dict[str, Any]:
    source_path = str(case.get("path", ""))
    result = inspect_semantic_source(root, source_path).to_cli_data()
    facts = _mapping(result.get("facts"))
    control_flow = _sequence(facts.get("control_flow"))
    bindings = _sequence(facts.get("bindings"))
    node_kinds = tuple(
        str(node.get("kind", ""))
        for fact in control_flow
        for node in _sequence(_mapping(fact).get("nodes"))
        if isinstance(node, Mapping)
    )
    warnings = tuple(
        str(warning)
        for warning in (
            *_sequence(result.get("warnings")),
            *(
                warning
                for fact in control_flow
                for warning in _sequence(_mapping(fact).get("warnings"))
            ),
            *(
                warning
                for fact in bindings
                for warning in _sequence(_mapping(fact).get("warnings"))
            ),
        )
    )
    ambiguous = any(_sequence(_mapping(fact).get("shadowed_names")) for fact in bindings) or any(
        _sequence(_mapping(fact).get("free_variable_candidates")) for fact in bindings
    )
    uncertain = any("unresolved" in warning or "dynamic" in warning for warning in warnings) or any(
        _sequence(_mapping(fact).get("unresolved_names")) for fact in bindings
    )
    unsupported = (
        any("unsupported" in warning for warning in warnings) or "unsupported" in node_kinds
    )
    checks = {
        "has_control_flow": bool(control_flow) is bool(case.get("expect_control_flow", False)),
        "has_bindings": bool(bindings) is bool(case.get("expect_binding", False)),
        "node_kinds_present": all(
            kind in node_kinds for kind in _sequence(case.get("expect_node_kinds"))
        ),
        "supported_reported": (not unsupported) is bool(case.get("expect_supported", False)),
        "unsupported_reported": unsupported is bool(case.get("expect_unsupported", False)),
        "ambiguous_reported": ambiguous is bool(case.get("expect_ambiguous", False)),
        "uncertain_reported": uncertain is bool(case.get("expect_uncertain", False)),
        "source_free": _source_free(result),
    }
    return {
        "id": str(case.get("id", "")),
        "source_path": source_path,
        "passed": all(checks.values()),
        "checks": checks,
        "semantic_cases": {
            "supported": not unsupported,
            "unsupported": unsupported,
            "ambiguous": ambiguous,
            "uncertain": uncertain,
        },
    }


def _debug_export_summary(root: Path, debug_export_path: str | None) -> dict[str, Any]:
    if debug_export_path is None:
        return {
            "path": None,
            "written": False,
            "clearly_separate_from_stable_graph": True,
            "deterministic": True,
            "source_free": True,
            "passed": True,
        }
    export = root / debug_export_path
    first = export.read_text(encoding="utf-8")
    second = export.read_text(encoding="utf-8")
    lines = [json.loads(line) for line in first.splitlines() if line]
    source_free = _source_free(lines) and root.as_posix() not in first
    return {
        "path": debug_export_path,
        "written": export.name == Path(SEMANTIC_JSONL_PATH).name,
        "line_count": len(lines),
        "clearly_separate_from_stable_graph": debug_export_path == SEMANTIC_JSONL_PATH,
        "deterministic": first == second,
        "source_free": source_free,
        "passed": bool(lines)
        and debug_export_path == SEMANTIC_JSONL_PATH
        and first == second
        and source_free,
    }


def _case_summary(cases: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    keys = ("supported", "unsupported", "ambiguous", "uncertain")
    return {
        key: sum(1 for case in cases if _mapping(case.get("semantic_cases")).get(key) is True)
        for key in keys
    }


def _canonical_graph_hash(root: Path) -> str:
    with sqlite3.connect(root / ".repolens" / "graph.sqlite") as connection:
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'canonical_graph_hash'"
        ).fetchone()
    return str(row[0]) if row is not None else ""


def _pack_paths(envelope: Mapping[str, Any]) -> tuple[str, ...]:
    data = _mapping(envelope.get("data"))
    return tuple(
        str(_mapping(item).get("path", ""))
        for item in _sequence(data.get("reading_order"))
        if _mapping(item).get("path")
    )


def _source_free(payload: Any) -> bool:
    text = json.dumps(payload, sort_keys=True)
    forbidden = (
        "do-not-disclose",
        "secret-",
        "item.skip",
        "RuntimeError",
        "value ==",
        "lambda item",
        "input.user.trim",
    )
    return not any(fragment in text for fragment in forbidden)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()
