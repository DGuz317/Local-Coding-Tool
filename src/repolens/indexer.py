"""Index command orchestration for RepoLens."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from repolens.graph import (
    FileChange,
    GraphArtifactsStatus,
    GraphExportError,
    GraphStoreError,
    SelectiveUpdatePlan,
    plan_selective_update,
)
from repolens.graph_store import (
    FULL_GRAPH_INDEX_PATH,
    GRAPH_EXPORT_PATHS,
    GRAPH_STORE_PATH,
    SqliteGraphStore,
)
from repolens.parser_backends import ParserBackendOption
from repolens.scanner import ARTIFACT_DIR_NAME, ScanError, ScanResult, scan_repository
from repolens.semantic_artifact import (
    SemanticArtifactError,
    write_semantic_artifact,
    write_semantic_debug_export,
)

SCAN_ARTIFACT_PATH = f"{ARTIFACT_DIR_NAME}/scan.json"
ARTIFACT_GITIGNORE_CONTENT = "*\n!.gitignore\n"
REPOSITORY_ROOT_MARKERS = ("pyproject.toml", "package.json")


class RepoLensIndexError(RuntimeError):
    """Raised when indexing cannot bootstrap artifacts safely."""


def discover_repository_root(start_path: Path | str) -> Path:
    """Discover a repository root from a root or one of its subdirectories."""
    try:
        start = Path(start_path).resolve(strict=True)
    except OSError as exc:
        raise RepoLensIndexError("analysis_root_not_found") from exc
    if not start.is_dir():
        start = start.parent

    candidates = (start, *start.parents)
    for candidate in candidates:
        if (candidate / ".git").exists():
            return candidate
    for candidate in candidates:
        if (candidate / ARTIFACT_DIR_NAME).is_dir():
            return candidate
    for candidate in candidates:
        if any((candidate / marker).is_file() for marker in REPOSITORY_ROOT_MARKERS):
            return candidate
    raise RepoLensIndexError("unsupported_repository_root")


@dataclass(frozen=True)
class IndexResult:
    """Result of a RepoLens index run."""

    root: Path
    scan: ScanResult
    artifact_dir: str = ARTIFACT_DIR_NAME
    scan_artifact: str = SCAN_ARTIFACT_PATH
    graph_store: str = GRAPH_STORE_PATH
    graph_exports: tuple[str, ...] = GRAPH_EXPORT_PATHS
    semantic_artifact: str | None = None
    semantic_debug_export: str | None = None
    warnings: tuple[str, ...] = ()

    def to_cli_data(self) -> dict[str, object]:
        scan_data = self.scan.to_artifact_dict()
        data = {
            "artifact_dir": self.artifact_dir,
            "counts": scan_data["counts"],
            "eligible_files": scan_data["files"],
            "graph_exports": list(self.graph_exports),
            "graph_store": self.graph_store,
            "repo_path": str(self.root),
            "scan_artifact": self.scan_artifact,
            "skipped_paths": scan_data["skipped_paths"],
        }
        if self.semantic_artifact is not None:
            data["semantic_artifact"] = self.semantic_artifact
            data["semantic_artifact_status"] = "experimental"
        if self.semantic_debug_export is not None:
            data["semantic_debug_export"] = self.semantic_debug_export
            data["semantic_debug_export_status"] = "experimental_debug_only"
        return data


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
    parser_backend: ParserBackendOption = "default",
    full_graph_index: bool = False,
    experimental_semantic_artifact: bool = False,
    experimental_semantic_jsonl: bool = False,
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
    graph_store = SqliteGraphStore(root)
    try:
        graph_store.rebuild(scan, file_changes=file_changes, parser_backend=parser_backend)
        graph_exports = GRAPH_EXPORT_PATHS
        warnings: tuple[str, ...] = ()
        if full_graph_index:
            full_index_path = graph_store.export_full_index()
            graph_exports = (*graph_exports, full_index_path)
            warnings = (
                f"Full graph index export may be large; RepoLens wrote {FULL_GRAPH_INDEX_PATH}.",
            )
        semantic_artifact = None
        semantic_debug_export = None
        if experimental_semantic_artifact:
            semantic_artifact = write_semantic_artifact(
                root,
                scan,
                parser_backend=parser_backend,
            )
        if experimental_semantic_jsonl:
            semantic_debug_export = write_semantic_debug_export(
                root,
                scan,
                parser_backend=parser_backend,
            )
    except (GraphStoreError, GraphExportError, SemanticArtifactError) as exc:
        raise RepoLensIndexError(str(exc)) from exc
    return IndexResult(
        root=root,
        scan=scan,
        graph_exports=graph_exports,
        semantic_artifact=semantic_artifact,
        semantic_debug_export=semantic_debug_export,
        warnings=warnings,
    )


def update_repository(
    repo_path: Path | str,
    *,
    parser_backend: ParserBackendOption = "default",
    experimental_semantic_artifact: bool = False,
    experimental_semantic_jsonl: bool = False,
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

    graph_store = SqliteGraphStore(root)
    previous_status = graph_store.inspect()
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
            graph_store.replace_selectively(
                scan,
                plan,
                file_changes=changes,
                parser_backend=parser_backend,
            )
            mode = "selective"
        else:
            graph_store.rebuild(scan, file_changes=changes, parser_backend=parser_backend)
            mode = "initialized" if initialized else "full_rebuild"
        semantic_artifact = None
        semantic_debug_export = None
        if experimental_semantic_artifact:
            semantic_artifact = write_semantic_artifact(
                root,
                scan,
                parser_backend=parser_backend,
            )
        if experimental_semantic_jsonl:
            semantic_debug_export = write_semantic_debug_export(
                root,
                scan,
                parser_backend=parser_backend,
            )
    except (GraphStoreError, GraphExportError, SemanticArtifactError) as exc:
        raise RepoLensIndexError(str(exc)) from exc

    index = IndexResult(
        root=root,
        scan=scan,
        semantic_artifact=semantic_artifact,
        semantic_debug_export=semantic_debug_export,
    )
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
