"""Command-line interface for RepoLens MCP."""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Annotated

import typer

from repolens.graph import inspect_graph_artifacts
from repolens.indexer import RepoLensIndexError, index_repository, update_repository
from repolens.report import RepoLensReportError, read_graph_report
from repolens.text_search import (
    SEARCH_DEFAULT_MAX_RESULTS,
    SEARCH_MAX_RESULTS_LIMIT,
    RepoLensSearchError,
    search_raw_text,
)

app = typer.Typer(help="RepoLens MCP repository intelligence CLI.")


@app.callback()
def main() -> None:
    """Run RepoLens MCP commands."""


@app.command()
def index(
    repo_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            resolve_path=True,
            help="Repository path to index.",
        ),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable JSON envelope."),
    ] = False,
) -> None:
    """Safely discover repository files and bootstrap RepoLens artifacts."""
    try:
        result = index_repository(repo_path)
    except RepoLensIndexError as exc:
        error = str(exc) or exc.__class__.__name__
        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "data": {},
                        "error": {"message": error},
                        "limits": {},
                        "ok": False,
                        "warnings": [],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            typer.echo(f"Index failed: {error}", err=True)
        raise typer.Exit(1) from exc

    data = result.to_cli_data()
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "data": data,
                    "limits": {"max_file_size_bytes": result.scan.max_file_size_bytes},
                    "ok": True,
                    "warnings": [],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    counts = data["counts"]
    if not isinstance(counts, dict):
        raise typer.Exit(1)
    typer.echo(f"Indexed repository: {result.root}")
    typer.echo(f"Eligible files: {counts['eligible_files']}")
    typer.echo(f"Skipped paths: {counts['skipped_paths']}")
    typer.echo(f"Artifact directory: {data['artifact_dir']}")
    typer.echo(f"Scan summary: {data['scan_artifact']}")
    typer.echo(f"Graph store: {data['graph_store']}")
    typer.echo("Graph exports:")
    graph_exports = data["graph_exports"]
    if not isinstance(graph_exports, list):
        raise typer.Exit(1)
    for graph_export in graph_exports:
        typer.echo(f"- {graph_export}")


@app.command()
def report(
    repo_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            resolve_path=True,
            help="Repository path whose graph report should be printed.",
        ),
    ],
    regenerate: Annotated[
        bool,
        typer.Option(
            "--regenerate",
            help="Regenerate graph exports from .repolens/graph.sqlite before printing.",
        ),
    ] = False,
) -> None:
    """Print the existing RepoLens graph report."""
    try:
        result = read_graph_report(repo_path, regenerate=regenerate)
    except RepoLensReportError as exc:
        error = str(exc) or exc.__class__.__name__
        typer.echo(f"Report failed: {error}", err=True)
        raise typer.Exit(1) from exc

    typer.echo(result.text, nl=False)


@app.command()
def update(
    repo_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            resolve_path=True,
            help="Repository path to update.",
        ),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable JSON envelope."),
    ] = False,
) -> None:
    """Update RepoLens artifacts using live file change classification."""
    try:
        result = update_repository(repo_path)
    except RepoLensIndexError as exc:
        error = str(exc) or exc.__class__.__name__
        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "data": {},
                        "error": {"message": error},
                        "limits": {},
                        "ok": False,
                        "warnings": [],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            typer.echo(f"Update failed: {error}", err=True)
        raise typer.Exit(1) from exc

    data = result.to_cli_data()
    warnings = list(result.previous_status.warnings)
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "data": data,
                    "limits": {"max_file_size_bytes": result.index.scan.max_file_size_bytes},
                    "ok": True,
                    "warnings": warnings,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    counts = data["counts"]
    if not isinstance(counts, dict):
        raise typer.Exit(1)
    if result.initialized:
        typer.echo(f"Initialized graph artifacts: {result.root}")
    else:
        typer.echo(f"Updated graph artifacts: {result.root}")
        _print_change_summary(result.previous_status.freshness or {})
    typer.echo(f"Eligible files: {counts['eligible_files']}")
    typer.echo(f"Skipped paths: {counts['skipped_paths']}")
    for warning in warnings:
        typer.echo(f"Warning: {warning}", err=True)


@app.command()
def search(
    repo_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            resolve_path=True,
            help="Repository path to search.",
        ),
    ],
    query: Annotated[str, typer.Argument(help="Non-empty raw text query.")],
    case_sensitive: Annotated[
        bool,
        typer.Option("--case-sensitive", help="Match query with case-sensitive comparison."),
    ] = False,
    max_results: Annotated[
        int,
        typer.Option(
            "--max-results",
            min=1,
            max=SEARCH_MAX_RESULTS_LIMIT,
            help="Maximum number of match previews to return.",
        ),
    ] = SEARCH_DEFAULT_MAX_RESULTS,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable JSON envelope."),
    ] = False,
) -> None:
    """Search eligible live files for raw text."""
    try:
        result = search_raw_text(
            repo_path,
            query,
            case_sensitive=case_sensitive,
            max_results=max_results,
        )
    except RepoLensSearchError as exc:
        error = str(exc) or exc.__class__.__name__
        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "data": {},
                        "error": {"message": error},
                        "limits": {"max_results": max_results},
                        "ok": False,
                        "warnings": [],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            typer.echo(f"Search failed: {error}", err=True)
        raise typer.Exit(1) from exc

    limits = {
        "max_file_size_bytes": result.scan.max_file_size_bytes,
        "max_results": result.max_results,
        "preview_chars": result.preview_chars,
    }
    warnings = list(result.warnings)
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "data": result.to_cli_data(),
                    "limits": limits,
                    "ok": True,
                    "warnings": warnings,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    typer.echo(
        f"Found {result.total_matches} matches for {json.dumps(result.query)} "
        f"(showing {len(result.matches)})."
    )
    if result.truncated:
        typer.echo(f"Results truncated at {result.max_results} matches.")
    for match in result.matches:
        truncated_marker = (
            " [preview truncated]"
            if match.preview_truncated_before or match.preview_truncated_after
            else ""
        )
        typer.echo(f"{match.path}:{match.line}:{match.column}: {match.preview}{truncated_marker}")
    for warning in warnings:
        typer.echo(f"Warning: {warning}", err=True)


@app.command()
def status(
    repo_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            resolve_path=True,
            help="Repository path to inspect.",
        ),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable JSON envelope."),
    ] = False,
) -> None:
    """Report whether RepoLens graph artifacts are available."""
    graph_status = inspect_graph_artifacts(repo_path)
    missing_artifacts = list(graph_status.missing_artifacts)
    recommended_action = f"repolens index {shlex.quote(str(repo_path))}"

    data: dict[str, object] = {
        "artifact_dir": ".repolens",
        "detected_schema_version": graph_status.detected_schema_version,
        "fresh": graph_status.fresh,
        "freshness": graph_status.freshness or {},
        "missing_artifacts": missing_artifacts,
        "reason": graph_status.reason,
        "recommended_action": recommended_action
        if graph_status.status in {"stale", "rebuild_required"}
        else None,
        "repo_path": str(repo_path),
        "status": graph_status.status,
        "supported_schema_version": graph_status.supported_schema_version,
    }
    warnings = list(graph_status.warnings)

    # Keep the missing-artifacts response compact and compatible with Issue #3 output.
    if graph_status.reason == "missing_graph_artifacts":
        data = {
            "artifact_dir": ".repolens",
            "fresh": False,
            "missing_artifacts": missing_artifacts,
            "reason": "missing_graph_artifacts",
            "recommended_action": recommended_action,
            "repo_path": str(repo_path),
            "status": "stale",
        }

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "data": data,
                    "limits": {},
                    "ok": True,
                    "warnings": warnings,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    typer.echo(f"Graph status: {data['status']}")
    typer.echo(f"Reason: {str(data['reason']).replace('_', ' ')}")
    if missing_artifacts:
        typer.echo("Missing artifacts:")
        for artifact in missing_artifacts:
            typer.echo(f"- {artifact}")
        typer.echo(f"Recommended action: {recommended_action}")
    elif graph_status.status == "rebuild_required":
        if graph_status.detected_schema_version is not None:
            typer.echo(f"Detected schema version: {graph_status.detected_schema_version}")
        typer.echo(f"Supported schema version: {graph_status.supported_schema_version}")
        typer.echo(f"Recommended action: {recommended_action}")
        _print_change_summary(graph_status.freshness or {})
    else:
        if graph_status.fresh:
            typer.echo("Graph artifacts are fresh.")
        else:
            typer.echo(f"Recommended action: {recommended_action}")
        _print_change_summary(graph_status.freshness or {})
    for warning in warnings:
        typer.echo(f"Warning: {warning}", err=True)


def _print_change_summary(freshness: dict[str, object]) -> None:
    change_counts = freshness.get("change_counts")
    if isinstance(change_counts, dict):
        typer.echo("Change summary:")
        for change_type in (
            "deleted",
            "new",
            "parse_error",
            "dependency_change",
            "structural_change",
            "content_only_change",
        ):
            count = change_counts.get(change_type, 0)
            if count:
                typer.echo(f"- {change_type.replace('_', ' ')}: {count}")
    changed_files = freshness.get("changed_files")
    if isinstance(changed_files, list) and changed_files:
        typer.echo("Changed files:")
        for changed_file in changed_files[:10]:
            if isinstance(changed_file, dict):
                typer.echo(f"- {changed_file.get('path')}: {changed_file.get('change_type')}")
