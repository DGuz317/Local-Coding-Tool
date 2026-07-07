from __future__ import annotations

import json
import sqlite3

from typer.testing import CliRunner

from repolens.cli import app
from repolens.context_pack import get_task_context
from repolens.indexer import index_repository
from repolens.semantic_artifact import SEMANTIC_STORE_PATH, inspect_semantic_artifact

runner = CliRunner()


def test_experimental_semantic_artifact_records_source_free_metadata(tmp_path):
    (tmp_path / "app.py").write_text(
        "def run():\n    return 'do-not-disclose-source'\n",
        encoding="utf-8",
    )

    result = index_repository(tmp_path, experimental_semantic_artifact=True)

    assert result.semantic_artifact == SEMANTIC_STORE_PATH
    assert (tmp_path / ".repolens" / "semantic.sqlite").is_file()
    with sqlite3.connect(tmp_path / ".repolens" / "semantic.sqlite") as connection:
        connection.row_factory = sqlite3.Row
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        rows = list(
            connection.execute(
                """
                SELECT
                    source_path,
                    source_language,
                    semantic_backend,
                    parser_backend,
                    provenance_json,
                    confidence,
                    evidence_labels_json,
                    experimental_status
                FROM semantic_sources
                """
            )
        )

    assert metadata["schema_version"] == "2"
    assert metadata["semantic_backend"] == "semantic_skeleton"
    assert metadata["parser_backend"] == "tree_sitter_js_ts"
    assert metadata["experimental_status"] == "experimental"
    assert len(rows) == 1
    row = rows[0]
    assert row["source_path"] == "app.py"
    assert row["source_language"] == "python"
    assert row["semantic_backend"] == "semantic_skeleton"
    assert row["parser_backend"] == "tree_sitter_js_ts"
    assert json.loads(row["provenance_json"])["semantic_backend"] == "semantic_skeleton"
    assert row["confidence"] == "candidate"
    assert json.loads(row["evidence_labels_json"]) == [
        "scanner:eligible_file",
        "semantic:skeleton",
    ]
    assert row["experimental_status"] == "experimental"
    assert (
        b"do-not-disclose-source" not in (tmp_path / ".repolens" / "semantic.sqlite").read_bytes()
    )


def test_experimental_semantic_artifact_excluded_from_stable_identity(tmp_path):
    (tmp_path / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")

    index_repository(tmp_path)
    stable_hash = _canonical_graph_hash(tmp_path)
    stable_pack_id = get_task_context(tmp_path, "change run")["data"]["context_pack_id"]

    index_repository(tmp_path, experimental_semantic_artifact=True)

    assert _canonical_graph_hash(tmp_path) == stable_hash
    assert get_task_context(tmp_path, "change run")["data"]["context_pack_id"] == stable_pack_id
    graph_payload = (tmp_path / ".repolens" / "graph.json").read_text(encoding="utf-8")
    assert "semantic_skeleton" not in graph_payload
    assert "semantic:skeleton" not in graph_payload


def test_semantic_artifact_status_reports_missing_present_stale_and_unsupported(tmp_path):
    (tmp_path / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")

    assert inspect_semantic_artifact(tmp_path).status == "missing"

    index_repository(tmp_path, experimental_semantic_artifact=True)
    present = inspect_semantic_artifact(tmp_path)
    assert present.status == "present"
    assert present.reason == "semantic_artifact_current"

    (tmp_path / "app.py").write_text("def run():\n    return 100\n", encoding="utf-8")
    stale = inspect_semantic_artifact(tmp_path)
    assert stale.status == "stale"
    assert stale.reason == "semantic_source_fingerprint_changed"

    with sqlite3.connect(tmp_path / ".repolens" / "semantic.sqlite") as connection:
        connection.execute("UPDATE metadata SET value = '999' WHERE key = 'schema_version'")

    unsupported = inspect_semantic_artifact(tmp_path)
    assert unsupported.status == "unsupported"
    assert unsupported.reason == "semantic_schema_version_unsupported"
    assert unsupported.detected_schema_version == "999"


def test_cli_can_enable_semantic_artifact_and_status_reports_it(tmp_path):
    (tmp_path / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")

    result = runner.invoke(
        app, ["index", str(tmp_path), "--experimental-semantic-artifact", "--json"]
    )

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    assert envelope["data"]["semantic_artifact"] == ".repolens/semantic.sqlite"

    status_result = runner.invoke(app, ["status", str(tmp_path), "--json"])

    assert status_result.exit_code == 0
    status_envelope = json.loads(status_result.output)
    assert status_envelope["data"]["semantic_artifact"]["status"] == "present"


def test_semantic_inspect_reads_present_artifact_without_source_text(tmp_path):
    secret_source = "do-not-disclose-semantic-inspect-source"
    (tmp_path / "app.py").write_text(
        f"def run():\n    return {secret_source!r}\n",
        encoding="utf-8",
    )
    index_repository(tmp_path, experimental_semantic_artifact=True)

    result = runner.invoke(
        app,
        ["semantic-inspect", "app.py", "--repo-path", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    data = envelope["data"]
    assert envelope["ok"] is True
    assert data["schema_version"] == 2
    assert data["semantic_backend"] == "semantic_skeleton"
    assert data["parser_backend"] == "tree_sitter_js_ts"
    assert data["source_language"] == "python"
    assert data["source_path"] == "app.py"
    assert data["experimental_status"] == "experimental"
    assert data["artifact_freshness"] == {
        "checked_without_live_parse": True,
        "fingerprint_strategy": "eligible_path_and_size",
        "fresh": True,
        "reason": "semantic_artifact_current",
        "recommended_action": None,
    }
    assert data["facts"]["calls"] == []
    assert data["facts"]["definitions"] == []
    assert data["facts"]["imports"] == []
    assert data["facts"]["relationships"] == []
    control_flow = data["facts"]["control_flow"]
    assert len(control_flow) == 1
    assert [node["kind"] for node in control_flow[0]["nodes"]] == ["entry", "return", "exit"]
    assert data["limits"] == {"fact_set": "python_branch_cfg", "source_snippets": 0}
    assert secret_source not in result.output
    assert str(tmp_path) not in result.output


def test_semantic_inspect_reports_missing_artifact_without_parsing_live_source(tmp_path):
    secret_source = "missing-artifact-source-must-not-leak"
    (tmp_path / "app.py").write_text(
        f"def run():\n    return {secret_source!r}\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["semantic-inspect", "app.py", "--repo-path", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    data = envelope["data"]
    assert data["artifact_status"]["status"] == "missing"
    assert data["artifact_freshness"] == {
        "checked_without_live_parse": True,
        "fresh": False,
        "reason": "semantic_artifact_missing",
        "recommended_action": "repolens index . --experimental-semantic-artifact",
    }
    assert data["source_path"] == "app.py"
    assert data["facts"] == {
        "calls": [],
        "control_flow": [],
        "definitions": [],
        "imports": [],
        "relationships": [],
    }
    assert envelope["warnings"] == [
        "Semantic artifacts are missing; run repolens index with --experimental-semantic-artifact."
    ]
    assert secret_source not in result.output
    assert str(tmp_path) not in result.output


def test_semantic_inspect_reports_stale_artifact_with_freshness_metadata(tmp_path):
    (tmp_path / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    index_repository(tmp_path, experimental_semantic_artifact=True)
    stale_secret_source = "stale-source-must-not-leak"
    (tmp_path / "app.py").write_text(
        f"def run():\n    return {stale_secret_source!r}\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["semantic-inspect", "app.py", "--repo-path", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    data = envelope["data"]
    assert data["artifact_status"]["status"] == "stale"
    assert data["artifact_status"]["reason"] == "semantic_source_fingerprint_changed"
    assert data["semantic_backend"] == "semantic_skeleton"
    assert data["parser_backend"] == "tree_sitter_js_ts"
    assert data["source_language"] == "python"
    assert data["experimental_status"] == "experimental"
    assert data["artifact_freshness"] == {
        "checked_without_live_parse": True,
        "fingerprint_strategy": "eligible_path_and_size",
        "fresh": False,
        "reason": "semantic_source_fingerprint_changed",
        "recommended_action": "repolens index . --experimental-semantic-artifact",
    }
    assert envelope["warnings"] == [
        "Semantic artifacts are stale; re-index before relying on semantic facts."
    ]
    assert stale_secret_source not in result.output
    assert str(tmp_path) not in result.output


def test_semantic_inspect_returns_source_free_python_branch_cfg(tmp_path):
    secret_source = "secret-branch-source-must-not-leak"
    (tmp_path / "app.py").write_text(
        "def choose(value):\n"
        "    if value == 1:\n"
        "        return 'one'\n"
        "    elif value == 2:\n"
        f"        return {secret_source!r}\n"
        "    else:\n"
        "        return 'other'\n",
        encoding="utf-8",
    )
    index_repository(tmp_path, experimental_semantic_artifact=True)

    result = runner.invoke(
        app,
        ["semantic-inspect", "app.py", "--repo-path", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    data = envelope["data"]
    control_flow = data["facts"]["control_flow"]
    assert data["limits"] == {"fact_set": "python_branch_cfg", "source_snippets": 0}
    assert len(control_flow) == 1
    fact = control_flow[0]
    assert fact["source_path"] == "app.py"
    assert fact["function"] == {
        "identity": "app.py:choose:1-7",
        "line_range": {"start": 1, "end": 7},
        "name": "choose",
    }
    assert [node["kind"] for node in fact["nodes"]] == [
        "entry",
        "branch",
        "return",
        "branch",
        "return",
        "return",
        "exit",
    ]
    assert {edge["kind"] for edge in fact["edges"]} == {
        "next",
        "true_branch",
        "false_branch",
    }
    assert fact["confidence"] == "candidate"
    assert fact["evidence_labels"] == [
        "scanner:eligible_file",
        "semantic:skeleton",
        "python:ast",
        "semantic:python_branch_cfg",
    ]
    assert fact["warnings"] == []
    assert secret_source not in result.output
    assert "value == 1" not in result.output
    assert "value == 2" not in result.output
    assert str(tmp_path) not in result.output


def test_semantic_inspect_returns_nested_multiple_return_and_unsupported_cfg(tmp_path):
    (tmp_path / "app.py").write_text(
        "def nested(value):\n"
        "    if value:\n"
        "        if value > 10:\n"
        "            return 10\n"
        "    return 0\n"
        "\n"
        "def unsupported(value):\n"
        "    if check(value):\n"
        "        return 1\n"
        "    while value:\n"
        "        value -= 1\n"
        "    return 0\n",
        encoding="utf-8",
    )
    index_repository(tmp_path, experimental_semantic_artifact=True)

    result = runner.invoke(
        app,
        ["semantic-inspect", "app.py", "--repo-path", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    facts = envelope["data"]["facts"]["control_flow"]
    assert [fact["function"]["name"] for fact in facts] == ["nested", "unsupported"]

    nested = facts[0]
    assert [node["kind"] for node in nested["nodes"]].count("branch") == 2
    assert [node["kind"] for node in nested["nodes"]].count("return") == 2
    assert nested["warnings"] == []

    unsupported = facts[1]
    assert "loop" in [node["kind"] for node in unsupported["nodes"]]
    assert unsupported["warnings"] == ["unsupported_dynamic_branch_condition"]
    assert any(edge["kind"] == "loop_body" for edge in unsupported["edges"])
    assert any(edge["kind"] == "loop_exit" for edge in unsupported["edges"])


def test_semantic_inspect_returns_loop_break_continue_and_exit_cfg(tmp_path):
    secret_source = "loop-exit-source-must-not-leak"
    (tmp_path / "app.py").write_text(
        "def loops(items):\n"
        "    for item in items:\n"
        "        if item.skip:\n"
        "            continue\n"
        "        if item.stop:\n"
        "            break\n"
        "    while items:\n"
        "        raise RuntimeError('hidden')\n"
        f"    return {secret_source!r}\n",
        encoding="utf-8",
    )
    index_repository(tmp_path, experimental_semantic_artifact=True)

    result = runner.invoke(
        app,
        ["semantic-inspect", "app.py", "--repo-path", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    fact = envelope["data"]["facts"]["control_flow"][0]
    node_kinds = [node["kind"] for node in fact["nodes"]]
    assert node_kinds == [
        "entry",
        "loop",
        "branch",
        "continue",
        "branch",
        "break",
        "loop",
        "raise",
        "return",
        "exit",
    ]
    assert {edge["kind"] for edge in fact["edges"]} == {
        "continue_loop",
        "false_branch",
        "loop_body",
        "loop_exit",
        "next",
        "true_branch",
    }
    assert fact["warnings"] == []
    assert envelope["data"]["limits"] == {"fact_set": "python_branch_cfg", "source_snippets": 0}
    assert all("line_range" in node for node in fact["nodes"])
    assert all(node["confidence"] == "candidate" for node in fact["nodes"])
    assert all(node["provenance"]["source"] == "python_ast" for node in fact["nodes"])
    assert secret_source not in result.output
    assert "item.skip" not in result.output
    assert "RuntimeError" not in result.output
    assert str(tmp_path) not in result.output


def test_semantic_inspect_marks_limited_and_unsupported_cfg_constructs(tmp_path):
    (tmp_path / "app.py").write_text(
        "async def async_run(items):\n"
        "    async for item in items:\n"
        "        await item.run()\n"
        "    return 1\n"
        "\n"
        "def uncertain(value):\n"
        "    try:\n"
        "        with value:\n"
        "            return 1\n"
        "    except ValueError:\n"
        "        return 2\n"
        "    match value:\n"
        "        case 3:\n"
        "            return 3\n"
        "\n"
        "def generator(items):\n"
        "    for item in items:\n"
        "        yield item\n",
        encoding="utf-8",
    )
    index_repository(tmp_path, experimental_semantic_artifact=True)

    result = runner.invoke(
        app,
        ["semantic-inspect", "app.py", "--repo-path", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    facts = json.loads(result.output)["data"]["facts"]["control_flow"]
    assert [fact["function"]["name"] for fact in facts] == [
        "async_run",
        "uncertain",
        "generator",
    ]
    assert facts[0]["warnings"] == [
        "unsupported_async_function",
        "unsupported_statement:AsyncFor",
    ]
    assert facts[1]["warnings"] == ["unsupported_statement:Match", "unsupported_statement:Try"]
    assert facts[2]["warnings"] == ["unsupported_statement:Expr"]
    assert all(any(node["kind"] == "unsupported" for node in fact["nodes"]) for fact in facts)


def _canonical_graph_hash(root) -> str:
    with sqlite3.connect(root / ".repolens" / "graph.sqlite") as connection:
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'canonical_graph_hash'"
        ).fetchone()
    assert row is not None
    return str(row[0])
