"""Authoritative graph storage and deterministic exports for RepoLens."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from repolens.config_index import (
    CONFIG_EXTRACTOR_VERSION,
    ConfigIndex,
    config_file_node_id,
    extract_config_index,
)
from repolens.documentation_index import (
    DOCUMENTATION_EXTRACTOR_VERSION,
    DocumentationIndex,
    documentation_file_node_id,
    extract_documentation_index,
)
from repolens.javascript_index import (
    JAVASCRIPT_EXTRACTOR_VERSION,
    JAVASCRIPT_SOURCE_SUFFIXES,
    JavaScriptIndex,
    extract_javascript_index,
    javascript_module_node_id,
    javascript_package_node_id,
)
from repolens.python_index import (
    PYTHON_EXTRACTOR_VERSION,
    PythonImportFact,
    PythonIndex,
    PythonModuleFact,
    extract_python_index,
    python_package_node_id,
)
from repolens.scanner import (
    ARTIFACT_DIR_NAME,
    DEFAULT_MAX_FILE_SIZE_BYTES,
    ScanError,
    ScannedFile,
    ScanResult,
    scan_repository,
)

GRAPH_SCHEMA_NAME = "repolens_graph"
GRAPH_SCHEMA_VERSION = 10
GRAPH_ARTIFACT_VERSION = 1
GRAPH_EXPORTER_VERSION = (
    f"{PYTHON_EXTRACTOR_VERSION}+{JAVASCRIPT_EXTRACTOR_VERSION}+"
    f"{CONFIG_EXTRACTOR_VERSION}+{DOCUMENTATION_EXTRACTOR_VERSION}"
)

GRAPH_STORE_FILENAME = "graph.sqlite"
GRAPH_STORE_PATH = f"{ARTIFACT_DIR_NAME}/{GRAPH_STORE_FILENAME}"
GRAPH_EXPORT_FILENAMES = (
    "graph.json",
    "graph-lite.json",
    "graph-report.md",
    "graph-index.md",
    "graph-status.json",
)
GRAPH_EXPORT_PATHS = tuple(f"{ARTIFACT_DIR_NAME}/{name}" for name in GRAPH_EXPORT_FILENAMES)
REQUIRED_GRAPH_ARTIFACTS = (GRAPH_STORE_PATH, *GRAPH_EXPORT_PATHS)

REPOSITORY_ID = "repository:."
ROOT_DIRECTORY_PATH = "."
ROOT_DIRECTORY_ID = "directory:."

CHANGE_TYPES = (
    "deleted",
    "new",
    "parse_error",
    "dependency_change",
    "structural_change",
    "content_only_change",
    "no_change",
)
HASH_FIELDS = (
    "raw",
    "normalized",
    "graph",
    "dependency",
    "symbol",
    "line_range",
)
PARSER_ERROR_WARNING = "Parser errors detected in the live graph overlay."
MAX_EDGE_EVIDENCE_ITEMS = 20
CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


class GraphStoreError(RuntimeError):
    """Raised when the authoritative graph store cannot be rebuilt."""


class GraphExportError(RuntimeError):
    """Raised when graph exports cannot be written."""


class GraphValidationError(GraphStoreError):
    """Raised when hard graph invariants fail before artifact replacement."""


@dataclass(frozen=True)
class GraphArtifactsStatus:
    """Read-like graph artifact status for CLI and future query services."""

    status: str
    reason: str
    fresh: bool | None
    missing_artifacts: tuple[str, ...]
    warnings: tuple[str, ...]
    detected_schema_version: str | None = None
    supported_schema_version: int = GRAPH_SCHEMA_VERSION
    freshness: dict[str, Any] | None = None
    file_changes: tuple["FileChange", ...] = ()


@dataclass(frozen=True)
class FileState:
    """A stored or live fingerprint for one scanner-approved file."""

    path: str
    size_bytes: int
    mtime_ns: int
    raw_hash: str
    normalized_hash: str
    graph_hash: str
    dependency_hash: str
    symbol_hash: str
    line_range_hash: str
    language: str
    parser_status: str
    indexed_at_utc: str

    def hash_payload(self, other: "FileState | None") -> dict[str, dict[str, str | None]]:
        """Return old/current hash details for status payloads."""
        return {
            "raw": {"old": self.raw_hash, "current": other.raw_hash if other else None},
            "normalized": {
                "old": self.normalized_hash,
                "current": other.normalized_hash if other else None,
            },
            "graph": {"old": self.graph_hash, "current": other.graph_hash if other else None},
            "dependency": {
                "old": self.dependency_hash,
                "current": other.dependency_hash if other else None,
            },
            "symbol": {"old": self.symbol_hash, "current": other.symbol_hash if other else None},
            "line_range": {
                "old": self.line_range_hash,
                "current": other.line_range_hash if other else None,
            },
        }

    def current_hash_payload(self) -> dict[str, dict[str, str | None]]:
        """Return a new-file hash payload using current values only."""
        return {
            "raw": {"old": None, "current": self.raw_hash},
            "normalized": {"old": None, "current": self.normalized_hash},
            "graph": {"old": None, "current": self.graph_hash},
            "dependency": {"old": None, "current": self.dependency_hash},
            "symbol": {"old": None, "current": self.symbol_hash},
            "line_range": {"old": None, "current": self.line_range_hash},
        }


@dataclass(frozen=True)
class FileChange:
    """Path-based latest change classification for one file."""

    path: str
    change_type: str
    secondary_signals: dict[str, bool]
    hashes: dict[str, dict[str, str | None]]
    parser_status: dict[str, str | None]
    size_bytes: dict[str, int | None]
    language: dict[str, str | None]

    @property
    def changed(self) -> bool:
        return self.change_type != "no_change"

    def to_status_dict(self) -> dict[str, object]:
        return {
            "change_type": self.change_type,
            "hashes": self.hashes,
            "language": self.language,
            "parser_status": self.parser_status,
            "path": self.path,
            "secondary_signals": self.secondary_signals,
            "size_bytes": self.size_bytes,
        }

    def to_changed_file_dict(self) -> dict[str, object]:
        return {
            "change_type": self.change_type,
            "path": self.path,
            "secondary_signals": self.secondary_signals,
        }


@dataclass(frozen=True)
class _ExtractedIndexes:
    python: PythonIndex
    javascript: JavaScriptIndex
    config: ConfigIndex
    documentation: DocumentationIndex
    parser_status_by_path: dict[str, str]


@dataclass(frozen=True)
class _GraphSignature:
    graph_hash: str
    dependency_hash: str
    symbol_hash: str
    line_range_hash: str


@dataclass(frozen=True)
class _GitMetadata:
    detected: bool
    branch: str | None
    commit: str | None

    def to_payload(self) -> dict[str, object]:
        return {"branch": self.branch, "commit": self.commit, "detected": self.detected}


@dataclass(frozen=True)
class _EdgeFact:
    source_id: str
    target_id: str
    kind: str
    metadata: dict[str, Any]
    confidence: str
    resolution_strategy: str
    evidence: list[dict[str, Any]]


def rebuild_graph_artifacts(
    root: Path,
    scan: ScanResult,
    *,
    file_changes: tuple[FileChange, ...] = (),
) -> tuple[str, ...]:
    """Rebuild the graph store and exports from one safe discovery result."""
    build_graph_store(root, scan, file_changes=file_changes)
    return export_graph_artifacts(root)


def build_graph_store(
    root: Path,
    scan: ScanResult,
    *,
    file_changes: tuple[FileChange, ...] = (),
) -> Path:
    """Build ``graph.sqlite`` in a temporary file and replace it after success."""
    artifact_dir = root / ARTIFACT_DIR_NAME
    target = root / GRAPH_STORE_PATH
    temp_path: Path | None = None

    try:
        artifact_dir.mkdir(exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "wb",
            delete=False,
            dir=str(artifact_dir),
            prefix="graph-",
            suffix=".sqlite.tmp",
        ) as temp_file:
            temp_path = Path(temp_file.name)

        with sqlite3.connect(temp_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.row_factory = sqlite3.Row
            _create_schema(connection)
            _populate_store(
                connection,
                root,
                scan,
                indexed_at_utc=_utc_now(),
                file_changes=file_changes,
            )
            _finalize_graph_metadata(connection)
            validation = _validate_graph_store(connection)
            if validation["hard_failures"]:
                raise GraphValidationError("graph_validation_failed")
            connection.commit()
            _ensure_supported_schema(connection)

        os.replace(temp_path, target)
    except GraphValidationError:
        raise
    except (OSError, sqlite3.Error) as exc:
        raise GraphStoreError("graph_store_rebuild_failed") from exc
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass

    return target


def export_graph_artifacts(root: Path) -> tuple[str, ...]:
    """Write deterministic graph exports through temporary files."""
    artifact_dir = root / ARTIFACT_DIR_NAME
    try:
        snapshot = _load_snapshot(root)
        exports = {
            "graph.json": _json_text(_graph_json_payload(snapshot)),
            "graph-lite.json": _json_text(_graph_lite_payload(snapshot)),
            "graph-report.md": _graph_report_text(snapshot),
            "graph-index.md": _graph_index_text(snapshot),
            "graph-status.json": _json_text(_graph_status_payload(snapshot)),
        }
        for filename in GRAPH_EXPORT_FILENAMES:
            _atomic_write_text(artifact_dir / filename, exports[filename])
    except (OSError, sqlite3.Error, GraphStoreError) as exc:
        raise GraphExportError("graph_export_write_failed") from exc

    return GRAPH_EXPORT_PATHS


def inspect_graph_artifacts(root: Path) -> GraphArtifactsStatus:
    """Inspect graph artifacts without mutating the repository."""
    missing_artifacts = tuple(
        artifact for artifact in REQUIRED_GRAPH_ARTIFACTS if not (root / artifact).exists()
    )
    if missing_artifacts:
        return GraphArtifactsStatus(
            status="stale",
            reason="missing_graph_artifacts",
            fresh=False,
            missing_artifacts=missing_artifacts,
            warnings=("Graph artifacts are missing.",),
        )

    try:
        schema_version = _read_schema_version(root / GRAPH_STORE_PATH)
    except sqlite3.Error:
        return GraphArtifactsStatus(
            status="rebuild_required",
            reason="graph_schema_unreadable",
            fresh=False,
            missing_artifacts=(),
            warnings=("Graph schema metadata is unreadable. Rebuild required.",),
        )

    if schema_version != str(GRAPH_SCHEMA_VERSION):
        return GraphArtifactsStatus(
            status="rebuild_required",
            reason="unsupported_schema_version",
            fresh=False,
            missing_artifacts=(),
            warnings=("Graph schema version is unsupported. Rebuild required.",),
            detected_schema_version=schema_version,
        )

    try:
        stored_metadata, stored_file_states = _read_graph_freshness_inputs(root)
    except sqlite3.Error:
        return GraphArtifactsStatus(
            status="rebuild_required",
            reason="graph_freshness_unreadable",
            fresh=False,
            missing_artifacts=(),
            warnings=("Graph freshness metadata is unreadable. Rebuild required.",),
            detected_schema_version=schema_version,
            freshness=_rebuild_required_freshness(
                root,
                stored_metadata={},
                reason="graph_freshness_unreadable",
            ),
        )

    if stored_metadata.get("exporter_version") != GRAPH_EXPORTER_VERSION:
        return GraphArtifactsStatus(
            status="rebuild_required",
            reason="extractor_version_changed",
            fresh=False,
            missing_artifacts=(),
            warnings=("Extractor version changed. Rebuild required.",),
            detected_schema_version=schema_version,
            freshness=_rebuild_required_freshness(
                root,
                stored_metadata=stored_metadata,
                reason="extractor_version_changed",
            ),
        )

    current_config_hash = _effective_config_hash(DEFAULT_MAX_FILE_SIZE_BYTES)
    if stored_metadata.get("effective_config_hash") != current_config_hash:
        return GraphArtifactsStatus(
            status="rebuild_required",
            reason="effective_config_changed",
            fresh=False,
            missing_artifacts=(),
            warnings=("Effective RepoLens config changed. Rebuild required.",),
            detected_schema_version=schema_version,
            freshness=_rebuild_required_freshness(
                root,
                stored_metadata=stored_metadata,
                reason="effective_config_changed",
            ),
        )

    try:
        freshness, file_changes = _compute_live_freshness(
            root,
            stored_metadata=stored_metadata,
            stored_file_states=stored_file_states,
        )
    except ScanError:
        return GraphArtifactsStatus(
            status="rebuild_required",
            reason="live_scan_failed",
            fresh=False,
            missing_artifacts=(),
            warnings=("Live freshness scan failed. Rebuild required.",),
            detected_schema_version=schema_version,
            freshness=_rebuild_required_freshness(
                root,
                stored_metadata=stored_metadata,
                reason="live_scan_failed",
            ),
        )

    warnings = (*_metadata_quality_warnings(stored_metadata), *_freshness_warnings(file_changes))
    return GraphArtifactsStatus(
        status=str(freshness["status"]),
        reason=str(freshness["reason"]),
        fresh=bool(freshness["fresh"]),
        missing_artifacts=(),
        warnings=warnings,
        detected_schema_version=schema_version,
        freshness=freshness,
        file_changes=file_changes,
    )


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE repositories (
            id TEXT PRIMARY KEY,
            analysis_root TEXT NOT NULL,
            name TEXT NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE directories (
            path TEXT PRIMARY KEY,
            node_id TEXT NOT NULL UNIQUE,
            parent_path TEXT REFERENCES directories(path) ON DELETE CASCADE
        ) WITHOUT ROWID;

        CREATE TABLE files (
            path TEXT PRIMARY KEY,
            node_id TEXT NOT NULL UNIQUE,
            directory_path TEXT NOT NULL REFERENCES directories(path) ON DELETE CASCADE,
            size_bytes INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL,
            raw_hash TEXT NOT NULL,
            normalized_hash TEXT NOT NULL,
            graph_hash TEXT NOT NULL,
            dependency_hash TEXT NOT NULL,
            symbol_hash TEXT NOT NULL,
            line_range_hash TEXT NOT NULL,
            language TEXT NOT NULL,
            indexed_at_utc TEXT NOT NULL,
            parser_status TEXT NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE skipped_paths (
            path TEXT PRIMARY KEY,
            reason TEXT NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE nodes (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            path TEXT,
            label TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE edges (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            target_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            confidence TEXT NOT NULL,
            resolution_strategy TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE python_modules (
            path TEXT PRIMARY KEY REFERENCES files(path) ON DELETE CASCADE,
            node_id TEXT NOT NULL UNIQUE REFERENCES nodes(id) ON DELETE CASCADE,
            module_name TEXT NOT NULL,
            package_root TEXT,
            parser_status TEXT NOT NULL,
            docstring_summary TEXT
        ) WITHOUT ROWID;

        CREATE TABLE python_symbols (
            id TEXT PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
            path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            module_node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            parent_id TEXT REFERENCES python_symbols(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            qualified_name TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            docstring_summary TEXT,
            decorators_json TEXT NOT NULL,
            bases_json TEXT NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE python_imports (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            module_node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            module TEXT NOT NULL,
            imported_name TEXT,
            alias TEXT,
            root_name TEXT NOT NULL,
            classification TEXT NOT NULL,
            level INTEGER NOT NULL,
            line INTEGER NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE python_packages (
            id TEXT PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            classification TEXT NOT NULL,
            inferred INTEGER NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE python_tagged_comments (
            id TEXT PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
            path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            module_node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            attached_node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            tag TEXT NOT NULL,
            text TEXT NOT NULL,
            line INTEGER NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE python_parse_errors (
            id TEXT PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
            path TEXT NOT NULL UNIQUE REFERENCES files(path) ON DELETE CASCADE,
            module_node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            message TEXT NOT NULL,
            line INTEGER,
            column INTEGER
        ) WITHOUT ROWID;

        CREATE TABLE python_calls (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            caller_id TEXT NOT NULL REFERENCES python_symbols(id) ON DELETE CASCADE,
            callee_id TEXT NOT NULL REFERENCES python_symbols(id) ON DELETE CASCADE,
            callee_name TEXT NOT NULL,
            line INTEGER NOT NULL,
            confidence TEXT NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE javascript_modules (
            path TEXT PRIMARY KEY REFERENCES files(path) ON DELETE CASCADE,
            node_id TEXT NOT NULL UNIQUE REFERENCES nodes(id) ON DELETE CASCADE,
            module_name TEXT NOT NULL,
            extension TEXT NOT NULL,
            parser_status TEXT NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE javascript_symbols (
            id TEXT PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
            path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            module_node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            qualified_name TEXT NOT NULL,
            line INTEGER NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE javascript_imports (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            module_node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            specifier TEXT NOT NULL,
            root_name TEXT,
            classification TEXT NOT NULL,
            resolved_path TEXT,
            resolution_status TEXT NOT NULL,
            line INTEGER NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE javascript_packages (
            id TEXT PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            classification TEXT NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE javascript_exports (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            module_node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            exported_name TEXT NOT NULL,
            local_name TEXT,
            line INTEGER NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE javascript_commonjs_assignments (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            module_node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            exported_name TEXT NOT NULL,
            assigned_name TEXT,
            line INTEGER NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE config_files (
            path TEXT PRIMARY KEY REFERENCES files(path) ON DELETE CASCADE,
            node_id TEXT NOT NULL UNIQUE REFERENCES nodes(id) ON DELETE CASCADE,
            config_kind TEXT NOT NULL,
            format TEXT NOT NULL,
            parser_status TEXT NOT NULL,
            top_level_keys_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE config_package_managers (
            id TEXT PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            ecosystem TEXT NOT NULL,
            source_path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            evidence_kind TEXT NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE config_packages (
            id TEXT PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            ecosystem TEXT NOT NULL,
            classification TEXT NOT NULL,
            source_path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            dependency_type TEXT NOT NULL,
            version_constraint TEXT
        ) WITHOUT ROWID;

        CREATE TABLE config_package_roots (
            id TEXT PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            ecosystem TEXT NOT NULL,
            path TEXT NOT NULL REFERENCES directories(path) ON DELETE CASCADE,
            source_path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE
        ) WITHOUT ROWID;

        CREATE TABLE config_lockfiles (
            id TEXT PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
            path TEXT NOT NULL UNIQUE REFERENCES files(path) ON DELETE CASCADE,
            manager TEXT NOT NULL,
            format TEXT NOT NULL,
            ecosystem TEXT NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE config_commands (
            id TEXT PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
            path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            source TEXT NOT NULL,
            name TEXT NOT NULL,
            command TEXT NOT NULL,
            purpose TEXT NOT NULL,
            not_run INTEGER NOT NULL,
            auto_run_recommended INTEGER NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE config_entrypoints (
            id TEXT PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
            path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            target TEXT NOT NULL,
            evidence TEXT NOT NULL,
            line INTEGER
        ) WITHOUT ROWID;

        CREATE TABLE config_parse_errors (
            id TEXT PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
            path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            message TEXT NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE documentation_files (
            path TEXT PRIMARY KEY REFERENCES files(path) ON DELETE CASCADE,
            node_id TEXT NOT NULL UNIQUE REFERENCES nodes(id) ON DELETE CASCADE,
            doc_kind TEXT NOT NULL,
            importance TEXT NOT NULL,
            parser_status TEXT NOT NULL,
            title TEXT,
            intro TEXT
        ) WITHOUT ROWID;

        CREATE TABLE markdown_headings (
            id TEXT PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
            path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            document_node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            heading_id TEXT NOT NULL,
            level INTEGER NOT NULL,
            text TEXT NOT NULL,
            line INTEGER NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE markdown_links (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            document_node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            label TEXT NOT NULL,
            target_path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            target_fragment TEXT,
            line INTEGER NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE markdown_path_mentions (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            document_node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            mentioned_path TEXT NOT NULL,
            target_path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            line INTEGER NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE markdown_code_fences (
            id TEXT PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
            path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            document_node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            language TEXT,
            info_string TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER
        ) WITHOUT ROWID;

        CREATE TABLE documentation_tagged_comments (
            id TEXT PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
            path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            tag TEXT NOT NULL,
            text TEXT NOT NULL,
            line INTEGER NOT NULL,
            language TEXT NOT NULL,
            syntax TEXT NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE skills (
            id TEXT PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
            path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT
        ) WITHOUT ROWID;

        CREATE TABLE runs (
            id INTEGER PRIMARY KEY,
            indexed_at_utc TEXT NOT NULL,
            scan_policy_version INTEGER NOT NULL,
            extractor_version TEXT NOT NULL,
            max_file_size_bytes INTEGER NOT NULL,
            repository_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
            directory_count INTEGER NOT NULL,
            file_count INTEGER NOT NULL,
            skipped_path_count INTEGER NOT NULL,
            graph_schema_version INTEGER NOT NULL,
            status TEXT NOT NULL
        );

        CREATE TABLE file_changes (
            path TEXT PRIMARY KEY,
            change_type TEXT NOT NULL,
            secondary_signals_json TEXT NOT NULL,
            payload_json TEXT NOT NULL
        ) WITHOUT ROWID;
        """
    )


def _populate_store(
    connection: sqlite3.Connection,
    root: Path,
    scan: ScanResult,
    *,
    indexed_at_utc: str,
    file_changes: tuple[FileChange, ...],
) -> None:
    directories = _directory_facts(scan)
    files = tuple(sorted(scan.files, key=lambda scanned_file: scanned_file.path))
    skipped_paths = tuple(sorted(scan.skipped, key=lambda skipped_path: skipped_path.path))
    extracted = _extract_indexes(root, files)
    file_states_by_path = _file_states_by_path(
        root,
        files,
        extracted,
        indexed_at_utc=indexed_at_utc,
    )
    git_metadata = _read_git_metadata(root)
    effective_config_hash = _effective_config_hash(scan.max_file_size_bytes)

    connection.executemany(
        "INSERT INTO metadata(key, value) VALUES (?, ?)",
        (
            ("schema_name", GRAPH_SCHEMA_NAME),
            ("schema_version", str(GRAPH_SCHEMA_VERSION)),
            ("artifact_version", str(GRAPH_ARTIFACT_VERSION)),
            ("exporter_version", GRAPH_EXPORTER_VERSION),
            ("effective_config_hash", effective_config_hash),
            ("git_branch", git_metadata.branch or ""),
            ("git_commit", git_metadata.commit or ""),
            ("git_detected", "1" if git_metadata.detected else "0"),
        ),
    )
    connection.execute(
        "INSERT INTO repositories(id, analysis_root, name) VALUES (?, ?, ?)",
        (REPOSITORY_ID, ".", root.name),
    )

    connection.executemany(
        "INSERT INTO directories(path, node_id, parent_path) VALUES (?, ?, ?)",
        ((directory.path, directory.node_id, directory.parent_path) for directory in directories),
    )
    connection.executemany(
        """
        INSERT INTO files(
            path,
            node_id,
            directory_path,
            size_bytes,
            mtime_ns,
            raw_hash,
            normalized_hash,
            graph_hash,
            dependency_hash,
            symbol_hash,
            line_range_hash,
            language,
            indexed_at_utc,
            parser_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                scanned_file.path,
                _file_node_id(scanned_file.path),
                _file_directory(scanned_file.path),
                scanned_file.size_bytes,
                file_states_by_path[scanned_file.path].mtime_ns,
                file_states_by_path[scanned_file.path].raw_hash,
                file_states_by_path[scanned_file.path].normalized_hash,
                file_states_by_path[scanned_file.path].graph_hash,
                file_states_by_path[scanned_file.path].dependency_hash,
                file_states_by_path[scanned_file.path].symbol_hash,
                file_states_by_path[scanned_file.path].line_range_hash,
                file_states_by_path[scanned_file.path].language,
                indexed_at_utc,
                file_states_by_path[scanned_file.path].parser_status,
            )
            for scanned_file in files
        ),
    )
    connection.executemany(
        "INSERT INTO skipped_paths(path, reason) VALUES (?, ?)",
        ((skipped.path, skipped.reason) for skipped in skipped_paths),
    )

    _insert_nodes(
        connection,
        root,
        directories,
        files,
        extracted.python,
        extracted.javascript,
        extracted.config,
        extracted.documentation,
        file_states_by_path,
    )
    _insert_python_tables(connection, extracted.python)
    _insert_javascript_tables(connection, extracted.javascript)
    _insert_config_tables(connection, extracted.config)
    _insert_documentation_tables(connection, extracted.documentation)
    _insert_edges(
        connection,
        directories,
        files,
        extracted.python,
        extracted.javascript,
        extracted.config,
        extracted.documentation,
    )
    _insert_file_changes(connection, file_changes)
    connection.execute(
        """
        INSERT INTO runs(
            id,
            indexed_at_utc,
            scan_policy_version,
            extractor_version,
            max_file_size_bytes,
            repository_id,
            directory_count,
            file_count,
            skipped_path_count,
            graph_schema_version,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            indexed_at_utc,
            1,
            GRAPH_EXPORTER_VERSION,
            scan.max_file_size_bytes,
            REPOSITORY_ID,
            len(directories),
            len(files),
            len(skipped_paths),
            GRAPH_SCHEMA_VERSION,
            "completed",
        ),
    )


def _finalize_graph_metadata(connection: sqlite3.Connection) -> None:
    quality_warnings = _quality_warnings(connection)
    connection.execute(
        "INSERT INTO metadata(key, value) VALUES (?, ?)",
        ("graph_quality_warnings", _json_value(quality_warnings)),
    )
    connection.execute(
        "INSERT INTO metadata(key, value) VALUES (?, ?)",
        ("canonical_graph_hash", _canonical_graph_hash(connection)),
    )


def _extract_indexes(root: Path, files: tuple[ScannedFile, ...]) -> _ExtractedIndexes:
    python_index = extract_python_index(root, files)
    javascript_index = extract_javascript_index(root, files)
    config_index = extract_config_index(root, files)
    documentation_index = extract_documentation_index(root, files)
    parser_status_by_path = {
        **python_index.parser_status_by_path,
        **javascript_index.parser_status_by_path,
        **config_index.parser_status_by_path,
        **documentation_index.parser_status_by_path,
    }
    return _ExtractedIndexes(
        python=python_index,
        javascript=javascript_index,
        config=config_index,
        documentation=documentation_index,
        parser_status_by_path=parser_status_by_path,
    )


def _file_states_by_path(
    root: Path,
    files: tuple[ScannedFile, ...],
    extracted: _ExtractedIndexes,
    *,
    indexed_at_utc: str,
) -> dict[str, FileState]:
    signatures = _file_signatures_by_path(files, extracted)
    return {
        scanned_file.path: _file_state(
            root,
            scanned_file,
            signature=signatures[scanned_file.path],
            parser_status=extracted.parser_status_by_path.get(scanned_file.path, "not_parsed"),
            indexed_at_utc=indexed_at_utc,
        )
        for scanned_file in files
    }


def _file_state(
    root: Path,
    scanned_file: ScannedFile,
    *,
    signature: _GraphSignature,
    parser_status: str,
    indexed_at_utc: str,
) -> FileState:
    path = root / scanned_file.path
    try:
        raw_bytes = path.read_bytes()
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        raw_bytes = b""
        mtime_ns = 0
    return FileState(
        path=scanned_file.path,
        size_bytes=scanned_file.size_bytes,
        mtime_ns=mtime_ns,
        raw_hash=_sha256_bytes(raw_bytes),
        normalized_hash=_normalized_hash(raw_bytes),
        graph_hash=signature.graph_hash,
        dependency_hash=signature.dependency_hash,
        symbol_hash=signature.symbol_hash,
        line_range_hash=signature.line_range_hash,
        language=_language_for_path(scanned_file.path),
        parser_status=parser_status,
        indexed_at_utc=indexed_at_utc,
    )


def _file_signatures_by_path(
    files: tuple[ScannedFile, ...], extracted: _ExtractedIndexes
) -> dict[str, _GraphSignature]:
    buckets: dict[str, dict[str, list[dict[str, object]]]] = {
        file.path: {"dependency": [], "graph": [], "line_range": [], "symbol": []} for file in files
    }

    def add(path: str, bucket: str, kind: str, payload: dict[str, object]) -> None:
        if path in buckets:
            buckets[path][bucket].append({"kind": kind, **payload})

    def add_graph(path: str, kind: str, payload: dict[str, object]) -> None:
        add(path, "graph", kind, payload)

    def add_dependency(path: str, kind: str, payload: dict[str, object]) -> None:
        add(path, "dependency", kind, payload)
        add_graph(path, kind, payload)

    def add_symbol(path: str, kind: str, payload: dict[str, object]) -> None:
        add(path, "symbol", kind, payload)
        add_graph(path, kind, payload)

    def add_line_range(path: str, kind: str, payload: dict[str, object]) -> None:
        add(path, "line_range", kind, payload)

    for py_module in extracted.python.modules:
        add_graph(
            py_module.path,
            "python_module",
            {
                "docstring_summary": py_module.docstring_summary,
                "module_name": py_module.module_name,
                "package_root": py_module.package_root,
                "parser_status": py_module.parser_status,
            },
        )
    for py_symbol in extracted.python.symbols:
        add_symbol(
            py_symbol.path,
            "python_symbol",
            {
                "bases": py_symbol.bases,
                "decorators": py_symbol.decorators,
                "docstring_summary": py_symbol.docstring_summary,
                "kind": py_symbol.kind,
                "name": py_symbol.name,
                "parent_id": py_symbol.parent_id,
                "qualified_name": py_symbol.qualified_name,
            },
        )
        add_line_range(
            py_symbol.path,
            "python_symbol",
            {"end_line": py_symbol.end_line, "start_line": py_symbol.start_line},
        )
    for py_import in extracted.python.imports:
        add_dependency(
            py_import.path,
            "python_import",
            {
                "alias": py_import.alias,
                "classification": py_import.classification,
                "imported_name": py_import.imported_name,
                "kind": py_import.kind,
                "level": py_import.level,
                "module": py_import.module,
                "root_name": py_import.root_name,
            },
        )
        add_line_range(py_import.path, "python_import", {"line": py_import.line})
    for py_comment in extracted.python.tagged_comments:
        add_graph(
            py_comment.path,
            "python_tagged_comment",
            {
                "attached_node_id": py_comment.attached_node_id,
                "tag": py_comment.tag,
                "text": py_comment.text,
            },
        )
        add_line_range(py_comment.path, "python_tagged_comment", {"line": py_comment.line})
    for py_error in extracted.python.parse_errors:
        add_graph(
            py_error.path,
            "python_parse_error",
            {"column": py_error.column, "message": py_error.message},
        )
        add_line_range(py_error.path, "python_parse_error", {"line": py_error.line})
    for py_call in extracted.python.calls:
        add_graph(
            py_call.path,
            "python_call",
            {
                "callee_id": py_call.callee_id,
                "callee_name": py_call.callee_name,
                "caller_id": py_call.caller_id,
                "confidence": py_call.confidence,
            },
        )
        add_line_range(py_call.path, "python_call", {"line": py_call.line})

    for js_module in extracted.javascript.modules:
        add_graph(
            js_module.path,
            "javascript_module",
            {
                "extension": js_module.extension,
                "module_name": js_module.module_name,
                "parser_status": js_module.parser_status,
            },
        )
    for js_symbol in extracted.javascript.symbols:
        add_symbol(
            js_symbol.path,
            "javascript_symbol",
            {
                "kind": js_symbol.kind,
                "name": js_symbol.name,
                "qualified_name": js_symbol.qualified_name,
            },
        )
        add_line_range(
            js_symbol.path,
            "javascript_symbol",
            {
                "end_line": js_symbol.end_line,
                "line": js_symbol.line,
                "start_line": js_symbol.start_line,
            },
        )
    for js_import in extracted.javascript.imports:
        add_dependency(
            js_import.path,
            "javascript_import",
            {
                "classification": js_import.classification,
                "kind": js_import.kind,
                "resolution_status": js_import.resolution_status,
                "resolved_path": js_import.resolved_path,
                "root_name": js_import.root_name,
                "specifier": js_import.specifier,
            },
        )
        add_line_range(js_import.path, "javascript_import", {"line": js_import.line})
    for js_export in extracted.javascript.exports:
        add_graph(
            js_export.path,
            "javascript_export",
            {
                "exported_name": js_export.exported_name,
                "kind": js_export.kind,
                "local_name": js_export.local_name,
            },
        )
        add_line_range(js_export.path, "javascript_export", {"line": js_export.line})
    for js_assignment in extracted.javascript.commonjs_assignments:
        add_graph(
            js_assignment.path,
            "javascript_commonjs_assignment",
            {
                "assigned_name": js_assignment.assigned_name,
                "exported_name": js_assignment.exported_name,
                "kind": js_assignment.kind,
            },
        )
        add_line_range(
            js_assignment.path,
            "javascript_commonjs_assignment",
            {"line": js_assignment.line},
        )

    for config in extracted.config.config_files:
        add_graph(
            config.path,
            "config_file",
            {
                "config_kind": config.config_kind,
                "format": config.format,
                "metadata": config.metadata,
                "parser_status": config.parser_status,
                "top_level_keys": config.top_level_keys,
            },
        )
    for package in extracted.config.packages:
        add_dependency(
            package.source_path,
            "config_package",
            {
                "classification": package.classification,
                "dependency_type": package.dependency_type,
                "ecosystem": package.ecosystem,
                "name": package.name,
                "version_constraint": package.version_constraint,
            },
        )
    for manager in extracted.config.package_managers:
        add_graph(
            manager.source_path,
            "config_package_manager",
            {
                "ecosystem": manager.ecosystem,
                "evidence_kind": manager.evidence_kind,
                "name": manager.name,
            },
        )
    for package_root in extracted.config.package_roots:
        add_graph(
            package_root.source_path,
            "config_package_root",
            {
                "ecosystem": package_root.ecosystem,
                "name": package_root.name,
                "path": package_root.path,
            },
        )
    for lockfile in extracted.config.lockfiles:
        add_graph(
            lockfile.path,
            "config_lockfile",
            {
                "ecosystem": lockfile.ecosystem,
                "format": lockfile.format,
                "manager": lockfile.manager,
            },
        )
    for command in extracted.config.commands:
        add_graph(
            command.path,
            "config_command",
            {
                "auto_run_recommended": command.auto_run_recommended,
                "command": command.command,
                "name": command.name,
                "not_run": command.not_run,
                "purpose": command.purpose,
                "source": command.source,
            },
        )
    for entrypoint in extracted.config.entrypoints:
        add_graph(
            entrypoint.path,
            "config_entrypoint",
            {
                "evidence": entrypoint.evidence,
                "kind": entrypoint.kind,
                "name": entrypoint.name,
                "target": entrypoint.target,
            },
        )
        add_line_range(
            entrypoint.path,
            "config_entrypoint",
            {"line": entrypoint.line},
        )
    for config_error in extracted.config.parse_errors:
        add_graph(config_error.path, "config_parse_error", {"message": config_error.message})

    for markdown in extracted.documentation.markdown_files:
        add_graph(
            markdown.path,
            "documentation_file",
            {
                "doc_kind": markdown.doc_kind,
                "importance": markdown.importance,
                "intro": markdown.intro,
                "parser_status": markdown.parser_status,
                "title": markdown.title,
            },
        )
    for heading in extracted.documentation.headings:
        add_graph(
            heading.path,
            "markdown_heading",
            {"heading_id": heading.heading_id, "level": heading.level, "text": heading.text},
        )
        add_line_range(heading.path, "markdown_heading", {"line": heading.line})
    for link in extracted.documentation.links:
        add_graph(
            link.path,
            "markdown_link",
            {
                "label": link.label,
                "target_fragment": link.target_fragment,
                "target_path": link.target_path,
            },
        )
        add_line_range(link.path, "markdown_link", {"line": link.line})
    for mention in extracted.documentation.path_mentions:
        add_graph(
            mention.path,
            "markdown_path_mention",
            {"mentioned_path": mention.mentioned_path, "target_path": mention.target_path},
        )
        add_line_range(mention.path, "markdown_path_mention", {"line": mention.line})
    for fence in extracted.documentation.code_fences:
        add_graph(
            fence.path,
            "markdown_code_fence",
            {"info_string": fence.info_string, "language": fence.language},
        )
        add_line_range(
            fence.path,
            "markdown_code_fence",
            {"end_line": fence.end_line, "start_line": fence.start_line},
        )
    for doc_comment in extracted.documentation.tagged_comments:
        add_graph(
            doc_comment.path,
            "documentation_tagged_comment",
            {
                "language": doc_comment.language,
                "syntax": doc_comment.syntax,
                "tag": doc_comment.tag,
                "text": doc_comment.text,
            },
        )
        add_line_range(doc_comment.path, "documentation_tagged_comment", {"line": doc_comment.line})
    for skill in extracted.documentation.skills:
        add_graph(skill.path, "skill", {"description": skill.description, "name": skill.name})

    return {
        path: _GraphSignature(
            graph_hash=_facts_hash(path_buckets["graph"]),
            dependency_hash=_facts_hash(path_buckets["dependency"]),
            symbol_hash=_facts_hash(path_buckets["symbol"]),
            line_range_hash=_facts_hash(path_buckets["line_range"]),
        )
        for path, path_buckets in buckets.items()
    }


@dataclass(frozen=True)
class _DirectoryFact:
    path: str
    node_id: str
    parent_path: str | None


def _directory_facts(scan: ScanResult) -> tuple[_DirectoryFact, ...]:
    paths = {ROOT_DIRECTORY_PATH}
    for scanned_file in scan.files:
        file_path = PurePosixPath(scanned_file.path)
        parent = file_path.parent.as_posix()
        if parent == ".":
            continue
        parts = parent.split("/")
        for index in range(1, len(parts) + 1):
            paths.add("/".join(parts[:index]))

    facts: list[_DirectoryFact] = []
    for directory_path in sorted(paths, key=_directory_sort_key):
        parent_path = (
            None if directory_path == ROOT_DIRECTORY_PATH else _directory_parent(directory_path)
        )
        facts.append(
            _DirectoryFact(
                path=directory_path,
                node_id=_directory_node_id(directory_path),
                parent_path=parent_path,
            )
        )
    return tuple(facts)


def _insert_nodes(
    connection: sqlite3.Connection,
    root: Path,
    directories: tuple[_DirectoryFact, ...],
    files: tuple[Any, ...],
    python_index: PythonIndex,
    javascript_index: JavaScriptIndex,
    config_index: ConfigIndex,
    documentation_index: DocumentationIndex,
    file_states_by_path: dict[str, FileState],
) -> None:
    connection.execute(
        "INSERT INTO nodes(id, kind, path, label, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (REPOSITORY_ID, "Repository", ".", root.name, _metadata_json({"analysis_root": "."})),
    )
    connection.executemany(
        "INSERT INTO nodes(id, kind, path, label, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                directory.node_id,
                "Directory",
                directory.path,
                "." if directory.path == ROOT_DIRECTORY_PATH else directory.path.rsplit("/", 1)[-1],
                _metadata_json({"parent_path": directory.parent_path}),
            )
            for directory in directories
        ),
    )
    connection.executemany(
        "INSERT INTO nodes(id, kind, path, label, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                _file_node_id(scanned_file.path),
                "File",
                scanned_file.path,
                scanned_file.path.rsplit("/", 1)[-1],
                _metadata_json(
                    {
                        "directory_path": _file_directory(scanned_file.path),
                        "graph_hash": file_states_by_path[scanned_file.path].graph_hash,
                        "language": file_states_by_path[scanned_file.path].language,
                        "parser_status": file_states_by_path[scanned_file.path].parser_status,
                        "raw_hash": file_states_by_path[scanned_file.path].raw_hash,
                        "size_bytes": scanned_file.size_bytes,
                    }
                ),
            )
            for scanned_file in files
        ),
    )
    connection.executemany(
        "INSERT INTO nodes(id, kind, path, label, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                markdown.node_id,
                "MarkdownFile",
                markdown.path,
                markdown.path.rsplit("/", 1)[-1],
                _metadata_json(
                    {
                        "doc_kind": markdown.doc_kind,
                        "importance": markdown.importance,
                        "intro": markdown.intro,
                        "parser_status": markdown.parser_status,
                        "title": markdown.title,
                    }
                ),
            )
            for markdown in documentation_index.markdown_files
        ),
    )
    connection.executemany(
        "INSERT INTO nodes(id, kind, path, label, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                heading.id,
                "MarkdownHeading",
                heading.path,
                heading.text,
                _metadata_json(
                    {
                        "heading_id": heading.heading_id,
                        "level": heading.level,
                        "line": heading.line,
                    }
                ),
            )
            for heading in documentation_index.headings
        ),
    )
    connection.executemany(
        "INSERT INTO nodes(id, kind, path, label, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                fence.id,
                "MarkdownCodeFence",
                fence.path,
                fence.language or "code fence",
                _metadata_json(
                    {
                        "end_line": fence.end_line,
                        "info_string": fence.info_string,
                        "language": fence.language,
                        "start_line": fence.start_line,
                    }
                ),
            )
            for fence in documentation_index.code_fences
        ),
    )
    connection.executemany(
        "INSERT INTO nodes(id, kind, path, label, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                comment.id,
                "TaggedComment",
                comment.path,
                comment.tag,
                _metadata_json(
                    {
                        "language": comment.language,
                        "line": comment.line,
                        "syntax": comment.syntax,
                        "tag": comment.tag,
                        "text": comment.text,
                    }
                ),
            )
            for comment in documentation_index.tagged_comments
        ),
    )
    connection.executemany(
        "INSERT INTO nodes(id, kind, path, label, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                skill.id,
                "Skill",
                skill.path,
                skill.name,
                _metadata_json({"description": skill.description, "manifest_path": skill.path}),
            )
            for skill in documentation_index.skills
        ),
    )
    connection.executemany(
        "INSERT INTO nodes(id, kind, path, label, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                config.node_id,
                "ConfigFile",
                config.path,
                config.path.rsplit("/", 1)[-1],
                _metadata_json(
                    {
                        "config_kind": config.config_kind,
                        "format": config.format,
                        "metadata": config.metadata,
                        "parser_status": config.parser_status,
                        "top_level_keys": list(config.top_level_keys),
                    }
                ),
            )
            for config in config_index.config_files
        ),
    )
    connection.executemany(
        "INSERT INTO nodes(id, kind, path, label, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                manager.id,
                "PackageManager",
                manager.source_path,
                manager.name,
                _metadata_json(
                    {
                        "ecosystem": manager.ecosystem,
                        "evidence_kind": manager.evidence_kind,
                        "source_path": manager.source_path,
                    }
                ),
            )
            for manager in config_index.package_managers
        ),
    )
    connection.executemany(
        "INSERT INTO nodes(id, kind, path, label, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                package.id,
                "ConfigPackage",
                package.source_path,
                package.name,
                _metadata_json(
                    {
                        "classification": package.classification,
                        "dependency_type": package.dependency_type,
                        "ecosystem": package.ecosystem,
                        "source_path": package.source_path,
                        "version_constraint": package.version_constraint,
                    }
                ),
            )
            for package in config_index.packages
        ),
    )
    connection.executemany(
        "INSERT INTO nodes(id, kind, path, label, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                package_root.id,
                "PackageRoot",
                package_root.path,
                package_root.name,
                _metadata_json(
                    {
                        "ecosystem": package_root.ecosystem,
                        "path": package_root.path,
                        "source_path": package_root.source_path,
                    }
                ),
            )
            for package_root in config_index.package_roots
        ),
    )
    connection.executemany(
        "INSERT INTO nodes(id, kind, path, label, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                lockfile.id,
                "Lockfile",
                lockfile.path,
                lockfile.manager,
                _metadata_json(
                    {
                        "ecosystem": lockfile.ecosystem,
                        "format": lockfile.format,
                        "manager": lockfile.manager,
                    }
                ),
            )
            for lockfile in config_index.lockfiles
        ),
    )
    connection.executemany(
        "INSERT INTO nodes(id, kind, path, label, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                command.id,
                "CandidateCommand",
                command.path,
                command.name,
                _metadata_json(
                    {
                        "auto_run_recommended": command.auto_run_recommended,
                        "command": command.command,
                        "not_run": command.not_run,
                        "purpose": command.purpose,
                        "source": command.source,
                    }
                ),
            )
            for command in config_index.commands
        ),
    )
    connection.executemany(
        "INSERT INTO nodes(id, kind, path, label, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                entrypoint.id,
                "Entrypoint",
                entrypoint.path,
                entrypoint.name,
                _metadata_json(
                    {
                        "evidence": entrypoint.evidence,
                        "kind": entrypoint.kind,
                        "line": entrypoint.line,
                        "target": entrypoint.target,
                    }
                ),
            )
            for entrypoint in config_index.entrypoints
        ),
    )
    connection.executemany(
        "INSERT INTO nodes(id, kind, path, label, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                error.id,
                "ConfigParseError",
                error.path,
                "parse error",
                _metadata_json({"message": error.message}),
            )
            for error in config_index.parse_errors
        ),
    )
    connection.executemany(
        "INSERT INTO nodes(id, kind, path, label, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                module.node_id,
                "PythonModule",
                module.path,
                module.module_name,
                _metadata_json(
                    {
                        "docstring_summary": module.docstring_summary,
                        "module_name": module.module_name,
                        "package_root": module.package_root,
                        "parser_status": module.parser_status,
                    }
                ),
            )
            for module in python_index.modules
        ),
    )
    connection.executemany(
        "INSERT INTO nodes(id, kind, path, label, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                module.node_id,
                "JavaScriptModule",
                module.path,
                module.module_name,
                _metadata_json(
                    {
                        "extension": module.extension,
                        "module_name": module.module_name,
                        "parser_status": module.parser_status,
                    }
                ),
            )
            for module in javascript_index.modules
        ),
    )
    connection.executemany(
        "INSERT INTO nodes(id, kind, path, label, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                symbol.id,
                _javascript_symbol_node_kind(symbol.kind),
                symbol.path,
                symbol.qualified_name,
                _metadata_json(
                    {
                        "end_line": symbol.end_line,
                        "kind": symbol.kind,
                        "line": symbol.line,
                        "module_node_id": symbol.module_node_id,
                        "name": symbol.name,
                        "qualified_name": symbol.qualified_name,
                        "start_line": symbol.start_line,
                    }
                ),
            )
            for symbol in javascript_index.symbols
        ),
    )
    connection.executemany(
        "INSERT INTO nodes(id, kind, path, label, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                package.id,
                "PythonPackage",
                None,
                package.name,
                _metadata_json(
                    {
                        "classification": package.classification,
                        "inferred": package.inferred,
                    }
                ),
            )
            for package in python_index.packages
        ),
    )
    connection.executemany(
        "INSERT INTO nodes(id, kind, path, label, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                package.id,
                "JavaScriptPackage",
                None,
                package.name,
                _metadata_json({"classification": package.classification}),
            )
            for package in javascript_index.packages
        ),
    )
    connection.executemany(
        "INSERT INTO nodes(id, kind, path, label, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                symbol.id,
                _python_symbol_node_kind(symbol.kind),
                symbol.path,
                symbol.qualified_name,
                _metadata_json(
                    {
                        "bases": list(symbol.bases),
                        "decorators": list(symbol.decorators),
                        "docstring_summary": symbol.docstring_summary,
                        "end_line": symbol.end_line,
                        "kind": symbol.kind,
                        "module_node_id": symbol.module_node_id,
                        "name": symbol.name,
                        "parent_id": symbol.parent_id,
                        "qualified_name": symbol.qualified_name,
                        "start_line": symbol.start_line,
                    }
                ),
            )
            for symbol in python_index.symbols
        ),
    )
    connection.executemany(
        "INSERT INTO nodes(id, kind, path, label, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                comment.id,
                "PythonTaggedComment",
                comment.path,
                comment.tag,
                _metadata_json(
                    {
                        "attached_node_id": comment.attached_node_id,
                        "line": comment.line,
                        "tag": comment.tag,
                        "text": comment.text,
                    }
                ),
            )
            for comment in python_index.tagged_comments
        ),
    )
    connection.executemany(
        "INSERT INTO nodes(id, kind, path, label, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                error.id,
                "PythonParseError",
                error.path,
                "parse error",
                _metadata_json(
                    {
                        "column": error.column,
                        "line": error.line,
                        "message": error.message,
                    }
                ),
            )
            for error in python_index.parse_errors
        ),
    )


def _insert_python_tables(connection: sqlite3.Connection, python_index: PythonIndex) -> None:
    connection.executemany(
        """
        INSERT INTO python_modules(
            path,
            node_id,
            module_name,
            package_root,
            parser_status,
            docstring_summary
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            (
                module.path,
                module.node_id,
                module.module_name,
                module.package_root,
                module.parser_status,
                module.docstring_summary,
            )
            for module in python_index.modules
        ),
    )
    connection.executemany(
        """
        INSERT INTO python_symbols(
            id,
            path,
            module_node_id,
            parent_id,
            kind,
            name,
            qualified_name,
            start_line,
            end_line,
            docstring_summary,
            decorators_json,
            bases_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                symbol.id,
                symbol.path,
                symbol.module_node_id,
                symbol.parent_id,
                symbol.kind,
                symbol.name,
                symbol.qualified_name,
                symbol.start_line,
                symbol.end_line,
                symbol.docstring_summary,
                _json_value(symbol.decorators),
                _json_value(symbol.bases),
            )
            for symbol in python_index.symbols
        ),
    )
    connection.executemany(
        """
        INSERT INTO python_imports(
            id,
            path,
            module_node_id,
            kind,
            module,
            imported_name,
            alias,
            root_name,
            classification,
            level,
            line
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                import_fact.id,
                import_fact.path,
                import_fact.module_node_id,
                import_fact.kind,
                import_fact.module,
                import_fact.imported_name,
                import_fact.alias,
                import_fact.root_name,
                import_fact.classification,
                import_fact.level,
                import_fact.line,
            )
            for import_fact in python_index.imports
        ),
    )
    connection.executemany(
        """
        INSERT INTO python_packages(id, name, classification, inferred)
        VALUES (?, ?, ?, ?)
        """,
        (
            (package.id, package.name, package.classification, int(package.inferred))
            for package in python_index.packages
        ),
    )
    connection.executemany(
        """
        INSERT INTO python_tagged_comments(
            id,
            path,
            module_node_id,
            attached_node_id,
            tag,
            text,
            line
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                comment.id,
                comment.path,
                comment.module_node_id,
                comment.attached_node_id,
                comment.tag,
                comment.text,
                comment.line,
            )
            for comment in python_index.tagged_comments
        ),
    )
    connection.executemany(
        """
        INSERT INTO python_parse_errors(id, path, module_node_id, message, line, column)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            (
                error.id,
                error.path,
                error.module_node_id,
                error.message,
                error.line,
                error.column,
            )
            for error in python_index.parse_errors
        ),
    )
    connection.executemany(
        """
        INSERT INTO python_calls(
            id,
            path,
            caller_id,
            callee_id,
            callee_name,
            line,
            confidence
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                call.id,
                call.path,
                call.caller_id,
                call.callee_id,
                call.callee_name,
                call.line,
                call.confidence,
            )
            for call in python_index.calls
        ),
    )


def _insert_javascript_tables(
    connection: sqlite3.Connection,
    javascript_index: JavaScriptIndex,
) -> None:
    connection.executemany(
        """
        INSERT INTO javascript_modules(path, node_id, module_name, extension, parser_status)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            (
                module.path,
                module.node_id,
                module.module_name,
                module.extension,
                module.parser_status,
            )
            for module in javascript_index.modules
        ),
    )
    connection.executemany(
        """
        INSERT INTO javascript_symbols(
            id,
            path,
            module_node_id,
            kind,
            name,
            qualified_name,
            line,
            start_line,
            end_line
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                symbol.id,
                symbol.path,
                symbol.module_node_id,
                symbol.kind,
                symbol.name,
                symbol.qualified_name,
                symbol.line,
                symbol.start_line,
                symbol.end_line,
            )
            for symbol in javascript_index.symbols
        ),
    )
    connection.executemany(
        """
        INSERT INTO javascript_imports(
            id,
            path,
            module_node_id,
            kind,
            specifier,
            root_name,
            classification,
            resolved_path,
            resolution_status,
            line
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                import_fact.id,
                import_fact.path,
                import_fact.module_node_id,
                import_fact.kind,
                import_fact.specifier,
                import_fact.root_name,
                import_fact.classification,
                import_fact.resolved_path,
                import_fact.resolution_status,
                import_fact.line,
            )
            for import_fact in javascript_index.imports
        ),
    )
    connection.executemany(
        """
        INSERT INTO javascript_packages(id, name, classification)
        VALUES (?, ?, ?)
        """,
        (
            (package.id, package.name, package.classification)
            for package in javascript_index.packages
        ),
    )
    connection.executemany(
        """
        INSERT INTO javascript_exports(
            id,
            path,
            module_node_id,
            kind,
            exported_name,
            local_name,
            line
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                export.id,
                export.path,
                export.module_node_id,
                export.kind,
                export.exported_name,
                export.local_name,
                export.line,
            )
            for export in javascript_index.exports
        ),
    )
    connection.executemany(
        """
        INSERT INTO javascript_commonjs_assignments(
            id,
            path,
            module_node_id,
            kind,
            exported_name,
            assigned_name,
            line
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                assignment.id,
                assignment.path,
                assignment.module_node_id,
                assignment.kind,
                assignment.exported_name,
                assignment.assigned_name,
                assignment.line,
            )
            for assignment in javascript_index.commonjs_assignments
        ),
    )


def _insert_config_tables(connection: sqlite3.Connection, config_index: ConfigIndex) -> None:
    connection.executemany(
        """
        INSERT INTO config_files(
            path,
            node_id,
            config_kind,
            format,
            parser_status,
            top_level_keys_json,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                config.path,
                config.node_id,
                config.config_kind,
                config.format,
                config.parser_status,
                _json_value(config.top_level_keys),
                _json_value(config.metadata),
            )
            for config in config_index.config_files
        ),
    )
    connection.executemany(
        """
        INSERT INTO config_package_managers(id, name, ecosystem, source_path, evidence_kind)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            (
                manager.id,
                manager.name,
                manager.ecosystem,
                manager.source_path,
                manager.evidence_kind,
            )
            for manager in config_index.package_managers
        ),
    )
    connection.executemany(
        """
        INSERT INTO config_packages(
            id,
            name,
            ecosystem,
            classification,
            source_path,
            dependency_type,
            version_constraint
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                package.id,
                package.name,
                package.ecosystem,
                package.classification,
                package.source_path,
                package.dependency_type,
                package.version_constraint,
            )
            for package in config_index.packages
        ),
    )
    connection.executemany(
        """
        INSERT INTO config_package_roots(id, name, ecosystem, path, source_path)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            (
                package_root.id,
                package_root.name,
                package_root.ecosystem,
                package_root.path,
                package_root.source_path,
            )
            for package_root in config_index.package_roots
        ),
    )
    connection.executemany(
        """
        INSERT INTO config_lockfiles(id, path, manager, format, ecosystem)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            (
                lockfile.id,
                lockfile.path,
                lockfile.manager,
                lockfile.format,
                lockfile.ecosystem,
            )
            for lockfile in config_index.lockfiles
        ),
    )
    connection.executemany(
        """
        INSERT INTO config_commands(
            id,
            path,
            source,
            name,
            command,
            purpose,
            not_run,
            auto_run_recommended
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                command.id,
                command.path,
                command.source,
                command.name,
                command.command,
                command.purpose,
                int(command.not_run),
                int(command.auto_run_recommended),
            )
            for command in config_index.commands
        ),
    )
    connection.executemany(
        """
        INSERT INTO config_entrypoints(id, path, kind, name, target, evidence, line)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                entrypoint.id,
                entrypoint.path,
                entrypoint.kind,
                entrypoint.name,
                entrypoint.target,
                entrypoint.evidence,
                entrypoint.line,
            )
            for entrypoint in config_index.entrypoints
        ),
    )
    connection.executemany(
        """
        INSERT INTO config_parse_errors(id, path, message)
        VALUES (?, ?, ?)
        """,
        ((error.id, error.path, error.message) for error in config_index.parse_errors),
    )


def _insert_documentation_tables(
    connection: sqlite3.Connection,
    documentation_index: DocumentationIndex,
) -> None:
    connection.executemany(
        """
        INSERT INTO documentation_files(
            path,
            node_id,
            doc_kind,
            importance,
            parser_status,
            title,
            intro
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                markdown.path,
                markdown.node_id,
                markdown.doc_kind,
                markdown.importance,
                markdown.parser_status,
                markdown.title,
                markdown.intro,
            )
            for markdown in documentation_index.markdown_files
        ),
    )
    connection.executemany(
        """
        INSERT INTO markdown_headings(
            id,
            path,
            document_node_id,
            heading_id,
            level,
            text,
            line
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                heading.id,
                heading.path,
                heading.document_node_id,
                heading.heading_id,
                heading.level,
                heading.text,
                heading.line,
            )
            for heading in documentation_index.headings
        ),
    )
    connection.executemany(
        """
        INSERT INTO markdown_links(
            id,
            path,
            document_node_id,
            label,
            target_path,
            target_fragment,
            line
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                link.id,
                link.path,
                link.document_node_id,
                link.label,
                link.target_path,
                link.target_fragment,
                link.line,
            )
            for link in documentation_index.links
        ),
    )
    connection.executemany(
        """
        INSERT INTO markdown_path_mentions(
            id,
            path,
            document_node_id,
            mentioned_path,
            target_path,
            line
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            (
                mention.id,
                mention.path,
                mention.document_node_id,
                mention.mentioned_path,
                mention.target_path,
                mention.line,
            )
            for mention in documentation_index.path_mentions
        ),
    )
    connection.executemany(
        """
        INSERT INTO markdown_code_fences(
            id,
            path,
            document_node_id,
            language,
            info_string,
            start_line,
            end_line
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                fence.id,
                fence.path,
                fence.document_node_id,
                fence.language,
                fence.info_string,
                fence.start_line,
                fence.end_line,
            )
            for fence in documentation_index.code_fences
        ),
    )
    connection.executemany(
        """
        INSERT INTO documentation_tagged_comments(
            id,
            path,
            tag,
            text,
            line,
            language,
            syntax
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                comment.id,
                comment.path,
                comment.tag,
                comment.text,
                comment.line,
                comment.language,
                comment.syntax,
            )
            for comment in documentation_index.tagged_comments
        ),
    )
    connection.executemany(
        """
        INSERT INTO skills(id, path, name, description)
        VALUES (?, ?, ?, ?)
        """,
        (
            (skill.id, skill.path, skill.name, skill.description)
            for skill in documentation_index.skills
        ),
    )


def _insert_file_changes(
    connection: sqlite3.Connection, file_changes: tuple[FileChange, ...]
) -> None:
    connection.executemany(
        """
        INSERT INTO file_changes(path, change_type, secondary_signals_json, payload_json)
        VALUES (?, ?, ?, ?)
        """,
        (
            (
                change.path,
                change.change_type,
                _json_value(change.secondary_signals),
                _json_value(change.to_status_dict()),
            )
            for change in sorted(file_changes, key=lambda item: item.path)
        ),
    )


def _insert_edges(
    connection: sqlite3.Connection,
    directories: tuple[_DirectoryFact, ...],
    files: tuple[Any, ...],
    python_index: PythonIndex,
    javascript_index: JavaScriptIndex,
    config_index: ConfigIndex,
    documentation_index: DocumentationIndex,
) -> None:
    edge_rows: list[_EdgeFact] = []

    def add_edge(
        source_id: str,
        target_id: str,
        kind: str,
        metadata: dict[str, Any] | None = None,
        *,
        confidence: str = "high",
        resolution_strategy: str = "direct",
        evidence: list[dict[str, Any]] | None = None,
    ) -> None:
        edge_metadata = metadata or {}
        edge_rows.append(
            _EdgeFact(
                source_id=source_id,
                target_id=target_id,
                kind=kind,
                metadata=edge_metadata,
                confidence=confidence,
                resolution_strategy=resolution_strategy,
                evidence=evidence
                if evidence is not None
                else _edge_evidence_from_metadata(edge_metadata),
            )
        )

    add_edge(REPOSITORY_ID, ROOT_DIRECTORY_ID, "CONTAINS")
    for directory in directories:
        if directory.parent_path is not None:
            add_edge(_directory_node_id(directory.parent_path), directory.node_id, "CONTAINS")
    for scanned_file in files:
        add_edge(
            _directory_node_id(_file_directory(scanned_file.path)),
            _file_node_id(scanned_file.path),
            "CONTAINS",
        )
    for markdown in documentation_index.markdown_files:
        add_edge(
            _file_node_id(markdown.path),
            markdown.node_id,
            "CONTAINS",
            {"doc_kind": markdown.doc_kind, "importance": markdown.importance},
        )
    for heading in documentation_index.headings:
        add_edge(
            heading.document_node_id,
            heading.id,
            "CONTAINS",
            {"heading_id": heading.heading_id, "level": heading.level, "line": heading.line},
        )
    for fence in documentation_index.code_fences:
        add_edge(
            fence.document_node_id,
            fence.id,
            "CONTAINS",
            {
                "end_line": fence.end_line,
                "info_string": fence.info_string,
                "language": fence.language,
                "start_line": fence.start_line,
            },
        )
    for skill in documentation_index.skills:
        add_edge(
            documentation_file_node_id(skill.path),
            skill.id,
            "DECLARES_SKILL",
            {"name": skill.name},
        )

    markdown_file_paths = {markdown.path for markdown in documentation_index.markdown_files}
    javascript_module_paths = {module.path for module in javascript_index.modules}

    def documentation_comment_source_node_id(path: str) -> str:
        if path in markdown_file_paths:
            return documentation_file_node_id(path)
        if path in javascript_module_paths:
            return javascript_module_node_id(path)
        return _file_node_id(path)

    for tagged_comment in documentation_index.tagged_comments:
        add_edge(
            documentation_comment_source_node_id(tagged_comment.path),
            tagged_comment.id,
            "CONTAINS",
            {
                "language": tagged_comment.language,
                "line": tagged_comment.line,
                "tag": tagged_comment.tag,
            },
        )

    markdown_link_edges: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for link in documentation_index.links:
        link_key = (link.document_node_id, _file_node_id(link.target_path))
        markdown_link_edges.setdefault(link_key, []).append(
            {
                "fragment": link.target_fragment,
                "id": link.id,
                "label": link.label,
                "line": link.line,
                "target_path": link.target_path,
            }
        )
    for (source_id, target_id), link_facts in sorted(markdown_link_edges.items()):
        add_edge(
            source_id,
            target_id,
            "LINKS_TO_FILE",
            {
                "lines": sorted({link["line"] for link in link_facts}),
                "links": sorted(link_facts, key=lambda link: (link["line"], link["label"])),
            },
        )

    markdown_mention_edges: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for mention in documentation_index.path_mentions:
        mention_key = (mention.document_node_id, _file_node_id(mention.target_path))
        markdown_mention_edges.setdefault(mention_key, []).append(
            {
                "id": mention.id,
                "line": mention.line,
                "mentioned_path": mention.mentioned_path,
                "target_path": mention.target_path,
            }
        )
    for (source_id, target_id), mention_facts in sorted(markdown_mention_edges.items()):
        add_edge(
            source_id,
            target_id,
            "MENTIONS_FILE",
            {
                "lines": sorted({mention["line"] for mention in mention_facts}),
                "mentions": sorted(
                    mention_facts,
                    key=lambda mention: (mention["line"], mention["mentioned_path"]),
                ),
            },
        )

    for python_module in python_index.modules:
        add_edge(_file_node_id(python_module.path), python_module.node_id, "CONTAINS")
    for javascript_module in javascript_index.modules:
        add_edge(_file_node_id(javascript_module.path), javascript_module.node_id, "CONTAINS")
    for javascript_symbol in javascript_index.symbols:
        add_edge(javascript_symbol.module_node_id, javascript_symbol.id, "CONTAINS")
    for python_symbol in python_index.symbols:
        add_edge(
            python_symbol.parent_id or python_symbol.module_node_id,
            python_symbol.id,
            "CONTAINS",
        )
    for comment in python_index.tagged_comments:
        add_edge(
            comment.attached_node_id,
            comment.id,
            "CONTAINS",
            {"line": comment.line, "tag": comment.tag},
        )
    for error in python_index.parse_errors:
        add_edge(
            error.module_node_id,
            error.id,
            "HAS_PARSE_ERROR",
            {"line": error.line, "message": error.message},
        )

    config_file_paths = {config.path for config in config_index.config_files}
    for config in config_index.config_files:
        add_edge(
            _file_node_id(config.path),
            config.node_id,
            "CONTAINS",
            {"config_kind": config.config_kind, "parser_status": config.parser_status},
        )

    def config_source_node_id(source_path: str) -> str:
        if source_path in config_file_paths:
            return config_file_node_id(source_path)
        return _file_node_id(source_path)

    for manager in config_index.package_managers:
        add_edge(
            config_source_node_id(manager.source_path),
            manager.id,
            "DECLARES_PACKAGE_MANAGER",
            {"ecosystem": manager.ecosystem, "evidence_kind": manager.evidence_kind},
        )
    for package in config_index.packages:
        add_edge(
            config_source_node_id(package.source_path),
            package.id,
            "DECLARES_PACKAGE",
            {
                "classification": package.classification,
                "dependency_type": package.dependency_type,
                "ecosystem": package.ecosystem,
            },
        )
    for package_root in config_index.package_roots:
        add_edge(
            config_source_node_id(package_root.source_path),
            package_root.id,
            "DECLARES_PACKAGE_ROOT",
            {"ecosystem": package_root.ecosystem, "path": package_root.path},
        )
    for lockfile in config_index.lockfiles:
        add_edge(
            config_source_node_id(lockfile.path),
            lockfile.id,
            "DETECTS_LOCKFILE",
            {"ecosystem": lockfile.ecosystem, "manager": lockfile.manager},
        )
    for command in config_index.commands:
        add_edge(
            config_source_node_id(command.path),
            command.id,
            "DECLARES_COMMAND",
            {
                "auto_run_recommended": command.auto_run_recommended,
                "not_run": command.not_run,
                "purpose": command.purpose,
                "source": command.source,
            },
        )
    for entrypoint in config_index.entrypoints:
        add_edge(
            config_source_node_id(entrypoint.path),
            entrypoint.id,
            "DECLARES_ENTRYPOINT",
            {"kind": entrypoint.kind, "line": entrypoint.line},
        )
    for config_error in config_index.parse_errors:
        add_edge(
            config_file_node_id(config_error.path),
            config_error.id,
            "HAS_PARSE_ERROR",
            {"message": config_error.message},
        )

    python_modules_by_name = _python_modules_by_name(python_index)
    python_modules_by_node_id = {module.node_id: module for module in python_index.modules}
    python_local_import_edges: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    import_edges: dict[tuple[str, str, str, str], list[int]] = {}
    import_edge_ids: dict[tuple[str, str, str, str], list[str]] = {}
    for python_import in python_index.imports:
        resolved_module = _resolve_python_local_import(
            python_import,
            modules_by_name=python_modules_by_name,
            modules_by_node_id=python_modules_by_node_id,
        )
        if resolved_module is not None:
            strategy = "local_import"
            resolved_key = (
                python_import.module_node_id,
                resolved_module.node_id,
                resolved_module.path,
                strategy,
            )
            python_local_import_edges.setdefault(resolved_key, []).append(
                {
                    "id": python_import.id,
                    "imported_name": python_import.imported_name,
                    "line": python_import.line,
                    "module": python_import.module,
                }
            )
        if not python_import.root_name:
            continue
        package_id = python_package_node_id(python_import.root_name, python_import.classification)
        python_import_key = (
            python_import.module_node_id,
            package_id,
            python_import.root_name,
            python_import.classification,
        )
        import_edges.setdefault(python_import_key, []).append(python_import.line)
        import_edge_ids.setdefault(python_import_key, []).append(python_import.id)

    for (source_id, target_id, root_name, classification), lines in sorted(import_edges.items()):
        add_edge(
            source_id,
            target_id,
            "IMPORTS",
            {
                "classification": classification,
                "import_ids": sorted(
                    import_edge_ids[(source_id, target_id, root_name, classification)]
                ),
                "lines": sorted(set(lines)),
                "root_name": root_name,
            },
            resolution_strategy=_import_resolution_strategy(classification),
        )

    for (source_id, target_id, resolved_path, strategy), facts in sorted(
        python_local_import_edges.items()
    ):
        add_edge(
            source_id,
            target_id,
            "IMPORTS",
            {
                "classification": "local_resolved",
                "import_ids": sorted(fact["id"] for fact in facts),
                "lines": sorted({fact["line"] for fact in facts}),
                "resolved_path": resolved_path,
            },
            confidence="high",
            resolution_strategy=strategy,
            evidence=[
                {
                    "import_id": fact["id"],
                    "imported_name": fact["imported_name"],
                    "kind": "python_import",
                    "line": fact["line"],
                    "module": fact["module"],
                    "resolved_path": resolved_path,
                }
                for fact in sorted(facts, key=lambda item: (item["line"], item["id"]))
            ],
        )

    javascript_import_edges: dict[tuple[str, str, str, str], list[int]] = {}
    javascript_import_edge_ids: dict[tuple[str, str, str, str], list[str]] = {}
    javascript_import_specifiers: dict[tuple[str, str, str, str], set[str]] = {}
    javascript_import_statuses: dict[tuple[str, str, str, str], set[str]] = {}
    javascript_import_facts: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for javascript_import in javascript_index.imports:
        if javascript_import.resolved_path is not None:
            target_id = javascript_module_node_id(javascript_import.resolved_path)
            javascript_import_key = (
                javascript_import.module_node_id,
                target_id,
                javascript_import.resolved_path,
                javascript_import.classification,
            )
            javascript_import_edges.setdefault(javascript_import_key, []).append(
                javascript_import.line
            )
            javascript_import_edge_ids.setdefault(javascript_import_key, []).append(
                javascript_import.id
            )
            javascript_import_specifiers.setdefault(javascript_import_key, set()).add(
                javascript_import.specifier
            )
            javascript_import_statuses.setdefault(javascript_import_key, set()).add(
                javascript_import.resolution_status
            )
            javascript_import_facts.setdefault(javascript_import_key, []).append(
                {
                    "id": javascript_import.id,
                    "kind": javascript_import.kind,
                    "line": javascript_import.line,
                    "resolved_path": javascript_import.resolved_path,
                    "resolution_status": javascript_import.resolution_status,
                    "specifier": javascript_import.specifier,
                }
            )
            continue
        if javascript_import.root_name is None:
            continue
        package_id = javascript_package_node_id(
            javascript_import.root_name, javascript_import.classification
        )
        javascript_import_key = (
            javascript_import.module_node_id,
            package_id,
            javascript_import.root_name,
            javascript_import.classification,
        )
        javascript_import_edges.setdefault(javascript_import_key, []).append(javascript_import.line)
        javascript_import_edge_ids.setdefault(javascript_import_key, []).append(
            javascript_import.id
        )
        javascript_import_specifiers.setdefault(javascript_import_key, set()).add(
            javascript_import.specifier
        )
        javascript_import_statuses.setdefault(javascript_import_key, set()).add(
            javascript_import.resolution_status
        )
        javascript_import_facts.setdefault(javascript_import_key, []).append(
            {
                "id": javascript_import.id,
                "kind": javascript_import.kind,
                "line": javascript_import.line,
                "resolution_status": javascript_import.resolution_status,
                "specifier": javascript_import.specifier,
            }
        )

    for (source_id, target_id, target_name, classification), lines in sorted(
        javascript_import_edges.items()
    ):
        metadata = {
            "classification": classification,
            "import_ids": sorted(
                javascript_import_edge_ids[(source_id, target_id, target_name, classification)]
            ),
            "lines": sorted(set(lines)),
            "specifiers": sorted(
                javascript_import_specifiers[(source_id, target_id, target_name, classification)]
            ),
        }
        if classification == "local_resolved":
            metadata["resolved_path"] = target_name
        else:
            metadata["root_name"] = target_name
        add_edge(
            source_id,
            target_id,
            "IMPORTS",
            metadata,
            confidence=_javascript_import_confidence(
                classification,
                javascript_import_statuses[(source_id, target_id, target_name, classification)],
            ),
            resolution_strategy=_javascript_import_resolution_strategy(
                classification,
                javascript_import_statuses[(source_id, target_id, target_name, classification)],
            ),
            evidence=_javascript_import_evidence(
                javascript_import_facts[(source_id, target_id, target_name, classification)]
            ),
        )

    call_edges: dict[tuple[str, str, str], list[int]] = {}
    for call in python_index.calls:
        call_edges.setdefault((call.caller_id, call.callee_id, call.callee_name), []).append(
            call.line
        )
    for (source_id, target_id, callee_name), lines in sorted(call_edges.items()):
        add_edge(
            source_id,
            target_id,
            "CALLS",
            {"callee_name": callee_name, "confidence": "high", "lines": sorted(set(lines))},
            resolution_strategy="same_file_symbol",
        )

    normalized_edges = _normalize_edge_facts(edge_rows)
    connection.executemany(
        """
        INSERT INTO edges(
            id,
            source_id,
            target_id,
            kind,
            confidence,
            resolution_strategy,
            evidence_json,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                _edge_id(edge.kind, edge.source_id, edge.target_id),
                edge.source_id,
                edge.target_id,
                edge.kind,
                edge.confidence,
                edge.resolution_strategy,
                _json_value(edge.evidence),
                _metadata_json(edge.metadata),
            )
            for edge in normalized_edges
        ),
    )


def _normalize_edge_facts(edge_facts: list[_EdgeFact]) -> tuple[_EdgeFact, ...]:
    grouped: dict[tuple[str, str, str], list[_EdgeFact]] = {}
    for edge in edge_facts:
        grouped.setdefault((edge.source_id, edge.target_id, edge.kind), []).append(edge)

    normalized = []
    for (source_id, target_id, kind), duplicates in grouped.items():
        normalized.append(
            _EdgeFact(
                source_id=source_id,
                target_id=target_id,
                kind=kind,
                metadata=_merge_edge_metadata(edge.metadata for edge in duplicates),
                confidence=_merge_edge_confidence(edge.confidence for edge in duplicates),
                resolution_strategy=_merge_resolution_strategy(
                    edge.resolution_strategy for edge in duplicates
                ),
                evidence=_merge_edge_evidence(edge.evidence for edge in duplicates),
            )
        )
    return tuple(sorted(normalized, key=lambda edge: (edge.source_id, edge.kind, edge.target_id)))


def _merge_edge_metadata(values: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for metadata in values:
        for key, value in metadata.items():
            if key not in merged:
                merged[key] = value
                continue
            merged[key] = _merge_metadata_value(merged[key], value)
    return {key: _sort_json_like(value) for key, value in sorted(merged.items())}


def _merge_metadata_value(left: Any, right: Any) -> Any:
    if left == right:
        return left
    if isinstance(left, list) and isinstance(right, list):
        return _dedupe_json_like([*left, *right])
    if isinstance(left, list):
        return _dedupe_json_like([*left, right])
    if isinstance(right, list):
        return _dedupe_json_like([left, *right])
    return _dedupe_json_like([left, right])


def _merge_edge_confidence(values: Any) -> str:
    return max(values, key=lambda value: (CONFIDENCE_RANK.get(str(value), -1), str(value)))


def _merge_resolution_strategy(values: Any) -> str:
    unique = sorted({str(value) for value in values})
    return unique[0] if len(unique) == 1 else "+".join(unique)


def _merge_edge_evidence(values: Any) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for items in values:
        evidence.extend(items)
    return _dedupe_json_like(evidence)[:MAX_EDGE_EVIDENCE_ITEMS]


def _edge_evidence_from_metadata(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = []
    if isinstance(metadata.get("line"), int):
        evidence.append({"kind": "line", "line": metadata["line"]})
    lines = metadata.get("lines")
    if isinstance(lines, list):
        for line in lines:
            if isinstance(line, int):
                evidence.append({"kind": "line", "line": line})
    return _dedupe_json_like(evidence)[:MAX_EDGE_EVIDENCE_ITEMS]


def _import_resolution_strategy(classification: str) -> str:
    if classification in {"node_builtin", "standard_library", "stdlib"}:
        return "standard_library_import"
    if classification == "third_party":
        return "external_import"
    if classification in {"local", "local_resolved"}:
        return "local_import"
    return "direct"


def _python_modules_by_name(python_index: PythonIndex) -> dict[str, list[PythonModuleFact]]:
    modules_by_name: dict[str, list[PythonModuleFact]] = {}
    for module in python_index.modules:
        modules_by_name.setdefault(module.module_name, []).append(module)
    return modules_by_name


def _resolve_python_local_import(
    python_import: PythonImportFact,
    *,
    modules_by_name: dict[str, list[PythonModuleFact]],
    modules_by_node_id: dict[str, PythonModuleFact],
) -> PythonModuleFact | None:
    if python_import.classification != "local":
        return None

    for target_name in _python_import_target_names(python_import, modules_by_node_id):
        matches = modules_by_name.get(target_name, [])
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return None
    return None


def _python_import_target_names(
    python_import: PythonImportFact,
    modules_by_node_id: dict[str, PythonModuleFact],
) -> tuple[str, ...]:
    if python_import.kind == "import" and python_import.level == 0:
        return (python_import.module,)

    if python_import.level > 0:
        source_module = modules_by_node_id.get(python_import.module_node_id)
        if source_module is None:
            return ()
        base_parts = _python_relative_base_parts(
            source_module.module_name,
            source_module.path,
            python_import.level,
        )
        if base_parts is None:
            return ()
        module_parts = tuple(part for part in python_import.module.split(".") if part)
        base_name = ".".join((*base_parts, *module_parts))
    else:
        base_name = python_import.module

    candidates: list[str] = []
    if python_import.imported_name and python_import.imported_name != "*":
        candidates.append(
            f"{base_name}.{python_import.imported_name}"
            if base_name
            else python_import.imported_name
        )
    if base_name:
        candidates.append(base_name)
    return tuple(dict.fromkeys(candidate for candidate in candidates if candidate))


def _python_relative_base_parts(
    module_name: str,
    path: str,
    level: int,
) -> tuple[str, ...] | None:
    if path == "__init__.py" or path.endswith("/__init__.py"):
        package_parts = tuple(module_name.split(".")) if module_name != "__init__" else ()
    else:
        package_parts = tuple(module_name.split(".")[:-1])
    ascend = level - 1
    if ascend > len(package_parts):
        return None
    if ascend == 0:
        return package_parts
    return package_parts[:-ascend]


def _javascript_import_confidence(classification: str, statuses: set[str]) -> str:
    if classification == "local_resolved" and "resolved_alias" in statuses:
        return "medium"
    return "high"


def _javascript_import_resolution_strategy(classification: str, statuses: set[str]) -> str:
    if classification == "local_resolved":
        strategies = []
        if "resolved_alias" in statuses:
            strategies.append("path_alias_import")
        if "resolved_relative" in statuses:
            strategies.append("local_import")
        return "+".join(sorted(strategies)) if strategies else "local_import"
    return _import_resolution_strategy(classification)


def _javascript_import_evidence(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "import_id": fact["id"],
            "kind": "javascript_import",
            "line": fact["line"],
            "resolved_path": fact.get("resolved_path"),
            "resolution_status": fact["resolution_status"],
            "specifier": fact["specifier"],
            "statement_kind": fact["kind"],
        }
        for fact in sorted(facts, key=lambda item: (item["line"], item["id"]))
    ][:MAX_EDGE_EVIDENCE_ITEMS]


def _dedupe_json_like(values: list[Any]) -> list[Any]:
    unique = {_json_value(_sort_json_like(value)): _sort_json_like(value) for value in values}
    return [unique[key] for key in sorted(unique)]


def _sort_json_like(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sort_json_like(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_sort_json_like(item) for item in sorted(value, key=lambda item: _json_value(item))]
    return value


def _load_snapshot(root: Path) -> dict[str, Any]:
    graph_store = root / GRAPH_STORE_PATH
    with sqlite3.connect(graph_store) as connection:
        connection.row_factory = sqlite3.Row
        _ensure_supported_schema(connection)
        metadata = _metadata(connection)
        repository = _single_row(
            connection.execute("SELECT id, analysis_root, name FROM repositories ORDER BY id")
        )
        directories = _rows(
            connection.execute("SELECT path, node_id, parent_path FROM directories ORDER BY path")
        )
        files = _rows(
            connection.execute(
                """
                SELECT
                    path,
                    node_id,
                    directory_path,
                    size_bytes,
                    mtime_ns,
                    raw_hash,
                    normalized_hash,
                    graph_hash,
                    dependency_hash,
                    symbol_hash,
                    line_range_hash,
                    language,
                    indexed_at_utc,
                    parser_status
                FROM files
                ORDER BY path
                """
            )
        )
        skipped_paths = _rows(
            connection.execute("SELECT path, reason FROM skipped_paths ORDER BY path")
        )
        nodes = _rows(
            connection.execute("SELECT id, kind, path, label, metadata_json FROM nodes ORDER BY id")
        )
        edges = _rows(
            connection.execute(
                """
                SELECT
                    id,
                    source_id,
                    target_id,
                    kind,
                    confidence,
                    resolution_strategy,
                    evidence_json,
                    metadata_json
                FROM edges
                ORDER BY source_id, kind, target_id, id
                """
            )
        )
        python_modules = _rows(
            connection.execute(
                """
                SELECT
                    path,
                    node_id,
                    module_name,
                    package_root,
                    parser_status,
                    docstring_summary
                FROM python_modules
                ORDER BY path
                """
            )
        )
        python_symbols = _decode_python_symbol_rows(
            _rows(
                connection.execute(
                    """
                    SELECT
                        id,
                        path,
                        module_node_id,
                        parent_id,
                        kind,
                        name,
                        qualified_name,
                        start_line,
                        end_line,
                        docstring_summary,
                        decorators_json,
                        bases_json
                    FROM python_symbols
                    ORDER BY path, qualified_name, id
                    """
                )
            )
        )
        python_imports = _rows(
            connection.execute(
                """
                SELECT
                    id,
                    path,
                    module_node_id,
                    kind,
                    module,
                    imported_name,
                    alias,
                    root_name,
                    classification,
                    level,
                    line
                FROM python_imports
                ORDER BY path, line, id
                """
            )
        )
        python_packages = _decode_python_package_rows(
            _rows(
                connection.execute(
                    """
                    SELECT id, name, classification, inferred
                    FROM python_packages
                    ORDER BY classification, name
                    """
                )
            )
        )
        python_tagged_comments = _rows(
            connection.execute(
                """
                SELECT
                    id,
                    path,
                    module_node_id,
                    attached_node_id,
                    tag,
                    text,
                    line
                FROM python_tagged_comments
                ORDER BY path, line, id
                """
            )
        )
        python_parse_errors = _rows(
            connection.execute(
                """
                SELECT id, path, module_node_id, message, line, column
                FROM python_parse_errors
                ORDER BY path
                """
            )
        )
        python_calls = _rows(
            connection.execute(
                """
                SELECT id, path, caller_id, callee_id, callee_name, line, confidence
                FROM python_calls
                ORDER BY path, line, id
                """
            )
        )
        javascript_modules = _rows(
            connection.execute(
                """
                SELECT path, node_id, module_name, extension, parser_status
                FROM javascript_modules
                ORDER BY path
                """
            )
        )
        javascript_symbols = _rows(
            connection.execute(
                """
                SELECT
                    id,
                    path,
                    module_node_id,
                    kind,
                    name,
                    qualified_name,
                    line,
                    start_line,
                    end_line
                FROM javascript_symbols
                ORDER BY path, qualified_name, id
                """
            )
        )
        javascript_imports = _rows(
            connection.execute(
                """
                SELECT
                    id,
                    path,
                    module_node_id,
                    kind,
                    specifier,
                    root_name,
                    classification,
                    resolved_path,
                    resolution_status,
                    line
                FROM javascript_imports
                ORDER BY path, line, id
                """
            )
        )
        javascript_packages = _rows(
            connection.execute(
                """
                SELECT id, name, classification
                FROM javascript_packages
                ORDER BY classification, name
                """
            )
        )
        javascript_exports = _rows(
            connection.execute(
                """
                SELECT id, path, module_node_id, kind, exported_name, local_name, line
                FROM javascript_exports
                ORDER BY path, line, id
                """
            )
        )
        javascript_commonjs_assignments = _rows(
            connection.execute(
                """
                SELECT id, path, module_node_id, kind, exported_name, assigned_name, line
                FROM javascript_commonjs_assignments
                ORDER BY path, line, id
                """
            )
        )
        config_files = _decode_config_file_rows(
            _rows(
                connection.execute(
                    """
                    SELECT
                        path,
                        node_id,
                        config_kind,
                        format,
                        parser_status,
                        top_level_keys_json,
                        metadata_json
                    FROM config_files
                    ORDER BY path
                    """
                )
            )
        )
        config_package_managers = _rows(
            connection.execute(
                """
                SELECT id, name, ecosystem, source_path, evidence_kind
                FROM config_package_managers
                ORDER BY ecosystem, name, source_path, evidence_kind
                """
            )
        )
        config_packages = _rows(
            connection.execute(
                """
                SELECT
                    id,
                    name,
                    ecosystem,
                    classification,
                    source_path,
                    dependency_type,
                    version_constraint
                FROM config_packages
                ORDER BY ecosystem, classification, name, source_path, dependency_type
                """
            )
        )
        config_package_roots = _rows(
            connection.execute(
                """
                SELECT id, name, ecosystem, path, source_path
                FROM config_package_roots
                ORDER BY ecosystem, path, name
                """
            )
        )
        config_lockfiles = _rows(
            connection.execute(
                """
                SELECT id, path, manager, format, ecosystem
                FROM config_lockfiles
                ORDER BY path
                """
            )
        )
        config_commands = _decode_config_command_rows(
            _rows(
                connection.execute(
                    """
                    SELECT
                        id,
                        path,
                        source,
                        name,
                        command,
                        purpose,
                        not_run,
                        auto_run_recommended
                    FROM config_commands
                    ORDER BY path, source, name
                    """
                )
            )
        )
        config_entrypoints = _rows(
            connection.execute(
                """
                SELECT id, path, kind, name, target, evidence, line
                FROM config_entrypoints
                ORDER BY path, kind, name, target
                """
            )
        )
        config_parse_errors = _rows(
            connection.execute(
                """
                SELECT id, path, message
                FROM config_parse_errors
                ORDER BY path
                """
            )
        )
        documentation_files = _rows(
            connection.execute(
                """
                SELECT path, node_id, doc_kind, importance, parser_status, title, intro
                FROM documentation_files
                ORDER BY path
                """
            )
        )
        markdown_headings = _rows(
            connection.execute(
                """
                SELECT id, path, document_node_id, heading_id, level, text, line
                FROM markdown_headings
                ORDER BY path, line, id
                """
            )
        )
        markdown_links = _rows(
            connection.execute(
                """
                SELECT id, path, document_node_id, label, target_path, target_fragment, line
                FROM markdown_links
                ORDER BY path, line, id
                """
            )
        )
        markdown_path_mentions = _rows(
            connection.execute(
                """
                SELECT id, path, document_node_id, mentioned_path, target_path, line
                FROM markdown_path_mentions
                ORDER BY path, line, target_path, id
                """
            )
        )
        markdown_code_fences = _rows(
            connection.execute(
                """
                SELECT id, path, document_node_id, language, info_string, start_line, end_line
                FROM markdown_code_fences
                ORDER BY path, start_line, id
                """
            )
        )
        documentation_tagged_comments = _rows(
            connection.execute(
                """
                SELECT id, path, tag, text, line, language, syntax
                FROM documentation_tagged_comments
                ORDER BY path, line, id
                """
            )
        )
        skills = _rows(
            connection.execute(
                """
                SELECT id, path, name, description
                FROM skills
                ORDER BY name, path
                """
            )
        )
        run = _single_row(
            connection.execute(
                """
                SELECT
                    id,
                    indexed_at_utc,
                    scan_policy_version,
                    extractor_version,
                    max_file_size_bytes,
                    repository_id,
                    directory_count,
                    file_count,
                    skipped_path_count,
                    graph_schema_version,
                    status
                FROM runs
                WHERE id = 1
                """
            )
        )
        file_changes = _decode_file_change_rows(
            _rows(
                connection.execute(
                    """
                    SELECT path, change_type, secondary_signals_json, payload_json
                    FROM file_changes
                    ORDER BY path
                    """
                )
            )
        )

    counts = {
        "config_commands": len(config_commands),
        "config_entrypoints": len(config_entrypoints),
        "config_files": len(config_files),
        "config_lockfiles": len(config_lockfiles),
        "config_package_managers": len(config_package_managers),
        "config_package_roots": len(config_package_roots),
        "config_packages": len(config_packages),
        "config_parse_errors": len(config_parse_errors),
        "documentation_files": len(documentation_files),
        "documentation_tagged_comments": len(documentation_tagged_comments),
        "directories": len(directories),
        "edges": len(edges),
        "files": len(files),
        "javascript_commonjs_assignments": len(javascript_commonjs_assignments),
        "javascript_exports": len(javascript_exports),
        "javascript_imports": len(javascript_imports),
        "javascript_modules": len(javascript_modules),
        "javascript_packages": len(javascript_packages),
        "javascript_symbols": len(javascript_symbols),
        "nodes": len(nodes),
        "python_calls": len(python_calls),
        "python_imports": len(python_imports),
        "python_modules": len(python_modules),
        "python_packages": len(python_packages),
        "python_parse_errors": len(python_parse_errors),
        "python_symbols": len(python_symbols),
        "python_tagged_comments": len(python_tagged_comments),
        "markdown_code_fences": len(markdown_code_fences),
        "markdown_headings": len(markdown_headings),
        "markdown_links": len(markdown_links),
        "markdown_path_mentions": len(markdown_path_mentions),
        "skills": len(skills),
        "skipped_paths": len(skipped_paths),
    }
    skip_reasons = dict(sorted(Counter(path["reason"] for path in skipped_paths).items()))
    schema = {"name": metadata["schema_name"], "version": int(metadata["schema_version"])}
    return {
        "artifact_version": GRAPH_ARTIFACT_VERSION,
        "config": {
            "commands": config_commands,
            "config_files": config_files,
            "entrypoints": config_entrypoints,
            "lockfiles": config_lockfiles,
            "package_managers": config_package_managers,
            "package_roots": config_package_roots,
            "packages": config_packages,
            "parse_errors": config_parse_errors,
        },
        "counts": counts,
        "directories": directories,
        "documentation": {
            "code_fences": markdown_code_fences,
            "files": documentation_files,
            "headings": markdown_headings,
            "links": markdown_links,
            "path_mentions": markdown_path_mentions,
            "skills": skills,
            "tagged_comments": documentation_tagged_comments,
        },
        "edges": _decode_edge_rows(edges),
        "files": files,
        "javascript": {
            "commonjs_assignments": javascript_commonjs_assignments,
            "exports": javascript_exports,
            "imports": javascript_imports,
            "modules": javascript_modules,
            "packages": javascript_packages,
            "symbols": javascript_symbols,
        },
        "limits": {"max_file_size_bytes": run["max_file_size_bytes"]},
        "metadata": metadata,
        "nodes": _decode_metadata_rows(nodes),
        "python": {
            "calls": python_calls,
            "imports": python_imports,
            "modules": python_modules,
            "packages": python_packages,
            "parse_errors": python_parse_errors,
            "symbols": python_symbols,
            "tagged_comments": python_tagged_comments,
        },
        "repository": repository,
        "run": run,
        "schema": schema,
        "file_changes": file_changes,
        "skip_reasons": skip_reasons,
        "skipped_paths": skipped_paths,
    }


def _graph_json_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact": "graph",
        "artifact_version": snapshot["artifact_version"],
        "canonical_graph_hash": snapshot["metadata"].get("canonical_graph_hash"),
        "changes": _changes_payload(snapshot["file_changes"]),
        "config": snapshot["config"],
        "counts": snapshot["counts"],
        "directories": snapshot["directories"],
        "documentation": snapshot["documentation"],
        "edges": snapshot["edges"],
        "files": snapshot["files"],
        "javascript": snapshot["javascript"],
        "limits": snapshot["limits"],
        "python": snapshot["python"],
        "repository": snapshot["repository"],
        "run": _run_payload(snapshot),
        "schema": snapshot["schema"],
        "skipped_paths": snapshot["skipped_paths"],
        "nodes": snapshot["nodes"],
        "validation": _validation_payload(snapshot),
    }


def _graph_lite_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact": "graph-lite",
        "artifact_version": snapshot["artifact_version"],
        "canonical_graph_hash": snapshot["metadata"].get("canonical_graph_hash"),
        "counts": snapshot["counts"],
        "files": [
            {
                "path": file["path"],
                "graph_hash": file["graph_hash"],
                "parser_status": file["parser_status"],
                "raw_hash": file["raw_hash"],
                "size_bytes": file["size_bytes"],
            }
            for file in snapshot["files"]
        ],
        "changes": _changes_payload(snapshot["file_changes"]),
        "config": _config_lite_payload(snapshot),
        "documentation": _documentation_lite_payload(snapshot),
        "freshness": _stored_freshness_payload(),
        "javascript": _javascript_lite_payload(snapshot),
        "python": _python_lite_payload(snapshot),
        "repository": snapshot["repository"],
        "run": _run_payload(snapshot),
        "schema": snapshot["schema"],
        "skip_reasons": snapshot["skip_reasons"],
        "validation": _validation_payload(snapshot),
    }


def _graph_status_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact": "graph-status",
        "artifact_version": snapshot["artifact_version"],
        "canonical_graph_hash": snapshot["metadata"].get("canonical_graph_hash"),
        "changes": _changes_payload(snapshot["file_changes"]),
        "counts": snapshot["counts"],
        "effective_config_hash": snapshot["metadata"].get("effective_config_hash"),
        "freshness": _stored_freshness_payload(),
        "git": _git_metadata_from_metadata(snapshot["metadata"]).to_payload(),
        "limits": snapshot["limits"],
        "repository": snapshot["repository"],
        "run": _run_payload(snapshot),
        "scan": {
            "artifact": f"{ARTIFACT_DIR_NAME}/scan.json",
            "scan_policy_version": snapshot["run"]["scan_policy_version"],
        },
        "schema": snapshot["schema"],
        "skip_reasons": snapshot["skip_reasons"],
        "validation": _validation_payload(snapshot),
    }


def _validation_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "hard_failures": [],
        "quality_warnings": _metadata_quality_warnings(snapshot["metadata"]),
    }


def _config_lite_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    config = snapshot["config"]
    return {
        "commands": [
            {
                "auto_run_recommended": command["auto_run_recommended"],
                "command": command["command"],
                "name": command["name"],
                "not_run": command["not_run"],
                "path": command["path"],
                "purpose": command["purpose"],
                "source": command["source"],
            }
            for command in config["commands"]
        ],
        "config_files": [
            {
                "config_kind": config_file["config_kind"],
                "format": config_file["format"],
                "parser_status": config_file["parser_status"],
                "path": config_file["path"],
                "top_level_keys": config_file["top_level_keys"],
            }
            for config_file in config["config_files"]
        ],
        "entrypoints": [
            {
                "evidence": entrypoint["evidence"],
                "kind": entrypoint["kind"],
                "line": entrypoint["line"],
                "name": entrypoint["name"],
                "path": entrypoint["path"],
                "target": entrypoint["target"],
            }
            for entrypoint in config["entrypoints"]
        ],
        "lockfiles": config["lockfiles"],
        "package_managers": config["package_managers"],
        "package_roots": config["package_roots"],
        "packages": [
            {
                "classification": package["classification"],
                "dependency_type": package["dependency_type"],
                "ecosystem": package["ecosystem"],
                "name": package["name"],
                "source_path": package["source_path"],
                "version_constraint": package["version_constraint"],
            }
            for package in config["packages"]
        ],
        "parse_errors": config["parse_errors"],
    }


def _documentation_lite_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    documentation = snapshot["documentation"]
    return {
        "code_fences": [
            {
                "end_line": fence["end_line"],
                "info_string": fence["info_string"],
                "language": fence["language"],
                "path": fence["path"],
                "start_line": fence["start_line"],
            }
            for fence in documentation["code_fences"]
        ],
        "files": [
            {
                "doc_kind": markdown["doc_kind"],
                "importance": markdown["importance"],
                "intro": markdown["intro"],
                "parser_status": markdown["parser_status"],
                "path": markdown["path"],
                "title": markdown["title"],
            }
            for markdown in documentation["files"]
        ],
        "headings": [
            {
                "heading_id": heading["heading_id"],
                "level": heading["level"],
                "line": heading["line"],
                "path": heading["path"],
                "text": heading["text"],
            }
            for heading in documentation["headings"]
        ],
        "links": [
            {
                "label": link["label"],
                "line": link["line"],
                "path": link["path"],
                "target_fragment": link["target_fragment"],
                "target_path": link["target_path"],
            }
            for link in documentation["links"]
        ],
        "path_mentions": [
            {
                "line": mention["line"],
                "mentioned_path": mention["mentioned_path"],
                "path": mention["path"],
                "target_path": mention["target_path"],
            }
            for mention in documentation["path_mentions"]
        ],
        "skills": [
            {
                "description": skill["description"],
                "name": skill["name"],
                "path": skill["path"],
            }
            for skill in documentation["skills"]
        ],
        "tagged_comments": [
            {
                "language": comment["language"],
                "line": comment["line"],
                "path": comment["path"],
                "syntax": comment["syntax"],
                "tag": comment["tag"],
                "text": comment["text"],
            }
            for comment in documentation["tagged_comments"]
        ],
    }


def _python_lite_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    python = snapshot["python"]
    return {
        "calls": [
            {
                "callee_id": call["callee_id"],
                "callee_name": call["callee_name"],
                "caller_id": call["caller_id"],
                "confidence": call["confidence"],
                "line": call["line"],
                "path": call["path"],
            }
            for call in python["calls"]
        ],
        "imports": [
            {
                "classification": import_fact["classification"],
                "imported_name": import_fact["imported_name"],
                "kind": import_fact["kind"],
                "line": import_fact["line"],
                "module": import_fact["module"],
                "path": import_fact["path"],
                "root_name": import_fact["root_name"],
            }
            for import_fact in python["imports"]
        ],
        "modules": [
            {
                "docstring_summary": module["docstring_summary"],
                "module_name": module["module_name"],
                "parser_status": module["parser_status"],
                "path": module["path"],
            }
            for module in python["modules"]
        ],
        "packages": python["packages"],
        "parse_errors": python["parse_errors"],
        "symbols": [
            {
                "bases": symbol["bases"],
                "decorators": symbol["decorators"],
                "docstring_summary": symbol["docstring_summary"],
                "end_line": symbol["end_line"],
                "kind": symbol["kind"],
                "path": symbol["path"],
                "qualified_name": symbol["qualified_name"],
                "start_line": symbol["start_line"],
            }
            for symbol in python["symbols"]
        ],
        "tagged_comments": [
            {
                "line": comment["line"],
                "path": comment["path"],
                "tag": comment["tag"],
                "text": comment["text"],
            }
            for comment in python["tagged_comments"]
        ],
    }


def _javascript_lite_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    javascript = snapshot["javascript"]
    return {
        "commonjs_assignments": [
            {
                "assigned_name": assignment["assigned_name"],
                "exported_name": assignment["exported_name"],
                "kind": assignment["kind"],
                "line": assignment["line"],
                "path": assignment["path"],
            }
            for assignment in javascript["commonjs_assignments"]
        ],
        "exports": [
            {
                "exported_name": export["exported_name"],
                "kind": export["kind"],
                "line": export["line"],
                "local_name": export["local_name"],
                "path": export["path"],
            }
            for export in javascript["exports"]
        ],
        "imports": [
            {
                "classification": import_fact["classification"],
                "kind": import_fact["kind"],
                "line": import_fact["line"],
                "path": import_fact["path"],
                "resolved_path": import_fact["resolved_path"],
                "resolution_status": import_fact["resolution_status"],
                "root_name": import_fact["root_name"],
                "specifier": import_fact["specifier"],
            }
            for import_fact in javascript["imports"]
        ],
        "modules": [
            {
                "extension": module["extension"],
                "module_name": module["module_name"],
                "parser_status": module["parser_status"],
                "path": module["path"],
            }
            for module in javascript["modules"]
        ],
        "packages": javascript["packages"],
        "symbols": [
            {
                "end_line": symbol["end_line"],
                "kind": symbol["kind"],
                "path": symbol["path"],
                "qualified_name": symbol["qualified_name"],
                "start_line": symbol["start_line"],
            }
            for symbol in javascript["symbols"]
        ],
    }


def _run_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    run = snapshot["run"]
    return {
        "extractor_version": run["extractor_version"],
        "id": run["id"],
        "indexed_at_utc": run["indexed_at_utc"],
        "status": run["status"],
    }


def _graph_report_text(snapshot: dict[str, Any]) -> str:
    counts = snapshot["counts"]
    run = snapshot["run"]
    repository = snapshot["repository"]
    python = snapshot["python"]
    javascript = snapshot["javascript"]
    config = snapshot["config"]
    documentation = snapshot["documentation"]
    symbol_labels = _symbol_labels(python)
    lines = [
        "# RepoLens Graph Report",
        "",
        f"Repository: {repository['name']}",
        "Analysis root: .",
        f"Indexed at UTC: {run['indexed_at_utc']}",
        f"Schema version: {snapshot['schema']['version']}",
        f"Canonical graph hash: {snapshot['metadata'].get('canonical_graph_hash', '')}",
        "",
        "## Summary",
        "",
        f"- Directories: {counts['directories']}",
        f"- Files: {counts['files']}",
        f"- Skipped paths: {counts['skipped_paths']}",
        f"- Python modules: {counts['python_modules']}",
        f"- Python symbols: {counts['python_symbols']}",
        f"- Python imports: {counts['python_imports']}",
        f"- Python tagged comments: {counts['python_tagged_comments']}",
        f"- Python parse errors: {counts['python_parse_errors']}",
        f"- JavaScript modules: {counts['javascript_modules']}",
        f"- JavaScript symbols: {counts['javascript_symbols']}",
        f"- JavaScript imports: {counts['javascript_imports']}",
        f"- JavaScript packages: {counts['javascript_packages']}",
        f"- JavaScript exports: {counts['javascript_exports']}",
        f"- JavaScript CommonJS assignments: {counts['javascript_commonjs_assignments']}",
        f"- Config files: {counts['config_files']}",
        f"- Config packages: {counts['config_packages']}",
        f"- Config commands: {counts['config_commands']}",
        f"- Config entrypoints: {counts['config_entrypoints']}",
        f"- Documentation files: {counts['documentation_files']}",
        f"- Markdown headings: {counts['markdown_headings']}",
        f"- Markdown links: {counts['markdown_links']}",
        f"- Markdown path mentions: {counts['markdown_path_mentions']}",
        f"- Markdown code fences: {counts['markdown_code_fences']}",
        f"- Documentation tagged comments: {counts['documentation_tagged_comments']}",
        f"- Skills: {counts['skills']}",
        "- Live freshness checks: available.",
        "",
        "## Files",
        "",
        "| Path | Size bytes | Parser status |",
        "| --- | ---: | --- |",
    ]
    if snapshot["files"]:
        lines.extend(
            f"| `{file['path']}` | {file['size_bytes']} | {file['parser_status']} |"
            for file in snapshot["files"]
        )
    else:
        lines.append("| Not detected | 0 | not_parsed |")

    lines.extend(_documentation_report_lines(documentation))

    lines.extend(
        [
            "",
            "## Python Modules",
            "",
            "| Path | Module | Parser status | Docstring |",
            "| --- | --- | --- | --- |",
        ]
    )
    if python["modules"]:
        lines.extend(
            "| "
            f"`{module['path']}` | "
            f"`{module['module_name']}` | "
            f"{module['parser_status']} | "
            f"{_md_cell(module['docstring_summary'] or '')} |"
            for module in python["modules"]
        )
    else:
        lines.append("| Not detected |  | not_parsed |  |")

    lines.extend(
        [
            "",
            "## Python Symbols",
            "",
            "| Path | Kind | Qualified name | Lines | Decorators | Bases | Docstring |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    if python["symbols"]:
        lines.extend(
            "| "
            f"`{symbol['path']}` | "
            f"{symbol['kind']} | "
            f"`{symbol['qualified_name']}` | "
            f"{symbol['start_line']}-{symbol['end_line']} | "
            f"{_md_cell(_join_list(symbol['decorators']))} | "
            f"{_md_cell(_join_list(symbol['bases']))} | "
            f"{_md_cell(symbol['docstring_summary'] or '')} |"
            for symbol in python["symbols"]
        )
    else:
        lines.append("| Not detected |  |  |  |  |  |  |")

    lines.extend(
        [
            "",
            "## Python Imports",
            "",
            "| Path | Import | Root | Classification | Line |",
            "| --- | --- | --- | --- | ---: |",
        ]
    )
    if python["imports"]:
        lines.extend(
            "| "
            f"`{import_fact['path']}` | "
            f"`{_python_import_display(import_fact)}` | "
            f"`{import_fact['root_name']}` | "
            f"{import_fact['classification']} | "
            f"{import_fact['line']} |"
            for import_fact in python["imports"]
        )
    else:
        lines.append("| Not detected |  |  |  | 0 |")

    lines.extend(
        [
            "",
            "## Python Packages",
            "",
            "| Name | Classification | Inferred |",
            "| --- | --- | --- |",
        ]
    )
    if python["packages"]:
        lines.extend(
            f"| `{package['name']}` | {package['classification']} | {package['inferred']} |"
            for package in python["packages"]
        )
    else:
        lines.append("| Not detected |  | false |")

    lines.extend(
        [
            "",
            "## JavaScript Modules",
            "",
            "| Path | Module | Extension | Parser status |",
            "| --- | --- | --- | --- |",
        ]
    )
    if javascript["modules"]:
        lines.extend(
            "| "
            f"`{module['path']}` | "
            f"`{module['module_name']}` | "
            f"`{module['extension']}` | "
            f"{module['parser_status']} |"
            for module in javascript["modules"]
        )
    else:
        lines.append("| Not detected |  |  | not_parsed |")

    lines.extend(
        [
            "",
            "## JavaScript Symbols",
            "",
            "| Path | Kind | Qualified name | Lines |",
            "| --- | --- | --- | --- |",
        ]
    )
    if javascript["symbols"]:
        lines.extend(
            "| "
            f"`{symbol['path']}` | "
            f"{symbol['kind']} | "
            f"`{symbol['qualified_name']}` | "
            f"{symbol['start_line']}-{symbol['end_line']} |"
            for symbol in javascript["symbols"]
        )
    else:
        lines.append("| Not detected |  |  |  |")

    lines.extend(
        [
            "",
            "## JavaScript Imports",
            "",
            "| Path | Import | Root | Classification | Resolved path | Resolution | Line |",
            "| --- | --- | --- | --- | --- | --- | ---: |",
        ]
    )
    if javascript["imports"]:
        lines.extend(
            "| "
            f"`{import_fact['path']}` | "
            f"`{_javascript_import_display(import_fact)}` | "
            f"`{import_fact['root_name'] or ''}` | "
            f"{import_fact['classification']} | "
            f"`{import_fact['resolved_path'] or ''}` | "
            f"{import_fact['resolution_status']} | "
            f"{import_fact['line']} |"
            for import_fact in javascript["imports"]
        )
    else:
        lines.append("| Not detected |  |  |  |  |  | 0 |")

    lines.extend(
        [
            "",
            "## JavaScript Packages",
            "",
            "| Name | Classification |",
            "| --- | --- |",
        ]
    )
    if javascript["packages"]:
        lines.extend(
            f"| `{package['name']}` | {package['classification']} |"
            for package in javascript["packages"]
        )
    else:
        lines.append("| Not detected |  |")

    lines.extend(
        [
            "",
            "## JavaScript Exports",
            "",
            "| Path | Kind | Exported name | Local name | Line |",
            "| --- | --- | --- | --- | ---: |",
        ]
    )
    if javascript["exports"]:
        lines.extend(
            "| "
            f"`{export['path']}` | "
            f"{export['kind']} | "
            f"`{export['exported_name']}` | "
            f"`{export['local_name'] or ''}` | "
            f"{export['line']} |"
            for export in javascript["exports"]
        )
    else:
        lines.append("| Not detected |  |  |  | 0 |")

    lines.extend(
        [
            "",
            "## JavaScript CommonJS Assignments",
            "",
            "| Path | Kind | Exported name | Assigned name | Line |",
            "| --- | --- | --- | --- | ---: |",
        ]
    )
    if javascript["commonjs_assignments"]:
        lines.extend(
            "| "
            f"`{assignment['path']}` | "
            f"{assignment['kind']} | "
            f"`{assignment['exported_name']}` | "
            f"`{assignment['assigned_name'] or ''}` | "
            f"{assignment['line']} |"
            for assignment in javascript["commonjs_assignments"]
        )
    else:
        lines.append("| Not detected |  |  |  | 0 |")

    lines.extend(
        [
            "",
            "## Config Files",
            "",
            "| Path | Kind | Format | Parser status | Top-level keys |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    if config["config_files"]:
        lines.extend(
            "| "
            f"`{config_file['path']}` | "
            f"{config_file['config_kind']} | "
            f"{config_file['format']} | "
            f"{config_file['parser_status']} | "
            f"{_md_cell(_join_list(config_file['top_level_keys']))} |"
            for config_file in config["config_files"]
        )
    else:
        lines.append("| Not detected |  |  | not_parsed |  |")

    lines.extend(
        [
            "",
            "## Config Package Managers",
            "",
            "| Source | Ecosystem | Manager | Evidence |",
            "| --- | --- | --- | --- |",
        ]
    )
    if config["package_managers"]:
        lines.extend(
            "| "
            f"`{manager['source_path']}` | "
            f"{manager['ecosystem']} | "
            f"`{manager['name']}` | "
            f"{manager['evidence_kind']} |"
            for manager in config["package_managers"]
        )
    else:
        lines.append("| Not detected |  |  |  |")

    lines.extend(
        [
            "",
            "## Config Packages",
            "",
            "| Source | Ecosystem | Classification | Name | Dependency type | Version |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    if config["packages"]:
        lines.extend(
            "| "
            f"`{package['source_path']}` | "
            f"{package['ecosystem']} | "
            f"{package['classification']} | "
            f"`{package['name']}` | "
            f"{package['dependency_type']} | "
            f"{_md_cell(package['version_constraint'] or '')} |"
            for package in config["packages"]
        )
    else:
        lines.append("| Not detected |  |  |  |  |  |")

    lines.extend(
        [
            "",
            "## Config Package Roots",
            "",
            "| Source | Ecosystem | Name | Root |",
            "| --- | --- | --- | --- |",
        ]
    )
    if config["package_roots"]:
        lines.extend(
            "| "
            f"`{package_root['source_path']}` | "
            f"{package_root['ecosystem']} | "
            f"`{package_root['name']}` | "
            f"`{package_root['path']}` |"
            for package_root in config["package_roots"]
        )
    else:
        lines.append("| Not detected |  |  |  |")

    lines.extend(
        [
            "",
            "## Config Lockfiles",
            "",
            "| Path | Ecosystem | Manager | Format |",
            "| --- | --- | --- | --- |",
        ]
    )
    if config["lockfiles"]:
        lines.extend(
            "| "
            f"`{lockfile['path']}` | "
            f"{lockfile['ecosystem']} | "
            f"{lockfile['manager']} | "
            f"{lockfile['format']} |"
            for lockfile in config["lockfiles"]
        )
    else:
        lines.append("| Not detected |  |  |  |")

    lines.extend(
        [
            "",
            "## Config Commands",
            "",
            "| Path | Source | Name | Purpose | Command | Not run | Auto-run recommended |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    if config["commands"]:
        lines.extend(
            "| "
            f"`{command['path']}` | "
            f"{command['source']} | "
            f"`{command['name']}` | "
            f"{command['purpose']} | "
            f"`{_md_cell(command['command'])}` | "
            f"{command['not_run']} | "
            f"{command['auto_run_recommended']} |"
            for command in config["commands"]
        )
    else:
        lines.append("| Not detected |  |  |  |  | true | false |")

    lines.extend(
        [
            "",
            "## Config Entrypoints",
            "",
            "| Path | Kind | Name | Target | Evidence | Line |",
            "| --- | --- | --- | --- | --- | ---: |",
        ]
    )
    if config["entrypoints"]:
        lines.extend(
            "| "
            f"`{entrypoint['path']}` | "
            f"{entrypoint['kind']} | "
            f"`{entrypoint['name']}` | "
            f"`{_md_cell(entrypoint['target'])}` | "
            f"{_md_cell(entrypoint['evidence'])} | "
            f"{entrypoint['line'] or ''} |"
            for entrypoint in config["entrypoints"]
        )
    else:
        lines.append("| Not detected |  |  |  |  |  |")

    lines.extend(
        [
            "",
            "## Config Parse Errors",
            "",
            "| Path | Message |",
            "| --- | --- |",
        ]
    )
    if config["parse_errors"]:
        lines.extend(
            f"| `{error['path']}` | {error['message']} |" for error in config["parse_errors"]
        )
    else:
        lines.append("| Not detected |  |")

    lines.extend(
        [
            "",
            "## Python Tagged Comments",
            "",
            "| Path | Tag | Text | Line |",
            "| --- | --- | --- | ---: |",
        ]
    )
    if python["tagged_comments"]:
        lines.extend(
            "| "
            f"`{comment['path']}` | "
            f"{comment['tag']} | "
            f"{_md_cell(comment['text'])} | "
            f"{comment['line']} |"
            for comment in python["tagged_comments"]
        )
    else:
        lines.append("| Not detected |  |  | 0 |")

    lines.extend(
        [
            "",
            "## Python Same-Module Calls",
            "",
            "| Path | Caller | Callee | Line | Confidence |",
            "| --- | --- | --- | ---: | --- |",
        ]
    )
    if python["calls"]:
        lines.extend(
            "| "
            f"`{call['path']}` | "
            f"`{symbol_labels.get(call['caller_id'], call['caller_id'])}` | "
            f"`{symbol_labels.get(call['callee_id'], call['callee_name'])}` | "
            f"{call['line']} | "
            f"{call['confidence']} |"
            for call in python["calls"]
        )
    else:
        lines.append("| Not detected |  |  | 0 |  |")

    lines.extend(
        [
            "",
            "## Python Parse Errors",
            "",
            "| Path | Message | Line | Column |",
            "| --- | --- | ---: | ---: |",
        ]
    )
    if python["parse_errors"]:
        lines.extend(
            "| "
            f"`{error['path']}` | "
            f"{_md_cell(error['message'])} | "
            f"{error['line'] or ''} | "
            f"{error['column'] or ''} |"
            for error in python["parse_errors"]
        )
    else:
        lines.append("| Not detected |  |  |  |")

    lines.extend(
        [
            "",
            "## Skipped Paths",
            "",
            "| Reason | Count |",
            "| --- | ---: |",
        ]
    )
    if snapshot["skip_reasons"]:
        lines.extend(
            f"| {reason} | {count} |" for reason, count in snapshot["skip_reasons"].items()
        )
    else:
        lines.append("| None | 0 |")

    lines.extend(
        [
            "",
            "## Assistant Notes",
            "",
            "Python source facts are extracted with the standard library AST when files parse successfully.",
            "JavaScript and TypeScript facts are extracted with a bounded pure-Python scanner.",
            "Config facts are shallow, evidence-backed, and candidate commands are not executed.",
            "Deep semantic call graphs, runtime imports, deep lockfile parsing, and impact analysis are not detected yet.",
            "",
        ]
    )
    return "\n".join(lines)


def _graph_index_text(snapshot: dict[str, Any]) -> str:
    python = snapshot["python"]
    javascript = snapshot["javascript"]
    config = snapshot["config"]
    documentation = snapshot["documentation"]
    lines = [
        "# RepoLens Graph Index",
        "",
        f"Indexed at UTC: {snapshot['run']['indexed_at_utc']}",
        "",
        "## Directories",
        "",
        "| Path | Node ID | Parent |",
        "| --- | --- | --- |",
    ]
    lines.extend(
        f"| `{directory['path']}` | `{directory['node_id']}` | `{directory['parent_path'] or ''}` |"
        for directory in snapshot["directories"]
    )
    lines.extend(
        [
            "",
            "## Files",
            "",
            "| Path | Node ID | Size bytes | Parser status |",
            "| --- | --- | ---: | --- |",
        ]
    )
    lines.extend(
        f"| `{file['path']}` | `{file['node_id']}` | {file['size_bytes']} | {file['parser_status']} |"
        for file in snapshot["files"]
    )
    lines.extend(_documentation_index_lines(documentation))
    lines.extend(
        [
            "",
            "## Python Modules",
            "",
            "| Path | Node ID | Module | Parser status |",
            "| --- | --- | --- | --- |",
        ]
    )
    if python["modules"]:
        lines.extend(
            f"| `{module['path']}` | `{module['node_id']}` | `{module['module_name']}` | {module['parser_status']} |"
            for module in python["modules"]
        )
    else:
        lines.append("| Not detected |  |  | not_parsed |")

    lines.extend(
        [
            "",
            "## Python Symbols",
            "",
            "| Node ID | Path | Kind | Qualified name | Lines |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    if python["symbols"]:
        lines.extend(
            "| "
            f"`{symbol['id']}` | "
            f"`{symbol['path']}` | "
            f"{symbol['kind']} | "
            f"`{symbol['qualified_name']}` | "
            f"{symbol['start_line']}-{symbol['end_line']} |"
            for symbol in python["symbols"]
        )
    else:
        lines.append("| Not detected |  |  |  |  |")

    lines.extend(
        [
            "",
            "## Python Imports",
            "",
            "| Fact ID | Path | Import | Root | Classification | Line |",
            "| --- | --- | --- | --- | --- | ---: |",
        ]
    )
    if python["imports"]:
        lines.extend(
            "| "
            f"`{import_fact['id']}` | "
            f"`{import_fact['path']}` | "
            f"`{_python_import_display(import_fact)}` | "
            f"`{import_fact['root_name']}` | "
            f"{import_fact['classification']} | "
            f"{import_fact['line']} |"
            for import_fact in python["imports"]
        )
    else:
        lines.append("| Not detected |  |  |  |  | 0 |")

    lines.extend(
        [
            "",
            "## Python Packages",
            "",
            "| Node ID | Name | Classification | Inferred |",
            "| --- | --- | --- | --- |",
        ]
    )
    if python["packages"]:
        lines.extend(
            "| "
            f"`{package['id']}` | "
            f"`{package['name']}` | "
            f"{package['classification']} | "
            f"{package['inferred']} |"
            for package in python["packages"]
        )
    else:
        lines.append("| Not detected |  |  | false |")

    lines.extend(
        [
            "",
            "## JavaScript Modules",
            "",
            "| Path | Node ID | Module | Extension | Parser status |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    if javascript["modules"]:
        lines.extend(
            "| "
            f"`{module['path']}` | "
            f"`{module['node_id']}` | "
            f"`{module['module_name']}` | "
            f"`{module['extension']}` | "
            f"{module['parser_status']} |"
            for module in javascript["modules"]
        )
    else:
        lines.append("| Not detected |  |  |  | not_parsed |")

    lines.extend(
        [
            "",
            "## JavaScript Symbols",
            "",
            "| Node ID | Path | Kind | Qualified name | Lines |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    if javascript["symbols"]:
        lines.extend(
            "| "
            f"`{symbol['id']}` | "
            f"`{symbol['path']}` | "
            f"{symbol['kind']} | "
            f"`{symbol['qualified_name']}` | "
            f"{symbol['start_line']}-{symbol['end_line']} |"
            for symbol in javascript["symbols"]
        )
    else:
        lines.append("| Not detected |  |  |  |  |")

    lines.extend(
        [
            "",
            "## JavaScript Imports",
            "",
            "| Fact ID | Path | Kind | Specifier | Root | Classification | Resolved path | Resolution | Line |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | ---: |",
        ]
    )
    if javascript["imports"]:
        lines.extend(
            "| "
            f"`{import_fact['id']}` | "
            f"`{import_fact['path']}` | "
            f"{import_fact['kind']} | "
            f"`{import_fact['specifier']}` | "
            f"`{import_fact['root_name'] or ''}` | "
            f"{import_fact['classification']} | "
            f"`{import_fact['resolved_path'] or ''}` | "
            f"{import_fact['resolution_status']} | "
            f"{import_fact['line']} |"
            for import_fact in javascript["imports"]
        )
    else:
        lines.append("| Not detected |  |  |  |  |  |  |  | 0 |")

    lines.extend(
        [
            "",
            "## JavaScript Packages",
            "",
            "| Node ID | Name | Classification |",
            "| --- | --- | --- |",
        ]
    )
    if javascript["packages"]:
        lines.extend(
            f"| `{package['id']}` | `{package['name']}` | {package['classification']} |"
            for package in javascript["packages"]
        )
    else:
        lines.append("| Not detected |  |  |")

    lines.extend(
        [
            "",
            "## JavaScript Exports",
            "",
            "| Fact ID | Path | Kind | Exported name | Local name | Line |",
            "| --- | --- | --- | --- | --- | ---: |",
        ]
    )
    if javascript["exports"]:
        lines.extend(
            "| "
            f"`{export['id']}` | "
            f"`{export['path']}` | "
            f"{export['kind']} | "
            f"`{export['exported_name']}` | "
            f"`{export['local_name'] or ''}` | "
            f"{export['line']} |"
            for export in javascript["exports"]
        )
    else:
        lines.append("| Not detected |  |  |  |  | 0 |")

    lines.extend(
        [
            "",
            "## JavaScript CommonJS Assignments",
            "",
            "| Fact ID | Path | Kind | Exported name | Assigned name | Line |",
            "| --- | --- | --- | --- | --- | ---: |",
        ]
    )
    if javascript["commonjs_assignments"]:
        lines.extend(
            "| "
            f"`{assignment['id']}` | "
            f"`{assignment['path']}` | "
            f"{assignment['kind']} | "
            f"`{assignment['exported_name']}` | "
            f"`{assignment['assigned_name'] or ''}` | "
            f"{assignment['line']} |"
            for assignment in javascript["commonjs_assignments"]
        )
    else:
        lines.append("| Not detected |  |  |  |  | 0 |")

    lines.extend(
        [
            "",
            "## Config Files",
            "",
            "| Path | Node ID | Kind | Format | Parser status | Top-level keys |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    if config["config_files"]:
        lines.extend(
            "| "
            f"`{config_file['path']}` | "
            f"`{config_file['node_id']}` | "
            f"{config_file['config_kind']} | "
            f"{config_file['format']} | "
            f"{config_file['parser_status']} | "
            f"{_md_cell(_join_list(config_file['top_level_keys']))} |"
            for config_file in config["config_files"]
        )
    else:
        lines.append("| Not detected |  |  |  | not_parsed |  |")

    lines.extend(
        [
            "",
            "## Config Package Managers",
            "",
            "| Node ID | Source | Ecosystem | Manager | Evidence |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    if config["package_managers"]:
        lines.extend(
            "| "
            f"`{manager['id']}` | "
            f"`{manager['source_path']}` | "
            f"{manager['ecosystem']} | "
            f"`{manager['name']}` | "
            f"{manager['evidence_kind']} |"
            for manager in config["package_managers"]
        )
    else:
        lines.append("| Not detected |  |  |  |  |")

    lines.extend(
        [
            "",
            "## Config Packages",
            "",
            "| Node ID | Source | Ecosystem | Classification | Name | Dependency type | Version |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    if config["packages"]:
        lines.extend(
            "| "
            f"`{package['id']}` | "
            f"`{package['source_path']}` | "
            f"{package['ecosystem']} | "
            f"{package['classification']} | "
            f"`{package['name']}` | "
            f"{package['dependency_type']} | "
            f"{_md_cell(package['version_constraint'] or '')} |"
            for package in config["packages"]
        )
    else:
        lines.append("| Not detected |  |  |  |  |  |  |")

    lines.extend(
        [
            "",
            "## Config Package Roots",
            "",
            "| Node ID | Source | Ecosystem | Name | Root |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    if config["package_roots"]:
        lines.extend(
            "| "
            f"`{package_root['id']}` | "
            f"`{package_root['source_path']}` | "
            f"{package_root['ecosystem']} | "
            f"`{package_root['name']}` | "
            f"`{package_root['path']}` |"
            for package_root in config["package_roots"]
        )
    else:
        lines.append("| Not detected |  |  |  |  |")

    lines.extend(
        [
            "",
            "## Config Lockfiles",
            "",
            "| Node ID | Path | Ecosystem | Manager | Format |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    if config["lockfiles"]:
        lines.extend(
            "| "
            f"`{lockfile['id']}` | "
            f"`{lockfile['path']}` | "
            f"{lockfile['ecosystem']} | "
            f"{lockfile['manager']} | "
            f"{lockfile['format']} |"
            for lockfile in config["lockfiles"]
        )
    else:
        lines.append("| Not detected |  |  |  |  |")

    lines.extend(
        [
            "",
            "## Config Commands",
            "",
            "| Node ID | Path | Source | Name | Purpose | Command | Not run | Auto-run recommended |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    if config["commands"]:
        lines.extend(
            "| "
            f"`{command['id']}` | "
            f"`{command['path']}` | "
            f"{command['source']} | "
            f"`{command['name']}` | "
            f"{command['purpose']} | "
            f"`{_md_cell(command['command'])}` | "
            f"{command['not_run']} | "
            f"{command['auto_run_recommended']} |"
            for command in config["commands"]
        )
    else:
        lines.append("| Not detected |  |  |  |  |  | true | false |")

    lines.extend(
        [
            "",
            "## Config Entrypoints",
            "",
            "| Node ID | Path | Kind | Name | Target | Evidence | Line |",
            "| --- | --- | --- | --- | --- | --- | ---: |",
        ]
    )
    if config["entrypoints"]:
        lines.extend(
            "| "
            f"`{entrypoint['id']}` | "
            f"`{entrypoint['path']}` | "
            f"{entrypoint['kind']} | "
            f"`{entrypoint['name']}` | "
            f"`{_md_cell(entrypoint['target'])}` | "
            f"{_md_cell(entrypoint['evidence'])} | "
            f"{entrypoint['line'] or ''} |"
            for entrypoint in config["entrypoints"]
        )
    else:
        lines.append("| Not detected |  |  |  |  |  |  |")

    lines.extend(
        [
            "",
            "## Config Parse Errors",
            "",
            "| Node ID | Path | Message |",
            "| --- | --- | --- |",
        ]
    )
    if config["parse_errors"]:
        lines.extend(
            f"| `{error['id']}` | `{error['path']}` | {error['message']} |"
            for error in config["parse_errors"]
        )
    else:
        lines.append("| Not detected |  |  |")

    lines.extend(
        [
            "",
            "## Python Tagged Comments",
            "",
            "| Node ID | Path | Tag | Text | Line |",
            "| --- | --- | --- | --- | ---: |",
        ]
    )
    if python["tagged_comments"]:
        lines.extend(
            "| "
            f"`{comment['id']}` | "
            f"`{comment['path']}` | "
            f"{comment['tag']} | "
            f"{_md_cell(comment['text'])} | "
            f"{comment['line']} |"
            for comment in python["tagged_comments"]
        )
    else:
        lines.append("| Not detected |  |  |  | 0 |")

    lines.extend(
        [
            "",
            "## Python Same-Module Calls",
            "",
            "| Fact ID | Path | Caller ID | Callee ID | Callee | Line |",
            "| --- | --- | --- | --- | --- | ---: |",
        ]
    )
    if python["calls"]:
        lines.extend(
            "| "
            f"`{call['id']}` | "
            f"`{call['path']}` | "
            f"`{call['caller_id']}` | "
            f"`{call['callee_id']}` | "
            f"`{call['callee_name']}` | "
            f"{call['line']} |"
            for call in python["calls"]
        )
    else:
        lines.append("| Not detected |  |  |  |  | 0 |")

    lines.extend(
        [
            "",
            "## Python Parse Errors",
            "",
            "| Node ID | Path | Message | Line | Column |",
            "| --- | --- | --- | ---: | ---: |",
        ]
    )
    if python["parse_errors"]:
        lines.extend(
            "| "
            f"`{error['id']}` | "
            f"`{error['path']}` | "
            f"{_md_cell(error['message'])} | "
            f"{error['line'] or ''} | "
            f"{error['column'] or ''} |"
            for error in python["parse_errors"]
        )
    else:
        lines.append("| Not detected |  |  |  |  |")

    lines.extend(
        [
            "",
            "## Skipped Paths",
            "",
            "| Path | Reason |",
            "| --- | --- |",
        ]
    )
    if snapshot["skipped_paths"]:
        lines.extend(
            f"| `{skipped['path']}` | {skipped['reason']} |"
            for skipped in snapshot["skipped_paths"]
        )
    else:
        lines.append("| None | none |")
    lines.append("")
    return "\n".join(lines)


def _documentation_report_lines(documentation: dict[str, Any]) -> list[str]:
    lines = [
        "",
        "## Documentation Files",
        "",
        "| Path | Kind | Importance | Parser status | Title | Intro |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if documentation["files"]:
        lines.extend(
            "| "
            f"`{markdown['path']}` | "
            f"{markdown['doc_kind']} | "
            f"{markdown['importance']} | "
            f"{markdown['parser_status']} | "
            f"{_md_cell(markdown['title'] or '')} | "
            f"{_md_cell(markdown['intro'] or '')} |"
            for markdown in documentation["files"]
        )
    else:
        lines.append("| Not detected |  |  | not_parsed |  |  |")

    lines.extend(
        [
            "",
            "## Markdown Headings",
            "",
            "| Path | Heading ID | Level | Text | Line |",
            "| --- | --- | ---: | --- | ---: |",
        ]
    )
    if documentation["headings"]:
        lines.extend(
            "| "
            f"`{heading['path']}` | "
            f"`{heading['heading_id']}` | "
            f"{heading['level']} | "
            f"{_md_cell(heading['text'])} | "
            f"{heading['line']} |"
            for heading in documentation["headings"]
        )
    else:
        lines.append("| Not detected |  | 0 |  | 0 |")

    lines.extend(
        [
            "",
            "## Markdown Links",
            "",
            "| Path | Label | Target | Fragment | Line |",
            "| --- | --- | --- | --- | ---: |",
        ]
    )
    if documentation["links"]:
        lines.extend(
            "| "
            f"`{link['path']}` | "
            f"{_md_cell(link['label'])} | "
            f"`{link['target_path']}` | "
            f"`{link['target_fragment'] or ''}` | "
            f"{link['line']} |"
            for link in documentation["links"]
        )
    else:
        lines.append("| Not detected |  |  |  | 0 |")

    lines.extend(
        [
            "",
            "## Markdown Path Mentions",
            "",
            "| Path | Mention | Target | Line |",
            "| --- | --- | --- | ---: |",
        ]
    )
    if documentation["path_mentions"]:
        lines.extend(
            "| "
            f"`{mention['path']}` | "
            f"`{mention['mentioned_path']}` | "
            f"`{mention['target_path']}` | "
            f"{mention['line']} |"
            for mention in documentation["path_mentions"]
        )
    else:
        lines.append("| Not detected |  |  | 0 |")

    lines.extend(
        [
            "",
            "## Markdown Code Fences",
            "",
            "| Path | Language | Info string | Lines |",
            "| --- | --- | --- | --- |",
        ]
    )
    if documentation["code_fences"]:
        lines.extend(
            "| "
            f"`{fence['path']}` | "
            f"`{fence['language'] or ''}` | "
            f"`{_md_cell(fence['info_string'])}` | "
            f"{fence['start_line']}-{fence['end_line'] or ''} |"
            for fence in documentation["code_fences"]
        )
    else:
        lines.append("| Not detected |  |  |  |")

    lines.extend(
        [
            "",
            "## Documentation Tagged Comments",
            "",
            "| Path | Language | Syntax | Tag | Text | Line |",
            "| --- | --- | --- | --- | --- | ---: |",
        ]
    )
    if documentation["tagged_comments"]:
        lines.extend(
            "| "
            f"`{comment['path']}` | "
            f"{comment['language']} | "
            f"{comment['syntax']} | "
            f"{comment['tag']} | "
            f"{_md_cell(comment['text'])} | "
            f"{comment['line']} |"
            for comment in documentation["tagged_comments"]
        )
    else:
        lines.append("| Not detected |  |  |  |  | 0 |")

    lines.extend(
        [
            "",
            "## Skills",
            "",
            "| Path | Name | Description |",
            "| --- | --- | --- |",
        ]
    )
    if documentation["skills"]:
        lines.extend(
            f"| `{skill['path']}` | `{skill['name']}` | {_md_cell(skill['description'] or '')} |"
            for skill in documentation["skills"]
        )
    else:
        lines.append("| Not detected |  |  |")
    return lines


def _documentation_index_lines(documentation: dict[str, Any]) -> list[str]:
    lines = [
        "",
        "## Documentation Files",
        "",
        "| Path | Node ID | Kind | Importance | Parser status | Title |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if documentation["files"]:
        lines.extend(
            "| "
            f"`{markdown['path']}` | "
            f"`{markdown['node_id']}` | "
            f"{markdown['doc_kind']} | "
            f"{markdown['importance']} | "
            f"{markdown['parser_status']} | "
            f"{_md_cell(markdown['title'] or '')} |"
            for markdown in documentation["files"]
        )
    else:
        lines.append("| Not detected |  |  |  | not_parsed |  |")

    lines.extend(
        [
            "",
            "## Markdown Headings",
            "",
            "| Node ID | Path | Heading ID | Level | Text | Line |",
            "| --- | --- | --- | ---: | --- | ---: |",
        ]
    )
    if documentation["headings"]:
        lines.extend(
            "| "
            f"`{heading['id']}` | "
            f"`{heading['path']}` | "
            f"`{heading['heading_id']}` | "
            f"{heading['level']} | "
            f"{_md_cell(heading['text'])} | "
            f"{heading['line']} |"
            for heading in documentation["headings"]
        )
    else:
        lines.append("| Not detected |  |  | 0 |  | 0 |")

    lines.extend(
        [
            "",
            "## Markdown Links",
            "",
            "| Fact ID | Path | Label | Target | Fragment | Line |",
            "| --- | --- | --- | --- | --- | ---: |",
        ]
    )
    if documentation["links"]:
        lines.extend(
            "| "
            f"`{link['id']}` | "
            f"`{link['path']}` | "
            f"{_md_cell(link['label'])} | "
            f"`{link['target_path']}` | "
            f"`{link['target_fragment'] or ''}` | "
            f"{link['line']} |"
            for link in documentation["links"]
        )
    else:
        lines.append("| Not detected |  |  |  |  | 0 |")

    lines.extend(
        [
            "",
            "## Markdown Path Mentions",
            "",
            "| Fact ID | Path | Mention | Target | Line |",
            "| --- | --- | --- | --- | ---: |",
        ]
    )
    if documentation["path_mentions"]:
        lines.extend(
            "| "
            f"`{mention['id']}` | "
            f"`{mention['path']}` | "
            f"`{mention['mentioned_path']}` | "
            f"`{mention['target_path']}` | "
            f"{mention['line']} |"
            for mention in documentation["path_mentions"]
        )
    else:
        lines.append("| Not detected |  |  |  | 0 |")

    lines.extend(
        [
            "",
            "## Markdown Code Fences",
            "",
            "| Node ID | Path | Language | Info string | Lines |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    if documentation["code_fences"]:
        lines.extend(
            "| "
            f"`{fence['id']}` | "
            f"`{fence['path']}` | "
            f"`{fence['language'] or ''}` | "
            f"`{_md_cell(fence['info_string'])}` | "
            f"{fence['start_line']}-{fence['end_line'] or ''} |"
            for fence in documentation["code_fences"]
        )
    else:
        lines.append("| Not detected |  |  |  |  |")

    lines.extend(
        [
            "",
            "## Documentation Tagged Comments",
            "",
            "| Node ID | Path | Language | Syntax | Tag | Text | Line |",
            "| --- | --- | --- | --- | --- | --- | ---: |",
        ]
    )
    if documentation["tagged_comments"]:
        lines.extend(
            "| "
            f"`{comment['id']}` | "
            f"`{comment['path']}` | "
            f"{comment['language']} | "
            f"{comment['syntax']} | "
            f"{comment['tag']} | "
            f"{_md_cell(comment['text'])} | "
            f"{comment['line']} |"
            for comment in documentation["tagged_comments"]
        )
    else:
        lines.append("| Not detected |  |  |  |  |  | 0 |")

    lines.extend(
        [
            "",
            "## Skills",
            "",
            "| Node ID | Path | Name | Description |",
            "| --- | --- | --- | --- |",
        ]
    )
    if documentation["skills"]:
        lines.extend(
            "| "
            f"`{skill['id']}` | "
            f"`{skill['path']}` | "
            f"`{skill['name']}` | "
            f"{_md_cell(skill['description'] or '')} |"
            for skill in documentation["skills"]
        )
    else:
        lines.append("| Not detected |  |  |  |")
    return lines


def _atomic_write_text(target: Path, content: str) -> None:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            delete=False,
            dir=str(target.parent),
            encoding="utf-8",
            prefix=f"{target.name}-",
            suffix=".tmp",
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(content)
        os.replace(temp_path, target)
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _ensure_supported_schema(connection: sqlite3.Connection) -> None:
    schema_version = _schema_version(connection)
    if schema_version != str(GRAPH_SCHEMA_VERSION):
        raise GraphStoreError("unsupported_schema_version")


def _validate_graph_store(connection: sqlite3.Connection) -> dict[str, list[str]]:
    hard_failures: list[str] = []
    metadata = _metadata(connection)

    if metadata.get("schema_name") != GRAPH_SCHEMA_NAME:
        hard_failures.append("invalid_schema_name")
    if metadata.get("schema_version") != str(GRAPH_SCHEMA_VERSION):
        hard_failures.append("invalid_schema_version")
    if metadata.get("canonical_graph_hash") != _canonical_graph_hash(connection):
        hard_failures.append("canonical_graph_hash_mismatch")

    for table, expected_count in (("repositories", 1), ("runs", 1)):
        count = _table_count(connection, table)
        if count != expected_count:
            hard_failures.append(f"invalid_{table}_count")

    if _table_count(connection, "nodes") == 0:
        hard_failures.append("missing_nodes")

    invalid_paths = _invalid_repo_paths(connection)
    if invalid_paths:
        hard_failures.append("invalid_repo_relative_paths")

    invalid_edge_contracts = _invalid_edge_contracts(connection)
    if invalid_edge_contracts:
        hard_failures.append("invalid_edge_contracts")

    return {"hard_failures": hard_failures, "quality_warnings": _quality_warnings(connection)}


def _canonical_graph_hash(connection: sqlite3.Connection) -> str:
    facts: list[dict[str, object]] = []

    facts.extend(
        {
            "kind": "directory",
            "node_id": row["node_id"],
            "parent_path": row["parent_path"],
            "path": row["path"],
        }
        for row in connection.execute(
            "SELECT path, node_id, parent_path FROM directories ORDER BY path"
        )
    )
    facts.extend(
        {
            "graph_hash": row["graph_hash"],
            "kind": "file",
            "language": row["language"],
            "node_id": row["node_id"],
            "parser_status": row["parser_status"],
            "path": row["path"],
        }
        for row in connection.execute(
            "SELECT path, node_id, language, parser_status, graph_hash FROM files ORDER BY path"
        )
    )
    facts.extend(
        {
            "id": row["id"],
            "kind": "node",
            "label": row["label"],
            "metadata": _stable_graph_value(json.loads(row["metadata_json"])),
            "node_kind": row["kind"],
            "path": row["path"],
        }
        for row in connection.execute(
            "SELECT id, kind, path, label, metadata_json FROM nodes ORDER BY id"
        )
    )
    facts.extend(
        {
            "confidence": row["confidence"],
            "kind": "edge",
            "edge_kind": row["kind"],
            "metadata": _stable_graph_value(json.loads(row["metadata_json"])),
            "resolution_strategy": row["resolution_strategy"],
            "source_id": row["source_id"],
            "target_id": row["target_id"],
        }
        for row in connection.execute(
            """
            SELECT source_id, target_id, kind, confidence, resolution_strategy, metadata_json
            FROM edges
            ORDER BY source_id, kind, target_id
            """
        )
    )
    return _facts_hash(facts)


def _stable_graph_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _stable_graph_value(child)
            for key, child in sorted(value.items())
            if key
            not in {
                "end_line",
                "import_ids",
                "line",
                "lines",
                "raw_hash",
                "size_bytes",
                "start_line",
            }
        }
    if isinstance(value, list):
        return [_stable_graph_value(child) for child in value]
    return value


def _quality_warnings(connection: sqlite3.Connection) -> list[str]:
    warnings: list[str] = []
    parse_error_count = sum(
        _table_count(connection, table) for table in ("python_parse_errors", "config_parse_errors")
    )
    if parse_error_count:
        warnings.append(PARSER_ERROR_WARNING)
    return warnings


def _metadata_quality_warnings(metadata: dict[str, str]) -> list[str]:
    raw_warnings = metadata.get("graph_quality_warnings")
    if raw_warnings is None:
        return []
    try:
        warnings = json.loads(raw_warnings)
    except json.JSONDecodeError:
        return ["Graph quality warnings metadata is unreadable."]
    if not isinstance(warnings, list):
        return []
    return [str(warning) for warning in warnings]


def _table_count(connection: sqlite3.Connection, table: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return int(row[0] if row is not None else 0)


def _invalid_repo_paths(connection: sqlite3.Connection) -> list[str]:
    paths: list[str] = []
    for table, column in (("directories", "path"), ("files", "path"), ("nodes", "path")):
        for row in connection.execute(f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL"):
            path = str(row[0])
            if (
                path.startswith("/")
                or path == ARTIFACT_DIR_NAME
                or path.startswith(f"{ARTIFACT_DIR_NAME}/")
            ):
                paths.append(path)
            elif ".." in PurePosixPath(path).parts:
                paths.append(path)
    return paths


def _invalid_edge_contracts(connection: sqlite3.Connection) -> list[str]:
    invalid: list[str] = []
    for row in connection.execute(
        "SELECT id, confidence, resolution_strategy, evidence_json FROM edges ORDER BY id"
    ):
        if str(row["confidence"]) not in CONFIDENCE_RANK:
            invalid.append(str(row["id"]))
            continue
        if not str(row["resolution_strategy"]).strip():
            invalid.append(str(row["id"]))
            continue
        try:
            evidence = json.loads(row["evidence_json"])
        except json.JSONDecodeError:
            invalid.append(str(row["id"]))
            continue
        if not isinstance(evidence, list):
            invalid.append(str(row["id"]))
    return invalid


def _read_graph_freshness_inputs(root: Path) -> tuple[dict[str, str], dict[str, FileState]]:
    with sqlite3.connect(root / GRAPH_STORE_PATH) as connection:
        connection.row_factory = sqlite3.Row
        metadata = _metadata(connection)
        rows = connection.execute(
            """
            SELECT
                path,
                size_bytes,
                mtime_ns,
                raw_hash,
                normalized_hash,
                graph_hash,
                dependency_hash,
                symbol_hash,
                line_range_hash,
                language,
                parser_status,
                indexed_at_utc
            FROM files
            ORDER BY path
            """
        ).fetchall()
    file_states = {}
    for row in rows:
        state = _file_state_from_row(row)
        file_states[state.path] = state
    return metadata, file_states


def _file_state_from_row(row: sqlite3.Row) -> FileState:
    return FileState(
        path=str(row["path"]),
        size_bytes=int(row["size_bytes"]),
        mtime_ns=int(row["mtime_ns"]),
        raw_hash=str(row["raw_hash"]),
        normalized_hash=str(row["normalized_hash"]),
        graph_hash=str(row["graph_hash"]),
        dependency_hash=str(row["dependency_hash"]),
        symbol_hash=str(row["symbol_hash"]),
        line_range_hash=str(row["line_range_hash"]),
        language=str(row["language"]),
        parser_status=str(row["parser_status"]),
        indexed_at_utc=str(row["indexed_at_utc"]),
    )


def _compute_live_freshness(
    root: Path,
    *,
    stored_metadata: dict[str, str],
    stored_file_states: dict[str, FileState],
) -> tuple[dict[str, Any], tuple[FileChange, ...]]:
    scan = scan_repository(root)
    files = tuple(sorted(scan.files, key=lambda scanned_file: scanned_file.path))
    extracted = _extract_indexes(root, files)
    current_states = _file_states_by_path(root, files, extracted, indexed_at_utc=_utc_now())
    file_changes = _classify_file_changes(stored_file_states, current_states)
    changed_files = tuple(change for change in file_changes if change.changed)
    indexed_git = _git_metadata_from_metadata(stored_metadata)
    current_git = _read_git_metadata(root)
    git_changed = _git_metadata_changed(indexed_git, current_git)

    fresh = not changed_files and not git_changed
    reason = (
        "graph_current"
        if fresh
        else "git_metadata_changed"
        if git_changed
        else "file_changes_detected"
    )
    status = "available" if fresh else "stale"
    freshness = {
        "change_counts": _change_counts(file_changes),
        "changed_files": [change.to_changed_file_dict() for change in changed_files],
        "effective_config_hash": {
            "current": _effective_config_hash(scan.max_file_size_bytes),
            "indexed": stored_metadata.get("effective_config_hash"),
        },
        "files": [change.to_status_dict() for change in file_changes],
        "fresh": fresh,
        "full_reparse_required": False,
        "git": {"current": current_git.to_payload(), "indexed": indexed_git.to_payload()},
        "reason": reason,
        "status": status,
    }
    return freshness, file_changes


def _classify_file_changes(
    old_states: dict[str, FileState], current_states: dict[str, FileState]
) -> tuple[FileChange, ...]:
    changes: list[FileChange] = []
    for path in sorted(set(old_states) | set(current_states)):
        old = old_states.get(path)
        current = current_states.get(path)
        if old is None and current is not None:
            changes.append(
                FileChange(
                    path=path,
                    change_type="new",
                    secondary_signals=_secondary_signals(None, current),
                    hashes=current.current_hash_payload(),
                    parser_status={"old": None, "current": current.parser_status},
                    size_bytes={"old": None, "current": current.size_bytes},
                    language={"old": None, "current": current.language},
                )
            )
            continue
        if old is not None and current is None:
            changes.append(
                FileChange(
                    path=path,
                    change_type="deleted",
                    secondary_signals=_secondary_signals(old, None),
                    hashes=old.hash_payload(None),
                    parser_status={"old": old.parser_status, "current": None},
                    size_bytes={"old": old.size_bytes, "current": None},
                    language={"old": old.language, "current": None},
                )
            )
            continue
        if old is None or current is None:
            continue

        signals = _secondary_signals(old, current)
        if current.parser_status == "parse_error":
            change_type = "parse_error"
        elif signals["dependency_changed"]:
            change_type = "dependency_change"
        elif signals["symbol_changed"] or signals["graph_changed"]:
            change_type = "structural_change"
        elif (
            signals["raw_content_changed"]
            or signals["normalized_content_changed"]
            or signals["line_range_changed"]
        ):
            change_type = "content_only_change"
        else:
            change_type = "no_change"
        changes.append(
            FileChange(
                path=path,
                change_type=change_type,
                secondary_signals=signals,
                hashes=old.hash_payload(current),
                parser_status={"old": old.parser_status, "current": current.parser_status},
                size_bytes={"old": old.size_bytes, "current": current.size_bytes},
                language={"old": old.language, "current": current.language},
            )
        )
    return tuple(changes)


def _secondary_signals(old: FileState | None, current: FileState | None) -> dict[str, bool]:
    if old is None or current is None:
        return {
            "dependency_changed": True,
            "graph_changed": True,
            "line_range_changed": True,
            "normalized_content_changed": True,
            "raw_content_changed": True,
            "symbol_changed": True,
        }
    return {
        "dependency_changed": old.dependency_hash != current.dependency_hash,
        "graph_changed": old.graph_hash != current.graph_hash,
        "line_range_changed": old.line_range_hash != current.line_range_hash,
        "normalized_content_changed": old.normalized_hash != current.normalized_hash,
        "raw_content_changed": old.raw_hash != current.raw_hash,
        "symbol_changed": old.symbol_hash != current.symbol_hash,
    }


def _change_counts(file_changes: tuple[FileChange, ...] | list[FileChange]) -> dict[str, int]:
    counts = {change_type: 0 for change_type in CHANGE_TYPES}
    counts.update(Counter(change.change_type for change in file_changes))
    return counts


def _freshness_warnings(file_changes: tuple[FileChange, ...]) -> tuple[str, ...]:
    if any(change.parser_status.get("current") == "parse_error" for change in file_changes):
        return (PARSER_ERROR_WARNING,)
    return ()


def _rebuild_required_freshness(
    root: Path, *, stored_metadata: dict[str, str], reason: str
) -> dict[str, Any]:
    current_git = _read_git_metadata(root)
    return {
        "change_counts": {change_type: 0 for change_type in CHANGE_TYPES},
        "changed_files": [],
        "effective_config_hash": {
            "current": _effective_config_hash(DEFAULT_MAX_FILE_SIZE_BYTES),
            "indexed": stored_metadata.get("effective_config_hash"),
        },
        "files": [],
        "fresh": False,
        "full_reparse_required": True,
        "git": {
            "current": current_git.to_payload(),
            "indexed": _git_metadata_from_metadata(stored_metadata).to_payload(),
        },
        "reason": reason,
        "status": "rebuild_required",
    }


def _changes_payload(file_changes: list[dict[str, Any]]) -> dict[str, Any]:
    change_objects = [
        FileChange(
            path=str(change["path"]),
            change_type=str(change["change_type"]),
            secondary_signals=dict(change["secondary_signals"]),
            hashes=dict(change["hashes"]),
            parser_status=dict(change["parser_status"]),
            size_bytes=dict(change["size_bytes"]),
            language=dict(change["language"]),
        )
        for change in file_changes
    ]
    return {
        "change_counts": _change_counts(change_objects),
        "changed_files": [
            change.to_changed_file_dict() for change in change_objects if change.changed
        ],
        "files": [change.to_status_dict() for change in change_objects],
    }


def _stored_freshness_payload() -> dict[str, Any]:
    return {
        "fresh": True,
        "full_reparse_required": False,
        "reason": "graph_current",
        "status": "available",
    }


def _git_metadata_from_metadata(metadata: dict[str, str]) -> _GitMetadata:
    return _GitMetadata(
        detected=metadata.get("git_detected") == "1",
        branch=metadata.get("git_branch") or None,
        commit=metadata.get("git_commit") or None,
    )


def _git_metadata_changed(indexed: _GitMetadata, current: _GitMetadata) -> bool:
    if not indexed.detected and not current.detected:
        return False
    return indexed.branch != current.branch or indexed.commit != current.commit


def _read_git_metadata(root: Path) -> _GitMetadata:
    git_dir = _git_dir(root)
    if git_dir is None:
        return _GitMetadata(detected=False, branch=None, commit=None)
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return _GitMetadata(detected=False, branch=None, commit=None)

    if head.startswith("ref:"):
        ref = head.removeprefix("ref:").strip()
        branch = ref.removeprefix("refs/heads/") if ref.startswith("refs/heads/") else ref
        return _GitMetadata(detected=True, branch=branch, commit=_read_git_ref(git_dir, ref))
    return _GitMetadata(detected=True, branch=None, commit=head or None)


def _git_dir(root: Path) -> Path | None:
    git_path = root / ".git"
    if git_path.is_dir():
        return git_path
    if not git_path.is_file():
        return None
    try:
        content = git_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not content.startswith("gitdir:"):
        return None
    raw_git_dir = content.removeprefix("gitdir:").strip()
    candidate = Path(raw_git_dir)
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


def _read_git_ref(git_dir: Path, ref: str) -> str | None:
    ref_path = git_dir / ref
    try:
        commit = ref_path.read_text(encoding="utf-8", errors="replace").strip()
        if commit:
            return commit
    except OSError:
        pass
    try:
        for line in (
            (git_dir / "packed-refs").read_text(encoding="utf-8", errors="replace").splitlines()
        ):
            if not line or line.startswith(("#", "^")):
                continue
            parts = line.split(" ", 1)
            if len(parts) == 2 and parts[1] == ref:
                return parts[0]
    except OSError:
        return None
    return None


def _effective_config_hash(max_file_size_bytes: int) -> str:
    return _facts_hash(
        [
            {
                "artifact_version": GRAPH_ARTIFACT_VERSION,
                "max_file_size_bytes": max_file_size_bytes,
                "scan_policy_version": 1,
            }
        ]
    )


def _language_for_path(path: str) -> str:
    posix_path = PurePosixPath(path)
    suffix = posix_path.suffix.lower()
    if suffix == ".py":
        return "python"
    if suffix in {".ts", ".tsx", ".mts", ".cts"}:
        return "typescript"
    if suffix in JAVASCRIPT_SOURCE_SUFFIXES:
        return "javascript"
    if suffix in {".md", ".markdown", ".mdx"}:
        return "markdown"
    if suffix in {".json", ".toml", ".yaml", ".yml"}:
        return "config"
    return "text"


def _normalized_hash(raw_bytes: bytes) -> str:
    text = raw_bytes.decode("utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized_lines: list[str] = []
    previous_blank = False
    for line in text.split("\n"):
        stripped = line.rstrip(" \t")
        is_blank = stripped == ""
        if is_blank and previous_blank:
            continue
        normalized_lines.append(stripped)
        previous_blank = is_blank
    return _sha256_string("\n".join(normalized_lines))


def _facts_hash(facts: list[dict[str, object]]) -> str:
    canonical_facts = sorted(facts, key=lambda item: json.dumps(item, sort_keys=True, default=list))
    return _sha256_string(_json_value(canonical_facts))


def _sha256_bytes(raw_bytes: bytes) -> str:
    return hashlib.sha256(raw_bytes).hexdigest()


def _sha256_string(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _read_schema_version(graph_store: Path) -> str | None:
    with sqlite3.connect(graph_store) as connection:
        return _schema_version(connection)


def _schema_version(connection: sqlite3.Connection) -> str | None:
    row = connection.execute("SELECT value FROM metadata WHERE key = 'schema_version'").fetchone()
    if row is None:
        return None
    return str(row[0])


def _metadata(connection: sqlite3.Connection) -> dict[str, str]:
    return dict(connection.execute("SELECT key, value FROM metadata ORDER BY key"))


def _single_row(cursor: sqlite3.Cursor) -> dict[str, Any]:
    row = cursor.fetchone()
    if row is None:
        raise GraphStoreError("graph_store_missing_required_row")
    return dict(row)


def _rows(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


def _decode_metadata_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decoded_rows = []
    for row in rows:
        decoded = dict(row)
        decoded["metadata"] = json.loads(decoded.pop("metadata_json"))
        decoded_rows.append(decoded)
    return decoded_rows


def _decode_edge_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decoded_rows = []
    for row in rows:
        decoded = dict(row)
        decoded["evidence"] = json.loads(decoded.pop("evidence_json"))
        decoded["metadata"] = json.loads(decoded.pop("metadata_json"))
        decoded_rows.append(decoded)
    return decoded_rows


def _decode_python_symbol_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decoded_rows = []
    for row in rows:
        decoded = dict(row)
        decoded["decorators"] = json.loads(decoded.pop("decorators_json"))
        decoded["bases"] = json.loads(decoded.pop("bases_json"))
        decoded_rows.append(decoded)
    return decoded_rows


def _decode_python_package_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decoded_rows = []
    for row in rows:
        decoded = dict(row)
        decoded["inferred"] = bool(decoded["inferred"])
        decoded_rows.append(decoded)
    return decoded_rows


def _decode_config_file_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decoded_rows = []
    for row in rows:
        decoded = dict(row)
        decoded["top_level_keys"] = json.loads(decoded.pop("top_level_keys_json"))
        decoded["metadata"] = json.loads(decoded.pop("metadata_json"))
        decoded_rows.append(decoded)
    return decoded_rows


def _decode_config_command_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decoded_rows = []
    for row in rows:
        decoded = dict(row)
        decoded["not_run"] = bool(decoded["not_run"])
        decoded["auto_run_recommended"] = bool(decoded["auto_run_recommended"])
        decoded_rows.append(decoded)
    return decoded_rows


def _decode_file_change_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decoded_rows = []
    for row in rows:
        payload = json.loads(str(row["payload_json"]))
        decoded_rows.append(payload)
    return decoded_rows


def _python_symbol_node_kind(kind: str) -> str:
    return {
        "async_function": "PythonAsyncFunction",
        "async_method": "PythonAsyncMethod",
        "class": "PythonClass",
        "function": "PythonFunction",
        "method": "PythonMethod",
    }[kind]


def _javascript_symbol_node_kind(kind: str) -> str:
    return {
        "arrow_function": "JavaScriptArrowFunction",
        "class": "JavaScriptClass",
        "function": "JavaScriptFunction",
        "interface": "TypeScriptInterface",
        "type_alias": "TypeScriptTypeAlias",
    }[kind]


def _symbol_labels(python: dict[str, Any]) -> dict[str, str]:
    return {symbol["id"]: symbol["qualified_name"] for symbol in python["symbols"]}


def _python_import_display(import_fact: dict[str, Any]) -> str:
    alias = f" as {import_fact['alias']}" if import_fact["alias"] else ""
    if import_fact["kind"] == "import":
        return f"import {import_fact['module']}{alias}"
    relative_prefix = "." * import_fact["level"]
    imported_name = import_fact["imported_name"] or ""
    return f"from {relative_prefix}{import_fact['module']} import {imported_name}{alias}"


def _javascript_import_display(import_fact: dict[str, Any]) -> str:
    specifier = import_fact["specifier"]
    kind = import_fact["kind"]
    if kind == "require":
        return f'require("{specifier}")'
    if kind == "dynamic_import":
        return f'import("{specifier}")'
    if kind == "side_effect_import":
        return f'import "{specifier}"'
    return f'{kind} from "{specifier}"'


def _join_list(values: list[str]) -> str:
    return ", ".join(values)


def _md_cell(value: object) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|")


def _directory_node_id(path: str) -> str:
    return ROOT_DIRECTORY_ID if path == ROOT_DIRECTORY_PATH else f"directory:{path}"


def _file_node_id(path: str) -> str:
    return f"file:{path}"


def _edge_id(kind: str, source_id: str, target_id: str) -> str:
    return f"edge:{kind}:{source_id}->{target_id}"


def _file_directory(path: str) -> str:
    parent = PurePosixPath(path).parent.as_posix()
    return ROOT_DIRECTORY_PATH if parent == "." else parent


def _directory_parent(path: str) -> str:
    parent = PurePosixPath(path).parent.as_posix()
    return ROOT_DIRECTORY_PATH if parent == "." else parent


def _directory_sort_key(path: str) -> tuple[int, str]:
    if path == ROOT_DIRECTORY_PATH:
        return (0, path)
    return (path.count("/") + 1, path)


def _metadata_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _json_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
