"""Command-line interface for RepoLens MCP."""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Annotated

import typer

from repolens.graph import inspect_graph_artifacts
from repolens.indexer import RepoLensIndexError, index_repository

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
    else:
        typer.echo(
            "Graph artifacts are present, but live freshness checks are not implemented yet."
        )
