"""Local Context Pack Evaluation runner for release-readiness evidence."""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from repolens.context_pack import expand_context, get_task_context
from repolens.context_pack_contract import DEFAULT_CONTEXT_PACK_BUDGET, guard_context_pack_output
from repolens.indexer import index_repository
from repolens.mcp_envelope import mcp_success, truncation_metadata
from repolens.query import GraphQueryService
from repolens.scanner import scan_repository

_CONFIDENCE_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}
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
    data = {
        "cases": cases,
        "manifest_version": str(manifest.get("manifest_version", "")),
        "release_gate": {
            "gate_type": "expectation_based",
            "passed": failed_cases == 0,
            "required_cases": [case["id"] for case in cases],
        },
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
        lines.append(f"- {marker} {mapped.get('id')}")
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

        reading = GraphQueryService(work_repo).suggest_reading_order(task)
        lexical_paths = _lexical_baseline_paths(work_repo, task)
        case_result = _case_result(
            case,
            expected=expected,
            pack_envelope=pack_envelope,
            reading_envelope=reading,
            lexical_paths=lexical_paths,
            expansion_envelope=expansion_envelope,
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
    expansion_envelope: Mapping[str, Any] | None,
    work_repo: Path,
) -> dict[str, Any]:
    pack = _mapping(pack_envelope.get("data"))
    first_read_paths = _paths(pack.get("first_read_files"))
    likely_test_paths = _paths(pack.get("likely_tests"))
    relevant_paths = _expected_relevant_paths(expected)
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
        safety_outcomes=safety_outcomes,
    )
    return {
        "category": str(case.get("category", "")),
        "checks": checks,
        "id": str(case.get("id", "")),
        "metrics": {
            "context_pack": _metrics_for_paths(
                first_read_paths,
                likely_test_paths=likely_test_paths,
                relevant_paths=relevant_paths,
                expected=expected,
                expansion_count=len(_sequence(pack.get("expansion_handles"))),
                safety_negative_outcomes=safety_outcomes,
            ),
            "lexical": _metrics_for_paths(
                lexical_paths,
                likely_test_paths=[path for path in lexical_paths if _is_test_path(path)],
                relevant_paths=relevant_paths,
                expected=expected,
                expansion_count=0,
                safety_negative_outcomes={},
            ),
            "suggest_reading_order": _metrics_for_paths(
                _paths(_mapping(reading_envelope.get("data")).get("reading_order")),
                likely_test_paths=[
                    path
                    for path in _paths(_mapping(reading_envelope.get("data")).get("reading_order"))
                    if _is_test_path(path)
                ],
                relevant_paths=relevant_paths,
                expected=expected,
                expansion_count=0,
                safety_negative_outcomes={},
            ),
        },
        "passed": all(check["passed"] is True for check in checks),
        "safety_negative_outcomes": safety_outcomes,
    }


def _expectation_checks(
    *,
    expected: Mapping[str, Any],
    pack_envelope: Mapping[str, Any],
    expansion_envelope: Mapping[str, Any] | None,
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
    if "ambiguity_candidates_include_any" in expected:
        _add_check(
            checks,
            "ambiguity_candidates_include_any",
            _includes_any(
                _paths(pack.get("ambiguity")), expected["ambiguity_candidates_include_any"]
            ),
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
    for name, passed in safety_outcomes.items():
        _add_check(checks, name, passed)
    return checks


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
        commands = _sequence(
            _mapping(pack_envelope.get("data")).get("candidate_verification_commands")
        )
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
        "expansion_count": expansion_count,
        "first_read_hit_rate": first_read_hit_rate,
        "irrelevant_file_count": irrelevant_file_count,
        "pack_size": len(paths),
        "safety_negative_outcomes": sum(
            1 for passed in safety_negative_outcomes.values() if passed is True
        ),
        "test_inclusion": test_inclusion,
    }


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
