from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from repolens.cli import app
from repolens.context_evaluation import run_context_evaluation

runner = CliRunner()


def test_context_evaluation_runs_manifest_cases_with_metrics() -> None:
    manifest_path = Path("tests/fixtures/context_pack/evaluation_manifest.json")

    envelope = run_context_evaluation(manifest_path=manifest_path)

    assert envelope["ok"] is True
    data = envelope["data"]
    assert data["manifest_version"] == "0.4.eval.v1"
    assert data["summary"]["total_cases"] == 19
    assert data["summary"]["passed_cases"] == 19
    assert data["summary"]["failed_cases"] == 0
    assert data["release_gate"]["passed"] is True
    assert data["release_gate"]["required_cases"] == [
        case["id"] for case in data["cases"] if case["corpus"] == "release_blocking"
    ]
    assert data["corpora"] == {
        "expanded": {"failed_cases": 0, "passed_cases": 1, "total_cases": 1},
        "release_blocking": {"failed_cases": 0, "passed_cases": 18, "total_cases": 18},
    }
    assert data["structural_summary_caching"] == {
        "decision": "derived_on_demand",
        "findings": [],
        "persisted_cache_enabled": False,
        "reason": (
            "Persisted Structural Summary caching requires a concrete evaluation performance "
            "or stability finding. Current fixture evaluation does not provide one."
        ),
    }
    assert data["local_savings_summary"]["baseline"] == "lexical_path_search"
    assert data["local_savings_summary"]["estimate_kind"] == ("local_fixture_metadata_estimate")
    assert data["local_savings_summary"]["case_count"] == 19
    assert data["local_savings_summary"]["not_run_command_count"] >= 1
    assert data["local_savings_summary"]["stale_graph_risk_case_count"] == 1
    assert "not telemetry" in data["local_savings_summary"]["explanation"]

    case_by_id = {case["id"]: case for case in data["cases"]}
    direct_case = case_by_id["happy_path_direct_symbol_login"]
    assert direct_case["passed"] is True
    assert direct_case["metrics"]["context_pack"]["first_read_hit_rate"] == 1.0
    assert direct_case["metrics"]["context_pack"]["approximate_token_estimate"] >= 1
    assert direct_case["metrics"]["suggest_reading_order"]["pack_size"] >= 1
    assert "lexical" in direct_case["metrics"]
    assert direct_case["local_savings"]["baseline"] == "lexical_path_search"
    assert direct_case["local_savings"]["files_avoided_vs_lexical"] == 0
    assert (
        direct_case["local_savings"]["context_pack"]["approximate_token_estimate"]
        == (direct_case["metrics"]["context_pack"]["approximate_token_estimate"])
    )
    assert direct_case["local_savings"]["context_pack"]["first_read_hit_rate"] == 1.0
    assert direct_case["local_savings"]["context_pack"]["likely_irrelevant_file_count"] == 0
    assert direct_case["local_savings"]["context_pack"]["not_run_command_count"] >= 1
    assert direct_case["local_savings"]["context_pack"]["pack_size"] == 2
    assert direct_case["local_savings"]["context_pack"]["stale_graph_risk"] is False
    assert direct_case["local_savings"]["lexical_baseline"]["pack_size"] == 2
    assert direct_case["local_savings"]["lexical_baseline"]["likely_irrelevant_file_count"] == 1

    safety_case = case_by_id["secret_redaction_task_and_hints"]
    assert safety_case["safety_negative_outcomes"]["raw_task_text_absent"] is True
    assert safety_case["safety_negative_outcomes"]["pack_id_redacted_fragments_absent"] is True
    assert "API_TOKEN=abc123" not in json.dumps(envelope)

    expanded_case = case_by_id["expanded_cli_invoice_export"]
    assert expanded_case["corpus"] == "expanded"
    assert expanded_case["metrics"]["context_pack"]["first_read_hit_rate"] == 1.0

    workspace_case = case_by_id["v0_4_js_ts_workspace_package_import"]
    assert workspace_case["passed"] is True
    assert workspace_case["metrics"]["context_pack"]["expansion_count"] >= 1

    unresolved_case = case_by_id["v0_4_unresolved_ts_alias_warning"]
    assert unresolved_case["passed"] is True
    assert any(
        check["name"]
        == "relationship_candidates_include:graph_quality:unresolved_import_relationship"
        for check in unresolved_case["checks"]
    )

    command_case = case_by_id["v0_4_command_risk_bucket_gate"]
    assert command_case["passed"] is True
    assert command_case["local_savings"]["context_pack"]["not_run_command_count"] >= 1
    assert any(
        check["name"] == "candidate_command_risk_buckets_include:risky_or_external"
        for check in command_case["checks"]
    )


def test_evaluate_context_cli_emits_json_for_ci() -> None:
    result = runner.invoke(
        app,
        [
            "evaluate-context",
            "--manifest",
            "tests/fixtures/context_pack/evaluation_manifest.json",
            "--json",
        ],
    )

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    assert envelope["ok"] is True
    assert envelope["data"]["release_gate"]["passed"] is True
    assert "local_savings_summary" in envelope["data"]


def test_evaluate_context_human_output_explains_savings_are_estimates() -> None:
    result = runner.invoke(
        app,
        [
            "evaluate-context",
            "--manifest",
            "tests/fixtures/context_pack/evaluation_manifest.json",
        ],
    )

    assert result.exit_code == 0
    assert "Local Savings Metrics" in result.output
    assert "Savings are estimates from local fixtures" in result.output
    assert "not telemetry" in result.output
