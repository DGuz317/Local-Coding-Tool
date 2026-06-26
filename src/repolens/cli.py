"""Command-line interface for RepoLens MCP."""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Annotated

import typer

from repolens.benchmark import RepoLensBenchmarkError, run_update_benchmark
from repolens.context_evaluation import human_context_evaluation, run_context_evaluation
from repolens.context_pack import get_task_context, human_context_pack
from repolens.graph import inspect_graph_artifacts
from repolens.indexer import RepoLensIndexError, index_repository, update_repository
from repolens.mcp_server import run_mcp_server
from repolens.query import QUERY_DEFAULT_LIMIT, QUERY_MAX_LIMIT, GraphQueryService
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
    parser_backend: Annotated[
        str,
        typer.Option(
            "--parser-backend",
            help="Parser backend to use: stable or experimental.",
        ),
    ] = "stable",
    full_index: Annotated[
        bool,
        typer.Option(
            "--full-index",
            help="Also write .repolens/graph-index-full.md; this may be large.",
        ),
    ] = False,
) -> None:
    """Safely discover repository files and bootstrap RepoLens artifacts."""
    try:
        result = index_repository(
            repo_path, parser_backend=parser_backend, full_graph_index=full_index
        )
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
                    "warnings": list(result.warnings),
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
    for warning in result.warnings:
        typer.echo(f"Warning: {warning}", err=True)


@app.command()
def benchmark_update(
    fixture_path: Annotated[
        Path | None,
        typer.Option(
            "--fixture-path",
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
            help="Empty directory where the generated benchmark fixture should be created.",
        ),
    ] = None,
    file_count: Annotated[
        int,
        typer.Option("--file-count", min=1, help="Number of generated Python modules."),
    ] = 200,
    changed_file_count: Annotated[
        int,
        typer.Option(
            "--changed-file-count", min=1, help="Number of modules changed before update."
        ),
    ] = 1,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable JSON envelope."),
    ] = False,
) -> None:
    """Generate a fixture and report relative update speedup evidence."""
    try:
        result = run_update_benchmark(
            fixture_path=fixture_path,
            file_count=file_count,
            changed_file_count=changed_file_count,
        )
    except (RepoLensBenchmarkError, RepoLensIndexError) as exc:
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
            typer.echo(f"Benchmark failed: {error}", err=True)
        raise typer.Exit(1) from exc

    data = result.to_cli_data()
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "data": data,
                    "limits": {"fixed_wall_clock_claim": False},
                    "ok": True,
                    "warnings": [],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    speedup = data["relative_speedup"]
    if not isinstance(speedup, dict):
        raise typer.Exit(1)
    factor = speedup.get("factor")
    factor_text = "unavailable" if factor is None else f"{factor:.2f}x"
    typer.echo("RepoLens update benchmark")
    typer.echo(f"Fixture path: {data['fixture_path']}")
    typer.echo(f"Generated files: {data['file_count']}")
    typer.echo(f"Changed files: {data['changed_file_count']}")
    typer.echo(f"Selective update seconds: {data['selective_update_seconds']:.6f}")
    typer.echo(f"Full rebuild seconds: {data['full_rebuild_seconds']:.6f}")
    typer.echo(f"Relative speedup evidence: {factor_text}")
    typer.echo("No fixed wall-clock claim is made.")


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
    parser_backend: Annotated[
        str,
        typer.Option(
            "--parser-backend",
            help="Parser backend to use: stable or experimental.",
        ),
    ] = "stable",
) -> None:
    """Update RepoLens artifacts using live file change classification."""
    try:
        result = update_repository(repo_path, parser_backend=parser_backend)
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


@app.command("search-graph")
def search_graph(
    repo_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            resolve_path=True,
            help="Repository path whose graph metadata should be searched.",
        ),
    ],
    query: Annotated[str, typer.Argument(help="Non-empty graph metadata query.")],
    kind: Annotated[
        str,
        typer.Option(
            "--kind",
            help="Metadata kind to search: all, symbol, file, or command.",
        ),
    ] = "all",
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            min=1,
            max=QUERY_MAX_LIMIT,
            help="Maximum number of graph matches to return.",
        ),
    ] = QUERY_DEFAULT_LIMIT,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable JSON envelope."),
    ] = False,
) -> None:
    """Search existing graph metadata without reading repository source files."""
    envelope = GraphQueryService(repo_path).search_graph(query, kind=kind, max_results=limit)
    if json_output:
        typer.echo(json.dumps(envelope, indent=2, sort_keys=True))
        if not envelope.get("ok", False):
            raise typer.Exit(1)
        return

    if not envelope.get("ok", False):
        error = envelope.get("error", {})
        message = error.get("message") if isinstance(error, dict) else None
        typer.echo(f"Graph search failed: {message or 'unknown error'}", err=True)
        raise typer.Exit(1)

    data = envelope["data"]
    pagination = envelope.get("pagination", {})
    matches = data.get("matches", []) if isinstance(data, dict) else []
    total = data.get("total_matches", 0) if isinstance(data, dict) else 0
    returned = (
        pagination.get("returned", len(matches)) if isinstance(pagination, dict) else len(matches)
    )
    typer.echo(
        f"Found {total} graph matches for {json.dumps(query)} "
        f"in {data.get('kind', 'all')} metadata (showing {returned})."
    )
    if isinstance(pagination, dict) and pagination.get("truncated"):
        typer.echo(f"Results truncated at {pagination.get('limit', limit)} matches.")
    if data.get("no_match"):
        typer.echo("No graph metadata matches found.")
    for match in matches:
        node = match.get("node", {}) if isinstance(match, dict) else {}
        node_id = node.get("id", "")
        node_kind = node.get("kind", "")
        label = node.get("label", "")
        path = node.get("path") or ""
        typer.echo(f"{node_kind}: {label} ({node_id}) {path}".rstrip())
    for warning in envelope.get("warnings", []):
        typer.echo(f"Warning: {warning}", err=True)


@app.command()
def context(
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
    task: Annotated[str, typer.Argument(help="Natural-language task to orient around.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable JSON envelope."),
    ] = False,
) -> None:
    """Return a deterministic, bounded Context Pack for a task."""
    envelope = get_task_context(repo_path, task)
    if json_output:
        typer.echo(json.dumps(envelope, indent=2, sort_keys=True))
        if not envelope.get("ok", False):
            raise typer.Exit(1)
        return

    typer.echo(human_context_pack(envelope), nl=False)
    if not envelope.get("ok", False):
        raise typer.Exit(1)


@app.command("evaluate-context")
def evaluate_context(
    manifest_path: Annotated[
        Path,
        typer.Option(
            "--manifest",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
            help="Context Pack Evaluation manifest to run.",
        ),
    ] = Path("tests/fixtures/context_pack/evaluation_manifest.json"),
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable JSON envelope."),
    ] = False,
) -> None:
    """Run local Context Pack Evaluation fixtures."""
    envelope = run_context_evaluation(manifest_path=manifest_path)
    if json_output:
        typer.echo(json.dumps(envelope, indent=2, sort_keys=True))
        if not envelope.get("ok", False) or not envelope["data"]["release_gate"]["passed"]:
            raise typer.Exit(1)
        return

    typer.echo(human_context_evaluation(envelope), nl=False)
    if not envelope.get("ok", False) or not envelope["data"]["release_gate"]["passed"]:
        raise typer.Exit(1)


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


@app.command()
def mcp(
    repo_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            resolve_path=True,
            help="Repository path to serve through read-only MCP tools.",
        ),
    ],
) -> None:
    """Start a read-only RepoLens stdio MCP server."""
    run_mcp_server(repo_path)


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
