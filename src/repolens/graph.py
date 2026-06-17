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

from repolens.python_index import (
    PYTHON_EXTRACTOR_VERSION,
    PythonIndex,
    extract_python_index,
    python_package_node_id,
)
from repolens.scanner import ARTIFACT_DIR_NAME, ScanResult

GRAPH_SCHEMA_NAME = "repolens_graph"
GRAPH_SCHEMA_VERSION = 2
GRAPH_ARTIFACT_VERSION = 1
GRAPH_EXPORTER_VERSION = PYTHON_EXTRACTOR_VERSION

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
    python_index = extract_python_index(root, files)
    python_parser_status = python_index.parser_status_by_path

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
                python_parser_status.get(scanned_file.path, "not_parsed"),
            )
            for scanned_file in files
        ),
    )
    connection.executemany(
        "INSERT INTO skipped_paths(path, reason) VALUES (?, ?)",
        ((skipped.path, skipped.reason) for skipped in skipped_paths),
    )

    _insert_nodes(connection, root, directories, files, python_index)
    _insert_python_tables(connection, python_index)
    _insert_edges(connection, directories, files, python_index)
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
    python_index: PythonIndex,
) -> None:
    python_parser_status = python_index.parser_status_by_path
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
                        "parser_status": python_parser_status.get(scanned_file.path, "not_parsed"),
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


def _insert_edges(
    connection: sqlite3.Connection,
    directories: tuple[_DirectoryFact, ...],
    files: tuple[Any, ...],
    python_index: PythonIndex,
) -> None:
    edge_rows: list[tuple[str, str, str, dict[str, Any]]] = []

    def add_edge(
        source_id: str,
        target_id: str,
        kind: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        edge_rows.append((source_id, target_id, kind, metadata or {}))

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
    for module in python_index.modules:
        add_edge(_file_node_id(module.path), module.node_id, "CONTAINS")
    for symbol in python_index.symbols:
        add_edge(symbol.parent_id or symbol.module_node_id, symbol.id, "CONTAINS")
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

    import_edges: dict[tuple[str, str, str, str], list[int]] = {}
    import_edge_ids: dict[tuple[str, str, str, str], list[str]] = {}
    for import_fact in python_index.imports:
        if not import_fact.root_name:
            continue
        package_id = python_package_node_id(import_fact.root_name, import_fact.classification)
        key = (
            import_fact.module_node_id,
            package_id,
            import_fact.root_name,
            import_fact.classification,
        )
        import_edges.setdefault(key, []).append(import_fact.line)
        import_edge_ids.setdefault(key, []).append(import_fact.id)

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
        )

    connection.executemany(
        "INSERT INTO edges(id, source_id, target_id, kind, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (
            (
                _edge_id(kind, source_id, target_id),
                source_id,
                target_id,
                kind,
                _metadata_json(metadata),
            )
            for source_id, target_id, kind, metadata in sorted(
                edge_rows, key=lambda row: (row[0], row[2], row[1])
            )
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
        "python_calls": len(python_calls),
        "python_imports": len(python_imports),
        "python_modules": len(python_modules),
        "python_packages": len(python_packages),
        "python_parse_errors": len(python_parse_errors),
        "python_symbols": len(python_symbols),
        "python_tagged_comments": len(python_tagged_comments),
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
        "python": snapshot["python"],
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
        "python": _python_lite_payload(snapshot),
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
    python = snapshot["python"]
    symbol_labels = _symbol_labels(python)
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
        f"- Python modules: {counts['python_modules']}",
        f"- Python symbols: {counts['python_symbols']}",
        f"- Python imports: {counts['python_imports']}",
        f"- Python tagged comments: {counts['python_tagged_comments']}",
        f"- Python parse errors: {counts['python_parse_errors']}",
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
            "Deep semantic call graphs, runtime imports, commands, config parsing, and impact analysis are not detected yet.",
            "",
        ]
    )
    return "\n".join(lines)


def _graph_index_text(snapshot: dict[str, Any]) -> str:
    python = snapshot["python"]
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


def _python_symbol_node_kind(kind: str) -> str:
    return {
        "async_function": "PythonAsyncFunction",
        "async_method": "PythonAsyncMethod",
        "class": "PythonClass",
        "function": "PythonFunction",
        "method": "PythonMethod",
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
