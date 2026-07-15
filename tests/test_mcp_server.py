from __future__ import annotations

import asyncio
import os
import sqlite3
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


def test_mcp_create_ai_proposal_returns_patch_plan(tmp_path):
    _write_text(
        tmp_path / "package.json",
        '{"scripts":{"test":"pytest tests/test_app.py"}}\n',
    )
    _write_text(tmp_path / "src" / "app.py", "def app():\n    return 1\n")
    _write_text(tmp_path / "tests" / "test_app.py", "from src.app import app\n")
    index_repository(tmp_path)
    tools = RepoLensMcpTools(tmp_path)

    result = tools.create_ai_proposal(
        "patch_plan",
        task="Plan app.py change",
        enable_ai=True,
        provider="test",
        model="patch-plan-v1",
    )

    assert result["ok"] is True
    assert result["data"]["status"] == "available"
    proposal = result["data"]["proposal"]
    assert proposal["kind"] == "patch_plan"
    assert proposal["target_files_to_inspect"]
    assert proposal["implementation_boundary"]["can_apply"] is False
    assert all(command["run"] is False for command in proposal["candidate_verification_commands"])


def test_mcp_create_ai_proposal_returns_architecture_explanation(tmp_path):
    _write_text(tmp_path / "src" / "app.py", "def app():\n    return 1\n")
    index_repository(tmp_path)
    tools = RepoLensMcpTools(tmp_path)

    result = tools.create_ai_proposal(
        "architecture_explanation",
        target="src/app.py",
        enable_ai=True,
        provider="test",
        model="architecture-explanation-v1",
    )

    assert result["ok"] is True
    assert result["data"]["status"] == "available"
    proposal = result["data"]["proposal"]
    assert proposal["kind"] == "architecture_explanation"
    assert proposal["deterministic_evidence"]["target_node"]["path"] == "src/app.py"


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
    assert data["graph_lifecycle"] == {
        "detected_state": "fresh",
        "initial": data["freshness"],
        "update": {
            "attempted": False,
            "mode": "none",
            "outcome": "not_needed",
            "reason": "graph_current",
        },
    }
    assert [item["path"] for item in data["first_read_files"]] == ["src/auth/login.ts"]
    assert [item["path"] for item in data["likely_tests"]] == ["tests/login.test.ts"]
    assert len(data["candidate_verification_commands"]) == 1
    assert all(command["found"] is True for command in data["candidate_verification_commands"])
    assert all(command["run"] is False for command in data["candidate_verification_commands"])
    assert "abc123" not in str(result)
    assert "return input.user" not in str(result)


def test_mcp_assistant_preflight_initializes_missing_graph_from_nested_directory(tmp_path):
    _write_preflight_fixture_repo(tmp_path)
    (tmp_path / ".git").mkdir()
    nested = tmp_path / "src" / "auth"
    source_before = (nested / "login.ts").read_text(encoding="utf-8")
    tools = RepoLensMcpTools(nested)

    first = tools.assistant_preflight(
        "Fix login validation",
        focus_hints=["src/auth/login.ts"],
        max_first_read_files=1,
    )
    second = tools.assistant_preflight(
        "Fix login validation",
        focus_hints=["src/auth/login.ts"],
        max_first_read_files=1,
    )

    assert first["ok"] is True
    assert first["data"]["assistant_preflight_version"] == "0.5.preflight.v1"
    assert first["freshness"]["fresh"] is True
    assert first["data"]["graph_lifecycle"]["detected_state"] == "missing"
    assert first["data"]["graph_lifecycle"]["update"] == {
        "attempted": True,
        "mode": "initialized",
        "outcome": "initialized",
        "reason": "missing_graph_artifacts",
        "selective_update": {
            "changed_count": 0,
            "deleted_count": 0,
            "parse_error_count": 0,
            "reparse_count": 3,
            "reused_count": 0,
            "safe": False,
            "stale_cleanup_count": 0,
        },
    }
    assert second["data"]["graph_lifecycle"]["detected_state"] == "fresh"
    assert first["data"]["context_pack_id"] == second["data"]["context_pack_id"]
    first_stable_data = dict(first["data"])
    second_stable_data = dict(second["data"])
    first_stable_data.pop("graph_lifecycle")
    second_stable_data.pop("graph_lifecycle")
    assert first_stable_data == second_stable_data
    assert [item["path"] for item in first["data"]["first_read_files"]] == ["src/auth/login.ts"]
    assert (tmp_path / ".repolens" / "graph.sqlite").is_file()
    assert (nested / "login.ts").read_text(encoding="utf-8") == source_before
    assert str(tmp_path) not in str(first)
    assert "return input.user" not in str(first)


def test_mcp_assistant_preflight_detects_supported_python_package_without_configuration(tmp_path):
    (tmp_path / ".git").mkdir()
    _write_text(
        tmp_path / "pyproject.toml",
        dedent(
            """
            [build-system]
            requires = ["hatchling"]
            build-backend = "hatchling.build"

            [project]
            name = "acme-service"
            version = "1.0.0"
            """
        ).lstrip(),
    )
    _write_text(tmp_path / "src" / "acme_service" / "__init__.py", "")
    _write_text(
        tmp_path / "src" / "acme_service" / "billing.py",
        "def calculate_invoice():\n    return 1\n",
    )
    _write_text(
        tmp_path / "tests" / "test_billing.py",
        "from acme_service.billing import calculate_invoice\n",
    )

    result = RepoLensMcpTools(tmp_path).assistant_preflight("Change invoice calculation")

    assert result["ok"] is True
    assert result["data"]["graph_lifecycle"]["detected_state"] == "missing"
    assert [item["path"] for item in result["data"]["first_read_files"]] == [
        "src/acme_service/billing.py"
    ]
    assert [item["path"] for item in result["data"]["likely_tests"]] == ["tests/test_billing.py"]
    assert result["data"]["graph_quality_warnings"] == []
    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        package_roots = list(
            connection.execute(
                """
                SELECT ecosystem, name, path, source_path
                FROM config_package_roots
                ORDER BY ecosystem, name, path
                """
            )
        )
    assert package_roots == [("python", "acme-service", "src/acme_service", "pyproject.toml")]


def test_mcp_assistant_preflight_warns_about_ambiguous_python_package_identity(tmp_path):
    (tmp_path / ".git").mkdir()
    for service in ("alpha", "beta"):
        _write_text(
            tmp_path / "services" / service / "pyproject.toml",
            '[project]\nname = "shared-service"\nversion = "1.0.0"\n',
        )
        _write_text(tmp_path / "services" / service / "shared_service" / "__init__.py", "")
        _write_text(
            tmp_path / "services" / service / "shared_service" / "billing.py",
            f"def {service}_invoice():\n    return 1\n",
        )

    result = RepoLensMcpTools(tmp_path).assistant_preflight(
        "Change alpha invoice",
        focus_hints=["services/alpha/shared_service/billing.py"],
    )

    assert result["ok"] is True
    assert result["data"]["graph_quality_warnings"] == [
        "graph_quality:ambiguous_package_identity:count=1"
    ]
    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        package_roots = list(
            connection.execute(
                """
                SELECT name, path, source_path
                FROM config_package_roots
                WHERE ecosystem = 'python'
                ORDER BY path
                """
            )
        )
    assert package_roots == [
        (
            "shared-service",
            "services/alpha/shared_service",
            "services/alpha/pyproject.toml",
        ),
        (
            "shared-service",
            "services/beta/shared_service",
            "services/beta/pyproject.toml",
        ),
    ]


def test_mcp_assistant_preflight_detects_supported_javascript_workspace(tmp_path):
    (tmp_path / ".git").mkdir()
    marker = tmp_path / "package-manager-was-run"
    _write_text(
        tmp_path / "package.json",
        dedent(
            """
            {
              "name": "workspace-root",
              "private": true,
              "workspaces": ["packages/*"],
              "scripts": {"preinstall": "touch package-manager-was-run"}
            }
            """
        ).lstrip(),
    )
    _write_text(
        tmp_path / "packages" / "app" / "package.json",
        '{"name":"@acme/app","dependencies":{"@acme/lib":"workspace:*"}}\n',
    )
    _write_text(
        tmp_path / "packages" / "lib" / "package.json",
        '{"name":"@acme/lib","exports":"./src/index.ts"}\n',
    )
    _write_text(
        tmp_path / "packages" / "app" / "src" / "main.ts",
        "import { invoice } from '@acme/lib';\nexport const total = invoice;\n",
    )
    _write_text(
        tmp_path / "packages" / "lib" / "src" / "index.ts",
        "export const invoice = 1;\n",
    )

    result = RepoLensMcpTools(tmp_path).assistant_preflight(
        "Change app invoice import",
        focus_hints=["packages/app/src/main.ts"],
    )

    assert result["ok"] is True
    assert result["data"]["graph_lifecycle"]["detected_state"] == "missing"
    assert result["data"]["graph_quality_warnings"] == []
    assert marker.exists() is False
    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        package_roots = list(
            connection.execute(
                """
                SELECT name, path
                FROM config_package_roots
                WHERE ecosystem = 'javascript'
                ORDER BY path
                """
            )
        )
        workspaces = list(
            connection.execute(
                """
                SELECT path, source_path, evidence_kind
                FROM config_workspaces
                ORDER BY path, source_path
                """
            )
        )
        import_resolution = connection.execute(
            """
            SELECT classification, resolved_path, resolution_status
            FROM javascript_imports
            WHERE path = 'packages/app/src/main.ts'
            """
        ).fetchone()
    assert package_roots == [
        ("workspace-root", "."),
        ("@acme/app", "packages/app"),
        ("@acme/lib", "packages/lib"),
    ]
    assert workspaces == [("packages/*", "package.json", "package.workspaces")]
    assert import_resolution == (
        "local_resolved",
        "packages/lib/src/index.ts",
        "resolved_workspace_package",
    )


def test_mcp_assistant_preflight_keeps_ambiguous_javascript_workspace_as_warnings(
    tmp_path,
):
    (tmp_path / ".git").mkdir()
    _write_text(
        tmp_path / "package.json",
        '{"name":"workspace-root","private":true,"workspaces":["packages/*"]}\n',
    )
    _write_text(
        tmp_path / "packages" / "app" / "package.json",
        '{"name":"@acme/app","dependencies":{"@acme/lib":"workspace:*"}}\n',
    )
    for package in ("lib-a", "lib-b"):
        _write_text(
            tmp_path / "packages" / package / "package.json",
            '{"name":"@acme/lib","exports":"./src/index.ts"}\n',
        )
        _write_text(
            tmp_path / "packages" / package / "src" / "index.ts",
            "export const invoice = 1;\n",
        )
    _write_text(
        tmp_path / "packages" / "app" / "src" / "main.ts",
        "import { invoice } from '@acme/lib';\nexport const total = invoice;\n",
    )

    result = RepoLensMcpTools(tmp_path).assistant_preflight(
        "Change app invoice import",
        focus_hints=["packages/app/src/main.ts"],
    )

    assert result["ok"] is True
    assert result["data"]["graph_quality_warnings"] == [
        "graph_quality:ambiguous_package_identity:count=1",
        "graph_quality:ambiguous_workspace_package_import:count=1",
    ]
    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        import_resolution = connection.execute(
            """
            SELECT classification, resolved_path, resolution_status
            FROM javascript_imports
            WHERE path = 'packages/app/src/main.ts'
            """
        ).fetchone()
        definitive_edges = connection.execute(
            """
            SELECT COUNT(*)
            FROM edges
            WHERE source_id = 'javascript_module:packages/app/src/main.ts'
              AND target_id LIKE 'javascript_module:packages/lib-%'
              AND kind = 'IMPORTS'
            """
        ).fetchone()[0]
        candidates = connection.execute(
            """
            SELECT COUNT(*)
            FROM relationship_candidates
            WHERE source_id = 'javascript_module:packages/app/src/main.ts'
              AND kind = 'IMPORTS'
            """
        ).fetchone()[0]
    assert import_resolution == ("third_party", None, "external")
    assert definitive_edges == 0
    assert candidates == 2


def test_mcp_assistant_preflight_returns_problem_for_unsupported_root(tmp_path):
    tools = RepoLensMcpTools(tmp_path)

    result = tools.assistant_preflight("Inspect this unsupported root")

    assert result["ok"] is False
    assert result["error"]["code"] == "unsupported_repository_root"
    assert result["error"]["problem"] == {
        "reason": "unsupported_repository_root",
        "recoverable": True,
    }
    assert result["freshness"] == {"fresh": False, "status": "unavailable"}
    assert result["warnings"] == [
        "No repository facts were guessed after preflight preparation failed."
    ]


def test_mcp_assistant_preflight_returns_problem_when_indexing_fails(tmp_path):
    _write_preflight_fixture_repo(tmp_path)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".repolens").symlink_to(tmp_path / "missing-artifact-target")
    tools = RepoLensMcpTools(tmp_path)

    result = tools.assistant_preflight("Fix login validation")

    assert result["ok"] is False
    assert result["error"]["code"] == "preflight_index_failed"
    assert result["error"]["problem"] == {
        "reason": "artifact_dir_is_symlink",
        "recoverable": True,
    }
    assert result["data"] == {}


def test_mcp_assistant_preflight_selectively_refreshes_changed_graph(tmp_path):
    _write_preflight_fixture_repo(tmp_path)
    index_repository(tmp_path)
    _write_text(tmp_path / "src" / "auth" / "login.ts", "export const changed = true;\n")
    tools = RepoLensMcpTools(tmp_path)

    result = tools.assistant_preflight("Fix login validation")

    assert result["ok"] is True
    assert result["freshness"]["fresh"] is True
    assert result["data"]["freshness"]["status"] == "available"
    lifecycle = result["data"]["graph_lifecycle"]
    assert lifecycle["detected_state"] == "changed"
    assert lifecycle["initial"]["status"] == "stale"
    assert lifecycle["update"] == {
        "attempted": True,
        "mode": "selective",
        "outcome": "updated",
        "reason": "file_changes_detected",
        "selective_update": {
            "changed_count": 1,
            "deleted_count": 0,
            "parse_error_count": 0,
            "reparse_count": 1,
            "reused_count": 2,
            "safe": True,
            "stale_cleanup_count": 0,
        },
    }
    assert "Graph artifacts may be stale" not in " ".join(result["warnings"])


def test_mcp_assistant_preflight_removes_deleted_and_unparseable_stale_facts(tmp_path):
    _write_text(tmp_path / "deleted.py", "def deleted_symbol():\n    return 1\n")
    _write_text(tmp_path / "broken.py", "def old_symbol():\n    return 1\n")
    index_repository(tmp_path)
    (tmp_path / "deleted.py").unlink()
    _write_text(tmp_path / "broken.py", "def broken(:\n    pass\n")

    result = RepoLensMcpTools(tmp_path).assistant_preflight("Inspect symbols")

    assert result["ok"] is True
    assert result["freshness"]["fresh"] is True
    lifecycle = result["data"]["graph_lifecycle"]
    assert lifecycle["detected_state"] == "deleted_files"
    assert lifecycle["update"]["mode"] == "selective"
    assert lifecycle["update"]["selective_update"] == {
        "changed_count": 2,
        "deleted_count": 1,
        "parse_error_count": 1,
        "reparse_count": 1,
        "reused_count": 0,
        "safe": True,
        "stale_cleanup_count": 2,
    }
    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        deleted_count = connection.execute(
            "SELECT COUNT(*) FROM files WHERE path = 'deleted.py'"
        ).fetchone()[0]
        stale_symbol_count = connection.execute(
            "SELECT COUNT(*) FROM python_symbols WHERE path IN ('deleted.py', 'broken.py')"
        ).fetchone()[0]
        parse_error_count = connection.execute(
            "SELECT COUNT(*) FROM python_parse_errors WHERE path = 'broken.py'"
        ).fetchone()[0]
    assert deleted_count == 0
    assert stale_symbol_count == 0
    assert parse_error_count == 1


def test_mcp_assistant_preflight_refreshes_branch_mismatch(tmp_path):
    _write_preflight_fixture_repo(tmp_path)
    git_dir = tmp_path / ".git"
    (git_dir / "refs" / "heads").mkdir(parents=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git_dir / "refs" / "heads" / "main").write_text("a" * 40 + "\n", encoding="utf-8")
    index_repository(tmp_path)
    (git_dir / "HEAD").write_text("ref: refs/heads/feature\n", encoding="utf-8")
    (git_dir / "refs" / "heads" / "feature").write_text("b" * 40 + "\n", encoding="utf-8")

    result = RepoLensMcpTools(tmp_path).assistant_preflight("Fix login validation")

    assert result["ok"] is True
    lifecycle = result["data"]["graph_lifecycle"]
    assert lifecycle["detected_state"] == "branch_mismatch"
    assert lifecycle["initial"]["git"] == {
        "current": {"branch": "feature", "commit": "b" * 40, "detected": True},
        "indexed": {"branch": "main", "commit": "a" * 40, "detected": True},
    }
    assert lifecycle["update"]["mode"] == "selective"
    assert result["freshness"]["git"]["indexed"]["branch"] == "feature"
    assert result["freshness"]["git"]["current"]["branch"] == "feature"


def test_mcp_assistant_preflight_rebuilds_invalid_artifacts(tmp_path):
    _write_preflight_fixture_repo(tmp_path)
    index_repository(tmp_path)
    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        connection.execute("UPDATE metadata SET value = '0' WHERE key = 'schema_version'")

    result = RepoLensMcpTools(tmp_path).assistant_preflight("Fix login validation")

    assert result["ok"] is True
    assert result["freshness"]["fresh"] is True
    lifecycle = result["data"]["graph_lifecycle"]
    assert lifecycle["detected_state"] == "invalid_artifacts"
    assert lifecycle["initial"]["reason"] == "unsupported_schema_version"
    assert lifecycle["update"]["mode"] == "full_rebuild"
    assert lifecycle["update"]["outcome"] == "rebuilt"
    assert lifecycle["update"]["selective_update"]["safe"] is False


def test_mcp_assistant_preflight_reports_graph_quality_warnings_deterministically(tmp_path):
    _write_text(
        tmp_path / "src" / "app.ts",
        "import { missing } from './missing';\nexport const value = missing;\n",
    )
    index_repository(tmp_path)

    first = RepoLensMcpTools(tmp_path).assistant_preflight("Inspect app import")
    second = RepoLensMcpTools(tmp_path).assistant_preflight("Inspect app import")

    assert first["data"]["graph_quality_warnings"] == [
        "graph_quality:javascript_unresolved_import_relationships:count=1"
    ]
    assert second["data"]["graph_quality_warnings"] == first["data"]["graph_quality_warnings"]


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


def test_mcp_stdio_assistant_preflight_builds_missing_graph_from_nested_directory(tmp_path):
    _write_preflight_fixture_repo(tmp_path)
    (tmp_path / ".git").mkdir()
    nested = tmp_path / "src" / "auth"

    async def run_smoke() -> None:
        server_params = StdioServerParameters(
            command="uv",
            args=["run", "repolens", "mcp", str(nested)],
            env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "assistant_preflight",
                    arguments={
                        "task": "Fix login validation",
                        "focus_hints": ["src/auth/login.ts"],
                        "max_first_read_files": 1,
                    },
                )

        assert result.structuredContent is not None
        envelope = result.structuredContent
        assert envelope["ok"] is True
        assert envelope["freshness"]["fresh"] is True
        assert [item["path"] for item in envelope["data"]["first_read_files"]] == [
            "src/auth/login.ts"
        ]
        assert str(tmp_path) not in str(envelope)
        assert "return input.user" not in str(envelope)

    asyncio.run(run_smoke())
    assert (tmp_path / ".repolens" / "graph.sqlite").is_file()


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
