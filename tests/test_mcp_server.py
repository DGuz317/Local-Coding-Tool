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


def _write_text(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
