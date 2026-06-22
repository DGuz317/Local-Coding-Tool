"""Index command orchestration for RepoLens."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from repolens.graph import (
    GRAPH_EXPORT_PATHS,
    GRAPH_STORE_PATH,
    FileChange,
    GraphArtifactsStatus,
    GraphExportError,
    GraphStoreError,
    SelectiveUpdatePlan,
    inspect_graph_artifacts,
    plan_selective_update,
    rebuild_graph_artifacts,
    replace_graph_artifacts_selectively,
)
from repolens.parser_backends import ParserBackendOption
from repolens.scanner import ARTIFACT_DIR_NAME, ScanError, ScanResult, scan_repository

SCAN_ARTIFACT_PATH = f"{ARTIFACT_DIR_NAME}/scan.json"
ARTIFACT_GITIGNORE_CONTENT = "*\n!.gitignore\n"


class RepoLensIndexError(RuntimeError):
    """Raised when indexing cannot bootstrap artifacts safely."""


@dataclass(frozen=True)
class IndexResult:
    """Result of a RepoLens index run."""

    root: Path
    scan: ScanResult
    artifact_dir: str = ARTIFACT_DIR_NAME
    scan_artifact: str = SCAN_ARTIFACT_PATH
    graph_store: str = GRAPH_STORE_PATH
    graph_exports: tuple[str, ...] = GRAPH_EXPORT_PATHS

    def to_cli_data(self) -> dict[str, object]:
        scan_data = self.scan.to_artifact_dict()
        return {
            "artifact_dir": self.artifact_dir,
            "counts": scan_data["counts"],
            "eligible_files": scan_data["files"],
            "graph_exports": list(self.graph_exports),
            "graph_store": self.graph_store,
            "repo_path": str(self.root),
            "scan_artifact": self.scan_artifact,
            "skipped_paths": scan_data["skipped_paths"],
        }


@dataclass(frozen=True)
class UpdateResult:
    """Result of a RepoLens update run."""

    root: Path
    index: IndexResult
    previous_status: GraphArtifactsStatus
    mode: str
    initialized: bool
    plan: SelectiveUpdatePlan | None = None

    def to_cli_data(self) -> dict[str, object]:
        data = self.index.to_cli_data()
        data["freshness"] = self.previous_status.freshness or {}
        data["initialized"] = self.initialized
        data["mode"] = self.mode
        if self.plan is not None:
            data["selective_update"] = self.plan.to_cli_data()
        data["previous_reason"] = self.previous_status.reason
        data["previous_status"] = self.previous_status.status
        return data


def index_repository(
    repo_path: Path | str,
    *,
    file_changes: tuple[FileChange, ...] = (),
    parser_backend: ParserBackendOption = "stable",
) -> IndexResult:
    """Run the safe discovery index path for ``repo_path`` and write bootstrap artifacts."""
    try:
        root = Path(repo_path).resolve(strict=True)
    except OSError as exc:
        raise RepoLensIndexError("analysis_root_not_found") from exc

    if not root.is_dir():
        raise RepoLensIndexError("analysis_root_not_directory")
    if ARTIFACT_DIR_NAME in root.parts:
        raise RepoLensIndexError("analysis_root_is_repolens_artifact_dir")

    _bootstrap_artifact_dir(root)
    try:
        scan = scan_repository(root)
    except ScanError as exc:
        raise RepoLensIndexError(str(exc)) from exc
    _write_scan_artifact(root, scan)
    try:
        rebuild_graph_artifacts(
            root, scan, file_changes=file_changes, parser_backend=parser_backend
        )
    except (GraphStoreError, GraphExportError) as exc:
        raise RepoLensIndexError(str(exc)) from exc
    return IndexResult(root=root, scan=scan)


def update_repository(
    repo_path: Path | str,
    *,
    parser_backend: ParserBackendOption = "stable",
) -> UpdateResult:
    """Update an existing graph, or initialize one when artifacts are missing."""
    try:
        root = Path(repo_path).resolve(strict=True)
    except OSError as exc:
        raise RepoLensIndexError("analysis_root_not_found") from exc

    if not root.is_dir():
        raise RepoLensIndexError("analysis_root_not_directory")
    if ARTIFACT_DIR_NAME in root.parts:
        raise RepoLensIndexError("analysis_root_is_repolens_artifact_dir")

    previous_status = inspect_graph_artifacts(root)
    initialized = previous_status.reason == "missing_graph_artifacts"
    _bootstrap_artifact_dir(root)
    try:
        scan = scan_repository(root)
    except ScanError as exc:
        raise RepoLensIndexError(str(exc)) from exc
    _write_scan_artifact(root, scan)

    plan = plan_selective_update(previous_status, scan)
    changes = () if initialized else previous_status.file_changes
    try:
        if plan.safe:
            replace_graph_artifacts_selectively(
                root,
                scan,
                plan,
                file_changes=changes,
                parser_backend=parser_backend,
            )
            mode = "selective"
        else:
            rebuild_graph_artifacts(root, scan, file_changes=changes, parser_backend=parser_backend)
            mode = "initialized" if initialized else "full_rebuild"
    except (GraphStoreError, GraphExportError) as exc:
        raise RepoLensIndexError(str(exc)) from exc

    index = IndexResult(root=root, scan=scan)
    return UpdateResult(
        root=root,
        index=index,
        previous_status=previous_status,
        mode=mode,
        initialized=initialized,
        plan=plan,
    )


def _bootstrap_artifact_dir(root: Path) -> None:
    artifact_dir = root / ARTIFACT_DIR_NAME
    if artifact_dir.is_symlink():
        raise RepoLensIndexError("artifact_dir_is_symlink")
    if artifact_dir.exists() and not artifact_dir.is_dir():
        raise RepoLensIndexError("artifact_dir_not_directory")

    try:
        artifact_dir.mkdir(exist_ok=True)
    except OSError as exc:
        raise RepoLensIndexError("artifact_dir_create_failed") from exc

    artifact_gitignore = artifact_dir / ".gitignore"
    if artifact_gitignore.is_symlink():
        raise RepoLensIndexError("artifact_gitignore_is_symlink")
    try:
        artifact_gitignore.write_text(ARTIFACT_GITIGNORE_CONTENT, encoding="utf-8")
    except OSError as exc:
        raise RepoLensIndexError("artifact_gitignore_write_failed") from exc


def _write_scan_artifact(root: Path, scan: ScanResult) -> None:
    artifact_dir = root / ARTIFACT_DIR_NAME
    target = root / SCAN_ARTIFACT_PATH
    payload = scan.to_artifact_dict()

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            delete=False,
            dir=str(artifact_dir),
            encoding="utf-8",
            prefix="scan-",
            suffix=".tmp",
        ) as temp_file:
            temp_path = Path(temp_file.name)
            json.dump(payload, temp_file, indent=2, sort_keys=True)
            temp_file.write("\n")
        os.replace(temp_path, target)
    except OSError as exc:
        raise RepoLensIndexError("scan_artifact_write_failed") from exc
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
