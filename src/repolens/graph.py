"""Authoritative graph storage and deterministic exports for RepoLens."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from repolens.scanner import ARTIFACT_DIR_NAME, ScanResult

GRAPH_SCHEMA_NAME = "repolens_graph"
GRAPH_SCHEMA_VERSION = 1
GRAPH_ARTIFACT_VERSION = 1
GRAPH_EXPORTER_VERSION = "issue-5-minimal-v1"

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


class GraphStoreError(RuntimeError):
    """Raised when the authoritative graph store cannot be rebuilt."""


class GraphExportError(RuntimeError):
    """Raised when graph exports cannot be written."""


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


def rebuild_graph_artifacts(root: Path, scan: ScanResult) -> tuple[str, ...]:
    """Rebuild the graph store and exports from one safe discovery result."""
    build_graph_store(root, scan)
    return export_graph_artifacts(root)


def build_graph_store(root: Path, scan: ScanResult) -> Path:
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
            _create_schema(connection)
            _populate_store(connection, root, scan, indexed_at_utc=_utc_now())
            connection.commit()
            _ensure_supported_schema(connection)

        os.replace(temp_path, target)
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

    return GraphArtifactsStatus(
        status="available",
        reason="graph_artifacts_present",
        fresh=None,
        missing_artifacts=(),
        warnings=("Graph artifacts exist, but live freshness checks are not implemented yet.",),
        detected_schema_version=schema_version,
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
            metadata_json TEXT NOT NULL
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
        """
    )


def _populate_store(
    connection: sqlite3.Connection,
    root: Path,
    scan: ScanResult,
    *,
    indexed_at_utc: str,
) -> None:
    directories = _directory_facts(scan)
    files = tuple(sorted(scan.files, key=lambda scanned_file: scanned_file.path))
    skipped_paths = tuple(sorted(scan.skipped, key=lambda skipped_path: skipped_path.path))

    connection.executemany(
        "INSERT INTO metadata(key, value) VALUES (?, ?)",
        (
            ("schema_name", GRAPH_SCHEMA_NAME),
            ("schema_version", str(GRAPH_SCHEMA_VERSION)),
            ("artifact_version", str(GRAPH_ARTIFACT_VERSION)),
            ("exporter_version", GRAPH_EXPORTER_VERSION),
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
        INSERT INTO files(path, node_id, directory_path, size_bytes, parser_status)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            (
                scanned_file.path,
                _file_node_id(scanned_file.path),
                _file_directory(scanned_file.path),
                scanned_file.size_bytes,
                "not_parsed",
            )
            for scanned_file in files
        ),
    )
    connection.executemany(
        "INSERT INTO skipped_paths(path, reason) VALUES (?, ?)",
        ((skipped.path, skipped.reason) for skipped in skipped_paths),
    )

    _insert_nodes(connection, root, directories, files)
    _insert_edges(connection, directories, files)
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
                        "parser_status": "not_parsed",
                        "size_bytes": scanned_file.size_bytes,
                    }
                ),
            )
            for scanned_file in files
        ),
    )


def _insert_edges(
    connection: sqlite3.Connection,
    directories: tuple[_DirectoryFact, ...],
    files: tuple[Any, ...],
) -> None:
    edges = [(REPOSITORY_ID, ROOT_DIRECTORY_ID)]
    for directory in directories:
        if directory.parent_path is not None:
            edges.append((_directory_node_id(directory.parent_path), directory.node_id))
    for scanned_file in files:
        edges.append(
            (
                _directory_node_id(_file_directory(scanned_file.path)),
                _file_node_id(scanned_file.path),
            )
        )

    connection.executemany(
        "INSERT INTO edges(id, source_id, target_id, kind, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                _edge_id("CONTAINS", source_id, target_id),
                source_id,
                target_id,
                "CONTAINS",
                _metadata_json({}),
            )
            for source_id, target_id in sorted(edges)
        ),
    )


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
                SELECT path, node_id, directory_path, size_bytes, parser_status
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
                SELECT id, source_id, target_id, kind, metadata_json
                FROM edges
                ORDER BY source_id, kind, target_id, id
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

    counts = {
        "directories": len(directories),
        "edges": len(edges),
        "files": len(files),
        "nodes": len(nodes),
        "skipped_paths": len(skipped_paths),
    }
    skip_reasons = dict(sorted(Counter(path["reason"] for path in skipped_paths).items()))
    schema = {"name": metadata["schema_name"], "version": int(metadata["schema_version"])}
    return {
        "artifact_version": GRAPH_ARTIFACT_VERSION,
        "counts": counts,
        "directories": directories,
        "edges": _decode_metadata_rows(edges),
        "files": files,
        "limits": {"max_file_size_bytes": run["max_file_size_bytes"]},
        "metadata": metadata,
        "nodes": _decode_metadata_rows(nodes),
        "repository": repository,
        "run": run,
        "schema": schema,
        "skip_reasons": skip_reasons,
        "skipped_paths": skipped_paths,
    }


def _graph_json_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact": "graph",
        "artifact_version": snapshot["artifact_version"],
        "counts": snapshot["counts"],
        "directories": snapshot["directories"],
        "edges": snapshot["edges"],
        "files": snapshot["files"],
        "limits": snapshot["limits"],
        "repository": snapshot["repository"],
        "run": _run_payload(snapshot),
        "schema": snapshot["schema"],
        "skipped_paths": snapshot["skipped_paths"],
        "nodes": snapshot["nodes"],
    }


def _graph_lite_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact": "graph-lite",
        "artifact_version": snapshot["artifact_version"],
        "counts": snapshot["counts"],
        "files": [
            {
                "path": file["path"],
                "parser_status": file["parser_status"],
                "size_bytes": file["size_bytes"],
            }
            for file in snapshot["files"]
        ],
        "freshness": _freshness_payload(),
        "repository": snapshot["repository"],
        "run": _run_payload(snapshot),
        "schema": snapshot["schema"],
        "skip_reasons": snapshot["skip_reasons"],
    }


def _graph_status_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact": "graph-status",
        "artifact_version": snapshot["artifact_version"],
        "counts": snapshot["counts"],
        "freshness": _freshness_payload(),
        "limits": snapshot["limits"],
        "repository": snapshot["repository"],
        "run": _run_payload(snapshot),
        "scan": {
            "artifact": f"{ARTIFACT_DIR_NAME}/scan.json",
            "scan_policy_version": snapshot["run"]["scan_policy_version"],
        },
        "schema": snapshot["schema"],
        "skip_reasons": snapshot["skip_reasons"],
    }


def _run_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    run = snapshot["run"]
    return {
        "extractor_version": run["extractor_version"],
        "id": run["id"],
        "indexed_at_utc": run["indexed_at_utc"],
        "status": run["status"],
    }


def _freshness_payload() -> dict[str, Any]:
    return {
        "fresh": None,
        "reason": "live_freshness_not_implemented",
        "status": "available",
    }


def _graph_report_text(snapshot: dict[str, Any]) -> str:
    counts = snapshot["counts"]
    run = snapshot["run"]
    repository = snapshot["repository"]
    lines = [
        "# RepoLens Graph Report",
        "",
        f"Repository: {repository['name']}",
        "Analysis root: .",
        f"Indexed at UTC: {run['indexed_at_utc']}",
        f"Schema version: {snapshot['schema']['version']}",
        "",
        "## Summary",
        "",
        f"- Directories: {counts['directories']}",
        f"- Files: {counts['files']}",
        f"- Skipped paths: {counts['skipped_paths']}",
        "- Parser facts: not extracted in Issue #5.",
        "- Live freshness checks: not implemented yet.",
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
            "This Issue #5 graph stores repository, directory, file, skipped-path, and run metadata facts only.",
            "Deep parser facts, imports, symbols, comments, commands, and impact analysis are not detected yet.",
            "",
        ]
    )
    return "\n".join(lines)


def _graph_index_text(snapshot: dict[str, Any]) -> str:
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


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
