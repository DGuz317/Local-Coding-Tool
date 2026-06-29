from __future__ import annotations

import json
from textwrap import dedent

from typer.testing import CliRunner

from repolens.cli import app
from repolens.context_pack import expand_context, explain_relevance, get_task_context
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
        "freshness": pack["freshness"],
        "headings": [{"level": 1, "line": 1, "text": "Auth Demo"}],
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
            "relationship": "local_resolution",
            "resolution_status": "unresolved_missing_alias",
            "specifier": "@missing/thing",
        }
    ]


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
