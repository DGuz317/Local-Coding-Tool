from __future__ import annotations

from textwrap import dedent

from repolens.indexer import index_repository
from repolens.query import GraphQueryService


def test_query_service_returns_actionable_missing_graph_response(tmp_path):
    service = GraphQueryService(tmp_path)

    result = service.repo_summary()

    assert result["ok"] is False
    assert result["error"]["code"] == "missing_graph_artifacts"
    assert result["error"]["recommended_action"].startswith("repolens index ")
    assert ".repolens/graph.sqlite" in result["error"]["missing_artifacts"]
    assert result["confidence"] == "none"
    assert result["evidence"] == []


def test_query_service_summarizes_status_report_nodes_neighbors_and_entrypoints(tmp_path):
    _write_fixture_repo(tmp_path)
    index_repository(tmp_path)
    service = GraphQueryService(tmp_path)

    summary = service.repo_summary(max_entrypoints=2, max_commands=2)
    status = service.graph_status()
    report = service.get_graph_report(max_chars=80)
    entrypoints = service.list_entrypoints(max_results=10)
    search = service.search_graph("public widget", max_results=5)

    assert summary["ok"] is True
    assert summary["data"]["repository"]["name"] == tmp_path.name
    assert {item["language"] for item in summary["data"]["languages"]} >= {"python", "typescript"}
    assert summary["data"]["counts"]["nodes"] > 0
    assert summary["data"]["entrypoints"][0]["name"] == "demo"
    assert summary["limits"]["max_entrypoints"] == 2
    assert summary["confidence"] == "high"
    assert summary["evidence"][0]["artifact"] == ".repolens/graph.sqlite"

    assert status["ok"] is True
    assert status["data"]["status"] == "available"
    assert status["data"]["fresh"] is True
    assert status["data"]["changed_files"] == []
    assert status["warnings"] == []

    assert report["ok"] is True
    assert report["data"]["report_path"] == ".repolens/graph-report.md"
    assert report["data"]["truncated"] is True
    assert report["pagination"]["truncated"] is True

    assert entrypoints["ok"] is True
    assert [entrypoint["name"] for entrypoint in entrypoints["data"]["entrypoints"]] == [
        "demo",
        "start",
    ]
    assert entrypoints["data"]["entrypoints"][0]["evidence"] == "project.scripts"

    assert search["ok"] is True
    assert search["data"]["matches"][0]["node"]["label"] == "PublicWidget"
    assert search["data"]["matches"][0]["confidence"] == "high"
    assert search["data"]["matches"][0]["evidence"]

    node_id = search["data"]["matches"][0]["node"]["id"]
    node = service.get_node(node_id=node_id)
    neighbors = service.get_neighbors(node_id=node_id, depth=1, max_results=10)
    path = service.shortest_path("README.md", "PublicWidget", max_depth=5)

    assert node["ok"] is True
    assert node["data"]["node"]["id"] == node_id
    assert node["data"]["ambiguous"] is False

    assert neighbors["ok"] is True
    assert neighbors["data"]["center"]["id"] == node_id
    assert any(item["edge"]["kind"] == "CONTAINS" for item in neighbors["data"]["neighbors"])
    assert neighbors["pagination"]["returned"] == len(neighbors["data"]["neighbors"])

    assert path["ok"] is True
    assert path["data"]["found"] is True
    assert path["data"]["path"][0]["node"]["path"] == "README.md"
    assert path["data"]["path"][-1]["node"]["label"] == "PublicWidget"
    assert path["data"]["edge_count"] >= 1


def test_search_graph_ranks_exact_paths_names_tokens_and_public_symbols(tmp_path):
    _write_fixture_repo(tmp_path)
    index_repository(tmp_path)
    service = GraphQueryService(tmp_path)

    exact_path = service.search_graph("src/demo/web.ts", max_results=3)
    exact_name = service.search_graph("PublicWidget", max_results=3)
    token_search = service.search_graph("private helper", max_results=3)

    assert exact_path["data"]["matches"][0]["node"]["path"] == "src/demo/web.ts"
    assert exact_path["data"]["matches"][0]["matched_fields"][0]["field"] == "path"
    assert exact_name["data"]["matches"][0]["node"]["label"] == "PublicWidget"
    assert token_search["data"]["matches"][0]["node"]["label"] == "privateHelper"
    assert exact_name["pagination"] == {
        "limit": 3,
        "offset": 0,
        "returned": 1,
        "total": 1,
        "truncated": False,
    }


def test_ambiguous_node_lookup_returns_candidates_without_choosing(tmp_path):
    _write_text(tmp_path / "src" / "demo" / "one.py", "def handler():\n    return 1\n")
    _write_text(tmp_path / "src" / "demo" / "two.py", "def handler():\n    return 2\n")
    index_repository(tmp_path)
    service = GraphQueryService(tmp_path)

    result = service.get_node(query="handler")

    assert result["ok"] is True
    assert result["data"]["ambiguous"] is True
    assert result["data"]["node"] is None
    assert [candidate["node"]["path"] for candidate in result["data"]["candidates"]] == [
        "src/demo/one.py",
        "src/demo/two.py",
    ]
    assert result["confidence"] == "low"


def test_query_service_reports_stale_warnings_without_reading_source_files(tmp_path, monkeypatch):
    _write_fixture_repo(tmp_path)
    index_repository(tmp_path)
    _write_text(tmp_path / "src" / "demo" / "service.py", "def changed():\n    return 2\n")
    service = GraphQueryService(tmp_path)

    def fail_source_read(path):
        if "src" in path.parts:
            raise AssertionError(f"source file was read: {path}")
        return original_read_bytes(path)

    original_read_bytes = type(tmp_path).read_bytes
    monkeypatch.setattr(type(tmp_path), "read_bytes", fail_source_read)

    status = service.graph_status()
    search = service.search_graph("PublicWidget")

    assert status["data"]["status"] == "stale"
    assert status["data"]["fresh"] is False
    assert status["data"]["changed_files"] == [
        {"change_type": "metadata_changed", "path": "src/demo/service.py"}
    ]
    assert status["warnings"] == [
        "Graph artifacts may be stale; file metadata changed since indexing."
    ]
    assert search["warnings"] == status["warnings"]


def test_neighbors_and_entrypoints_include_pagination_and_truncation(tmp_path):
    _write_fixture_repo(tmp_path)
    index_repository(tmp_path)
    service = GraphQueryService(tmp_path)
    node_id = service.search_graph("src/demo/web.ts")["data"]["matches"][0]["node"]["id"]

    neighbors = service.get_neighbors(node_id=node_id, depth=2, max_results=1)
    entrypoints = service.list_entrypoints(max_results=1)

    assert neighbors["pagination"]["limit"] == 1
    assert neighbors["pagination"]["returned"] == 1
    assert neighbors["pagination"]["truncated"] is True
    assert entrypoints["pagination"] == {
        "limit": 1,
        "offset": 0,
        "returned": 1,
        "total": 2,
        "truncated": True,
    }


def test_impact_analysis_returns_affected_context_and_verification_commands(tmp_path):
    _write_impact_fixture_repo(tmp_path)
    index_repository(tmp_path)
    service = GraphQueryService(tmp_path)

    result = service.impact_analysis("src/auth/login.ts", max_results=2)

    assert result["ok"] is True
    assert result["confidence"] == "high"
    assert result["data"]["ambiguous"] is False
    assert result["limits"] == {"max_depth": 2, "max_results": 2}
    assert result["data"]["caps"] == {"depth": 1, "max_results": 2}

    direct_paths = [item["path"] for item in result["data"]["direct_affected_files"]]
    assert direct_paths == ["src/auth/login.ts", "src/auth/router.ts"]

    likely_paths = [item["path"] for item in result["data"]["likely_affected_files"]]
    assert likely_paths == ["tests/login.test.ts", "README.md"]
    assert result["data"]["truncated"]["likely_affected_files"] is True

    assert [item["path"] for item in result["data"]["dependencies"]] == ["src/auth/policy.ts"]
    assert [item["path"] for item in result["data"]["dependents"]] == [
        "src/auth/router.ts",
        "tests/login.test.ts",
    ]
    assert result["data"]["likely_tests"][0]["path"] == "tests/login.test.ts"
    assert result["data"]["likely_tests"][0]["reason"] == "imports_target"
    assert result["data"]["related_docs"][0]["path"] == "README.md"
    assert result["data"]["related_configs"][0]["path"] == "package.json"
    assert result["data"]["risk_comments"][0] == {
        "confidence": "high",
        "line": 3,
        "path": "src/auth/login.ts",
        "reason": "tagged_comment_on_target_file",
        "tag": "RISK",
        "text": "validation protects locked accounts",
    }
    assert [command["name"] for command in result["data"]["candidate_verification_commands"]] == [
        "lint",
        "test",
    ]
    assert all(command["not_run"] for command in result["data"]["candidate_verification_commands"])
    assert result["evidence"][-1] == {"source": "graph_metadata", "tool": "impact_analysis"}


def test_reading_order_uses_task_tokens_tests_caps_and_contextual_configs(tmp_path):
    _write_impact_fixture_repo(tmp_path)
    index_repository(tmp_path)
    service = GraphQueryService(tmp_path)

    result = service.suggest_reading_order("Add validation to login flow tests", max_files=3)

    assert result["ok"] is True
    assert result["confidence"] == "medium"
    assert result["limits"] == {"max_files": 3}
    assert result["data"]["caps"] == {"max_files": 3}
    assert result["data"]["tokens"] == ["validation", "login", "flow", "test"]
    assert result["data"]["truncated"] is True
    assert result["pagination"]["truncated"] is True
    assert [item["path"] for item in result["data"]["reading_order"]] == [
        "src/auth/login.ts",
        "tests/login.test.ts",
        "README.md",
    ]
    assert result["data"]["reading_order"][0]["reason"] == "task_matches_symbols"
    assert result["data"]["reading_order"][1]["reason"] == "likely_related_test"
    assert "package.json" not in [item["path"] for item in result["data"]["reading_order"]]
    assert result["data"]["reading_order"][0]["evidence"]

    config_result = service.suggest_reading_order("fix package test command", max_files=3)

    assert config_result["data"]["reading_order"][0]["path"] == "package.json"
    assert config_result["data"]["reading_order"][0]["reason"] == "config_matches_task"


def test_impact_analysis_and_reading_order_return_ambiguous_candidates(tmp_path):
    _write_text(tmp_path / "src" / "demo" / "one.py", "def handler():\n    return 1\n")
    _write_text(tmp_path / "src" / "demo" / "two.py", "def handler():\n    return 2\n")
    index_repository(tmp_path)
    service = GraphQueryService(tmp_path)

    impact = service.impact_analysis("handler")
    reading = service.suggest_reading_order("handler")

    assert impact["ok"] is True
    assert impact["confidence"] == "low"
    assert impact["data"]["ambiguous"] is True
    assert [candidate["node"]["path"] for candidate in impact["data"]["candidates"]] == [
        "src/demo/one.py",
        "src/demo/two.py",
    ]
    assert impact["data"]["direct_affected_files"] == []

    assert reading["ok"] is True
    assert reading["confidence"] == "low"
    assert reading["data"]["ambiguous"] is True
    assert [candidate["node"]["path"] for candidate in reading["data"]["candidates"]] == [
        "src/demo/one.py",
        "src/demo/two.py",
    ]
    assert reading["data"]["reading_order"] == []


def test_impact_analysis_and_reading_order_include_stale_warnings(tmp_path):
    _write_impact_fixture_repo(tmp_path)
    index_repository(tmp_path)
    _write_text(tmp_path / "src" / "auth" / "login.ts", "export function changed() {}\n")
    service = GraphQueryService(tmp_path)

    impact = service.impact_analysis("src/auth/login.ts")
    reading = service.suggest_reading_order("login flow")

    assert impact["warnings"] == [
        "Graph artifacts may be stale; file metadata changed since indexing."
    ]
    assert reading["warnings"] == impact["warnings"]


def _write_fixture_repo(root) -> None:
    _write_text(
        root / "pyproject.toml",
        dedent(
            """
            [project]
            name = "demo"

            [project.scripts]
            demo = "demo.service:main"
            """
        ).lstrip(),
    )
    _write_text(
        root / "package.json",
        dedent(
            """
            {
              "name": "demo-web",
              "scripts": {"start": "vite --host 0.0.0.0"},
              "dependencies": {"react": "^19.0.0"}
            }
            """
        ).lstrip(),
    )
    _write_text(
        root / "README.md",
        dedent(
            """
            # Demo

            See `src/demo/web.ts` for the public widget.
            """
        ).lstrip(),
    )
    _write_text(root / "src" / "demo" / "__init__.py", "")
    _write_text(
        root / "src" / "demo" / "service.py",
        dedent(
            """
            def main():
                return helper()

            def helper():
                return 1
            """
        ).lstrip(),
    )
    _write_text(
        root / "src" / "demo" / "web.ts",
        dedent(
            """
            export class PublicWidget {}
            class PrivateWidget {}
            function privateHelper() {}
            """
        ).lstrip(),
    )


def _write_impact_fixture_repo(root) -> None:
    _write_text(
        root / "package.json",
        dedent(
            """
            {
              "name": "auth-demo",
              "scripts": {
                "lint": "eslint .",
                "publish": "npm publish",
                "test": "vitest run tests/login.test.ts"
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
        root / "src" / "auth" / "policy.ts",
        dedent(
            """
            export function requirePolicy() {
              return true;
            }
            """
        ).lstrip(),
    )
    _write_text(
        root / "src" / "auth" / "login.ts",
        dedent(
            """
            import { requirePolicy } from "./policy";

            // RISK: validation protects locked accounts
            export function validateLogin(input: { user: string }) {
              return requirePolicy() && input.user.length > 0;
            }

            export function loginFlow(input: { user: string }) {
              return validateLogin(input);
            }
            """
        ).lstrip(),
    )
    _write_text(
        root / "src" / "auth" / "router.ts",
        dedent(
            """
            import { loginFlow } from "./login";

            export function routeLogin() {
              return loginFlow({ user: "demo" });
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
