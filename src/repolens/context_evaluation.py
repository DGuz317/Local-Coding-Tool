"""Local Context Pack Evaluation runner for release-readiness evidence."""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from repolens.artifact_audit import audit_artifacts
from repolens.context_pack import expand_context, get_assistant_preflight, get_task_context
from repolens.context_pack_contract import DEFAULT_CONTEXT_PACK_BUDGET, guard_context_pack_output
from repolens.indexer import index_repository
from repolens.mcp_envelope import mcp_success, truncation_metadata
from repolens.query import GraphQueryService
from repolens.scanner import scan_repository

_CONFIDENCE_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}
_LOCAL_SAVINGS_EXPLANATION = (
    "Estimates compare bounded RepoLens output with deterministic lexical filename/path "
    "search for committed fixtures. They are local evaluation signals, not telemetry, "
    "exact model-token claims, or universal productivity scores."
)
_FORBIDDEN_EVALUATION_STRINGS = (
    "API_TOKEN=abc123",
    "password=hunter2",
    "hunter2",
    "abc123",
)
_FORBIDDEN_FIELD_NAMES = (
    "snippet",
    "source_text",
    "function_body",
    "function_signature",
    "paragraph_excerpt",
    "raw_comment_text",
    "raw_agent_guidance",
)


def run_context_evaluation(
    *,
    manifest_path: Path | str = Path("tests/fixtures/context_pack/evaluation_manifest.json"),
) -> dict[str, Any]:
    """Run committed Context Pack Evaluation fixtures and return CI-suitable JSON."""
    manifest_file = Path(manifest_path)
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest_root = manifest_file.parent.parent.parent.parent
    cases = [
        _evaluate_case(manifest_root, _mapping(case)) for case in _sequence(manifest.get("cases"))
    ]
    passed_cases = sum(1 for case in cases if case["passed"] is True)
    failed_cases = len(cases) - passed_cases
    corpora = _corpora_summary(cases)
    artifact_audit_summary = _artifact_audit_summary(cases)
    local_savings_summary = _local_savings_summary(cases)
    preflight_summary = _preflight_summary(cases)
    release_cases = [case for case in cases if case.get("corpus") == "release_blocking"]
    release_failed_cases = sum(1 for case in release_cases if case["passed"] is not True)
    data = {
        "cases": cases,
        "artifact_audit_summary": artifact_audit_summary,
        "corpora": corpora,
        "local_savings_summary": local_savings_summary,
        "manifest_version": str(manifest.get("manifest_version", "")),
        "preflight_summary": preflight_summary,
        "release_gate": {
            "gate_type": "expectation_based",
            "passed": release_failed_cases == 0,
            "required_cases": [case["id"] for case in release_cases],
        },
        "structural_summary_caching": _structural_summary_caching_assessment(cases),
        "summary": {
            "failed_cases": failed_cases,
            "passed_cases": passed_cases,
            "total_cases": len(cases),
        },
    }
    return guard_context_pack_output(
        mcp_success(
            data=guard_context_pack_output(data),
            confidence="medium" if failed_cases else "high",
            evidence=[{"manifest": manifest_file.name, "source": "context_pack_fixtures"}],
            freshness={"fresh": True, "status": "fixture_evaluation"},
            limits={"cases": len(cases), **DEFAULT_CONTEXT_PACK_BUDGET},
            truncation=truncation_metadata(),
            warnings=[],
        )
    )


def _structural_summary_caching_assessment(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    failed_cases = [str(case.get("id", "")) for case in cases if case.get("passed") is not True]
    findings: list[dict[str, Any]] = []
    if failed_cases:
        findings.append(
            {
                "category": "stability",
                "case_ids": failed_cases,
                "reason": "Context Pack Evaluation failures need diagnosis before adding persisted summary state.",
            }
        )
    return {
        "decision": "defer_persisted_cache" if findings else "derived_on_demand",
        "findings": findings,
        "persisted_cache_enabled": False,
        "reason": (
            "Persisted Structural Summary caching requires a concrete evaluation performance "
            "or stability finding. Current fixture evaluation does not provide one."
        ),
    }


def _corpora_summary(cases: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for case in cases:
        corpus = str(case.get("corpus") or "release_blocking")
        corpus_summary = summary.setdefault(
            corpus, {"failed_cases": 0, "passed_cases": 0, "total_cases": 0}
        )
        corpus_summary["total_cases"] += 1
        if case.get("passed") is True:
            corpus_summary["passed_cases"] += 1
        else:
            corpus_summary["failed_cases"] += 1
    return dict(sorted(summary.items()))


def _local_savings_summary(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    savings = [_mapping(case.get("local_savings")) for case in cases]
    return {
        "approx_tokens_avoided_vs_lexical": sum(
            int(item.get("approx_tokens_avoided_vs_lexical", 0)) for item in savings
        ),
        "baseline": "lexical_path_search",
        "case_count": len(cases),
        "estimate_kind": "local_fixture_metadata_estimate",
        "explanation": _LOCAL_SAVINGS_EXPLANATION,
        "files_avoided_vs_lexical": sum(
            int(item.get("files_avoided_vs_lexical", 0)) for item in savings
        ),
        "first_read_hit_rate_delta_vs_lexical": _average(
            float(item.get("first_read_hit_rate_delta_vs_lexical", 0.0)) for item in savings
        ),
        "likely_irrelevant_files_avoided_vs_lexical": sum(
            int(item.get("likely_irrelevant_files_avoided_vs_lexical", 0)) for item in savings
        ),
        "not_run_command_count": sum(
            int(_mapping(item.get("context_pack")).get("not_run_command_count", 0))
            for item in savings
        ),
        "stale_graph_risk_case_count": sum(
            1
            for item in savings
            if _mapping(item.get("context_pack")).get("stale_graph_risk") is True
        ),
    }


def _preflight_summary(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    evaluated = [case for case in cases if _mapping(case.get("preflight_evidence"))]
    passed = sum(
        1 for case in evaluated if _mapping(case.get("preflight_evidence")).get("ok") is True
    )
    return {
        "evaluated_cases": [str(case.get("id", "")) for case in evaluated],
        "failed_cases": len(evaluated) - passed,
        "passed_cases": passed,
        "purpose": "assistant_preflight_before_broad_repository_reads",
        "total_cases": len(evaluated),
    }


def _artifact_audit_summary(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    evaluated = [case for case in cases if _mapping(case.get("artifact_audit_evidence"))]
    passed = sum(
        1
        for case in evaluated
        if _mapping(case.get("artifact_audit_evidence")).get("passed") is True
    )
    return {
        "evaluated_cases": [str(case.get("id", "")) for case in evaluated],
        "failed_cases": len(evaluated) - passed,
        "passed_cases": passed,
        "purpose": "artifact_safety_disclosure_gate",
        "total_cases": len(evaluated),
    }


def human_context_evaluation(envelope: Mapping[str, Any]) -> str:
    """Render a compact human evaluation summary."""
    if not envelope.get("ok", False):
        error = _mapping(envelope.get("error"))
        return f"Context Pack Evaluation failed: {error.get('message', 'unknown error')}\n"
    data = _mapping(envelope.get("data"))
    summary = _mapping(data.get("summary"))
    lines = [
        "Context Pack Evaluation",
        f"Release gate: {'passed' if _mapping(data.get('release_gate')).get('passed') else 'failed'}",
        f"Cases: {summary.get('passed_cases', 0)}/{summary.get('total_cases', 0)} passed",
        "",
    ]
    for case in _sequence(data.get("cases")):
        mapped = _mapping(case)
        marker = "PASS" if mapped.get("passed") is True else "FAIL"
        lines.append(f"- {marker} [{mapped.get('corpus')}] {mapped.get('id')}")
    local_savings = _mapping(data.get("local_savings_summary"))
    lines.extend(
        [
            "",
            "Local Savings Metrics",
            f"Baseline: {local_savings.get('baseline', 'lexical_path_search')}",
            f"Files avoided vs baseline: {local_savings.get('files_avoided_vs_lexical', 0)}",
            "Savings are estimates from local fixtures, not telemetry, exact model-token claims, "
            "or universal productivity scores.",
        ]
    )
    return "\n".join(lines) + "\n"


def _evaluate_case(manifest_root: Path, case: Mapping[str, Any]) -> dict[str, Any]:
    expected = _mapping(case.get("expected_outcomes"))
    fixture_repo = manifest_root / str(case.get("fixture_repo", ""))
    with tempfile.TemporaryDirectory(prefix="repolens-context-eval-") as temp_dir:
        work_repo = Path(temp_dir) / "repo"
        shutil.copytree(fixture_repo, work_repo)
        index_repository(work_repo)

        task = str(case.get("task", ""))
        focus_hints = [str(hint) for hint in _sequence(case.get("focus_hints"))]
        pack_envelope = get_task_context(work_repo, task, focus_hints=focus_hints)
        expansion_envelope: dict[str, Any] | None = None
        if case.get("expand_first_handle") is True:
            original_pack = _mapping(pack_envelope.get("data"))
            expansion_envelope = expand_context(
                work_repo,
                task,
                str(original_pack.get("context_pack_id", "")),
                _first_expansion_handle(original_pack),
                focus_hints=focus_hints,
            )
        if str(case.get("graph_state", "")) == "stale_but_readable":
            _touch_stale_fixture(work_repo)
            pack_envelope = get_task_context(work_repo, task, focus_hints=focus_hints)
        elif str(case.get("graph_state", "")) == "pack_id_mismatched_with_current_graph":
            original_pack = _mapping(pack_envelope.get("data"))
            first_handle = _first_expansion_handle(original_pack)
            _touch_stale_fixture(work_repo)
            expansion_envelope = expand_context(
                work_repo,
                task,
                str(original_pack.get("context_pack_id", "")),
                first_handle,
                focus_hints=focus_hints,
            )

        preflight_envelope = (
            get_assistant_preflight(work_repo, task, focus_hints=focus_hints)
            if case.get("evaluate_preflight") is True
            else None
        )
        artifact_audit_envelope = (
            audit_artifacts(work_repo) if case.get("evaluate_artifact_audit") is True else None
        )

        reading = GraphQueryService(work_repo).suggest_reading_order(task)
        lexical_paths = _lexical_baseline_paths(work_repo, task)
        case_result = _case_result(
            case,
            expected=expected,
            pack_envelope=pack_envelope,
            reading_envelope=reading,
            lexical_paths=lexical_paths,
            preflight_envelope=preflight_envelope,
            expansion_envelope=expansion_envelope,
            artifact_audit_envelope=artifact_audit_envelope,
            work_repo=work_repo,
        )
        return case_result


def _case_result(
    case: Mapping[str, Any],
    *,
    expected: Mapping[str, Any],
    pack_envelope: Mapping[str, Any],
    reading_envelope: Mapping[str, Any],
    lexical_paths: Sequence[str],
    preflight_envelope: Mapping[str, Any] | None,
    expansion_envelope: Mapping[str, Any] | None,
    artifact_audit_envelope: Mapping[str, Any] | None,
    work_repo: Path,
) -> dict[str, Any]:
    pack = _mapping(pack_envelope.get("data"))
    first_read_paths = _paths(pack.get("first_read_files"))
    likely_test_paths = _paths(pack.get("likely_tests"))
    relevant_paths = _expected_relevant_paths(expected)
    candidate_commands = _all_candidate_commands(pack)
    safety_outcomes = _safety_outcomes(
        case,
        expected=expected,
        pack_envelope=pack_envelope,
        expansion_envelope=expansion_envelope,
        work_repo=work_repo,
    )
    checks = _expectation_checks(
        expected=expected,
        pack_envelope=pack_envelope,
        expansion_envelope=expansion_envelope,
        preflight_envelope=preflight_envelope,
        artifact_audit_envelope=artifact_audit_envelope,
        safety_outcomes=safety_outcomes,
    )
    context_metrics = _metrics_for_paths(
        first_read_paths,
        likely_test_paths=likely_test_paths,
        relevant_paths=relevant_paths,
        expected=expected,
        expansion_count=len(_sequence(pack.get("expansion_handles"))),
        safety_negative_outcomes=safety_outcomes,
        approximate_token_estimate=_context_pack_approx_tokens(pack),
    )
    lexical_metrics = _metrics_for_paths(
        lexical_paths,
        likely_test_paths=[path for path in lexical_paths if _is_test_path(path)],
        relevant_paths=relevant_paths,
        expected=expected,
        expansion_count=0,
        safety_negative_outcomes={},
    )
    reading_paths = _paths(_mapping(reading_envelope.get("data")).get("reading_order"))
    reading_metrics = _metrics_for_paths(
        reading_paths,
        likely_test_paths=[path for path in reading_paths if _is_test_path(path)],
        relevant_paths=relevant_paths,
        expected=expected,
        expansion_count=0,
        safety_negative_outcomes={},
    )
    return {
        "category": str(case.get("category", "")),
        "checks": checks,
        "corpus": str(case.get("corpus") or "release_blocking"),
        "artifact_audit_evidence": _artifact_audit_evidence(artifact_audit_envelope),
        "id": str(case.get("id", "")),
        "local_savings": _local_savings_metrics(
            context_metrics=context_metrics,
            lexical_metrics=lexical_metrics,
            not_run_command_count=sum(
                1 for command in candidate_commands if _mapping(command).get("not_run") is True
            ),
            stale_graph_risk=_stale_graph_risk(pack_envelope),
        ),
        "metrics": {
            "assistant_preflight": _preflight_evidence(preflight_envelope),
            "artifact_audit": _artifact_audit_evidence(artifact_audit_envelope),
            "context_pack": context_metrics,
            "lexical": lexical_metrics,
            "suggest_reading_order": reading_metrics,
        },
        "passed": all(check["passed"] is True for check in checks),
        "preflight_evidence": _preflight_evidence(preflight_envelope),
        "safety_negative_outcomes": safety_outcomes,
    }


def _expectation_checks(
    *,
    expected: Mapping[str, Any],
    pack_envelope: Mapping[str, Any],
    expansion_envelope: Mapping[str, Any] | None,
    preflight_envelope: Mapping[str, Any] | None,
    artifact_audit_envelope: Mapping[str, Any] | None,
    safety_outcomes: Mapping[str, bool],
) -> list[dict[str, Any]]:
    pack = _mapping(pack_envelope.get("data"))
    checks: list[dict[str, Any]] = []
    _add_check(checks, "ok", _expected_ok(expected, pack_envelope, expansion_envelope))
    if "confidence_at_least" in expected:
        _add_check(
            checks,
            "confidence_at_least",
            _confidence_at_least(
                str(pack_envelope.get("confidence", "none")), str(expected["confidence_at_least"])
            ),
        )
    if "confidence_at_most" in expected:
        _add_check(
            checks,
            "confidence_at_most",
            _confidence_at_most(
                str(pack_envelope.get("confidence", "none")), str(expected["confidence_at_most"])
            ),
        )
    if "confidence" in expected:
        _add_check(checks, "confidence", pack_envelope.get("confidence") == expected["confidence"])
    if "first_read_files_include_any" in expected:
        _add_check(
            checks,
            "first_read_files_include_any",
            _includes_any(
                _paths(pack.get("first_read_files")), expected["first_read_files_include_any"]
            ),
        )
    if "likely_tests_include_any" in expected:
        _add_check(
            checks,
            "likely_tests_include_any",
            _includes_any(_paths(pack.get("likely_tests")), expected["likely_tests_include_any"]),
        )
    if "supporting_configs_include_any" in expected:
        _add_check(
            checks,
            "supporting_configs_include_any",
            _includes_any(
                _paths(pack.get("supporting_configs")), expected["supporting_configs_include_any"]
            ),
        )
    if "supporting_docs_include_any" in expected:
        _add_check(
            checks,
            "supporting_docs_include_any",
            _includes_any(
                _paths(pack.get("supporting_docs")), expected["supporting_docs_include_any"]
            ),
        )
    if "package_boundaries_include" in expected:
        for expected_boundary in _sequence(expected["package_boundaries_include"]):
            mapped_boundary = _mapping(expected_boundary)
            name = str(mapped_boundary.get("name", ""))
            path = str(mapped_boundary.get("path", ""))
            _add_check(
                checks,
                f"package_boundaries_include:{name or path}",
                _package_boundary_present(pack, name=name, path=path),
            )
    if "workspace_memberships_include" in expected:
        for expected_membership in _sequence(expected["workspace_memberships_include"]):
            mapped_membership = _mapping(expected_membership)
            package_name = str(mapped_membership.get("package_name", ""))
            package_root = str(mapped_membership.get("package_root", ""))
            _add_check(
                checks,
                f"workspace_memberships_include:{package_name or package_root}",
                _workspace_membership_present(
                    pack, package_name=package_name, package_root=package_root
                ),
            )
    if "relationship_candidates_include" in expected:
        for expected_candidate in _sequence(expected["relationship_candidates_include"]):
            mapped_candidate = _mapping(expected_candidate)
            label = str(
                mapped_candidate.get("warning_code")
                or mapped_candidate.get("resolution_status")
                or mapped_candidate.get("reason")
                or mapped_candidate.get("specifier")
            )
            _add_check(
                checks,
                f"relationship_candidates_include:{label}",
                _relationship_candidate_present(pack, expected_candidate=mapped_candidate),
            )
    if "graph_quality_warning_codes_include" in expected:
        for expected_code in _sequence(expected["graph_quality_warning_codes_include"]):
            _add_check(
                checks,
                f"graph_quality_warning_codes_include:{expected_code}",
                str(expected_code) in _graph_quality_warning_codes(pack),
            )
    if "ambiguity_candidates_include_any" in expected:
        _add_check(
            checks,
            "ambiguity_candidates_include_any",
            _includes_any(
                _paths(pack.get("ambiguity")), expected["ambiguity_candidates_include_any"]
            ),
        )
    if "candidate_command_risk_buckets_include" in expected:
        risk_buckets = {
            str(_mapping(command).get("risk_bucket")) for command in _all_candidate_commands(pack)
        }
        for expected_bucket in _sequence(expected["candidate_command_risk_buckets_include"]):
            _add_check(
                checks,
                f"candidate_command_risk_buckets_include:{expected_bucket}",
                str(expected_bucket) in risk_buckets,
            )
    if "candidate_commands_include" in expected:
        for expected_command in _sequence(expected["candidate_commands_include"]):
            mapped_command = _mapping(expected_command)
            name = str(mapped_command.get("name", ""))
            _add_check(
                checks,
                f"candidate_commands_include:{name}",
                _candidate_command_present(pack, expected_command=mapped_command),
            )
    if "first_read_files_max" in expected:
        _add_check(
            checks,
            "first_read_files_max",
            len(_paths(pack.get("first_read_files"))) <= int(expected["first_read_files_max"]),
        )
    if expected.get("bounded_by_default_budget") is True:
        _add_check(
            checks,
            "bounded_by_default_budget",
            len(_paths(pack.get("first_read_files")))
            <= DEFAULT_CONTEXT_PACK_BUDGET["max_first_read_files"],
        )
    if "freshness_status" in expected:
        _add_check(
            checks,
            "freshness_status",
            _mapping(pack.get("freshness")).get("status") == expected["freshness_status"],
        )
    if "warnings_include" in expected:
        warnings = [str(warning) for warning in _sequence(pack_envelope.get("warnings"))]
        for expected_warning in _sequence(expected["warnings_include"]):
            _add_check(
                checks,
                f"warnings_include:{expected_warning}",
                _warning_present(warnings, str(expected_warning)),
            )
    if "error_code" in expected:
        target_envelope = expansion_envelope or pack_envelope
        _add_check(
            checks,
            "error_code",
            _mapping(target_envelope.get("error")).get("code") == expected["error_code"],
        )
    if "expansion_ok" in expected:
        _add_check(
            checks,
            "expansion_ok",
            expansion_envelope is not None
            and expansion_envelope.get("ok") is expected["expansion_ok"],
        )
    if "assistant_preflight_ok" in expected:
        _add_check(
            checks,
            "assistant_preflight_ok",
            preflight_envelope is not None
            and preflight_envelope.get("ok") is expected["assistant_preflight_ok"],
        )
    if "assistant_preflight_version" in expected:
        _add_check(
            checks,
            "assistant_preflight_version",
            preflight_envelope is not None
            and _mapping(preflight_envelope.get("data")).get("assistant_preflight_version")
            == expected["assistant_preflight_version"],
        )
    if "artifact_audit_passed" in expected:
        _add_check(
            checks,
            "artifact_audit_passed",
            artifact_audit_envelope is not None
            and _mapping(_mapping(artifact_audit_envelope.get("data")).get("summary")).get("passed")
            is expected["artifact_audit_passed"],
        )
    for name, passed in safety_outcomes.items():
        _add_check(checks, name, passed)
    return checks


def _preflight_evidence(envelope: Mapping[str, Any] | None) -> dict[str, Any]:
    if envelope is None:
        return {}
    data = _mapping(envelope.get("data"))
    return {
        "candidate_commands_not_run": all(
            _mapping(command).get("not_run") is True
            for command in _sequence(data.get("candidate_verification_commands"))
        ),
        "first_read_count": len(_paths(data.get("first_read_files"))),
        "freshness_status": _mapping(data.get("freshness")).get("status", ""),
        "ok": envelope.get("ok") is True,
        "version": str(data.get("assistant_preflight_version", "")),
    }


def _artifact_audit_evidence(envelope: Mapping[str, Any] | None) -> dict[str, Any]:
    if envelope is None:
        return {}
    data = _mapping(envelope.get("data"))
    summary = _mapping(data.get("summary"))
    return {
        "audited_artifact_count": len(_sequence(data.get("audited_artifacts"))),
        "ok": envelope.get("ok") is True,
        "passed": summary.get("passed") is True,
        "violation_count": int(summary.get("violation_count", 0)),
    }


def _safety_outcomes(
    case: Mapping[str, Any],
    *,
    expected: Mapping[str, Any],
    pack_envelope: Mapping[str, Any],
    expansion_envelope: Mapping[str, Any] | None,
    work_repo: Path,
) -> dict[str, bool]:
    outcomes: dict[str, bool] = {}
    serialized = json.dumps(pack_envelope, sort_keys=True)
    if expansion_envelope is not None:
        serialized = f"{serialized}\n{json.dumps(expansion_envelope, sort_keys=True)}"
    if expected.get("raw_task_text_absent") is True or expected.get("redacted_task_text") is True:
        outcomes["raw_task_text_absent"] = not any(
            forbidden in serialized for forbidden in _FORBIDDEN_EVALUATION_STRINGS
        )
    if expected.get("pack_id_does_not_include_secret_fragments") is True:
        pack_id = str(_mapping(pack_envelope.get("data")).get("context_pack_id", ""))
        outcomes["pack_id_redacted_fragments_absent"] = not any(
            forbidden in pack_id for forbidden in _FORBIDDEN_EVALUATION_STRINGS
        )
    if expected.get("handles_do_not_include_secret_fragments") is True:
        handles = json.dumps(_mapping(pack_envelope.get("data")).get("expansion_handles", []))
        outcomes["handles_redacted_fragments_absent"] = not any(
            forbidden in handles for forbidden in _FORBIDDEN_EVALUATION_STRINGS
        )
    if expected.get("no_source_snippets") is True or expected.get(
        "forbidden_fields_rejected_or_sanitized"
    ):
        outcomes["no_source_snippets"] = not any(
            f'"{field}"' in serialized for field in _FORBIDDEN_FIELD_NAMES
        )
    if expected.get("candidate_commands_marked_not_run") is True:
        commands = _all_candidate_commands(_mapping(pack_envelope.get("data")))
        outcomes["candidate_commands_marked_not_run"] = bool(commands) and all(
            _mapping(command).get("not_run") is True
            and _mapping(command).get("auto_run_recommended") is False
            for command in commands
        )
    if expected.get("invalid_outside_root_hints_are_errors") is True:
        outside = work_repo.parent / "outside.py"
        invalid = get_task_context(work_repo, str(case.get("task", "")), focus_hints=[str(outside)])
        outcomes["invalid_outside_root_hints_are_errors"] = (
            invalid.get("ok") is False
            and _mapping(invalid.get("error")).get("code") == "focus_hint_outside_root"
        )
    if expected.get("requires_fresh_pack") is True and expansion_envelope is not None:
        outcomes["requires_fresh_pack"] = (
            _mapping(expansion_envelope.get("error")).get("requires_new_pack") is True
        )
    if expected.get("repo_relative_paths_only") is True:
        outcomes["repo_relative_paths_only"] = str(work_repo) not in serialized
    return outcomes


def _metrics_for_paths(
    paths: Sequence[str],
    *,
    likely_test_paths: Sequence[str],
    relevant_paths: set[str],
    expected: Mapping[str, Any],
    expansion_count: int,
    safety_negative_outcomes: Mapping[str, bool],
    approximate_token_estimate: int | None = None,
) -> dict[str, Any]:
    expected_first_read = {
        str(path) for path in _sequence(expected.get("first_read_files_include_any"))
    }
    first_read_hit_rate = 0.0
    if expected_first_read:
        first_read_hit_rate = 1.0 if expected_first_read.intersection(paths) else 0.0
    expected_tests = {str(path) for path in _sequence(expected.get("likely_tests_include_any"))}
    test_inclusion = 0.0
    if expected_tests:
        test_inclusion = 1.0 if expected_tests.intersection(likely_test_paths) else 0.0
    irrelevant_file_count = 0
    if relevant_paths:
        irrelevant_file_count = sum(1 for path in paths if path not in relevant_paths)
    return {
        "approximate_token_estimate": approximate_token_estimate
        if approximate_token_estimate is not None
        else _approx_tokens_for_paths(paths),
        "expansion_count": expansion_count,
        "first_read_hit_rate": first_read_hit_rate,
        "irrelevant_file_count": irrelevant_file_count,
        "pack_size": len(paths),
        "safety_negative_outcomes": sum(
            1 for passed in safety_negative_outcomes.values() if passed is True
        ),
        "test_inclusion": test_inclusion,
    }


def _local_savings_metrics(
    *,
    context_metrics: Mapping[str, Any],
    lexical_metrics: Mapping[str, Any],
    not_run_command_count: int,
    stale_graph_risk: bool,
) -> dict[str, Any]:
    context_pack = {
        "approximate_token_estimate": int(context_metrics.get("approximate_token_estimate", 0)),
        "first_read_hit_rate": float(context_metrics.get("first_read_hit_rate", 0.0)),
        "likely_irrelevant_file_count": int(context_metrics.get("irrelevant_file_count", 0)),
        "not_run_command_count": not_run_command_count,
        "pack_size": int(context_metrics.get("pack_size", 0)),
        "stale_graph_risk": stale_graph_risk,
    }
    lexical = {
        "approximate_token_estimate": int(lexical_metrics.get("approximate_token_estimate", 0)),
        "first_read_hit_rate": float(lexical_metrics.get("first_read_hit_rate", 0.0)),
        "likely_irrelevant_file_count": int(lexical_metrics.get("irrelevant_file_count", 0)),
        "not_run_command_count": 0,
        "pack_size": int(lexical_metrics.get("pack_size", 0)),
        "stale_graph_risk": False,
    }
    return {
        "approx_tokens_avoided_vs_lexical": lexical["approximate_token_estimate"]
        - context_pack["approximate_token_estimate"],
        "baseline": "lexical_path_search",
        "context_pack": context_pack,
        "estimate_kind": "local_fixture_metadata_estimate",
        "explanation": _LOCAL_SAVINGS_EXPLANATION,
        "files_avoided_vs_lexical": lexical["pack_size"] - context_pack["pack_size"],
        "first_read_hit_rate_delta_vs_lexical": round(
            context_pack["first_read_hit_rate"] - lexical["first_read_hit_rate"], 3
        ),
        "lexical_baseline": lexical,
        "likely_irrelevant_files_avoided_vs_lexical": lexical["likely_irrelevant_file_count"]
        - context_pack["likely_irrelevant_file_count"],
    }


def _context_pack_approx_tokens(pack: Mapping[str, Any]) -> int:
    budget = _mapping(pack.get("budget"))
    try:
        return int(budget.get("approx_tokens", 0))
    except (TypeError, ValueError):
        return 0


def _approx_tokens_for_paths(paths: Sequence[str]) -> int:
    serialized_chars = len(
        json.dumps({"first_read_files": [{"path": path} for path in paths]}, sort_keys=True)
    )
    return serialized_chars // DEFAULT_CONTEXT_PACK_BUDGET["approx_token_estimate_divisor"] + 1


def _stale_graph_risk(envelope: Mapping[str, Any]) -> bool:
    freshness = _mapping(_mapping(envelope.get("data")).get("freshness"))
    status = str(freshness.get("status", ""))
    return status in {"stale", "rebuild_required"} or freshness.get("fresh") is False


def _average(values: Iterable[float]) -> float:
    items = list(values)
    if not items:
        return 0.0
    return round(sum(items) / len(items), 3)


def _lexical_baseline_paths(repo_path: Path, task: str, *, max_files: int = 7) -> list[str]:
    tokens = _tokens(task)
    scored: list[tuple[int, str]] = []
    for scanned_file in scan_repository(repo_path).files:
        path = scanned_file.path
        path_text = path.lower().replace("/", " ").replace("_", " ").replace("-", " ")
        score = sum(1 for token in tokens if token in path_text)
        if score:
            scored.append((-score, path))
    return [path for _, path in sorted(scored)[:max_files]]


def _touch_stale_fixture(repo_path: Path) -> None:
    candidates = [
        repo_path / "src" / "auth" / "login.py",
        repo_path / "src" / "demo.py",
        next(repo_path.rglob("*.py"), None),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            candidate.write_text(
                candidate.read_text(encoding="utf-8") + "\nSTALE_MARKER = True\n", encoding="utf-8"
            )
            return


def _expected_ok(
    expected: Mapping[str, Any],
    pack_envelope: Mapping[str, Any],
    expansion_envelope: Mapping[str, Any] | None,
) -> bool:
    if "ok" not in expected:
        return True
    target_envelope = expansion_envelope or pack_envelope
    return target_envelope.get("ok") is expected["ok"]


def _expected_relevant_paths(expected: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    for key in (
        "first_read_files_include_any",
        "likely_tests_include_any",
        "supporting_configs_include_any",
        "supporting_docs_include_any",
        "ambiguity_candidates_include_any",
    ):
        result.update(str(path) for path in _sequence(expected.get(key)))
    return result


def _all_pack_items(pack: Mapping[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key in (
        "first_read_files",
        "likely_tests",
        "supporting_docs",
        "supporting_configs",
        "lower_priority_context",
        "ambiguity",
        "candidate_verification_commands",
        "risk_signals",
        "agent_guidance",
    ):
        items.extend(_mapping(item) for item in _sequence(pack.get(key)))
    return items


def _package_boundary_present(pack: Mapping[str, Any], *, name: str, path: str) -> bool:
    for item in _all_pack_items(pack):
        boundary = _mapping(item.get("package_boundary"))
        if (
            boundary
            and (not name or boundary.get("name") == name)
            and (not path or boundary.get("path") == path)
        ):
            return True
    return False


def _workspace_membership_present(
    pack: Mapping[str, Any], *, package_name: str, package_root: str
) -> bool:
    for item in _all_pack_items(pack):
        membership = _mapping(item.get("workspace_membership"))
        if (
            membership
            and (not package_name or membership.get("package_name") == package_name)
            and (not package_root or membership.get("package_root") == package_root)
        ):
            return True
    return False


def _relationship_candidate_present(
    pack: Mapping[str, Any], *, expected_candidate: Mapping[str, Any]
) -> bool:
    for item in _all_pack_items(pack):
        for candidate in (
            _mapping(value) for value in _sequence(item.get("relationship_candidates"))
        ):
            if all(candidate.get(key) == value for key, value in expected_candidate.items()):
                return True
    return False


def _graph_quality_warning_codes(pack: Mapping[str, Any]) -> set[str]:
    codes: set[str] = set()
    for item in _all_pack_items(pack):
        codes.update(str(code) for code in _sequence(item.get("graph_quality_warning_codes")))
    return codes


def _all_candidate_commands(pack: Mapping[str, Any]) -> list[dict[str, Any]]:
    commands = [_mapping(value) for value in _sequence(pack.get("candidate_verification_commands"))]
    for item in _all_pack_items(pack):
        summary = _mapping(item.get("structural_summary"))
        commands.extend(
            _mapping(command) for command in _sequence(summary.get("candidate_commands"))
        )
    return commands


def _candidate_command_present(
    pack: Mapping[str, Any], *, expected_command: Mapping[str, Any]
) -> bool:
    for command in _all_candidate_commands(pack):
        if all(command.get(key) == value for key, value in expected_command.items()):
            return True
    return False


def _paths(items: Any) -> list[str]:
    return [
        str(item.get("path"))
        for item in (_mapping(item) for item in _sequence(items))
        if item.get("path")
    ]


def _includes_any(paths: Sequence[str], expected_paths: Any) -> bool:
    return bool(set(paths).intersection(str(path) for path in _sequence(expected_paths)))


def _warning_present(warnings: Sequence[str], expected_warning: str) -> bool:
    aliases = {
        "breadth_warning": "broad",
        "stale_graph": "stale",
        "unresolved_focus_hint": "unresolved focus hint",
    }
    needle = aliases.get(expected_warning, expected_warning).lower().replace("_", " ")
    return any(needle in warning.lower().replace("_", " ") for warning in warnings)


def _confidence_at_least(actual: str, expected: str) -> bool:
    return _CONFIDENCE_RANK.get(actual, 0) >= _CONFIDENCE_RANK.get(expected, 0)


def _confidence_at_most(actual: str, expected: str) -> bool:
    return _CONFIDENCE_RANK.get(actual, 0) <= _CONFIDENCE_RANK.get(expected, 0)


def _first_expansion_handle(pack: Mapping[str, Any]) -> str:
    handles = _sequence(pack.get("expansion_handles"))
    if not handles:
        return "item_missing"
    return str(_mapping(handles[0]).get("handle", "item_missing"))


def _tokens(value: str) -> tuple[str, ...]:
    stopwords = {"a", "add", "and", "fix", "for", "in", "of", "the", "to"}
    return tuple(
        token
        for token in "".join(char.lower() if char.isalnum() else " " for char in value).split()
        if len(token) > 2 and token not in stopwords
    )


def _is_test_path(path: str) -> bool:
    lowered = path.lower()
    return (
        "/test" in lowered
        or lowered.startswith("test")
        or ".test." in lowered
        or ".spec." in lowered
    )


def _add_check(checks: list[dict[str, Any]], name: str, passed: bool) -> None:
    checks.append({"name": name, "passed": bool(passed)})


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []
