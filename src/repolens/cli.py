"""Command-line interface for RepoLens MCP."""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(help="RepoLens MCP repository intelligence CLI.")

REQUIRED_ARTIFACTS = (
    ".repolens/graph.sqlite",
    ".repolens/graph.json",
    ".repolens/graph-lite.json",
    ".repolens/graph-report.md",
    ".repolens/graph-index.md",
    ".repolens/graph-status.json",
)


@app.callback()
def main() -> None:
    """Run RepoLens MCP commands."""


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
    missing_artifacts = [
        artifact for artifact in REQUIRED_ARTIFACTS if not (repo_path / artifact).exists()
    ]
    recommended_action = f"repolens index {shlex.quote(str(repo_path))}"

    if missing_artifacts:
        data: dict[str, object] = {
            "artifact_dir": ".repolens",
            "fresh": False,
            "missing_artifacts": missing_artifacts,
            "reason": "missing_graph_artifacts",
            "recommended_action": recommended_action,
            "repo_path": str(repo_path),
            "status": "stale",
        }
        warnings = ["Graph artifacts are missing."]
    else:
        data = {
            "artifact_dir": ".repolens",
            "fresh": None,
            "missing_artifacts": [],
            "reason": "graph_artifacts_present",
            "recommended_action": None,
            "repo_path": str(repo_path),
            "status": "unknown",
        }
        warnings = ["Graph artifacts exist, but freshness checks are not implemented yet."]

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
    else:
        typer.echo("Graph artifacts are present, but freshness checks are not implemented yet.")
