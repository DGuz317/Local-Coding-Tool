from __future__ import annotations

from pathlib import Path

from repolens.artifact_budget_contract import (
    DEFAULT_GRAPH_INDEX_BUDGET,
    DEFAULT_GRAPH_INDEX_MAX_SECTION_ROWS,
    DEFAULT_GRAPH_INDEX_MAX_TOTAL_CHARS,
    GRAPH_INDEX_ORDERING_CONTRACT,
    GRAPH_INDEX_SECTION_BUDGETS,
    graph_index_section_truncation,
)

ROOT = Path(__file__).resolve().parents[1]


def test_graph_index_budget_contract_has_default_caps() -> None:
    assert DEFAULT_GRAPH_INDEX_BUDGET["max_total_chars"] == 200_000
    assert DEFAULT_GRAPH_INDEX_BUDGET["max_section_rows"] == 100
    assert DEFAULT_GRAPH_INDEX_BUDGET["section_budgets"] == GRAPH_INDEX_SECTION_BUDGETS

    assert DEFAULT_GRAPH_INDEX_MAX_TOTAL_CHARS > 0
    assert DEFAULT_GRAPH_INDEX_MAX_SECTION_ROWS > 0
    assert GRAPH_INDEX_SECTION_BUDGETS
    assert all(cap > 0 for cap in GRAPH_INDEX_SECTION_BUDGETS.values())
    assert all(
        cap <= DEFAULT_GRAPH_INDEX_MAX_SECTION_ROWS for cap in GRAPH_INDEX_SECTION_BUDGETS.values()
    )


def test_graph_index_section_truncation_reports_shown_total_and_reason() -> None:
    cap = GRAPH_INDEX_SECTION_BUDGETS["python_symbols"]

    truncated = graph_index_section_truncation("python_symbols", cap + 25)
    untruncated = graph_index_section_truncation("python_symbols", cap)

    assert truncated == {
        "shown": cap,
        "total": cap + 25,
        "truncated": True,
        "reason": "section_row_budget",
    }
    assert untruncated == {
        "shown": cap,
        "total": cap,
        "truncated": False,
        "reason": None,
    }


def test_graph_index_budget_contract_defines_deterministic_ordering() -> None:
    assert GRAPH_INDEX_ORDERING_CONTRACT["must_be_deterministic"] is True
    assert "randomness" in GRAPH_INDEX_ORDERING_CONTRACT["must_not_depend_on"]
    assert "repo_relative_posix_path" in GRAPH_INDEX_ORDERING_CONTRACT["stable_tie_breakers"]


def test_graph_index_budget_contract_documents_navigation_view_and_full_source() -> None:
    contract = (ROOT / "docs" / "artifact-budget-contract.md").read_text(encoding="utf-8")
    release_plan = (ROOT / "docs" / "repolens-v0.3.1-issue-plan.md").read_text(encoding="utf-8")

    assert "SQLite remains the full graph source of truth" in contract
    assert "navigation view" in contract
    assert "not full graph dumps" in contract
    assert "shown" in contract
    assert "total" in contract
    assert "reason" in contract
    assert "truncation metadata" in contract
    assert "SQLite" in release_plan
