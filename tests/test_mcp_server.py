from __future__ import annotations

import asyncio
import os
from textwrap import dedent

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mcp_stdio_support import assert_no_stdout
from repolens.indexer import index_repository
from repolens.mcp_server import MCP_TOOL_NAMES, RepoLensMcpTools
from repolens.scanner import DEFAULT_MAX_FILE_SIZE_BYTES


def test_mcp_tools_return_missing_graph_envelopes_before_indexing(tmp_path, capsys):
    tools = RepoLensMcpTools(tmp_path)

    results = {
        "repo_summary": tools.repo_summary(),
        "graph_status": tools.graph_status(),
        "get_graph_report": tools.get_graph_report(),
        "search_graph": tools.search_graph("anything"),
        "get_node": tools.get_node(query="anything"),
        "get_neighbors": tools.get_neighbors(query="anything"),
        "shortest_path": tools.shortest_path("source", "target"),
        "impact_analysis": tools.impact_analysis("anything"),
        "suggest_reading_order": tools.suggest_reading_order("anything"),
        "list_entrypoints": tools.list_entrypoints(),
    }

    for result in results.values():
        assert set(result) >= {
            "confidence",
            "data",
            "error",
            "evidence",
            "freshness",
            "limits",
            "ok",
            "truncation",
            "warnings",
        }
        assert result["ok"] is False
        assert result["error"]["code"] == "missing_graph_artifacts"
        assert result["error"]["recommended_action"].startswith("repolens index ")
        assert result["data"] == {}
        assert result["freshness"]["fresh"] is False
        assert result["truncation"] == {"fields": [], "truncated": False}
    assert_no_stdout(capsys)


def test_mcp_tools_wrap_success_with_freshness_limits_and_truncation(tmp_path):
    _write_fixture_repo(tmp_path)
    index_repository(tmp_path)
    tools = RepoLensMcpTools(tmp_path)

    status = tools.graph_status()
    report = tools.get_graph_report(max_chars=40)
    text = tools.search_text("alpha", max_results=1)

    assert status["ok"] is True
    assert status["freshness"]["fresh"] is True
    assert status["freshness"]["status_cache"] == {"cached": False, "ttl_seconds": 2.0}
    assert status["warnings"] == []
    assert status["limits"] == {"max_changed_files": 20}
    assert status["truncation"] == {"fields": [], "truncated": False}

    assert report["ok"] is True
    assert report["limits"] == {"max_chars": 40}
    assert report["truncation"]["truncated"] is True
    assert len(report["data"]["text"]) == 40

    assert text["ok"] is True
    assert text["data"]["matches"][0]["path"] == "app.py"
    assert text["pagination"]["truncated"] is True
    assert text["truncation"] == {"fields": ["data", "pagination"], "truncated": True}
    assert text["limits"]["max_results"] == 1


def test_mcp_graph_tools_include_stale_freshness_metadata(tmp_path):
    _write_fixture_repo(tmp_path)
    index_repository(tmp_path)
    _write_text(tmp_path / "app.py", "alpha changed\n")
    tools = RepoLensMcpTools(tmp_path)

    result = tools.search_graph("app")

    assert result["ok"] is True
    assert result["freshness"] == {"fresh": False, "status": "stale"}
    assert result["warnings"] == [
        "Graph artifacts may be stale; file metadata changed since indexing."
    ]


def test_mcp_status_uses_short_ttl_cache(tmp_path):
    _write_fixture_repo(tmp_path)
    index_repository(tmp_path)
    tools = RepoLensMcpTools(tmp_path, status_ttl_seconds=60)

    first = tools.graph_status()
    _write_text(tmp_path / "app.py", "alpha changed\n")
    cached = tools.graph_status()

    assert first["data"]["fresh"] is True
    assert cached["data"]["fresh"] is True
    assert cached["freshness"]["status_cache"] == {"cached": True, "ttl_seconds": 60}


def test_mcp_text_search_returns_structured_expected_errors(tmp_path):
    tools = RepoLensMcpTools(tmp_path)

    result = tools.search_text(" ")

    assert result["ok"] is False
    assert result["error"] == {
        "code": "empty_query",
        "message": "Raw text search could not be completed.",
    }
    assert result["data"] == {}
    assert result["limits"]["max_results"] == 20


def test_mcp_text_search_returns_capped_redacted_previews_with_explicit_limits(tmp_path):
    full_line = f"{'a' * 120} API_TOKEN=super-secret needle {'b' * 220}"
    _write_text(tmp_path / "app.py", f"{full_line}\nneedle second\nneedle third\n")
    tools = RepoLensMcpTools(tmp_path)

    result = tools.search_text("needle", max_results=2)

    matches = result["data"]["matches"]

    assert result["ok"] is True
    assert result["limits"] == {
        "max_results": 2,
        "preview_chars": 160,
        "max_file_size_bytes": DEFAULT_MAX_FILE_SIZE_BYTES,
    }
    assert result["pagination"] == {
        "limit": 2,
        "offset": 0,
        "returned": 2,
        "total": 3,
        "truncated": True,
    }
    assert result["truncation"] == {"fields": ["data", "pagination"], "truncated": True}
    assert result["data"]["truncated"] is True
    assert len(matches) == 2
    assert len(matches[0]["preview"]) <= result["limits"]["preview_chars"]
    assert matches[0]["preview_truncated_before"] is True
    assert matches[0]["preview_truncated_after"] is True
    assert full_line not in str(result)
    assert "super-secret" not in str(result)
    assert "API_TOKEN=<redacted>" in matches[0]["preview"]


def test_mcp_text_search_does_not_read_oversized_files(tmp_path):
    oversized = f"needle {'x' * DEFAULT_MAX_FILE_SIZE_BYTES}"
    _write_text(tmp_path / "large.py", oversized)
    _write_text(tmp_path / "small.py", "needle small\n")
    tools = RepoLensMcpTools(tmp_path)

    result = tools.search_text("needle")

    paths = {match["path"] for match in result["data"]["matches"]}

    assert result["ok"] is True
    assert paths == {"small.py"}
    assert result["data"]["total_matches"] == 1
    assert result["data"]["skipped_paths"] == 1
    assert result["limits"]["max_file_size_bytes"] == DEFAULT_MAX_FILE_SIZE_BYTES


def test_mcp_surface_has_no_source_file_read_tool_behavior():
    forbidden_terms = ("read_file", "read_source", "get_file", "source_file", "cat")

    assert all(term not in MCP_TOOL_NAMES for term in forbidden_terms)


def test_mcp_tools_preserve_candidate_only_resolution_metadata(tmp_path):
    _write_text(tmp_path / "src" / "billing" / "invoice.py", "def total_due():\n    return 1\n")
    index_repository(tmp_path)
    tools = RepoLensMcpTools(tmp_path)

    result = tools.get_node(query="due missing")

    assert result["ok"] is True
    assert result["data"]["node"] is None
    assert result["data"]["reason"] == "fuzzy_candidate_only"
    assert result["data"]["resolution_strategy"] == "fuzzy_candidate"
    assert result["data"]["candidates"][0]["node"]["label"] == "total_due"
    assert result["truncation"] == {"fields": [], "truncated": False}


def test_mcp_assistant_preflight_returns_standard_envelope_with_focus_and_budget(
    tmp_path,
):
    _write_preflight_fixture_repo(tmp_path)
    index_repository(tmp_path)
    tools = RepoLensMcpTools(tmp_path)

    result = tools.assistant_preflight(
        "Fix API_TOKEN=abc123 login validation",
        focus_hints=["src/auth/login.ts"],
        max_first_read_files=1,
        max_items_per_support_group=1,
        max_candidate_verification_commands=1,
        max_total_chars=8_000,
    )

    data = result["data"]
    assert set(result) >= {
        "confidence",
        "data",
        "evidence",
        "freshness",
        "limits",
        "ok",
        "truncation",
        "warnings",
    }
    assert result["ok"] is True
    assert data["assistant_preflight_version"] == "0.5.preflight.v1"
    assert data["task_context"]["display_task"] == "Fix API_TOKEN login validation"
    assert data["focus_hints"]["items"] == ["src/auth/login.ts"]
    assert data["budget_controls"]["max_first_read_files"] == 1
    assert data["budget_controls"]["max_items_per_support_group"] == 1
    assert data["budget_controls"]["max_candidate_verification_commands"] == 1
    assert data["budget_controls"]["max_total_chars"] == 8_000
    assert data["freshness"]["fresh"] is True
    assert [item["path"] for item in data["first_read_files"]] == ["src/auth/login.ts"]
    assert [item["path"] for item in data["likely_tests"]] == ["tests/login.test.ts"]
    assert len(data["candidate_verification_commands"]) == 1
    assert all(command["found"] is True for command in data["candidate_verification_commands"])
    assert all(command["run"] is False for command in data["candidate_verification_commands"])
    assert "abc123" not in str(result)
    assert "return input.user" not in str(result)


def test_mcp_assistant_preflight_missing_graph_returns_standard_error(tmp_path):
    _write_preflight_fixture_repo(tmp_path)
    tools = RepoLensMcpTools(tmp_path)

    result = tools.assistant_preflight("Fix login validation")

    assert result["ok"] is False
    assert result["error"]["code"] == "missing_graph_artifacts"
    assert result["error"]["recommended_action"].startswith("repolens index ")
    assert result["data"] == {}
    assert result["freshness"]["fresh"] is False
    assert result["truncation"] == {"fields": [], "truncated": False}


def test_mcp_assistant_preflight_stale_graph_returns_bounded_warning(tmp_path):
    _write_preflight_fixture_repo(tmp_path)
    index_repository(tmp_path)
    _write_text(tmp_path / "src" / "auth" / "login.ts", "export const changed = true;\n")
    tools = RepoLensMcpTools(tmp_path)

    result = tools.assistant_preflight("Fix login validation")

    assert result["ok"] is True
    assert result["freshness"]["fresh"] is False
    assert result["data"]["freshness"]["status"] == "stale"
    assert "Graph artifacts may be stale" in " ".join(result["warnings"])


def test_mcp_envelope_redacts_secret_like_metadata_at_output_boundary(tmp_path):
    tools = RepoLensMcpTools(tmp_path)
    envelope = {
        "ok": True,
        "data": {
            "node": {
                "label": "TokenBucket",
                "metadata": {
                    "token": "should-not-leak",
                    "package": "secret-sauce",
                    "command": "TOKEN=abc npm test --token xyz",
                },
            }
        },
        "evidence": [{"source": "fixture", "api-key": "should-not-leak"}],
        "warnings": [],
        "limits": {},
    }

    result = tools._mcp_envelope(envelope)

    assert result["data"]["node"]["label"] == "TokenBucket"
    assert result["data"]["node"]["metadata"]["package"] == "secret-sauce"
    assert result["data"]["node"]["metadata"]["token"] == "redacted"
    assert result["data"]["node"]["metadata"]["command"] == (
        "TOKEN=<redacted> npm test --token <redacted>"
    )
    assert result["evidence"][0]["api-key"] == "redacted"
    assert "should-not-leak" not in str(result)


def test_create_ai_proposal_service_and_mcp_facade_return_disabled_standard_envelope(
    tmp_path,
):
    from repolens.ai_proposal import create_ai_proposal

    task = "Summarize the bounded context pack"

    service_envelope = create_ai_proposal(
        tmp_path,
        kind="context_pack_summary",
        task=task,
    )
    mcp_envelope = RepoLensMcpTools(tmp_path).create_ai_proposal(
        kind="context_pack_summary",
        task=task,
    )

    assert mcp_envelope == service_envelope
    _assert_ai_proposal_envelope(
        service_envelope,
        kind="context_pack_summary",
        task=task,
        status="disabled",
        reason_code="ai_disabled",
        provider_configured=False,
    )


def test_create_ai_proposal_mcp_facade_returns_configured_test_provider_success_after_indexing(
    tmp_path,
):
    _write_preflight_fixture_repo(tmp_path)
    index_repository(tmp_path)

    result = RepoLensMcpTools(tmp_path).create_ai_proposal(
        kind="context_pack_summary",
        task="Summarize auth login context without exposing API_TOKEN=mcp-secret-204",
        enable_ai=True,
        provider="test",
        model="context-pack-summary-v1",
    )

    assert result["ok"] is True
    data = result["data"]
    assert data["status"] == "available"
    assert data["kind"] == "context_pack_summary"
    provider = data["provider"]
    assert provider["configured"] is True
    assert provider["name"] == "test"
    assert provider["model"] == "context-pack-summary-v1"
    proposal = data["proposal"]
    assert proposal["kind"] == "context_pack_summary"
    proposal_provider = proposal["provider"]
    assert proposal_provider["name"] == "test"
    assert proposal_provider["model"] == "context-pack-summary-v1"
    assert proposal["input_boundary"]["default_scope"] == "bounded_repolens_metadata"
    assert set(proposal["input_boundary"]["excluded_material"]) >= {
        "source_bodies",
        "raw_comments",
        "raw_secrets",
        "raw_agent_guidance_text",
        "credential_values",
    }
    assert proposal["source_disclosure"]["source_text_included"] is False
    assert proposal["source_disclosure"]["raw_comments_included"] is False
    assert proposal["source_disclosure"]["raw_secrets_included"] is False
    assert proposal["source_disclosure"]["raw_agent_guidance_text_included"] is False
    assert proposal["deterministic_evidence"]["first_read_files"][0]["path"] == (
        "src/auth/login.ts"
    )
    assert proposal["ai_interpretation"]["summary"]

    serialized = str(result)
    assert "mcp-secret-204" not in serialized
    assert "return input.user" not in serialized


def test_create_ai_proposal_reports_unavailable_when_enabled_without_provider_config(
    tmp_path,
):
    from repolens.ai_proposal import create_ai_proposal

    task = "Explain architecture from bounded metadata"

    envelope = create_ai_proposal(
        tmp_path,
        kind="architecture_explanation",
        task=task,
        enable_ai=True,
    )

    _assert_ai_proposal_envelope(
        envelope,
        kind="architecture_explanation",
        task=task,
        status="unavailable",
        reason_code="provider_unconfigured",
        provider_configured=False,
    )


def test_create_ai_proposal_rejects_unsupported_kind_before_provider_fallback(tmp_path):
    from repolens.ai_proposal import create_ai_proposal

    task = "Find ownership hypotheses"

    envelope = create_ai_proposal(
        tmp_path,
        kind="ownership_hypothesis",
        task=task,
        enable_ai=True,
    )

    _assert_ai_proposal_envelope(
        envelope,
        kind="ownership_hypothesis",
        task=task,
        status="unsupported_kind",
        reason_code="unsupported_kind",
        provider_configured=False,
    )


def _assert_ai_proposal_envelope(
    envelope,
    *,
    kind: str,
    task: str,
    status: str,
    reason_code: str,
    provider_configured: bool,
) -> None:
    assert set(envelope) >= {
        "confidence",
        "data",
        "evidence",
        "freshness",
        "limits",
        "ok",
        "truncation",
        "warnings",
    }
    assert envelope["ok"] is True
    assert envelope["truncation"] == {"fields": [], "truncated": False}

    data = envelope["data"]
    assert data["ai_proposal_version"] == "0.8.ai_proposal.v1"
    assert data["kind"] == kind
    assert data["status"] == status
    assert data["reason"]["code"] == reason_code
    assert data["provider"] == {
        "configured": provider_configured,
        "name": None,
        "model": None,
    }
    assert data["request"]["kind"] == kind
    assert data["request"]["task"] == task
    assert data["request"]["metadata_only"] is True
    assert data["safety"] == {
        "provider_called": False,
        "network_accessed": False,
        "file_written": False,
        "command_executed": False,
        "patch_applied": False,
        "remote_posted": False,
    }


def test_mcp_stdio_smoke_lists_exact_tools_and_calls_create_ai_proposal(tmp_path):
    async def run_smoke() -> None:
        server_params = StdioServerParameters(
            command="uv",
            args=["run", "repolens", "mcp", str(tmp_path)],
            env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                tool_names = [tool.name for tool in tools.tools]
                assert tool_names == list(MCP_TOOL_NAMES)
                assert "create_ai_proposal" in tool_names

                result = await session.call_tool(
                    "create_ai_proposal",
                    arguments={
                        "kind": "context_pack_summary",
                        "task": "Summarize the bounded context pack",
                    },
                )
                assert result.structuredContent is not None
                _assert_ai_proposal_envelope(
                    result.structuredContent,
                    kind="context_pack_summary",
                    task="Summarize the bounded context pack",
                    status="disabled",
                    reason_code="ai_disabled",
                    provider_configured=False,
                )

    asyncio.run(run_smoke())


def test_mcp_stdio_smoke_lists_exact_tools_and_calls_status(tmp_path):
    async def run_smoke() -> None:
        server_params = StdioServerParameters(
            command="uv",
            args=["run", "repolens", "mcp", str(tmp_path)],
            env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert [tool.name for tool in tools.tools] == list(MCP_TOOL_NAMES)

                result = await session.call_tool("graph_status", arguments={})
                assert result.structuredContent is not None
                assert result.structuredContent["ok"] is False
                assert result.structuredContent["error"]["code"] == "missing_graph_artifacts"

    asyncio.run(run_smoke())


def _write_fixture_repo(root) -> None:
    _write_text(root / "app.py", "ALPHA = 'alpha'\nSECOND = 'alpha again'\n")
    _write_text(
        root / "pyproject.toml",
        dedent(
            """
            [project]
            name = "demo"
            """
        ).lstrip(),
    )


def _write_preflight_fixture_repo(root) -> None:
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
        root / "src" / "auth" / "login.ts",
        dedent(
            """
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
