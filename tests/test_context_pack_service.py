from __future__ import annotations

import json
from textwrap import dedent

from typer.testing import CliRunner

from repolens.cli import app
from repolens.context_pack import (
    expand_context,
    explain_relevance,
    get_assistant_preflight,
    get_task_context,
)
from repolens.context_pack_contract import CONTEXT_PACK_VERSION, DEFAULT_CONTEXT_PACK_BUDGET
from repolens.indexer import index_repository
from repolens.mcp_server import RepoLensMcpTools
from repolens.query import GraphQueryService

runner = CliRunner()


def test_get_task_context_returns_deterministic_context_pack_contract(tmp_path):
    _write_context_fixture_repo(tmp_path)
    index_repository(tmp_path)

    first = get_task_context(tmp_path, "Fix API_TOKEN=abc123 login validation")
    second = get_task_context(tmp_path, "Fix API_TOKEN=abc123 login validation")

    assert first == second
    assert first["ok"] is True
    assert first["confidence"] == "medium"
    assert first["limits"] == DEFAULT_CONTEXT_PACK_BUDGET

    pack = first["data"]
    assert pack["context_pack_version"] == CONTEXT_PACK_VERSION
    assert pack["context_pack_id"].startswith("cp_")
    assert pack["task"] == "Fix API_TOKEN login validation"
    assert pack["task_fingerprint"].startswith("task_")
    assert "abc123" not in json.dumps(first)
    assert pack["budget"]["max_first_read_files"] == 5
    assert pack["freshness"]["canonical_graph_hash"]
    assert pack["truncation"] == {"fields": [], "truncated": False}

    assert [item["path"] for item in pack["first_read_files"]] == ["src/auth/login.ts"]
    first_read = pack["first_read_files"][0]
    assert first_read["kind"] == "first_read_file"
    assert first_read["rank"] == 1
    assert first_read["handle"].startswith("item_")
    assert first_read["structural_summary"] == {
        "freshness": pack["freshness"],
        "scope": "file",
        "source": "graph_facts",
        "symbols": [
            {
                "kind": "JavaScriptFunction",
                "line_range": {"end": 4, "start": 2},
                "name": "validateLogin",
                "public": True,
                "qualified_name": "validateLogin",
            },
            {
                "kind": "JavaScriptFunction",
                "line_range": {"end": 8, "start": 6},
                "name": "loginFlow",
                "public": True,
                "qualified_name": "loginFlow",
            },
        ],
    }
    assert first_read["package_boundary"] == {
        "confidence": "high",
        "ecosystem": "javascript",
        "evidence": [
            {
                "package_root": ".",
                "source": "config_package_roots",
                "source_path": "package.json",
            }
        ],
        "name": "auth-demo",
        "path": ".",
    }
    assert first_read["symbols"]
    assert first_read["relationships"] == []
    assert first_read["related_tests"] == ["tests/login.test.ts"]

    assert [item["path"] for item in pack["likely_tests"]] == ["tests/login.test.ts"]
    assert [item["path"] for item in pack["supporting_docs"]] == ["README.md"]
    assert pack["supporting_docs"][0]["structural_summary"] == {
        "doc_kind": "readme",
        "freshness": pack["freshness"],
        "headings": [{"level": 1, "line": 1, "text": "Auth Demo"}],
        "importance": "important",
        "mentioned_paths": [
            {
                "line": 3,
                "mentioned_path": "src/auth/login.ts",
                "target_path": "src/auth/login.ts",
            }
        ],
        "parser_status": "parsed",
        "scope": "file",
        "source": "graph_facts",
        "title": "Auth Demo",
    }
    assert [item["path"] for item in pack["supporting_configs"]] == ["package.json"]
    assert [item["path"] for item in pack["agent_guidance"]] == ["AGENTS.md"]
    assert pack["agent_guidance"][0].keys() >= {
        "path",
        "kind",
        "freshness",
        "reason",
    }
    assert "raw_agent_guidance" not in pack["agent_guidance"][0]

    assert [item["category"] for item in pack["risk_signals"]] == ["TODO"]
    assert "handle secret rotation" not in json.dumps(pack["risk_signals"])

    command = pack["candidate_verification_commands"][0]
    assert command["path"] == "package.json"
    assert command["purpose"] == "lint"
    assert command["risk_bucket"] == "quality_check_likely"
    assert command["found"] is True
    assert command["run"] is False
    assert command["not_run"] is True
    assert command["auto_run_recommended"] is False

    assert [item["path"] for item in pack["lower_priority_context"]] == []
    assert all("ignore" not in item.lower() for item in pack["next_actions"])
    assert all("automatic" not in item.lower() for item in pack["next_actions"])
    assert [handle["handle"] for handle in pack["expansion_handles"]] == [
        item["handle"]
        for item in [
            *pack["first_read_files"],
            *pack["likely_tests"],
            *pack["supporting_docs"],
            *pack["supporting_configs"],
            *pack["agent_guidance"],
            *pack["candidate_verification_commands"],
            *pack["risk_signals"],
            *pack["lower_priority_context"],
            *pack["ambiguity"],
        ]
    ]
    assert all(
        handle["context_pack_id"] == pack["context_pack_id"] for handle in pack["expansion_handles"]
    )


def test_context_pack_cli_and_mcp_use_same_service(tmp_path):
    _write_context_fixture_repo(tmp_path)
    index_repository(tmp_path)

    cli_result = runner.invoke(
        app,
        ["context", str(tmp_path), "Add validation to login flow tests", "--json"],
    )
    mcp_result = RepoLensMcpTools(tmp_path).get_task_context("Add validation to login flow tests")

    assert cli_result.exit_code == 0
    cli_envelope = json.loads(cli_result.output)
    assert cli_envelope == mcp_result
    assert cli_envelope["data"]["first_read_files"][0]["path"] == "src/auth/login.ts"

    human_result = runner.invoke(
        app, ["context", str(tmp_path), "Add validation to login flow tests"]
    )

    assert human_result.exit_code == 0
    assert "Context Pack" in human_result.output
    assert "First-Read Files" in human_result.output
    assert "src/auth/login.ts" in human_result.output
    assert "Lower-priority context to inspect later" in human_result.output


def test_context_pack_and_preflight_opt_in_to_indexed_semantic_hints(tmp_path):
    secret_source = "semantic-hints-source-must-not-leak"
    _write_text(
        tmp_path / "src" / "workflow.py",
        dedent(
            f"""
            def run(items):
                total = 0
                for item in items:
                    if item.skip:
                        continue
                    if item.fail:
                        raise RuntimeError({secret_source!r})
                    total += missing_value
                total = [total for total in items]
                return total
            """
        ).lstrip(),
    )
    index_repository(tmp_path, experimental_semantic_artifact=True)
    task = "Fix src/workflow.py run workflow"
    default_context = get_task_context(tmp_path, task)
    default_preflight = get_assistant_preflight(tmp_path, task)
    opt_in_context = get_task_context(
        tmp_path,
        task,
        include_experimental_semantic_hints=True,
    )
    opt_in_preflight = get_assistant_preflight(
        tmp_path,
        task,
        include_experimental_semantic_hints=True,
    )
    cli_context_result = runner.invoke(
        app,
        [
            "context",
            str(tmp_path),
            task,
            "--include-experimental-semantic-hints",
            "--json",
        ],
    )
    mcp_preflight = RepoLensMcpTools(tmp_path).assistant_preflight(
        task,
        include_experimental_semantic_hints=True,
    )

    assert default_context["ok"] is True
    assert default_preflight["ok"] is True
    assert "experimental_semantic_hints" not in json.dumps(default_context)
    assert "experimental_semantic_hints" not in json.dumps(default_preflight)
    assert cli_context_result.exit_code == 0
    assert json.loads(cli_context_result.output) == opt_in_context
    assert opt_in_preflight == mcp_preflight

    context_hint = opt_in_context["data"]["first_read_files"][0]["experimental_semantic_hints"]
    preflight_hint = opt_in_preflight["data"]["first_read_files"][0]["experimental_semantic_hints"]
    assert context_hint == preflight_hint
    assert context_hint["experimental"] is True
    assert context_hint["experimental_status"] == "experimental"
    assert context_hint["confidence"] == "candidate"
    assert context_hint["limits"] == {
        "max_binding_scopes": 3,
        "max_control_flow_functions": 3,
        "source_snippets": 0,
    }
    assert context_hint["provenance"]["artifact"] == ".repolens/semantic.sqlite"
    assert context_hint["freshness"]["fresh"] is True
    assert context_hint["control_flow"][0]["shape"] == {
        "has_branch": True,
        "has_loop": True,
        "multiple_exits": True,
        "raise_path_count": 1,
        "terminal_path_count": 2,
    }
    assert context_hint["control_flow"][0]["raise_paths"] == [
        {"line_range": {"start": 7, "end": 7}}
    ]
    assert any(binding["unresolved_bindings"] for binding in context_hint["bindings"])
    assert any(binding["shadowed_locals"] for binding in context_hint["bindings"])
    serialized = json.dumps(opt_in_context, sort_keys=True)
    assert secret_source not in serialized
    assert "item.skip" not in serialized
    assert "RuntimeError" not in serialized
    assert "def run" not in serialized


def test_assistant_preflight_cli_and_mcp_share_bounded_contract(tmp_path):
    _write_context_fixture_repo(tmp_path)
    index_repository(tmp_path)

    budget = {
        "max_candidate_verification_commands": 1,
        "max_first_read_files": 1,
        "max_items_per_support_group": 1,
        "max_total_chars": 8_000,
    }
    service_envelope = get_assistant_preflight(
        tmp_path,
        "Fix API_TOKEN=abc123 login validation",
        focus_hints=["src/auth/login.ts"],
        budget=budget,
    )
    mcp_envelope = RepoLensMcpTools(tmp_path).assistant_preflight(
        "Fix API_TOKEN=abc123 login validation",
        focus_hints=["src/auth/login.ts"],
        max_candidate_verification_commands=1,
        max_first_read_files=1,
        max_items_per_support_group=1,
        max_total_chars=8_000,
    )
    cli_result = runner.invoke(
        app,
        [
            "preflight",
            str(tmp_path),
            "Fix API_TOKEN=abc123 login validation",
            "--focus-hint",
            "src/auth/login.ts",
            "--max-first-read-files",
            "1",
            "--max-items-per-support-group",
            "1",
            "--max-candidate-verification-commands",
            "1",
            "--max-total-chars",
            "8000",
            "--json",
        ],
    )

    assert cli_result.exit_code == 0
    assert json.loads(cli_result.output) == service_envelope == mcp_envelope
    assert service_envelope["ok"] is True
    assert service_envelope["confidence"] == "medium"
    data = service_envelope["data"]
    assert data["assistant_preflight_version"] == "0.5.preflight.v1"
    assert data["task_context"] == {
        "display_task": "Fix API_TOKEN login validation",
        "fingerprint": data["task_context"]["fingerprint"],
        "scope": "graph_bounded_orientation",
    }
    assert data["focus_hints"]["items"] == ["src/auth/login.ts"]
    assert data["budget_controls"] == {
        "deterministic": True,
        "max_candidate_verification_commands": 1,
        "max_first_read_files": 1,
        "max_items_per_support_group": 1,
        "max_total_chars": 8000,
        "units": ["items", "characters"],
        "used_chars": data["budget_controls"]["used_chars"],
    }
    assert [item["path"] for item in data["first_read_files"]] == ["src/auth/login.ts"]
    assert [item["path"] for item in data["likely_tests"]] == ["tests/login.test.ts"]
    assert data["candidate_verification_commands"][0]["run"] is False
    assert data["candidate_verification_commands"][0]["found"] is True
    assert "abc123" not in json.dumps(service_envelope)
    assert "return input.user" not in json.dumps(service_envelope)


def test_assistant_preflight_golden_outcomes_cover_stale_broad_ambiguity_and_no_match(
    tmp_path,
):
    stale_repo = tmp_path / "stale"
    _write_context_fixture_repo(stale_repo)
    index_repository(stale_repo)
    _write_text(stale_repo / "src" / "auth" / "login.ts", "export const changed = true;\n")

    broad_repo = tmp_path / "broad"
    _write_context_fixture_repo(broad_repo)
    _write_text(broad_repo / "src" / "billing" / "invoice.ts", "export const invoice = 1;\n")
    index_repository(broad_repo)

    ambiguity_repo = tmp_path / "ambiguity"
    _write_text(ambiguity_repo / "src" / "acme" / "ambiguous.py", "VALUE = 1\n")
    _write_text(ambiguity_repo / "acme" / "ambiguous.py", "VALUE = 2\n")
    index_repository(ambiguity_repo)

    stale = get_assistant_preflight(stale_repo, "Fix login validation")
    broad = get_assistant_preflight(broad_repo, "Update project")
    no_match = get_assistant_preflight(broad_repo, "Repair quantum banana telemetry")
    ambiguity = get_assistant_preflight(ambiguity_repo, "ambiguous")

    assert stale["freshness"]["fresh"] is False
    assert "Graph artifacts may be stale" in " ".join(stale["warnings"])
    assert broad["ok"] is True
    assert "Task is broad" in " ".join(broad["warnings"])
    assert (
        len(broad["data"]["first_read_files"])
        <= DEFAULT_CONTEXT_PACK_BUDGET["max_first_read_files"]
    )
    assert no_match["ok"] is True
    assert no_match["confidence"] == "low"
    assert no_match["data"]["first_read_files"] == []
    assert ambiguity["ok"] is True
    assert ambiguity["data"]["first_read_files"] == []
    assert all(item["kind"] == "ambiguity_candidate" for item in ambiguity["data"]["ambiguity"])
    assert sorted({item["path"] for item in ambiguity["data"]["ambiguity"]}) == [
        "acme/ambiguous.py",
        "src/acme/ambiguous.py",
    ]


def test_v0_6_js_ts_metadata_improves_first_read_ranking(tmp_path):
    _write_v0_6_js_ts_context_fixture(tmp_path)
    index_repository(tmp_path)

    import_pack = get_task_context(
        tmp_path,
        "Fix workspace package import from app to @dog/lib using TypeScript alias",
    )["data"]
    route_pack = get_task_context(tmp_path, "Fix account route loading state")["data"]
    call_chain_pack = get_task_context(tmp_path, "Fix query where order call chain")["data"]

    assert [item["path"] for item in import_pack["first_read_files"][:2]] == [
        "packages/lib/src/index.ts",
        "packages/app/src/index.ts",
    ]
    assert import_pack["first_read_files"][0]["reason"] == (
        "Task tokens matched resolved JS/TS import metadata."
    )
    assert import_pack["first_read_files"][0]["package_boundary"] == {
        "confidence": "high",
        "ecosystem": "javascript",
        "evidence": [
            {
                "package_root": "packages/lib",
                "source": "config_package_roots",
                "source_path": "packages/lib/package.json",
            }
        ],
        "name": "@dog/lib",
        "path": "packages/lib",
    }

    assert route_pack["first_read_files"][0]["path"] == "app/account/page.tsx"
    assert route_pack["first_read_files"][0]["reason"] == (
        "Task tokens matched indexed framework route metadata."
    )
    assert route_pack["first_read_files"][0]["route_hints"][0]["route_path"] == "/account"

    assert call_chain_pack["first_read_files"][0]["path"] == "src/query.ts"
    assert call_chain_pack["first_read_files"][0]["reason"] == (
        "Task tokens matched source-free JS/TS call-chain metadata."
    )
    assert "call_chains" in call_chain_pack["first_read_files"][0]["structural_summary"]


def test_context_pack_preserves_missing_graph_unavailable_error(tmp_path):
    _write_context_fixture_repo(tmp_path)

    envelope = get_task_context(tmp_path, "Fix login validation")

    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "missing_graph_artifacts"
    assert envelope["freshness"]["fresh"] is False


def test_context_pack_stale_graph_returns_downgraded_pack_with_warning(tmp_path):
    _write_context_fixture_repo(tmp_path)
    index_repository(tmp_path)
    _write_text(tmp_path / "src" / "auth" / "login.ts", "export const changed = true;\n")

    envelope = get_task_context(tmp_path, "Fix login validation")

    assert envelope["ok"] is True
    assert envelope["freshness"]["fresh"] is False
    assert envelope["data"]["freshness"]["status"] == "stale"
    assert "Graph artifacts may be stale" in " ".join(envelope["warnings"])


def test_context_pack_no_match_returns_low_confidence_without_repository_dump(tmp_path):
    _write_context_fixture_repo(tmp_path)
    _write_text(tmp_path / "src" / "billing" / "invoice.ts", "export const invoice = 1;\n")
    index_repository(tmp_path)

    envelope = get_task_context(tmp_path, "Repair quantum banana telemetry")

    assert envelope["ok"] is True
    assert envelope["confidence"] == "low"
    assert envelope["data"]["first_read_files"] == []
    assert envelope["data"]["likely_tests"] == []
    assert "No useful graph matches" in " ".join(envelope["warnings"])


def test_context_pack_broad_task_is_bounded_and_warned(tmp_path):
    _write_context_fixture_repo(tmp_path)
    _write_text(tmp_path / "src" / "billing" / "invoice.ts", "export const invoice = 1;\n")
    index_repository(tmp_path)

    envelope = get_task_context(tmp_path, "Update project")

    assert envelope["ok"] is True
    assert (
        len(envelope["data"]["first_read_files"])
        <= DEFAULT_CONTEXT_PACK_BUDGET["max_first_read_files"]
    )
    assert "Task is broad" in " ".join(envelope["warnings"])


def test_context_pack_docs_and_config_orientation_stays_structured_without_excerpts(tmp_path):
    _write_context_fixture_repo(tmp_path)
    _write_text(
        tmp_path / "docs" / "testing.md",
        dedent(
            """
            # Testing Setup

            Run the test script from package.json when changing src/auth/login.ts.

            ```ts
            export function leakedExample() {
              return true;
            }
            ```
            """
        ).lstrip(),
    )
    _write_text(
        tmp_path / "README.md",
        dedent(
            """
            # Auth Demo

            Read [testing setup](docs/testing.md) before changing `src/auth/login.ts`.
            """
        ).lstrip(),
    )
    index_repository(tmp_path)

    docs_envelope = get_task_context(tmp_path, "Update testing setup docs for login flow")
    config_envelope = get_task_context(tmp_path, "Fix package lint command")

    docs_pack = docs_envelope["data"]
    config_pack = config_envelope["data"]
    docs_by_path = {item["path"]: item for item in docs_pack["supporting_docs"]}
    readme_summary = docs_by_path["README.md"]["structural_summary"]
    testing_summary = docs_by_path["docs/testing.md"]["structural_summary"]
    config_summary = config_pack["supporting_configs"][0]["structural_summary"]

    assert readme_summary["links"] == [
        {"line": 3, "target_fragment": None, "target_path": "docs/testing.md"}
    ]
    assert {
        "line": 3,
        "mentioned_path": "src/auth/login.ts",
        "target_path": "src/auth/login.ts",
    } in readme_summary["mentioned_paths"]
    assert {
        "line": 3,
        "mentioned_path": "docs/testing.md",
        "target_path": "docs/testing.md",
    } in readme_summary["mentioned_paths"]
    assert {
        "line": 3,
        "mentioned_path": "package.json",
        "target_path": "package.json",
    } in testing_summary["mentioned_paths"]
    assert {
        "line": 3,
        "mentioned_path": "src/auth/login.ts",
        "target_path": "src/auth/login.ts",
    } in testing_summary["mentioned_paths"]
    assert testing_summary["headings"] == [{"level": 1, "line": 1, "text": "Testing Setup"}]
    assert testing_summary["code_fences"] == [
        {"language": "ts", "line_range": {"end": 9, "start": 5}}
    ]
    assert config_summary["config_kind"] == "package_manifest"
    assert config_summary["package_roots"][0]["name"] == "auth-demo"
    assert [command["risk_bucket"] for command in config_summary["candidate_commands"]] == [
        "quality_check_likely",
        "verification_likely",
    ]
    assert all(command["found"] is True for command in config_summary["candidate_commands"])
    assert all(command["run"] is False for command in config_summary["candidate_commands"])

    serialized = json.dumps({"docs": docs_pack, "config": config_pack})
    assert "Run the test script" not in serialized
    assert "export function leakedExample" not in serialized
    assert "Keep changes focused" not in serialized
    assert str(tmp_path) not in serialized


def test_context_pack_focus_path_outside_root_is_rejected(tmp_path):
    _write_context_fixture_repo(tmp_path)
    index_repository(tmp_path)
    outside_path = tmp_path.parent / "outside.py"

    envelope = get_task_context(tmp_path, "Fix login validation", focus_hints=[str(outside_path)])

    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "focus_hint_outside_root"
    assert str(outside_path) not in json.dumps(envelope)


def test_context_pack_unresolved_focus_hint_warns_and_lowers_confidence(tmp_path):
    _write_context_fixture_repo(tmp_path)
    index_repository(tmp_path)

    envelope = get_task_context(
        tmp_path,
        "Fix login validation",
        focus_hints=["src/auth/missing.ts", "API_TOKEN=abc123"],
    )

    assert envelope["ok"] is True
    assert envelope["confidence"] == "low"
    serialized = json.dumps(envelope)
    assert "Unresolved focus hint" in " ".join(envelope["warnings"])
    assert "src/auth/missing.ts" in serialized
    assert "abc123" not in serialized


def test_context_pack_focal_ambiguity_returns_candidates(tmp_path):
    _write_text(tmp_path / "src" / "acme" / "ambiguous.py", "VALUE = 1\n")
    _write_text(tmp_path / "acme" / "ambiguous.py", "VALUE = 2\n")
    index_repository(tmp_path)

    envelope = get_task_context(tmp_path, "ambiguous")

    pack = envelope["data"]

    assert envelope["ok"] is True
    assert pack["first_read_files"] == []
    assert all(item["kind"] == "ambiguity_candidate" for item in pack["ambiguity"])
    assert sorted({item["path"] for item in pack["ambiguity"]}) == [
        "acme/ambiguous.py",
        "src/acme/ambiguous.py",
    ]


def test_context_pack_does_not_infer_package_boundary_from_directory_name(tmp_path):
    _write_text(
        tmp_path / "src" / "auth" / "login.ts",
        "export function loginFlow() { return true; }\n",
    )
    index_repository(tmp_path)

    envelope = get_task_context(tmp_path, "loginFlow")

    first_read = envelope["data"]["first_read_files"][0]
    assert first_read["path"] == "src/auth/login.ts"
    assert "package_boundary" not in first_read


def test_context_pack_surfaces_package_workspace_contract_tracer(tmp_path):
    _write_text(
        tmp_path / "package.json",
        dedent(
            """
            {
              "name": "workspace-root",
              "private": true,
              "workspaces": ["workspaces/acme-app"]
            }
            """
        ).lstrip(),
    )
    _write_text(
        tmp_path / "workspaces" / "acme-app" / "package.json",
        dedent(
            """
            {
              "name": "@demo/app",
              "dependencies": {
                "@demo/missing": "workspace:*"
              }
            }
            """
        ).lstrip(),
    )
    _write_text(
        tmp_path / "tsconfig.json",
        dedent(
            """
            {
              "compilerOptions": {
                "paths": {
                  "@missing/*": ["workspaces/acme-app/src/missing/*"]
                }
              }
            }
            """
        ).lstrip(),
    )
    _write_text(
        tmp_path / "workspaces" / "acme-app" / "src" / "main.ts",
        dedent(
            """
            import missing from "@missing/thing";

            export function appMain() {
              return missing;
            }
            """
        ).lstrip(),
    )
    index_repository(tmp_path)

    query_metadata = GraphQueryService(tmp_path).context_pack_file_metadata(
        ["workspaces/acme-app/src/main.ts"]
    )
    envelope = get_task_context(tmp_path, "appMain package workspace")

    assert query_metadata["ok"] is True
    query_data = query_metadata["data"]
    assert sorted(query_data) == [
        "package_boundaries",
        "relationship_candidates",
        "route_hints",
        "structural_summaries",
        "workspace_memberships",
    ]
    assert "workspaces/acme-app/src/main.ts" in query_data["workspace_memberships"]
    assert "workspaces/acme-app/src/main.ts" in query_data["relationship_candidates"]
    assert envelope["ok"] is True
    assert any(
        warning.startswith("graph_quality:javascript_unresolved_import_relationships")
        for warning in envelope["warnings"]
    )
    serialized = json.dumps(envelope)
    assert str(tmp_path) not in serialized
    assert "return missing" not in serialized

    first_read = envelope["data"]["first_read_files"][0]
    assert first_read["path"] == "workspaces/acme-app/src/main.ts"
    assert first_read["package_boundary"] == {
        "confidence": "high",
        "ecosystem": "javascript",
        "evidence": [
            {
                "package_root": "workspaces/acme-app",
                "source": "config_package_roots",
                "source_path": "workspaces/acme-app/package.json",
            }
        ],
        "name": "@demo/app",
        "path": "workspaces/acme-app",
    }
    assert first_read["workspace_membership"] == {
        "confidence": "high",
        "ecosystem": "javascript",
        "evidence": [
            {
                "package_source_path": "workspaces/acme-app/package.json",
                "source": "config_workspaces",
                "workspace_source_path": "package.json",
            }
        ],
        "package_name": "@demo/app",
        "package_root": "workspaces/acme-app",
        "resolution_strategy": "explicit_workspace_and_package_identity",
        "workspace_path": "workspaces/acme-app",
    }
    assert first_read["relationship_candidates"] == [
        {
            "confidence": "low",
            "evidence": [{"line": 1, "source": "javascript_imports"}],
            "kind": "relationship_candidate",
            "reason": "import_resolution_not_definitive",
            "relationship": "local_resolution",
            "resolution_status": "unresolved_missing_alias",
            "specifier": "@missing/thing",
            "warning_code": "graph_quality:unresolved_import_relationship",
        }
    ]


def test_context_pack_surfaces_ambiguous_workspace_package_import_candidates(tmp_path):
    _write_text(
        tmp_path / "package.json",
        dedent(
            r"""
            {
              "name": "workspace-root",
              "private": true,
              "workspaces": ["packages/*"]
            }
            """
        ).lstrip(),
    )
    _write_text(
        tmp_path / "packages" / "app" / "package.json",
        dedent(
            r"""
            {
              "name": "@demo/app",
              "dependencies": {"@demo/lib": "workspace:*"}
            }
            """
        ).lstrip(),
    )
    for package_path in ("lib-a", "lib-b"):
        _write_text(
            tmp_path / "packages" / package_path / "package.json",
            dedent(
                r"""
                {
                  "name": "@demo/lib",
                  "exports": "./src/index.ts"
                }
                """
            ).lstrip(),
        )
        _write_text(
            tmp_path / "packages" / package_path / "src" / "index.ts",
            "export const value = 1;\n",
        )
    _write_text(
        tmp_path / "packages" / "app" / "src" / "main.ts",
        "import { value } from '@demo/lib';\nexport const appValue = value;\n",
    )
    index_repository(tmp_path)

    query_metadata = GraphQueryService(tmp_path).context_pack_file_metadata(
        ["packages/app/src/main.ts"]
    )
    envelope = get_task_context(tmp_path, "app imports demo lib")

    assert query_metadata["ok"] is True
    candidates = query_metadata["data"]["relationship_candidates"]["packages/app/src/main.ts"]
    assert [candidate["package_root"] for candidate in candidates] == [
        "packages/lib-a",
        "packages/lib-b",
    ]
    assert all(
        candidate["reason"] == "ambiguous_workspace_package_import" for candidate in candidates
    )
    assert any(
        warning.startswith("graph_quality:ambiguous_package_identity")
        for warning in envelope["warnings"]
    )
    assert any(
        warning.startswith("graph_quality:ambiguous_workspace_package_import")
        for warning in envelope["warnings"]
    )
    graph_json = json.loads((tmp_path / ".repolens" / "graph.json").read_text())
    assert not any(
        edge["target_id"].startswith("javascript_module:packages/lib-")
        for edge in graph_json["edges"]
        if edge["kind"] == "IMPORTS"
    )


def test_context_pack_and_preflight_surface_next_app_router_route_hints(tmp_path):
    _write_text(
        tmp_path / "package.json",
        dedent(
            """
            {
              "name": "next-route-demo",
              "dependencies": {"next": "workspace:*"}
            }
            """
        ).lstrip(),
    )
    _write_text(
        tmp_path / "app" / "page.tsx",
        "export default function HomePage() { return null; }\n",
    )
    _write_text(
        tmp_path / "app" / "dashboard" / "layout.tsx",
        "export default function DashboardLayout() { return null; }\n",
    )
    _write_text(
        tmp_path / "app" / "api" / "users" / "route.ts",
        "export function GET() { return Response.json({}); }\n",
    )
    _write_text(
        tmp_path / "app" / "blog" / "[slug]" / "page.tsx",
        "export default function BlogPage() { return null; }\n",
    )
    index_repository(tmp_path)

    query_metadata = GraphQueryService(tmp_path).context_pack_file_metadata(
        [
            "app/api/users/route.ts",
            "app/blog/[slug]/page.tsx",
            "app/dashboard/layout.tsx",
            "app/page.tsx",
        ]
    )
    context_envelope = get_task_context(
        tmp_path,
        "Update the home page route",
        focus_hints=["app/page.tsx"],
    )
    preflight_envelope = get_assistant_preflight(
        tmp_path,
        "Update the home page route",
        focus_hints=["app/page.tsx"],
    )
    graph_json = json.loads((tmp_path / ".repolens" / "graph.json").read_text())

    hints = query_metadata["data"]["route_hints"]
    assert hints["app/page.tsx"][0] == {
        "confidence": "medium",
        "evidence": [
            {
                "labels": [
                    "repo_relative_path",
                    "next_app_router_file_convention",
                    "framework_runtime_not_executed",
                ],
                "line_range": [1, 1],
                "source": "framework_route_hint",
            }
        ],
        "framework": "nextjs_app_router",
        "kind": "page",
        "path": "app/page.tsx",
        "relationship": "framework_route_hint",
        "route_path": "/",
        "warnings": [],
    }
    assert hints["app/dashboard/layout.tsx"][0]["route_path"] == "/dashboard"
    assert hints["app/api/users/route.ts"][0]["kind"] == "api_route_handler"
    assert hints["app/api/users/route.ts"][0]["route_path"] == "/api/users"
    assert hints["app/blog/[slug]/page.tsx"][0]["confidence"] == "low"
    assert hints["app/blog/[slug]/page.tsx"][0]["warnings"] == [
        "framework_route_hint:next_app_router_dynamic_segment_candidate"
    ]
    assert context_envelope["data"]["first_read_files"][0]["route_hints"] == hints["app/page.tsx"]
    assert preflight_envelope["data"]["first_read_files"][0]["route_hints"] == hints["app/page.tsx"]
    assert not any(edge["kind"] == "ROUTES_TO" for edge in graph_json["edges"])
    assert "return Response" not in json.dumps(preflight_envelope)


def test_expand_context_is_pack_scoped_bounded_and_source_free(tmp_path):
    _write_context_fixture_repo(tmp_path)
    index_repository(tmp_path)
    task = "Add validation to login flow tests"
    pack_envelope = get_task_context(tmp_path, task)
    pack = pack_envelope["data"]
    item = pack["first_read_files"][0]

    envelope = expand_context(
        tmp_path,
        task,
        pack["context_pack_id"],
        item["handle"],
        depth=99,
        max_items_per_kind=1,
        max_total_items=3,
    )

    assert envelope["ok"] is True
    assert envelope["data"]["context_pack_id"] == pack["context_pack_id"]
    assert envelope["data"]["item"]["handle"] == item["handle"]
    assert envelope["data"]["depth"] == 2
    assert envelope["limits"] == {
        "max_depth": 2,
        "max_items_per_kind": 1,
        "max_total_items": 3,
    }
    expanded = envelope["data"]["expanded_context"]
    assert [entry["path"] for entry in expanded["direct_affected_files"]] == ["src/auth/login.ts"]
    assert [entry["path"] for entry in expanded["likely_tests"]] == ["tests/login.test.ts"]
    assert sum(len(entries) for entries in expanded.values()) <= 3
    assert envelope["data"]["item"]["reason"] == item["reason"]
    assert envelope["confidence"] == item["confidence"]
    assert "return input.user" not in json.dumps(envelope)


def test_expand_context_rejects_handles_not_returned_in_pack(tmp_path):
    _write_context_fixture_repo(tmp_path)
    index_repository(tmp_path)
    task = "Add validation to login flow tests"
    pack = get_task_context(tmp_path, task)["data"]

    envelope = expand_context(
        tmp_path,
        task,
        pack["context_pack_id"],
        "item_not_returned",
    )

    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "context_pack_item_not_returned"
    assert envelope["error"]["requires_new_pack"] is True


def test_expand_context_rejects_stale_or_mismatched_pack_id(tmp_path):
    _write_context_fixture_repo(tmp_path)
    index_repository(tmp_path)
    task = "Add validation to login flow tests"
    pack = get_task_context(tmp_path, task)["data"]
    item = pack["first_read_files"][0]

    mismatched = expand_context(
        tmp_path,
        task,
        "cp_mismatch",
        item["handle"],
    )

    assert mismatched["ok"] is False
    assert mismatched["error"]["code"] == "context_pack_id_mismatch"
    assert mismatched["error"]["requires_new_pack"] is True

    _write_text(tmp_path / "src" / "auth" / "login.ts", "export const changed = true;\n")
    stale = expand_context(
        tmp_path,
        task,
        pack["context_pack_id"],
        item["handle"],
    )

    assert stale["ok"] is False
    assert stale["error"]["code"] == "stale_context_pack"
    assert stale["error"]["requires_new_pack"] is True


def test_explain_relevance_returns_item_reason_and_evidence(tmp_path):
    _write_context_fixture_repo(tmp_path)
    index_repository(tmp_path)
    task = "Add validation to login flow tests"
    pack = get_task_context(tmp_path, task)["data"]
    item = pack["likely_tests"][0]

    envelope = explain_relevance(
        tmp_path,
        task,
        pack["context_pack_id"],
        item["handle"],
    )

    assert envelope["ok"] is True
    assert envelope["data"] == {
        "confidence": item["confidence"],
        "context_pack_id": pack["context_pack_id"],
        "evidence": item["evidence"],
        "freshness": item["freshness"],
        "item_handle": item["handle"],
        "item_kind": item["kind"],
        "path": item["path"],
        "reason": item["reason"],
    }
    assert envelope["freshness"] == item["freshness"]


def test_context_pack_mcp_expansion_and_relevance_use_same_service(tmp_path):
    _write_context_fixture_repo(tmp_path)
    index_repository(tmp_path)
    tools = RepoLensMcpTools(tmp_path)
    task = "Add validation to login flow tests"
    pack = tools.get_task_context(task)["data"]
    item = pack["first_read_files"][0]

    assert tools.expand_context(task, pack["context_pack_id"], item["handle"]) == expand_context(
        tmp_path, task, pack["context_pack_id"], item["handle"]
    )
    assert tools.explain_relevance(
        task, pack["context_pack_id"], item["handle"]
    ) == explain_relevance(tmp_path, task, pack["context_pack_id"], item["handle"])


def _write_v0_6_js_ts_context_fixture(root) -> None:
    _write_text(
        root / "package.json",
        dedent(
            """
            {
              "name": "v06-js-ts-demo",
              "private": true,
              "workspaces": ["packages/*"],
              "scripts": {
                "test": "vitest run",
                "typecheck": "tsc -b"
              }
            }
            """
        ).lstrip(),
    )
    _write_text(
        root / "tsconfig.json",
        dedent(
            """
            {
              "compilerOptions": {
                "baseUrl": ".",
                "paths": {
                  "@dog/lib": ["packages/lib/src/index.ts"]
                }
              },
              "references": [
                {"path": "./packages/app"},
                {"path": "./packages/lib"}
              ]
            }
            """
        ).lstrip(),
    )
    _write_text(
        root / "packages" / "app" / "package.json",
        dedent(
            """
            {"name": "@dog/app", "dependencies": {"@dog/lib": "workspace:*"}}
            """
        ).lstrip(),
    )
    _write_text(
        root / "packages" / "app" / "src" / "index.ts",
        dedent(
            """
            import { describeValue } from "@dog/lib";

            export function render(): string {
              return describeValue("demo");
            }
            """
        ).lstrip(),
    )
    _write_text(
        root / "packages" / "lib" / "package.json",
        dedent(
            """
            {"name": "@dog/lib"}
            """
        ).lstrip(),
    )
    _write_text(
        root / "packages" / "lib" / "src" / "index.ts",
        dedent(
            """
            export function describeValue(value: string): string {
              return `value:${value}`;
            }
            """
        ).lstrip(),
    )
    _write_text(
        root / "app" / "account" / "page.tsx",
        dedent(
            """
            export default function AccountPage() {
              return null;
            }
            """
        ).lstrip(),
    )
    _write_text(
        root / "src" / "query.ts",
        dedent(
            """
            export function loadUsers(client: any) {
              return client.query().where().order();
            }
            """
        ).lstrip(),
    )


def _write_context_fixture_repo(root) -> None:
    _write_text(
        root / "package.json",
        dedent(
            """
            {
              "name": "auth-demo",
              "scripts": {
                "test": "vitest run tests/login.test.ts",
                "lint": "eslint src/auth/login.ts"
              }
            }
            """
        ).lstrip(),
    )
    _write_text(
        root / "README.md",
        dedent(
            """
            # Auth Demo

            The login flow is implemented in `src/auth/login.ts`.
            """
        ).lstrip(),
    )
    _write_text(
        root / "AGENTS.md",
        dedent(
            """
            # Agent Guidance

            Keep changes focused.
            """
        ).lstrip(),
    )
    _write_text(
        root / "src" / "auth" / "login.ts",
        dedent(
            """
            // TODO: handle secret rotation before changing validation
            export function validateLogin(input: { user: string }) {
              return input.user.length > 0;
            }

            export function loginFlow(input: { user: string }) {
              return validateLogin(input);
            }
            """
        ).lstrip(),
    )
    _write_text(
        root / "tests" / "login.test.ts",
        dedent(
            """
            import { validateLogin } from "../src/auth/login";

            test("validates login", () => {
              expect(validateLogin({ user: "demo" })).toBe(true);
            });
            """
        ).lstrip(),
    )


def _write_text(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
