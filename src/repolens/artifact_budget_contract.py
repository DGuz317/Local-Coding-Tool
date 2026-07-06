"""Budget contract for AI-facing generated graph artifacts."""

from __future__ import annotations

GRAPH_INDEX_BUDGET_REASON_SECTION_ROWS = "section_row_budget"
GRAPH_INDEX_BUDGET_REASON_TOTAL_CHARS = "total_character_budget"

DEFAULT_GRAPH_INDEX_MAX_TOTAL_CHARS = 200_000
DEFAULT_GRAPH_INDEX_MAX_SECTION_ROWS = 100

GRAPH_INDEX_SECTION_BUDGETS = {
    "directories": 100,
    "files": 100,
    "documentation_files": 50,
    "markdown_headings": 50,
    "markdown_links": 50,
    "markdown_path_mentions": 50,
    "markdown_code_fences": 50,
    "documentation_tagged_comments": 50,
    "skills": 50,
    "python_modules": 100,
    "python_symbols": 100,
    "python_imports": 100,
    "python_packages": 100,
    "python_tagged_comments": 50,
    "python_calls": 100,
    "python_parse_errors": 50,
    "javascript_modules": 100,
    "javascript_symbols": 100,
    "javascript_imports": 100,
    "javascript_packages": 100,
    "javascript_exports": 100,
    "javascript_commonjs_assignments": 100,
    "javascript_call_chains": 50,
    "config_files": 50,
    "config_package_managers": 50,
    "config_packages": 100,
    "config_package_roots": 50,
    "config_workspaces": 50,
    "config_lockfiles": 50,
    "config_commands": 50,
    "config_entrypoints": 50,
    "config_parse_errors": 50,
    "relationship_candidates": 100,
    "skipped_paths": 50,
}

DEFAULT_GRAPH_INDEX_BUDGET = {
    "max_total_chars": DEFAULT_GRAPH_INDEX_MAX_TOTAL_CHARS,
    "max_section_rows": DEFAULT_GRAPH_INDEX_MAX_SECTION_ROWS,
    "section_budgets": GRAPH_INDEX_SECTION_BUDGETS,
}

GRAPH_INDEX_ORDERING_CONTRACT = {
    "sort_scope": "within_each_section",
    "must_be_deterministic": True,
    "must_not_depend_on": ("filesystem_iteration_order", "randomness", "wall_clock_time"),
    "stable_tie_breakers": (
        "repo_relative_posix_path",
        "qualified_name_or_label",
        "line_number",
        "stable_node_or_fact_id",
    ),
}


def graph_index_section_truncation(section: str, total: int) -> dict[str, object]:
    """Return the required truncation metadata for one graph-index section."""
    shown = min(total, GRAPH_INDEX_SECTION_BUDGETS[section])
    return {
        "shown": shown,
        "total": total,
        "truncated": shown < total,
        "reason": GRAPH_INDEX_BUDGET_REASON_SECTION_ROWS if shown < total else None,
    }
