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
    assert data["manifest_version"] == "0.9.eval.v1"
    assert data["metric_contract"] == {
        "baseline": (
            "scanner-approved paths ranked by descending task-token matches, then POSIX path; "
            "limited to seven files"
        ),
        "expansion_count": "bounded expansion handles available in the initial Context Pack",
        "first_read_hit_rate": "expected relevant files present in First-Read Files",
        "irrelevant_file_count": (
            "returned paths outside declared relevant files and Related Tests"
        ),
        "pack_size": "number of paths in the evaluated orientation list",
        "related_test_inclusion": "expected Related Tests present in likely tests",
        "version": "0.9.metrics.v1",
    }
    assert data["summary"]["total_cases"] == 28
    assert data["summary"]["passed_cases"] == 28
    assert data["summary"]["failed_cases"] == 0
    assert data["release_gate"]["passed"] is True
    assert data["release_gate"]["required_cases"] == [
        case["id"] for case in data["cases"] if case["corpus"] == "release_blocking"
    ]
    assert data["corpora"] == {
        "expanded": {"failed_cases": 0, "passed_cases": 1, "total_cases": 1},
        "release_blocking": {"failed_cases": 0, "passed_cases": 27, "total_cases": 27},
    }
    assert data["preflight_summary"] == {
        "evaluated_cases": [
            "v0_5_dogfood_js_ts_workspace_preflight_audit",
            "v0_5_dogfood_python_package_preflight",
            "v0_5_dogfood_docs_heavy_preflight",
            "v0_5_dogfood_config_heavy_artifact_audit",
            "v0_6_js_ts_route_hint_first_read",
        ],
        "failed_cases": 0,
        "passed_cases": 5,
        "purpose": "assistant_preflight_before_broad_repository_reads",
        "total_cases": 5,
    }
    assert data["index_evidence_summary"]["case_count"] == 28
    assert data["index_evidence_summary"]["eligible_file_count"] >= 1
    assert data["index_evidence_summary"]["max_index_elapsed_ms"] >= 0
    assert data["index_evidence_summary"]["measurement"] == ("bounded_local_fixture_index_timing")
    assert data["artifact_audit_summary"] == {
        "evaluated_cases": [
            "v0_5_dogfood_js_ts_workspace_preflight_audit",
            "v0_5_dogfood_config_heavy_artifact_audit",
        ],
        "failed_cases": 0,
        "passed_cases": 2,
        "purpose": "artifact_safety_disclosure_gate",
        "total_cases": 2,
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
    assert data["local_savings_summary"]["case_count"] == 28
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

    hygiene_case = case_by_id["v0_9_context_hygiene"]
    assert hygiene_case["passed"] is True
    assert hygiene_case["index_evidence"]["eligible_file_count"] == 3
    assert hygiene_case["index_evidence"]["skipped_path_count"] == 3
    assert hygiene_case["metrics"]["context_pack"]["irrelevant_file_count"] == 0
    assert {check["name"] for check in hygiene_case["checks"]} >= {
        "deprioritized_context_include_any",
        "likely_irrelevant_file_count_max",
    }

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

    js_dogfood_case = case_by_id["v0_5_dogfood_js_ts_workspace_preflight_audit"]
    assert js_dogfood_case["preflight_evidence"] == {
        "candidate_commands_not_run": True,
        "first_read_count": 3,
        "freshness_status": "available",
        "ok": True,
        "version": "0.5.preflight.v1",
    }
    assert js_dogfood_case["artifact_audit_evidence"]["passed"] is True
    assert js_dogfood_case["evaluation_expectations"] == {
        "related_tests": [],
        "relevant_files": [
            "packages/app/src/index.ts",
            "packages/lib/src/index.ts",
            "packages/lib/src/value.ts",
        ],
    }
    assert js_dogfood_case["metrics"]["context_pack"]["first_read_hit_rate"] == 1.0
    assert js_dogfood_case["metrics"]["context_pack"]["irrelevant_file_count"] == 0
    assert {check["name"] for check in js_dogfood_case["checks"]} >= {
        "metric:first_read_hit_rate_min",
        "metric:irrelevant_file_count_max",
        "metric:pack_size_max",
    }

    python_dogfood_case = case_by_id["v0_5_dogfood_python_package_preflight"]
    assert python_dogfood_case["passed"] is True
    assert python_dogfood_case["evaluation_expectations"] == {
        "related_tests": ["tests/service_spec.py"],
        "relevant_files": ["src/dogpkg/service.py", "src/dogpkg/util.py"],
    }
    assert python_dogfood_case["metrics"]["assistant_preflight"]["ok"] is True
    assert python_dogfood_case["metrics"]["context_pack"]["first_read_hit_rate"] == 1.0
    assert python_dogfood_case["metrics"]["context_pack"]["related_test_inclusion"] == 1.0
    assert python_dogfood_case["metrics"]["context_pack"]["pack_size"] == 3
    assert {check["name"] for check in python_dogfood_case["checks"]} >= {
        "metric:first_read_hit_rate_min",
        "metric:irrelevant_file_count_max",
        "metric:pack_size_max",
        "metric:related_test_inclusion_min",
    }

    config_dogfood_case = case_by_id["v0_5_dogfood_config_heavy_artifact_audit"]
    assert config_dogfood_case["passed"] is True
    assert config_dogfood_case["metrics"]["artifact_audit"]["violation_count"] == 0

    v0_6_import_case = case_by_id["v0_6_js_ts_resolved_workspace_import_rank_improvement"]
    assert v0_6_import_case["passed"] is True
    assert v0_6_import_case["local_savings"]["context_pack"]["first_relevant_rank"] == 1
    assert v0_6_import_case["local_savings"]["lexical_baseline"]["first_relevant_rank"] > 1
    assert v0_6_import_case["local_savings"]["first_relevant_rank_delta_vs_lexical"] > 0

    v0_6_route_case = case_by_id["v0_6_js_ts_route_hint_first_read"]
    assert v0_6_route_case["passed"] is True
    assert v0_6_route_case["metrics"]["context_pack"]["first_relevant_rank"] == 1
    assert v0_6_route_case["metrics"]["assistant_preflight"]["ok"] is True

    v0_6_call_chain_case = case_by_id["v0_6_js_ts_call_chain_facts_source_free"]
    assert v0_6_call_chain_case["passed"] is True
    assert any(
        check["name"] == "structural_call_chains_include:packages/app/src/index.ts"
        for check in v0_6_call_chain_case["checks"]
    )

    v0_6_reexport_case = case_by_id["v0_6_js_ts_reexport_behavior"]
    assert v0_6_reexport_case["passed"] is True
    assert any(
        check["name"] == "javascript_exports_include:packages/lib/src/index.ts"
        for check in v0_6_reexport_case["checks"]
    )


def test_context_evaluation_relevance_and_savings_metrics_are_deterministic() -> None:
    manifest_path = Path("tests/fixtures/context_pack/evaluation_manifest.json")

    first = run_context_evaluation(manifest_path=manifest_path)["data"]
    second = run_context_evaluation(manifest_path=manifest_path)["data"]

    def stable_evidence(data):
        return {
            "local_savings_summary": data["local_savings_summary"],
            "metric_contract": data["metric_contract"],
            "cases": [
                {
                    "evaluation_expectations": case["evaluation_expectations"],
                    "id": case["id"],
                    "local_savings": case["local_savings"],
                    "metrics": case["metrics"],
                    "passed": case["passed"],
                }
                for case in data["cases"]
            ],
        }

    assert stable_evidence(first) == stable_evidence(second)


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
