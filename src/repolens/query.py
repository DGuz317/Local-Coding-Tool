"""Framework-independent read-only graph query service for RepoLens."""

from __future__ import annotations

import json
import re
import shlex
import sqlite3
from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from repolens.graph import (
    GRAPH_SCHEMA_VERSION,
    GRAPH_STORE_PATH,
    REQUIRED_GRAPH_ARTIFACTS,
)
from repolens.scanner import ARTIFACT_DIR_NAME

QUERY_DEFAULT_LIMIT = 20
QUERY_MAX_LIMIT = 100
NEIGHBOR_DEFAULT_LIMIT = 50
NEIGHBOR_MAX_DEPTH = 3
SHORTEST_PATH_DEFAULT_MAX_DEPTH = 6
SHORTEST_PATH_MAX_DEPTH = 8
GRAPH_REPORT_DEFAULT_MAX_CHARS = 20_000
GRAPH_REPORT_MAX_CHARS = 100_000

_SOURCE_HASH_METADATA_KEYS = {
    "dependency_hash",
    "graph_hash",
    "line_range_hash",
    "normalized_hash",
    "raw_hash",
    "symbol_hash",
}
_SYMBOL_NODE_KINDS = {
    "AsyncFunction",
    "AsyncMethod",
    "Class",
    "Function",
    "JavaScriptArrowFunction",
    "JavaScriptClass",
    "JavaScriptFunction",
    "JavaScriptInterface",
    "JavaScriptTypeAlias",
    "Method",
}
_EXACT_MATCH_SCORE = 850
_AMBIGUOUS_SCORE_DELTA = 80
_DEFAULT_PATH_EDGE_KINDS = {
    "CALLS",
    "CONTAINS",
    "DECLARES_COMMAND",
    "DECLARES_ENTRYPOINT",
    "DECLARES_PACKAGE",
    "DECLARES_PACKAGE_MANAGER",
    "DECLARES_PACKAGE_ROOT",
    "DECLARES_SKILL",
    "DETECTS_LOCKFILE",
    "HAS_PARSE_ERROR",
    "IMPORTS",
    "LINKS_TO_FILE",
    "MENTIONS_FILE",
}
_EDGE_PRIORITY = {
    "CALLS": 0,
    "IMPORTS": 1,
    "DECLARES_ENTRYPOINT": 2,
    "DECLARES_COMMAND": 3,
    "DECLARES_PACKAGE": 4,
    "DECLARES_PACKAGE_MANAGER": 4,
    "DECLARES_PACKAGE_ROOT": 4,
    "DECLARES_SKILL": 4,
    "DETECTS_LOCKFILE": 4,
    "LINKS_TO_FILE": 5,
    "MENTIONS_FILE": 6,
    "CONTAINS": 10,
    "HAS_PARSE_ERROR": 20,
}
_PATH_NODE_KIND_PRIORITY = {
    "PythonModule": 0,
    "JavaScriptModule": 0,
    "MarkdownFile": 0,
    "ConfigFile": 0,
    "File": 1,
    "Directory": 2,
}
_ENTRYPOINT_KIND_PRIORITY = {
    "python_console_script": 0,
    "package_bin": 1,
    "package_main": 2,
    "python_main_guard": 3,
    "docker_entrypoint": 4,
    "docker_cmd": 5,
    "package_script": 6,
    "shebang": 7,
}


class RepoLensQueryError(RuntimeError):
    """Raised when the query service cannot be initialized safely."""


@dataclass(frozen=True)
class _StatusSnapshot:
    data: dict[str, Any]
    warnings: tuple[str, ...]
    evidence: tuple[dict[str, Any], ...]
    available: bool

    @property
    def confidence(self) -> str:
        if not self.available:
            return "none"
        return "high" if self.data.get("fresh") is True else "medium"


@dataclass(frozen=True)
class _ResolvedNode:
    node: dict[str, Any] | None
    candidates: tuple[dict[str, Any], ...]
    ambiguous: bool
    confidence: str
    reason: str | None = None


class GraphQueryService:
    """Read-only graph metadata queries backed by generated graph storage."""

    def __init__(self, repo_path: Path | str):
        self.root = _resolve_root(repo_path)

    def repo_summary(
        self,
        *,
        max_entrypoints: int = 10,
        max_commands: int = 10,
        max_modules: int = 20,
        max_important_files: int = 20,
    ) -> dict[str, Any]:
        """Return high-level repository graph metadata."""
        status = self._status_snapshot()
        limits = {
            "max_commands": _clamp_limit(max_commands),
            "max_entrypoints": _clamp_limit(max_entrypoints),
            "max_important_files": _clamp_limit(max_important_files),
            "max_modules": _clamp_limit(max_modules),
        }
        if not status.available:
            return self._missing_graph_envelope(status, limits=limits)

        with self._connect() as connection:
            repository = _single_row_dict(
                connection.execute("SELECT id, analysis_root, name FROM repositories ORDER BY id")
            )
            run = _single_row_dict(
                connection.execute(
                    """
                    SELECT indexed_at_utc, extractor_version, graph_schema_version, status
                    FROM runs
                    WHERE id = 1
                    """
                )
            )
            counts = self._counts(connection)
            languages = _rows_to_dicts(
                connection.execute(
                    """
                    SELECT language, COUNT(*) AS file_count
                    FROM files
                    GROUP BY language
                    ORDER BY file_count DESC, language
                    """
                )
            )
            all_entrypoints = self._entrypoints(connection)
            all_commands = self._commands(connection)
            all_modules = self._major_modules(connection)
            all_important_files = self._important_files(connection)

        data = {
            "available_commands": all_commands[: limits["max_commands"]],
            "counts": counts,
            "entrypoints": all_entrypoints[: limits["max_entrypoints"]],
            "important_files": all_important_files[: limits["max_important_files"]],
            "indexed_at_utc": run.get("indexed_at_utc"),
            "languages": languages,
            "major_modules": all_modules[: limits["max_modules"]],
            "repository": repository,
            "run": run,
            "schema": {"version": GRAPH_SCHEMA_VERSION},
            "truncated": {
                "available_commands": len(all_commands) > limits["max_commands"],
                "entrypoints": len(all_entrypoints) > limits["max_entrypoints"],
                "important_files": len(all_important_files) > limits["max_important_files"],
                "major_modules": len(all_modules) > limits["max_modules"],
            },
        }
        return _envelope(
            data=data,
            confidence=status.confidence,
            evidence=status.evidence,
            limits=limits,
            warnings=status.warnings,
        )

    def graph_status(self, *, max_changed_files: int = QUERY_DEFAULT_LIMIT) -> dict[str, Any]:
        """Return source-free graph artifact and stored-file metadata status."""
        limit = _clamp_limit(max_changed_files)
        status = self._status_snapshot(max_changed_files=limit)
        pagination = {
            "limit": limit,
            "offset": 0,
            "returned": len(status.data.get("changed_files", [])),
            "total": status.data.get("total_changed_files", 0),
            "truncated": bool(status.data.get("changed_files_truncated", False)),
        }
        return _envelope(
            data=status.data,
            confidence=status.confidence,
            evidence=status.evidence,
            limits={"max_changed_files": limit},
            warnings=status.warnings,
            pagination=pagination,
        )

    def get_graph_report(
        self,
        *,
        max_chars: int = GRAPH_REPORT_DEFAULT_MAX_CHARS,
    ) -> dict[str, Any]:
        """Return the generated graph report artifact with explicit truncation metadata."""
        limit = min(max(1, max_chars), GRAPH_REPORT_MAX_CHARS)
        status = self._status_snapshot()
        report_path = self.root / ARTIFACT_DIR_NAME / "graph-report.md"
        limits = {"max_chars": limit}
        if report_path.is_symlink():
            return _error_envelope(
                code="graph_report_is_symlink",
                message="Graph report artifact is a symlink and will not be read.",
                recommended_action=self._recommended_action(),
                limits=limits,
            )
        if not report_path.is_file():
            return _error_envelope(
                code="graph_report_missing",
                message="Graph report artifact is missing.",
                recommended_action=self._recommended_action(),
                limits=limits,
                warnings=status.warnings,
            )

        try:
            text = report_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return _error_envelope(
                code="graph_report_read_failed",
                message="Graph report artifact could not be read.",
                recommended_action=self._recommended_action(),
                limits=limits,
                warnings=status.warnings,
            )

        truncated = len(text) > limit
        warnings = list(status.warnings)
        if not status.available:
            warnings.append("Graph store is unavailable; returning existing graph report only.")
        data = {
            "chars": min(len(text), limit),
            "report_path": f"{ARTIFACT_DIR_NAME}/graph-report.md",
            "text": text[:limit],
            "total_chars": len(text),
            "truncated": truncated,
        }
        return _envelope(
            data=data,
            confidence=status.confidence if status.available else "low",
            evidence=(
                *status.evidence,
                {"artifact": f"{ARTIFACT_DIR_NAME}/graph-report.md", "source": "graph_report"},
            ),
            limits=limits,
            warnings=tuple(warnings),
            pagination={
                "limit": limit,
                "offset": 0,
                "returned": min(len(text), limit),
                "total": len(text),
                "truncated": truncated,
            },
        )

    def search_graph(
        self,
        query: str,
        *,
        max_results: int = QUERY_DEFAULT_LIMIT,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Search graph metadata fields only; never read repository source text."""
        limit = _clamp_limit(max_results)
        normalized_offset = max(0, offset)
        limits = {"max_results": limit}
        if not query.strip():
            return _error_envelope(
                code="empty_query",
                message="Graph search query must not be empty.",
                limits=limits,
            )

        status = self._status_snapshot()
        if not status.available:
            return self._missing_graph_envelope(status, limits=limits)

        with self._connect() as connection:
            matches = self._search_matches(connection, query)

        page = matches[normalized_offset : normalized_offset + limit]
        pagination = _pagination(
            limit=limit,
            offset=normalized_offset,
            returned=len(page),
            total=len(matches),
        )
        data = {
            "ambiguous": _is_ambiguous(matches),
            "matches": page,
            "query": query,
            "total_matches": len(matches),
        }
        if data["ambiguous"]:
            data["candidates"] = matches[: min(5, len(matches))]
        return _envelope(
            data=data,
            confidence=status.confidence,
            evidence=(*status.evidence, {"source": "nodes", "fields": "structured_metadata"}),
            limits=limits,
            warnings=status.warnings,
            pagination=pagination,
        )

    def get_node(
        self,
        reference: str | None = None,
        *,
        node_id: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Return one graph node by exact ID, exact path, or unambiguous metadata query."""
        status = self._status_snapshot()
        if not status.available:
            return self._missing_graph_envelope(status, limits={})
        resolved_reference = node_id if node_id is not None else query or reference
        if resolved_reference is None or not resolved_reference.strip():
            return _error_envelope(
                code="missing_node_reference",
                message="Provide node_id or query.",
                warnings=status.warnings,
            )

        with self._connect() as connection:
            resolved = self._resolve_node(
                connection,
                resolved_reference,
                prefer_exact_id=node_id is not None,
            )

        if resolved.node is None and not resolved.ambiguous:
            return _error_envelope(
                code="node_not_found",
                message="No graph node matched the requested reference.",
                recommended_action="Use search_graph to find candidate node IDs.",
                confidence="low",
                evidence=status.evidence,
                warnings=status.warnings,
            )
        data = {
            "ambiguous": resolved.ambiguous,
            "candidates": list(resolved.candidates),
            "node": resolved.node,
            "reference": resolved_reference,
        }
        if resolved.reason is not None:
            data["reason"] = resolved.reason
        return _envelope(
            data=data,
            confidence="low" if resolved.ambiguous else resolved.confidence,
            evidence=status.evidence,
            limits={"max_candidates": 5},
            warnings=status.warnings,
        )

    def get_neighbors(
        self,
        reference: str | None = None,
        *,
        node_id: str | None = None,
        query: str | None = None,
        depth: int = 1,
        direction: str = "both",
        edge_kinds: tuple[str, ...] | list[str] | None = None,
        max_results: int = NEIGHBOR_DEFAULT_LIMIT,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return bounded neighboring graph relationships around one node."""
        status = self._status_snapshot()
        limit = _clamp_limit(max_results)
        normalized_offset = max(0, offset)
        max_depth = min(max(1, depth), NEIGHBOR_MAX_DEPTH)
        limits = {"max_depth": NEIGHBOR_MAX_DEPTH, "max_results": limit}
        if not status.available:
            return self._missing_graph_envelope(status, limits=limits)
        if direction not in {"incoming", "outgoing", "both"}:
            return _error_envelope(
                code="invalid_direction",
                message="Direction must be incoming, outgoing, or both.",
                limits=limits,
                warnings=status.warnings,
            )

        resolved_reference = node_id if node_id is not None else query or reference
        if resolved_reference is None or not resolved_reference.strip():
            return _error_envelope(
                code="missing_node_reference",
                message="Provide node_id or query.",
                limits=limits,
                warnings=status.warnings,
            )

        with self._connect() as connection:
            resolved = self._resolve_node(
                connection,
                resolved_reference,
                prefer_exact_id=node_id is not None,
            )
            if resolved.node is None or resolved.ambiguous:
                data = {
                    "ambiguous": resolved.ambiguous,
                    "candidates": list(resolved.candidates),
                    "center": None,
                    "neighbors": [],
                    "reference": resolved_reference,
                }
                return _envelope(
                    data=data,
                    confidence="low",
                    evidence=status.evidence,
                    limits=limits,
                    warnings=status.warnings,
                )
            neighbors = self._neighbors(
                connection,
                resolved.node["id"],
                depth=max_depth,
                direction=direction,
                edge_kinds=_normalize_edge_kinds(edge_kinds),
            )

        page = neighbors[normalized_offset : normalized_offset + limit]
        return _envelope(
            data={
                "ambiguous": False,
                "center": resolved.node,
                "depth": max_depth,
                "direction": direction,
                "neighbors": page,
            },
            confidence=min_confidence(status.confidence, resolved.confidence),
            evidence=status.evidence,
            limits=limits,
            warnings=status.warnings,
            pagination=_pagination(
                limit=limit,
                offset=normalized_offset,
                returned=len(page),
                total=len(neighbors),
            ),
        )

    def shortest_path(
        self,
        source: str,
        target: str,
        *,
        max_depth: int = SHORTEST_PATH_DEFAULT_MAX_DEPTH,
        edge_kinds: tuple[str, ...] | list[str] | None = None,
    ) -> dict[str, Any]:
        """Find a bounded priority-BFS path between two exact or resolved graph references."""
        status = self._status_snapshot()
        capped_depth = min(max(1, max_depth), SHORTEST_PATH_MAX_DEPTH)
        limits = {"max_depth": capped_depth}
        if not status.available:
            return self._missing_graph_envelope(status, limits=limits)

        with self._connect() as connection:
            source_node = self._resolve_node(connection, source)
            target_node = self._resolve_node(connection, target)
            if source_node.node is None or target_node.node is None:
                return _envelope(
                    data={
                        "found": False,
                        "path": [],
                        "resolution": {
                            "source": _resolution_payload(source_node),
                            "target": _resolution_payload(target_node),
                        },
                    },
                    confidence="low",
                    evidence=status.evidence,
                    limits=limits,
                    warnings=status.warnings,
                )
            if source_node.ambiguous or target_node.ambiguous:
                return _envelope(
                    data={
                        "found": False,
                        "path": [],
                        "resolution": {
                            "source": _resolution_payload(source_node),
                            "target": _resolution_payload(target_node),
                        },
                    },
                    confidence="low",
                    evidence=status.evidence,
                    limits=limits,
                    warnings=status.warnings,
                )
            path = self._shortest_path(
                connection,
                source_node.node,
                target_node.node,
                max_depth=capped_depth,
                edge_kinds=_normalize_edge_kinds(edge_kinds) or _DEFAULT_PATH_EDGE_KINDS,
            )

        found = path is not None
        data = {
            "edge_count": len(path) - 1 if path else 0,
            "found": found,
            "path": path or [],
            "resolution": {
                "source": _resolution_payload(source_node),
                "target": _resolution_payload(target_node),
            },
        }
        return _envelope(
            data=data,
            confidence=min_confidence(
                status.confidence,
                source_node.confidence,
                target_node.confidence,
                "high" if found else "low",
            ),
            evidence=status.evidence,
            limits=limits,
            warnings=status.warnings,
        )

    def list_entrypoints(
        self,
        *,
        kind: str | None = None,
        max_results: int = QUERY_DEFAULT_LIMIT,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return detected entrypoints with evidence and pagination metadata."""
        status = self._status_snapshot()
        limit = _clamp_limit(max_results)
        normalized_offset = max(0, offset)
        limits = {"max_results": limit}
        if not status.available:
            return self._missing_graph_envelope(status, limits=limits)

        with self._connect() as connection:
            entrypoints = self._entrypoints(connection, kind=kind)

        page = entrypoints[normalized_offset : normalized_offset + limit]
        return _envelope(
            data={"entrypoints": page, "kind": kind, "total_entrypoints": len(entrypoints)},
            confidence=status.confidence,
            evidence=(*status.evidence, {"source": "config_entrypoints"}),
            limits=limits,
            warnings=status.warnings,
            pagination=_pagination(
                limit=limit,
                offset=normalized_offset,
                returned=len(page),
                total=len(entrypoints),
            ),
        )

    def _connect(self) -> sqlite3.Connection:
        graph_store = self.root / GRAPH_STORE_PATH
        connection = sqlite3.connect(f"file:{graph_store}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def _status_snapshot(self, *, max_changed_files: int = QUERY_DEFAULT_LIMIT) -> _StatusSnapshot:
        missing_artifacts = tuple(
            artifact for artifact in REQUIRED_GRAPH_ARTIFACTS if not (self.root / artifact).exists()
        )
        recommended_action = self._recommended_action()
        base_data: dict[str, Any] = {
            "artifact_dir": ARTIFACT_DIR_NAME,
            "detected_schema_version": None,
            "fresh": False,
            "missing_artifacts": list(missing_artifacts),
            "recommended_action": recommended_action,
            "repo_path": str(self.root),
            "supported_schema_version": GRAPH_SCHEMA_VERSION,
        }
        if missing_artifacts:
            data = {
                **base_data,
                "changed_files": [],
                "changed_files_truncated": False,
                "reason": "missing_graph_artifacts",
                "status": "stale",
                "total_changed_files": 0,
            }
            return _StatusSnapshot(
                data=data,
                warnings=("Graph artifacts are missing.",),
                evidence=(),
                available=False,
            )

        graph_store = self.root / GRAPH_STORE_PATH
        if graph_store.is_symlink():
            data = {
                **base_data,
                "changed_files": [],
                "changed_files_truncated": False,
                "missing_artifacts": [],
                "reason": "graph_store_is_symlink",
                "status": "rebuild_required",
                "total_changed_files": 0,
            }
            return _StatusSnapshot(
                data=data,
                warnings=("Graph store is a symlink. Rebuild required.",),
                evidence=(),
                available=False,
            )

        try:
            with self._connect() as connection:
                metadata = _metadata(connection)
                schema_version = metadata.get("schema_version")
                evidence = (
                    {
                        "artifact": GRAPH_STORE_PATH,
                        "schema_version": schema_version,
                        "source": "sqlite_metadata",
                    },
                )
                if schema_version != str(GRAPH_SCHEMA_VERSION):
                    data = {
                        **base_data,
                        "changed_files": [],
                        "changed_files_truncated": False,
                        "detected_schema_version": schema_version,
                        "missing_artifacts": [],
                        "reason": "unsupported_schema_version",
                        "status": "rebuild_required",
                        "total_changed_files": 0,
                    }
                    return _StatusSnapshot(
                        data=data,
                        warnings=("Graph schema version is unsupported. Rebuild required.",),
                        evidence=evidence,
                        available=False,
                    )

                run = _single_row_dict(
                    connection.execute(
                        """
                        SELECT indexed_at_utc, extractor_version, graph_schema_version, status
                        FROM runs
                        WHERE id = 1
                        """
                    )
                )
                repository = _single_row_dict(
                    connection.execute(
                        "SELECT id, analysis_root, name FROM repositories ORDER BY id"
                    )
                )
                files = _rows_to_dicts(
                    connection.execute(
                        """
                        SELECT path, size_bytes, mtime_ns, parser_status, language
                        FROM files
                        ORDER BY path
                        """
                    )
                )
                changed_files = self._metadata_file_changes(files)
        except sqlite3.Error:
            data = {
                **base_data,
                "changed_files": [],
                "changed_files_truncated": False,
                "missing_artifacts": [],
                "reason": "graph_store_unreadable",
                "status": "rebuild_required",
                "total_changed_files": 0,
            }
            return _StatusSnapshot(
                data=data,
                warnings=("Graph store is unreadable. Rebuild required.",),
                evidence=(),
                available=False,
            )

        change_counts = dict(
            sorted(Counter(change["change_type"] for change in changed_files).items())
        )
        shown_changes = changed_files[:max_changed_files]
        fresh = not changed_files
        reason = "graph_current" if fresh else "file_metadata_changed"
        status = "available" if fresh else "stale"
        warnings = (
            ()
            if fresh
            else ("Graph artifacts may be stale; file metadata changed since indexing.",)
        )
        data = {
            **base_data,
            "change_counts": change_counts,
            "changed_files": shown_changes,
            "changed_files_truncated": len(changed_files) > max_changed_files,
            "detected_schema_version": str(GRAPH_SCHEMA_VERSION),
            "fresh": fresh,
            "indexed_at_utc": run.get("indexed_at_utc"),
            "missing_artifacts": [],
            "new_files": [],
            "new_file_detection": "not_performed",
            "reason": reason,
            "repository": repository,
            "run": run,
            "status": status,
            "total_changed_files": len(changed_files),
        }
        if fresh:
            data["recommended_action"] = None
        return _StatusSnapshot(
            data=data,
            warnings=warnings,
            evidence=evidence,
            available=True,
        )

    def _metadata_file_changes(self, files: list[dict[str, Any]]) -> list[dict[str, str]]:
        changes: list[dict[str, str]] = []
        for file in files:
            rel_path = str(file["path"])
            path = self.root / rel_path
            try:
                stat = path.stat()
            except OSError:
                changes.append({"change_type": "deleted", "path": rel_path})
                continue
            if not path.is_file():
                changes.append({"change_type": "metadata_changed", "path": rel_path})
                continue
            if stat.st_size != file["size_bytes"] or stat.st_mtime_ns != file["mtime_ns"]:
                changes.append({"change_type": "metadata_changed", "path": rel_path})
        return changes

    def _missing_graph_envelope(
        self,
        status: _StatusSnapshot,
        *,
        limits: dict[str, Any],
    ) -> dict[str, Any]:
        code = str(status.data.get("reason") or "graph_unavailable")
        error = {
            "code": code,
            "message": _missing_graph_message(code),
            "missing_artifacts": status.data.get("missing_artifacts", []),
            "recommended_action": status.data.get("recommended_action"),
            "status": status.data.get("status"),
        }
        return _envelope(
            ok=False,
            data={},
            confidence="none",
            evidence=status.evidence,
            limits=limits,
            warnings=status.warnings,
            error=error,
        )

    def _recommended_action(self) -> str:
        return f"repolens index {shlex.quote(str(self.root))}"

    def _counts(self, connection: sqlite3.Connection) -> dict[str, int]:
        tables = (
            "config_commands",
            "config_entrypoints",
            "config_files",
            "directories",
            "edges",
            "files",
            "javascript_exports",
            "javascript_imports",
            "javascript_modules",
            "javascript_packages",
            "javascript_symbols",
            "nodes",
            "python_calls",
            "python_imports",
            "python_modules",
            "python_packages",
            "python_parse_errors",
            "python_symbols",
            "skipped_paths",
        )
        counts: dict[str, int] = {}
        for table in tables:
            row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
            counts[table] = int(row["count"] if row is not None else 0)
        return counts

    def _entrypoints(
        self,
        connection: sqlite3.Connection,
        *,
        kind: str | None = None,
    ) -> list[dict[str, Any]]:
        if kind is None:
            rows = _rows_to_dicts(
                connection.execute(
                    """
                    SELECT id, path, kind, name, target, evidence, line
                    FROM config_entrypoints
                    """
                )
            )
        else:
            rows = _rows_to_dicts(
                connection.execute(
                    """
                    SELECT id, path, kind, name, target, evidence, line
                    FROM config_entrypoints
                    WHERE kind = ?
                    """,
                    (kind,),
                )
            )
        rows.sort(
            key=lambda row: (
                _ENTRYPOINT_KIND_PRIORITY.get(str(row["kind"]), 100),
                str(row["path"]),
                str(row["name"]),
                str(row["target"]),
            )
        )
        return [_entrypoint_payload(row) for row in rows]

    def _commands(self, connection: sqlite3.Connection) -> list[dict[str, Any]]:
        rows = _rows_to_dicts(
            connection.execute(
                """
                SELECT id, path, source, name, command, purpose, not_run, auto_run_recommended
                FROM config_commands
                ORDER BY purpose, source, path, name
                """
            )
        )
        return [_command_payload(row) for row in rows]

    def _major_modules(self, connection: sqlite3.Connection) -> list[dict[str, Any]]:
        python_modules = _rows_to_dicts(
            connection.execute(
                """
                SELECT node_id AS id, path, module_name, parser_status
                FROM python_modules
                ORDER BY path
                """
            )
        )
        javascript_modules = _rows_to_dicts(
            connection.execute(
                """
                SELECT node_id AS id, path, module_name, parser_status
                FROM javascript_modules
                ORDER BY path
                """
            )
        )
        modules = [{**module, "kind": "PythonModule"} for module in python_modules] + [
            {**module, "kind": "JavaScriptModule"} for module in javascript_modules
        ]
        modules.sort(key=lambda module: (str(module["path"]), str(module["module_name"])))
        return modules

    def _important_files(self, connection: sqlite3.Connection) -> list[dict[str, Any]]:
        docs = _rows_to_dicts(
            connection.execute(
                """
                SELECT node_id AS id, path, doc_kind, importance, title
                FROM documentation_files
                ORDER BY importance, path
                """
            )
        )
        configs = _rows_to_dicts(
            connection.execute(
                """
                SELECT node_id AS id, path, config_kind, parser_status
                FROM config_files
                ORDER BY path
                """
            )
        )
        files = [{**doc, "kind": "documentation"} for doc in docs]
        files.extend({**config, "kind": "config"} for config in configs)
        files.sort(key=lambda item: (_important_file_priority(item), str(item["path"])))
        return files

    def _search_matches(self, connection: sqlite3.Connection, query: str) -> list[dict[str, Any]]:
        query_tokens = _tokens(query)
        normalized_query = _normalize(query)
        exported_symbols = self._exported_javascript_symbols(connection)
        nodes = [
            _node_payload(row) for row in connection.execute("SELECT * FROM nodes ORDER BY id")
        ]
        matches: list[dict[str, Any]] = []
        for node in nodes:
            score, matched_fields = _score_node(
                node,
                query=query,
                normalized_query=normalized_query,
                query_tokens=query_tokens,
                exported_symbols=exported_symbols,
            )
            if score <= 0:
                continue
            matches.append(
                {
                    "confidence": _confidence_for_score(score),
                    "evidence": _match_evidence(node, matched_fields),
                    "matched_fields": matched_fields,
                    "node": node,
                    "score": score,
                }
            )

        exact_matches = [match for match in matches if match["score"] >= _EXACT_MATCH_SCORE]
        if exact_matches:
            matches = exact_matches
        matches.sort(
            key=lambda match: (
                -int(match["score"]),
                str(match["node"].get("path") or ""),
                str(match["node"].get("label") or ""),
                str(match["node"].get("id") or ""),
            )
        )
        return matches

    def _exported_javascript_symbols(self, connection: sqlite3.Connection) -> set[tuple[str, str]]:
        rows = _rows_to_dicts(
            connection.execute("SELECT path, exported_name, local_name FROM javascript_exports")
        )
        exported: set[tuple[str, str]] = set()
        for row in rows:
            path = str(row["path"])
            if row.get("local_name"):
                exported.add((path, str(row["local_name"])))
            if row.get("exported_name") and row["exported_name"] != "default":
                exported.add((path, str(row["exported_name"])))
        return exported

    def _resolve_node(
        self,
        connection: sqlite3.Connection,
        reference: str,
        *,
        prefer_exact_id: bool = False,
    ) -> _ResolvedNode:
        exact_id = _single_optional_row_dict(
            connection.execute(
                "SELECT id, kind, path, label, metadata_json FROM nodes WHERE id = ?",
                (reference,),
            )
        )
        if exact_id is not None:
            return _ResolvedNode(
                node=_node_payload(exact_id),
                candidates=(),
                ambiguous=False,
                confidence="high",
            )
        if prefer_exact_id:
            return _ResolvedNode(
                node=None,
                candidates=(),
                ambiguous=False,
                confidence="low",
                reason="node_id_not_found",
            )

        normalized_path = self._reference_to_repo_path(reference)
        if normalized_path is not None:
            exact_path_rows = _rows_to_dicts(
                connection.execute(
                    """
                    SELECT id, kind, path, label, metadata_json
                    FROM nodes
                    WHERE path = ?
                    ORDER BY kind, id
                    """,
                    (normalized_path,),
                )
            )
            if exact_path_rows:
                node = _preferred_path_node([_node_payload(row) for row in exact_path_rows])
                return _ResolvedNode(
                    node=node,
                    candidates=(),
                    ambiguous=False,
                    confidence="high",
                )

        matches = self._search_matches(connection, reference)
        if not matches:
            return _ResolvedNode(
                node=None,
                candidates=(),
                ambiguous=False,
                confidence="low",
                reason="not_found",
            )
        if _is_ambiguous(matches):
            return _ResolvedNode(
                node=None,
                candidates=tuple(matches[:5]),
                ambiguous=True,
                confidence="low",
                reason="ambiguous",
            )
        return _ResolvedNode(
            node=matches[0]["node"],
            candidates=(),
            ambiguous=False,
            confidence=matches[0]["confidence"],
        )

    def _reference_to_repo_path(self, reference: str) -> str | None:
        value = reference.strip()
        if not value:
            return None
        path = Path(value)
        if path.is_absolute():
            try:
                relative = path.resolve(strict=False).relative_to(self.root)
            except ValueError:
                return None
            return relative.as_posix() or "."
        normalized = PurePosixPath(value.replace("\\", "/"))
        parts = [part for part in normalized.parts if part not in {"", "."}]
        if not parts:
            return "."
        if any(part == ".." for part in parts):
            return None
        return "/".join(parts)

    def _neighbors(
        self,
        connection: sqlite3.Connection,
        node_id: str,
        *,
        depth: int,
        direction: str,
        edge_kinds: set[str] | None,
    ) -> list[dict[str, Any]]:
        nodes_by_id = self._nodes_by_id(connection)
        visited = {node_id}
        frontier = {node_id}
        results: list[dict[str, Any]] = []
        for current_depth in range(1, depth + 1):
            next_frontier: set[str] = set()
            edges = self._edges_for_nodes(
                connection,
                frontier,
                direction=direction,
                edge_kinds=edge_kinds,
            )
            for edge in edges:
                neighbor_id = (
                    edge["target_id"] if edge["source_id"] in frontier else edge["source_id"]
                )
                if neighbor_id not in nodes_by_id:
                    continue
                results.append(
                    {
                        "depth": current_depth,
                        "direction": "outgoing" if edge["source_id"] in frontier else "incoming",
                        "edge": _edge_payload(edge),
                        "node": nodes_by_id[neighbor_id],
                    }
                )
                if neighbor_id not in visited:
                    next_frontier.add(neighbor_id)
                    visited.add(neighbor_id)
            frontier = next_frontier
            if not frontier:
                break
        results.sort(
            key=lambda item: (
                int(item["depth"]),
                _EDGE_PRIORITY.get(str(item["edge"]["kind"]), 100),
                str(item["node"]["id"]),
                str(item["edge"]["id"]),
            )
        )
        return results

    def _shortest_path(
        self,
        connection: sqlite3.Connection,
        source: dict[str, Any],
        target: dict[str, Any],
        *,
        max_depth: int,
        edge_kinds: set[str],
    ) -> list[dict[str, Any]] | None:
        if source["id"] == target["id"]:
            return [{"edge": None, "node": source}]
        nodes_by_id = self._nodes_by_id(connection)
        queue: deque[tuple[str, list[tuple[dict[str, Any] | None, str]]]] = deque()
        queue.append((str(source["id"]), [(None, str(source["id"]))]))
        visited = {str(source["id"])}
        while queue:
            current_id, path = queue.popleft()
            if len(path) - 1 >= max_depth:
                continue
            edges = self._edges_for_nodes(
                connection,
                {current_id},
                direction="both",
                edge_kinds=edge_kinds,
            )
            for edge in edges:
                neighbor_id = (
                    edge["target_id"] if edge["source_id"] == current_id else edge["source_id"]
                )
                if neighbor_id in visited:
                    continue
                next_path = [*path, (_edge_payload(edge), str(neighbor_id))]
                if neighbor_id == target["id"]:
                    return [
                        {"edge": edge_payload, "node": nodes_by_id[path_node_id]}
                        for edge_payload, path_node_id in next_path
                    ]
                visited.add(neighbor_id)
                queue.append((str(neighbor_id), next_path))
        return None

    def _edges_for_nodes(
        self,
        connection: sqlite3.Connection,
        node_ids: set[str],
        *,
        direction: str,
        edge_kinds: set[str] | None,
    ) -> list[dict[str, Any]]:
        if not node_ids:
            return []
        conditions: list[str] = []
        params: list[str] = []
        placeholders = ",".join("?" for _ in node_ids)
        sorted_node_ids = sorted(node_ids)
        if direction in {"outgoing", "both"}:
            conditions.append(f"source_id IN ({placeholders})")
            params.extend(sorted_node_ids)
        if direction in {"incoming", "both"}:
            conditions.append(f"target_id IN ({placeholders})")
            params.extend(sorted_node_ids)
        sql = (
            "SELECT id, source_id, target_id, kind, metadata_json FROM edges WHERE "
            + " OR ".join(f"({condition})" for condition in conditions)
        )
        if edge_kinds:
            kind_placeholders = ",".join("?" for _ in edge_kinds)
            sql = f"SELECT * FROM ({sql}) WHERE kind IN ({kind_placeholders})"
            params.extend(sorted(edge_kinds))
        rows = [_edge_row_dict(row) for row in connection.execute(sql, params)]
        rows.sort(
            key=lambda row: (
                _EDGE_PRIORITY.get(str(row["kind"]), 100),
                str(row["source_id"]),
                str(row["target_id"]),
                str(row["id"]),
            )
        )
        return rows

    def _nodes_by_id(self, connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
        return {
            node["id"]: node
            for node in (
                _node_payload(row)
                for row in connection.execute(
                    "SELECT id, kind, path, label, metadata_json FROM nodes"
                )
            )
        }


def _resolve_root(repo_path: Path | str) -> Path:
    try:
        root = Path(repo_path).resolve(strict=True)
    except OSError as exc:
        raise RepoLensQueryError("analysis_root_not_found") from exc
    if not root.is_dir():
        raise RepoLensQueryError("analysis_root_not_directory")
    if ARTIFACT_DIR_NAME in root.parts:
        raise RepoLensQueryError("analysis_root_is_repolens_artifact_dir")
    return root


def _metadata(connection: sqlite3.Connection) -> dict[str, str]:
    return {
        str(row["key"]): str(row["value"])
        for row in connection.execute("SELECT key, value FROM metadata")
    }


def _single_row_dict(cursor: sqlite3.Cursor) -> dict[str, Any]:
    row = cursor.fetchone()
    return _row_to_dict(row) if row is not None else {}


def _single_optional_row_dict(cursor: sqlite3.Cursor) -> dict[str, Any] | None:
    row = cursor.fetchone()
    return _row_to_dict(row) if row is not None else None


def _rows_to_dicts(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [_row_to_dict(row) for row in cursor]


def _row_to_dict(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    return {key: row[key] for key in row.keys()}


def _node_payload(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = _row_to_dict(row)
    return {
        "id": data["id"],
        "kind": data["kind"],
        "label": data["label"],
        "metadata": _decode_metadata(data.get("metadata_json")),
        "path": data.get("path"),
    }


def _edge_row_dict(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = _row_to_dict(row)
    data["metadata"] = _decode_metadata(data.pop("metadata_json", None))
    return data


def _edge_payload(edge: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": edge["id"],
        "kind": edge["kind"],
        "metadata": edge.get("metadata", {}),
        "source_id": edge["source_id"],
        "target_id": edge["target_id"],
    }


def _decode_metadata(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    try:
        decoded = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _entrypoint_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "confidence": _entrypoint_confidence(str(row["kind"])),
        "evidence": row["evidence"],
        "id": row["id"],
        "kind": row["kind"],
        "line": row["line"],
        "name": row["name"],
        "path": row["path"],
        "target": row["target"],
    }


def _command_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "auto_run_recommended": bool(row["auto_run_recommended"]),
        "command": row["command"],
        "confidence": "high",
        "id": row["id"],
        "name": row["name"],
        "not_run": bool(row["not_run"]),
        "path": row["path"],
        "purpose": row["purpose"],
        "source": row["source"],
    }


def _entrypoint_confidence(kind: str) -> str:
    if kind in {
        "python_console_script",
        "package_bin",
        "package_main",
        "docker_entrypoint",
        "docker_cmd",
    }:
        return "high"
    if kind in {"package_script", "python_main_guard", "shebang"}:
        return "medium"
    return "low"


def _important_file_priority(item: dict[str, Any]) -> tuple[int, str]:
    if item.get("doc_kind") == "agent_instructions":
        return (0, str(item.get("path")))
    if item.get("doc_kind") == "readme":
        return (1, str(item.get("path")))
    if item.get("kind") == "config":
        return (2, str(item.get("path")))
    return (3, str(item.get("path")))


def _score_node(
    node: dict[str, Any],
    *,
    query: str,
    normalized_query: str,
    query_tokens: tuple[str, ...],
    exported_symbols: set[tuple[str, str]],
) -> tuple[int, list[dict[str, Any]]]:
    del query
    matched_fields: list[dict[str, Any]] = []
    best_score = 0
    for field_name, field_value in _node_search_fields(node):
        normalized_field = _normalize(field_value)
        field_tokens = _tokens(field_value)
        score = 0
        match_type = ""
        if normalized_field == normalized_query:
            score = _exact_field_score(field_name)
            match_type = "exact"
        elif field_name == "path" and _normalize(Path(field_value).name) == normalized_query:
            score = 820
            match_type = "basename_exact"
        elif query_tokens and all(token in field_tokens for token in query_tokens):
            score = _all_token_field_score(field_name) + len(query_tokens) * 10
            match_type = "all_tokens"
        elif query_tokens:
            overlap = sum(1 for token in query_tokens if token in field_tokens)
            if overlap:
                score = _any_token_field_score(field_name) + overlap * 10
                match_type = "some_tokens"
        if score <= 0:
            continue
        best_score = max(best_score, score)
        matched_fields.append(
            {"field": field_name, "match": match_type, "score": score, "value": field_value}
        )

    if best_score <= 0:
        return 0, []
    boost = _public_symbol_boost(node, exported_symbols)
    total_score = best_score + boost
    matched_fields.sort(key=lambda field: (-int(field["score"]), str(field["field"])))
    return total_score, matched_fields


def _node_search_fields(node: dict[str, Any]) -> list[tuple[str, str]]:
    fields = [
        ("id", str(node["id"])),
        ("kind", str(node["kind"])),
        ("label", str(node["label"])),
    ]
    if node.get("path") is not None:
        fields.append(("path", str(node["path"])))
    fields.extend(_metadata_fields(node.get("metadata", {})))
    return fields


def _metadata_fields(metadata: dict[str, Any], prefix: str = "metadata") -> list[tuple[str, str]]:
    fields: list[tuple[str, str]] = []
    for key, value in sorted(metadata.items()):
        if key in _SOURCE_HASH_METADATA_KEYS:
            continue
        field_name = f"{prefix}.{key}"
        if isinstance(value, dict):
            fields.extend(_metadata_fields(value, prefix=field_name))
        elif isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, (dict, list, tuple)):
                    continue
                if item is not None:
                    fields.append((field_name, str(item)))
        elif value is not None:
            fields.append((field_name, str(value)))
    return fields


def _exact_field_score(field_name: str) -> int:
    if field_name == "id":
        return 1000
    if field_name == "path":
        return 950
    if field_name == "label":
        return 900
    if field_name in {"metadata.name", "metadata.qualified_name", "metadata.module_name"}:
        return 880
    return 850


def _all_token_field_score(field_name: str) -> int:
    if field_name == "label":
        return 690
    if field_name == "path":
        return 650
    if field_name == "id":
        return 620
    return 500


def _any_token_field_score(field_name: str) -> int:
    if field_name == "label":
        return 180
    if field_name == "path":
        return 150
    return 100


def _public_symbol_boost(node: dict[str, Any], exported_symbols: set[tuple[str, str]]) -> int:
    if node["kind"] not in _SYMBOL_NODE_KINDS:
        return 0
    metadata = node.get("metadata", {})
    name = str(metadata.get("name") or node["label"])
    if (str(node.get("path")), name) in exported_symbols:
        return 60
    if not name.startswith("_"):
        return 20
    return 0


def _normalize(value: str) -> str:
    return " ".join(_tokens(value))


def _tokens(value: str) -> tuple[str, ...]:
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return tuple(re.findall(r"[a-z0-9]+", expanded.casefold()))


def _confidence_for_score(score: int) -> str:
    if score >= _EXACT_MATCH_SCORE:
        return "high"
    if score >= 500:
        return "medium"
    return "low"


def _match_evidence(
    node: dict[str, Any], matched_fields: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {
            "field": field["field"],
            "match": field["match"],
            "node_id": node["id"],
            "path": node.get("path"),
        }
        for field in matched_fields[:3]
    ]


def _is_ambiguous(matches: list[dict[str, Any]]) -> bool:
    if len(matches) < 2:
        return False
    top_score = int(matches[0]["score"])
    second_score = int(matches[1]["score"])
    return top_score - second_score < _AMBIGUOUS_SCORE_DELTA


def _preferred_path_node(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    nodes.sort(
        key=lambda node: (
            _PATH_NODE_KIND_PRIORITY.get(str(node["kind"]), 100),
            str(node["kind"]),
            str(node["id"]),
        )
    )
    return nodes[0]


def _normalize_edge_kinds(edge_kinds: tuple[str, ...] | list[str] | None) -> set[str] | None:
    if edge_kinds is None:
        return None
    normalized = {kind.strip().upper() for kind in edge_kinds if kind.strip()}
    return normalized or None


def _resolution_payload(resolved: _ResolvedNode) -> dict[str, Any]:
    return {
        "ambiguous": resolved.ambiguous,
        "candidates": list(resolved.candidates),
        "confidence": resolved.confidence,
        "node": resolved.node,
        "reason": resolved.reason,
    }


def _pagination(*, limit: int, offset: int, returned: int, total: int) -> dict[str, int | bool]:
    return {
        "limit": limit,
        "offset": offset,
        "returned": returned,
        "total": total,
        "truncated": offset + returned < total,
    }


def _clamp_limit(value: int) -> int:
    return min(max(1, value), QUERY_MAX_LIMIT)


def _envelope(
    *,
    data: dict[str, Any],
    confidence: str,
    evidence: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    limits: dict[str, Any],
    warnings: tuple[str, ...] | list[str],
    ok: bool = True,
    error: dict[str, Any] | None = None,
    pagination: dict[str, Any] | None = None,
) -> dict[str, Any]:
    envelope: dict[str, Any] = {
        "confidence": confidence,
        "data": data,
        "evidence": list(evidence),
        "limits": limits,
        "ok": ok,
        "warnings": list(warnings),
    }
    if error is not None:
        envelope["error"] = error
    if pagination is not None:
        envelope["pagination"] = pagination
    return envelope


def _error_envelope(
    *,
    code: str,
    message: str,
    limits: dict[str, Any] | None = None,
    recommended_action: str | None = None,
    confidence: str = "none",
    evidence: tuple[dict[str, Any], ...] | list[dict[str, Any]] = (),
    warnings: tuple[str, ...] | list[str] = (),
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if recommended_action is not None:
        error["recommended_action"] = recommended_action
    return _envelope(
        ok=False,
        data={},
        confidence=confidence,
        evidence=evidence,
        limits=limits or {},
        warnings=warnings,
        error=error,
    )


def _missing_graph_message(code: str) -> str:
    if code == "missing_graph_artifacts":
        return "RepoLens graph artifacts are missing. Run repolens index for this repository."
    if code == "unsupported_schema_version":
        return "RepoLens graph schema is unsupported. Rebuild graph artifacts."
    return "RepoLens graph is unavailable. Rebuild graph artifacts."


def min_confidence(*values: str) -> str:
    order = {"none": 0, "low": 1, "medium": 2, "high": 3}
    inverse = {value: key for key, value in order.items()}
    score = min(order.get(value, 0) for value in values)
    return inverse[score]
