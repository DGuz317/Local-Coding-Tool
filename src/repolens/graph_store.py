"""Internal graph store seam for RepoLens graph lifecycle and read queries."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Protocol

from repolens.graph import (
    FULL_GRAPH_INDEX_PATH,
    GRAPH_EXPORT_PATHS,
    GRAPH_SCHEMA_VERSION,
    GRAPH_STORE_PATH,
    REQUIRED_GRAPH_ARTIFACTS,
    FileChange,
    GraphArtifactsStatus,
    SelectiveUpdatePlan,
    export_full_graph_index,
    export_graph_artifacts,
    inspect_graph_artifacts,
    rebuild_graph_artifacts,
    replace_graph_artifacts_selectively,
)
from repolens.parser_backends import ParserBackendOption
from repolens.scanner import ScanResult


class GraphStore(Protocol):
    """Narrow high-level boundary for graph artifact lifecycle and SQLite reads.

    ``.repolens/graph.sqlite`` remains the complete graph artifact contract; this
    seam exists so callers depend on lifecycle/query entry points instead of
    scattering artifact-path and connection logic.
    """

    root: Path
    graph_store_path: str
    graph_export_paths: tuple[str, ...]
    full_graph_index_path: str
    required_artifacts: tuple[str, ...]
    supported_schema_version: int

    def connect_readonly(self) -> sqlite3.Connection:
        """Open the authoritative SQLite graph artifact for read-only queries."""

    def missing_artifacts(self) -> tuple[str, ...]:
        """Return required graph artifacts that are absent."""

    def is_graph_store_symlink(self) -> bool:
        """Return whether the SQLite graph artifact is a symlink."""

    def inspect(self) -> GraphArtifactsStatus:
        """Inspect graph freshness without mutating artifacts."""

    def rebuild(
        self,
        scan: ScanResult,
        *,
        file_changes: tuple[FileChange, ...] = (),
        parser_backend: ParserBackendOption = "default",
    ) -> tuple[str, ...]:
        """Replace graph store and deterministic exports after a full rebuild."""

    def replace_selectively(
        self,
        scan: ScanResult,
        plan: SelectiveUpdatePlan,
        *,
        file_changes: tuple[FileChange, ...] = (),
        parser_backend: ParserBackendOption = "default",
    ) -> tuple[str, ...]:
        """Replace graph artifacts through the validated selective update path."""

    def export_artifacts(self) -> tuple[str, ...]:
        """Write deterministic graph exports from the SQLite graph artifact."""

    def export_full_index(self) -> str:
        """Write the explicit full graph index export."""


class SqliteGraphStore:
    """SQLite-backed GraphStore; the only concrete graph store for RepoLens."""

    graph_store_path = GRAPH_STORE_PATH
    graph_export_paths = GRAPH_EXPORT_PATHS
    full_graph_index_path = FULL_GRAPH_INDEX_PATH
    required_artifacts = REQUIRED_GRAPH_ARTIFACTS
    supported_schema_version = GRAPH_SCHEMA_VERSION

    def __init__(self, root: Path):
        self.root = root

    def connect_readonly(self) -> sqlite3.Connection:
        graph_store = self.root / self.graph_store_path
        connection = sqlite3.connect(f"file:{graph_store}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def missing_artifacts(self) -> tuple[str, ...]:
        return tuple(
            artifact for artifact in self.required_artifacts if not (self.root / artifact).exists()
        )

    def is_graph_store_symlink(self) -> bool:
        return (self.root / self.graph_store_path).is_symlink()

    def inspect(self) -> GraphArtifactsStatus:
        return inspect_graph_artifacts(self.root)

    def rebuild(
        self,
        scan: ScanResult,
        *,
        file_changes: tuple[FileChange, ...] = (),
        parser_backend: ParserBackendOption = "default",
    ) -> tuple[str, ...]:
        return rebuild_graph_artifacts(
            self.root,
            scan,
            file_changes=file_changes,
            parser_backend=parser_backend,
        )

    def replace_selectively(
        self,
        scan: ScanResult,
        plan: SelectiveUpdatePlan,
        *,
        file_changes: tuple[FileChange, ...] = (),
        parser_backend: ParserBackendOption = "default",
    ) -> tuple[str, ...]:
        return replace_graph_artifacts_selectively(
            self.root,
            scan,
            plan,
            file_changes=file_changes,
            parser_backend=parser_backend,
        )

    def export_artifacts(self) -> tuple[str, ...]:
        return export_graph_artifacts(self.root)

    def export_full_index(self) -> str:
        return export_full_graph_index(self.root)
