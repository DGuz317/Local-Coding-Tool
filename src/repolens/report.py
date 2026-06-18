"""Graph report access for RepoLens CLI commands."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from repolens.graph import GraphExportError, export_graph_artifacts
from repolens.scanner import ARTIFACT_DIR_NAME

GRAPH_REPORT_PATH = f"{ARTIFACT_DIR_NAME}/graph-report.md"


class RepoLensReportError(RuntimeError):
    """Raised when a graph report cannot be read safely."""


@dataclass(frozen=True)
class GraphReportResult:
    """Text and metadata for a graph report read."""

    root: Path
    report_path: str
    text: str
    regenerated: bool


def read_graph_report(repo_path: Path | str, *, regenerate: bool = False) -> GraphReportResult:
    """Read the existing graph report, optionally regenerating exports from the store first."""
    root = _resolve_root(repo_path)
    artifact_dir = root / ARTIFACT_DIR_NAME
    report_path = root / GRAPH_REPORT_PATH

    if artifact_dir.is_symlink():
        raise RepoLensReportError("artifact_dir_is_symlink")

    if regenerate:
        try:
            export_graph_artifacts(root)
        except GraphExportError as exc:
            raise RepoLensReportError(str(exc) or "graph_report_regeneration_failed") from exc

    if report_path.is_symlink():
        raise RepoLensReportError("graph_report_is_symlink")
    if not report_path.is_file():
        raise RepoLensReportError("graph_report_missing")

    try:
        text = report_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise RepoLensReportError("graph_report_read_failed") from exc

    return GraphReportResult(
        root=root,
        report_path=GRAPH_REPORT_PATH,
        text=text,
        regenerated=regenerate,
    )


def _resolve_root(repo_path: Path | str) -> Path:
    try:
        root = Path(repo_path).resolve(strict=True)
    except OSError as exc:
        raise RepoLensReportError("analysis_root_not_found") from exc

    if not root.is_dir():
        raise RepoLensReportError("analysis_root_not_directory")
    if ARTIFACT_DIR_NAME in root.parts:
        raise RepoLensReportError("analysis_root_is_repolens_artifact_dir")
    return root
