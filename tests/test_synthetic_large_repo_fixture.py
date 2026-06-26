from __future__ import annotations

import sqlite3

from repolens.artifact_budget_contract import (
    DEFAULT_GRAPH_INDEX_MAX_TOTAL_CHARS,
    GRAPH_INDEX_SECTION_BUDGETS,
)
from repolens.indexer import index_repository
from synthetic_large_repo import generate_synthetic_large_repo


def test_synthetic_large_repo_generation_is_deterministic(tmp_path):
    first = generate_synthetic_large_repo(
        tmp_path / "first", python_module_count=4, javascript_module_count=4
    )
    second = generate_synthetic_large_repo(
        tmp_path / "second", python_module_count=4, javascript_module_count=4
    )

    assert _fixture_files(first) == _fixture_files(second)


def test_synthetic_large_repo_triggers_graph_index_truncation(tmp_path):
    python_count = GRAPH_INDEX_SECTION_BUDGETS["python_symbols"] + 1
    javascript_count = GRAPH_INDEX_SECTION_BUDGETS["javascript_symbols"] + 1
    fixture = generate_synthetic_large_repo(
        tmp_path / "fixture",
        python_module_count=python_count,
        javascript_module_count=javascript_count,
    )

    index_repository(fixture)

    graph_index_path = fixture / ".repolens" / "graph-index.md"
    graph_index = graph_index_path.read_text(encoding="utf-8")

    assert graph_index_path.stat().st_size <= DEFAULT_GRAPH_INDEX_MAX_TOTAL_CHARS
    assert (f"shown={GRAPH_INDEX_SECTION_BUDGETS['python_symbols']} total=") in graph_index
    assert "reason=section_row_budget" in graph_index
    assert "## JavaScript Symbols" in graph_index
    assert "        return 100" not in graph_index
    assert "  value(): number { return 100; }" not in graph_index
    assert "  return 100;" not in graph_index

    with sqlite3.connect(fixture / ".repolens" / "graph.sqlite") as connection:
        python_symbols = connection.execute("SELECT COUNT(*) FROM python_symbols").fetchone()[0]
        javascript_symbols = connection.execute(
            "SELECT COUNT(*) FROM javascript_symbols"
        ).fetchone()[0]

    assert python_symbols >= python_count * 2
    assert javascript_symbols >= javascript_count * 2


def test_synthetic_large_repo_index_runtime_smoke(tmp_path):
    fixture = generate_synthetic_large_repo(
        tmp_path / "fixture", python_module_count=8, javascript_module_count=8
    )

    result = index_repository(fixture)

    assert result.scan.to_artifact_dict()["counts"]["eligible_files"] > 20
    assert (fixture / ".repolens" / "graph.sqlite").is_file()
    with sqlite3.connect(fixture / ".repolens" / "graph.sqlite") as connection:
        python_symbols = connection.execute("SELECT COUNT(*) FROM python_symbols").fetchone()[0]
        javascript_symbols = connection.execute(
            "SELECT COUNT(*) FROM javascript_symbols"
        ).fetchone()[0]
    assert python_symbols >= 16
    assert javascript_symbols >= 16


def _fixture_files(root):
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
