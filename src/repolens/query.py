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
IMPACT_DEFAULT_MAX_RESULTS = 20
IMPACT_MAX_DEPTH = 2
READING_ORDER_DEFAULT_MAX_FILES = 7

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
    "RELATED_TEST",
}
_EDGE_PRIORITY = {
    "CALLS": 0,
    "IMPORTS": 1,
    "RELATED_TEST": 1,
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
_IMPACT_EDGE_KINDS = {"CALLS", "IMPORTS"}
_RELATED_TEST_EDGE_KINDS = {"RELATED_TEST"}
_RELATED_DOC_EDGE_KINDS = {"LINKS_TO_FILE", "MENTIONS_FILE"}
_VERIFICATION_PURPOSES = {"lint", "test", "typecheck"}
_TEST_PATH_TOKENS = {"spec", "test", "tests"}
_CONFIG_TASK_TOKENS = {
    "build",
    "command",
    "config",
    "configuration",
    "dependency",
    "dependencies",
    "docker",
    "entrypoint",
    "format",
    "lint",
    "make",
    "package",
    "script",
    "test",
    "typecheck",
}
_READING_ORDER_STOPWORDS = {
    "a",
    "add",
    "an",
    "and",
    "change",
    "fix",
    "for",
    "in",
    "of",
    "on",
    "the",
    "to",
    "update",
}
_CONFIG_NODE_KINDS = {
    "CandidateCommand",
    "ConfigFile",
    "ConfigPackage",
    "ConfigParseError",
    "Entrypoint",
    "Lockfile",
    "PackageManager",
    "PackageRoot",
}
_DOCUMENTATION_NODE_KINDS = {"MarkdownFile", "MarkdownHeading", "Skill"}
_SOURCE_MODULE_KINDS = {"JavaScriptModule", "PythonModule"}
_FILE_ANALYSIS_NODE_KINDS = {
    "ConfigFile",
    "JavaScriptModule",
    "MarkdownFile",
    "PythonModule",
}
_FILE_RECOMMENDATION_KIND_PRIORITY = {
    "source": 0,
    "test": 1,
    "documentation": 2,
    "config": 3,
    "other": 4,
}
_COMMAND_PURPOSE_PRIORITY = {"lint": 0, "test": 1, "typecheck": 2}


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
    resolution_strategy: str | None = None


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

        if resolved.node is None and not resolved.ambiguous and not resolved.candidates:
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
        if resolved.resolution_strategy is not None:
            data["resolution_strategy"] = resolved.resolution_strategy
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
                if resolved.reason is not None:
                    data["reason"] = resolved.reason
                if resolved.resolution_strategy is not None:
                    data["resolution_strategy"] = resolved.resolution_strategy
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

    def impact_analysis(
        self,
        target: str,
        *,
        depth: int = 1,
        max_results: int = IMPACT_DEFAULT_MAX_RESULTS,
    ) -> dict[str, Any]:
        """Return deterministic impact context for a graph target without reading source."""
        status = self._status_snapshot()
        limit = _clamp_limit(max_results)
        capped_depth = min(max(1, depth), IMPACT_MAX_DEPTH)
        limits = {"max_depth": IMPACT_MAX_DEPTH, "max_results": limit}
        if not target.strip():
            return _error_envelope(
                code="empty_target",
                message="Impact analysis target must not be empty.",
                limits=limits,
                warnings=status.warnings,
            )
        if not status.available:
            return self._missing_graph_envelope(status, limits=limits)

        with self._connect() as connection:
            resolved = self._resolve_node(connection, target)
            if resolved.node is None or resolved.ambiguous:
                return _envelope(
                    data=_empty_impact_data(
                        target=target,
                        resolved=resolved,
                        depth=capped_depth,
                        max_results=limit,
                    ),
                    confidence="low",
                    evidence=(
                        *status.evidence,
                        {"source": "graph_metadata", "tool": "impact_analysis"},
                    ),
                    limits=limits,
                    warnings=status.warnings,
                )
            data = self._impact_context(
                connection,
                resolved.node,
                requested_target=target,
                depth=capped_depth,
                max_results=limit,
            )

        return _envelope(
            data=data,
            confidence=min_confidence(status.confidence, resolved.confidence),
            evidence=(*status.evidence, {"source": "graph_metadata", "tool": "impact_analysis"}),
            limits=limits,
            warnings=status.warnings,
        )

    def suggest_reading_order(
        self,
        task: str,
        *,
        max_files: int = READING_ORDER_DEFAULT_MAX_FILES,
    ) -> dict[str, Any]:
        """Suggest a small deterministic file reading order for a natural-language task."""
        status = self._status_snapshot()
        limit = _clamp_limit(max_files)
        limits = {"max_files": limit}
        tokens = _meaningful_tokens(task)
        if not tokens:
            return _error_envelope(
                code="empty_task",
                message="Reading-order task must include at least one searchable token.",
                limits=limits,
                warnings=status.warnings,
            )
        if not status.available:
            return self._missing_graph_envelope(status, limits=limits)

        with self._connect() as connection:
            focused_resolution = self._focused_task_resolution(connection, task, tokens)
            if focused_resolution is not None and focused_resolution.ambiguous:
                data = {
                    "ambiguous": True,
                    "candidates": list(focused_resolution.candidates),
                    "caps": {"max_files": limit},
                    "candidate_verification_commands": [],
                    "reading_order": [],
                    "task": task,
                    "tokens": list(tokens),
                    "total_recommendations": 0,
                    "truncated": False,
                }
                return _envelope(
                    data=data,
                    confidence="low",
                    evidence=(
                        *status.evidence,
                        {"source": "graph_metadata", "tool": "suggest_reading_order"},
                    ),
                    limits=limits,
                    warnings=status.warnings,
                    pagination=_pagination(limit=limit, offset=0, returned=0, total=0),
                )

            recommendations = self._reading_order_recommendations(connection, task, tokens)
            candidate_commands = self._reading_order_candidate_verification_commands(
                connection,
                tokens=tokens,
                recommendations=recommendations,
                max_commands=limit,
            )

        page = recommendations[:limit]
        data = {
            "ambiguous": False,
            "candidates": [],
            "caps": {"max_files": limit},
            "candidate_verification_commands": candidate_commands,
            "reading_order": page,
            "task": task,
            "tokens": list(tokens),
            "total_recommendations": len(recommendations),
            "truncated": len(recommendations) > limit,
        }
        confidence = "medium" if page else "low"
        return _envelope(
            data=data,
            confidence=min_confidence(status.confidence, confidence),
            evidence=(
                *status.evidence,
                {"source": "graph_metadata", "tool": "suggest_reading_order"},
            ),
            limits=limits,
            warnings=status.warnings,
            pagination=_pagination(
                limit=limit, offset=0, returned=len(page), total=len(recommendations)
            ),
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
            "canonical_graph_hash": None,
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
                quality_warnings = _metadata_quality_warnings(metadata)
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
        warnings = tuple(quality_warnings)
        if not fresh:
            warnings = (
                *warnings,
                "Graph artifacts may be stale; file metadata changed since indexing.",
            )
        data = {
            **base_data,
            "canonical_graph_hash": metadata.get("canonical_graph_hash"),
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
                    "resolution_strategy": _resolution_strategy_for_score(score),
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
                resolution_strategy="exact_reference",
            )
        if prefer_exact_id:
            return _ResolvedNode(
                node=None,
                candidates=(),
                ambiguous=False,
                confidence="low",
                reason="node_id_not_found",
                resolution_strategy="exact_reference",
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
                    resolution_strategy="exact_reference",
                )

        matches = self._search_matches(connection, reference)
        if not matches:
            return _ResolvedNode(
                node=None,
                candidates=(),
                ambiguous=False,
                confidence="low",
                reason="not_found",
                resolution_strategy="structured_metadata_match",
            )
        if _is_ambiguous(matches):
            return _ResolvedNode(
                node=None,
                candidates=tuple(matches[:5]),
                ambiguous=True,
                confidence="low",
                reason="ambiguous",
                resolution_strategy="structured_metadata_match",
            )
        if matches[0]["confidence"] == "low":
            return _ResolvedNode(
                node=None,
                candidates=tuple(matches[:5]),
                ambiguous=False,
                confidence="low",
                reason="fuzzy_candidate_only",
                resolution_strategy="fuzzy_candidate",
            )
        return _ResolvedNode(
            node=matches[0]["node"],
            candidates=(),
            ambiguous=False,
            confidence=matches[0]["confidence"],
            resolution_strategy="structured_metadata_match",
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
        sql = """
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
            WHERE
            """ + " OR ".join(f"({condition})" for condition in conditions)
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

    def _files_by_path(self, connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
        return {
            str(row["path"]): _row_to_dict(row)
            for row in connection.execute(
                "SELECT path, node_id, language, parser_status FROM files ORDER BY path"
            )
        }

    def _node_ids_for_path(self, connection: sqlite3.Connection, path: str) -> set[str]:
        return {
            str(row["id"])
            for row in connection.execute("SELECT id FROM nodes WHERE path = ?", (path,))
        }

    def _direct_contains_child_ids(
        self,
        connection: sqlite3.Connection,
        node_ids: set[str],
    ) -> set[str]:
        if not node_ids:
            return set()
        placeholders = ",".join("?" for _ in node_ids)
        return {
            str(row["target_id"])
            for row in connection.execute(
                f"""
                SELECT target_id
                FROM edges
                WHERE kind = 'CONTAINS' AND source_id IN ({placeholders})
                """,
                sorted(node_ids),
            )
        }

    def _analysis_node_ids(
        self,
        connection: sqlite3.Connection,
        target_node: dict[str, Any],
    ) -> set[str]:
        node_ids = {str(target_node["id"])}
        path = _node_path(target_node)
        if target_node["kind"] in _FILE_ANALYSIS_NODE_KINDS and path is not None:
            same_path_ids = self._node_ids_for_path(connection, path)
            file_ids = {
                str(row["id"])
                for row in connection.execute(
                    "SELECT id FROM nodes WHERE path = ? AND kind = 'File'",
                    (path,),
                )
            }
            node_ids.update(file_ids)
            node_ids.update(self._direct_contains_child_ids(connection, file_ids | same_path_ids))
        else:
            node_ids.update(self._direct_contains_child_ids(connection, node_ids))
        return node_ids

    def _impact_context(
        self,
        connection: sqlite3.Connection,
        target_node: dict[str, Any],
        *,
        requested_target: str,
        depth: int,
        max_results: int,
    ) -> dict[str, Any]:
        files_by_path = self._files_by_path(connection)
        nodes_by_id = self._nodes_by_id(connection)
        target_path = _node_path(target_node)
        target_node_ids = self._analysis_node_ids(connection, target_node)

        dependencies = self._impact_relationships(
            connection,
            target_node_ids,
            nodes_by_id,
            direction="outgoing",
        )
        if target_path is not None:
            dependencies = _dedupe_relationships(
                [
                    *dependencies,
                    *self._javascript_local_import_relationships(
                        connection,
                        target_path=target_path,
                        nodes_by_id=nodes_by_id,
                        files_by_path=files_by_path,
                        direction="outgoing",
                    ),
                ]
            )
        dependents = self._impact_relationships(
            connection,
            target_node_ids,
            nodes_by_id,
            direction="incoming",
        )
        if target_path is not None:
            dependents = _dedupe_relationships(
                [
                    *dependents,
                    *self._javascript_local_import_relationships(
                        connection,
                        target_path=target_path,
                        nodes_by_id=nodes_by_id,
                        files_by_path=files_by_path,
                        direction="incoming",
                    ),
                ]
            )

        direct_affected = _dedupe_file_items(
            [
                *_target_file_items(files_by_path, target_path, target_node),
                *(
                    _relationship_file_item(item, reason=item["reason"])
                    for item in dependents
                    if not _is_test_path(str(item["path"]))
                ),
            ]
        )
        likely_tests = self._likely_tests(
            connection,
            target_path=target_path,
            target_node_ids=target_node_ids,
            files_by_path=files_by_path,
            dependent_relationships=dependents,
        )
        related_docs = self._related_docs(
            connection,
            target_node_ids,
            nodes_by_id,
            files_by_path=files_by_path,
        )
        related_configs = self._related_configs(
            connection,
            target_path=target_path,
            files_by_path=files_by_path,
        )
        risk_comments = self._risk_comments(
            connection,
            target_path=target_path,
            related_paths=tuple(item["path"] for item in direct_affected),
        )
        candidate_commands = self._candidate_verification_commands(
            connection,
            related_config_paths=tuple(item["path"] for item in related_configs),
        )
        likely_affected = _dedupe_file_items([*likely_tests, *related_docs, *related_configs])
        groups = _impact_groups(
            max_results=max_results,
            direct_affected=direct_affected,
            dependencies=dependencies,
            dependents=dependents,
            likely_tests=likely_tests,
            related_docs=related_docs,
            related_configs=related_configs,
            risk_comments=risk_comments,
            candidate_commands=candidate_commands,
        )
        rollups = _impact_rollups(groups)

        return {
            "ambiguous": False,
            "candidate_verification_commands": groups["candidate_verification_commands"]["items"],
            "candidates": [],
            "caps": {"depth": depth, "max_results": max_results},
            "dependencies": groups["dependencies"]["items"],
            "dependents": groups["dependents"]["items"],
            "direct_affected_files": groups["direct_affected_files"]["items"],
            "impact_groups": groups,
            "likely_affected_files": likely_affected[:max_results],
            "likely_tests": groups["likely_tests"]["items"],
            "related_configs": groups["related_configs"]["items"],
            "related_docs": groups["related_docs"]["items"],
            "requested_target": requested_target,
            "resolution": {"ambiguous": False, "candidates": [], "node": target_node},
            "risk_comments": groups["risk_comments"]["items"],
            "rollups": rollups,
            "target": target_node,
            "truncated": _impact_truncation(groups, likely_affected, max_results),
        }

    def _impact_relationships(
        self,
        connection: sqlite3.Connection,
        target_node_ids: set[str],
        nodes_by_id: dict[str, dict[str, Any]],
        *,
        direction: str,
    ) -> list[dict[str, Any]]:
        edges = self._edges_for_nodes(
            connection,
            target_node_ids,
            direction=direction,
            edge_kinds=_IMPACT_EDGE_KINDS,
        )
        relationships: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for edge in edges:
            if direction == "outgoing":
                if edge["source_id"] not in target_node_ids:
                    continue
                other_id = str(edge["target_id"])
            else:
                if edge["target_id"] not in target_node_ids:
                    continue
                other_id = str(edge["source_id"])
            if other_id in target_node_ids:
                continue
            node = nodes_by_id.get(other_id)
            if node is None:
                continue
            path = _node_path(node)
            if path is None:
                continue
            key = (path, str(edge["kind"]), direction)
            if key in seen:
                continue
            seen.add(key)
            reason = _relationship_reason(str(edge["kind"]), direction)
            relationships.append(
                {
                    "confidence": _relationship_confidence(str(edge["kind"])),
                    "edge": _edge_payload(edge),
                    "evidence": [_edge_evidence(edge, direction=direction, path=path)],
                    "node": node,
                    "path": path,
                    "reason": reason,
                }
            )
        relationships.sort(
            key=lambda item: (
                _relationship_sort_priority(str(item["reason"]), str(item["path"])),
                str(item["path"]),
            )
        )
        return relationships

    def _likely_tests(
        self,
        connection: sqlite3.Connection,
        *,
        target_path: str | None,
        target_node_ids: set[str],
        files_by_path: dict[str, dict[str, Any]],
        dependent_relationships: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        del dependent_relationships
        candidates: list[dict[str, Any]] = []
        if target_path is None:
            return candidates

        nodes_by_id = self._nodes_by_id(connection)
        for edge in self._edges_for_nodes(
            connection,
            target_node_ids,
            direction="outgoing",
            edge_kinds=_RELATED_TEST_EDGE_KINDS,
        ):
            if edge["source_id"] not in target_node_ids:
                continue
            node = nodes_by_id.get(str(edge["target_id"]))
            if node is None:
                continue
            path = _node_path(node)
            if path is None or path not in files_by_path or not _is_test_path(path):
                continue
            candidates.append(
                _file_context_item(
                    path=path,
                    reason=_related_test_reason(edge),
                    confidence=str(edge.get("confidence", "medium")),
                    evidence=edge.get("evidence", []),
                    node=node,
                    resolution_strategy=str(edge.get("resolution_strategy", "direct")),
                )
            )

        candidates = _dedupe_file_items(candidates)
        candidates.sort(
            key=lambda item: (
                0 if str(item.get("resolution_strategy", "")).startswith("direct_import") else 1,
                str(item["path"]),
            )
        )
        return candidates

    def _javascript_local_import_relationships(
        self,
        connection: sqlite3.Connection,
        *,
        target_path: str,
        nodes_by_id: dict[str, dict[str, Any]],
        files_by_path: dict[str, dict[str, Any]],
        direction: str,
    ) -> list[dict[str, Any]]:
        rows = _rows_to_dicts(
            connection.execute(
                """
                SELECT id, path, specifier, line
                FROM javascript_imports
                WHERE resolution_status = 'unresolved_local'
                ORDER BY path, line, id
                """
            )
        )
        relationships: list[dict[str, Any]] = []
        for row in rows:
            importer_path = str(row["path"])
            resolved_path = _resolve_relative_import_path(
                importer_path,
                str(row["specifier"]),
                files_by_path,
            )
            if resolved_path is None:
                continue
            if direction == "outgoing":
                if importer_path != target_path or resolved_path == target_path:
                    continue
                related_path = resolved_path
                reason = "target_imports"
            else:
                if resolved_path != target_path or importer_path == target_path:
                    continue
                related_path = importer_path
                reason = "imports_target"
            node = _preferred_node_for_path(nodes_by_id, related_path)
            evidence = {
                "import_id": row["id"],
                "line": row["line"],
                "path": related_path,
                "resolution": "relative_path_heuristic",
                "source": "javascript_imports",
                "specifier": row["specifier"],
            }
            relationships.append(
                {
                    "confidence": "high",
                    "edge": None,
                    "evidence": [evidence],
                    "node": node,
                    "path": related_path,
                    "reason": reason,
                }
            )
        relationships.sort(
            key=lambda item: (
                _relationship_sort_priority(str(item["reason"]), str(item["path"])),
                str(item["path"]),
            )
        )
        return relationships

    def _related_docs(
        self,
        connection: sqlite3.Connection,
        target_node_ids: set[str],
        nodes_by_id: dict[str, dict[str, Any]],
        *,
        files_by_path: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        edges = self._edges_for_nodes(
            connection,
            target_node_ids,
            direction="incoming",
            edge_kinds=_RELATED_DOC_EDGE_KINDS,
        )
        for edge in edges:
            if edge["target_id"] not in target_node_ids:
                continue
            node = nodes_by_id.get(str(edge["source_id"]))
            if node is None:
                continue
            path = _node_path(node)
            if path is None or path not in files_by_path or not _is_documentation_path(path):
                continue
            docs.append(
                _file_context_item(
                    path=path,
                    reason=_doc_relationship_reason(str(edge["kind"])),
                    confidence="high",
                    evidence=[_edge_evidence(edge, direction="incoming", path=path)],
                    node=node,
                )
            )
        return _dedupe_file_items(docs)

    def _related_configs(
        self,
        connection: sqlite3.Connection,
        *,
        target_path: str | None,
        files_by_path: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if target_path is None:
            return []
        config_paths: dict[str, dict[str, Any]] = {}
        for row in connection.execute(
            "SELECT name, ecosystem, path, source_path FROM config_package_roots ORDER BY path, name"
        ):
            package_root = str(row["path"])
            if not _path_is_under(target_path, package_root):
                continue
            source_path = str(row["source_path"])
            if source_path not in files_by_path:
                continue
            config_paths.setdefault(
                source_path,
                _file_context_item(
                    path=source_path,
                    reason="package_root_context",
                    confidence="medium",
                    evidence=[
                        {
                            "ecosystem": row["ecosystem"],
                            "package_root": package_root,
                            "source": "config_package_roots",
                        }
                    ],
                ),
            )
        for row in connection.execute(
            "SELECT path, kind, name, target, evidence FROM config_entrypoints ORDER BY path, name"
        ):
            entrypoint_target = str(row["target"])
            if not _entrypoint_targets_path(entrypoint_target, target_path):
                continue
            source_path = str(row["path"])
            if source_path not in files_by_path:
                continue
            config_paths.setdefault(
                source_path,
                _file_context_item(
                    path=source_path,
                    reason="entrypoint_context",
                    confidence="medium",
                    evidence=[
                        {
                            "entrypoint": row["name"],
                            "kind": row["kind"],
                            "source": "config_entrypoints",
                        }
                    ],
                ),
            )
        items = list(config_paths.values())
        items.sort(key=lambda item: str(item["path"]))
        return items

    def _risk_comments(
        self,
        connection: sqlite3.Connection,
        *,
        target_path: str | None,
        related_paths: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        paths = sorted({path for path in (*related_paths, target_path) if path is not None})
        if not paths:
            return []
        placeholders = ",".join("?" for _ in paths)
        rows: list[dict[str, Any]] = []
        rows.extend(
            _rows_to_dicts(
                connection.execute(
                    f"""
                    SELECT path, tag, text, line
                    FROM python_tagged_comments
                    WHERE path IN ({placeholders})
                    ORDER BY path, line, tag
                    """,
                    paths,
                )
            )
        )
        rows.extend(
            _rows_to_dicts(
                connection.execute(
                    f"""
                    SELECT path, tag, text, line
                    FROM documentation_tagged_comments
                    WHERE path IN ({placeholders})
                    ORDER BY path, line, tag
                    """,
                    paths,
                )
            )
        )
        comments = [
            {
                "confidence": "high" if row["path"] == target_path else "medium",
                "line": row["line"],
                "path": row["path"],
                "reason": "tagged_comment_on_target_file"
                if row["path"] == target_path
                else "tagged_comment_on_related_file",
                "tag": row["tag"],
                "text": row["text"],
            }
            for row in rows
        ]
        comments.sort(
            key=lambda item: (
                0 if item["path"] == target_path else 1,
                int(item["line"]),
                str(item["tag"]),
            )
        )
        return comments

    def _candidate_verification_commands(
        self,
        connection: sqlite3.Connection,
        *,
        related_config_paths: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        rows = _rows_to_dicts(
            connection.execute(
                """
                SELECT id, path, source, name, command, purpose, not_run, auto_run_recommended
                FROM config_commands
                ORDER BY purpose, path, source, name
                """
            )
        )
        related = set(related_config_paths)
        commands = []
        for row in rows:
            if row["purpose"] not in _VERIFICATION_PURPOSES:
                continue
            if related and row["path"] not in related:
                continue
            commands.append(_command_payload(row))
        commands.sort(
            key=lambda command: (
                _COMMAND_PURPOSE_PRIORITY.get(str(command["purpose"]), 100),
                str(command["path"]),
                str(command["name"]),
            )
        )
        return commands

    def _focused_task_resolution(
        self,
        connection: sqlite3.Connection,
        task: str,
        tokens: tuple[str, ...],
    ) -> _ResolvedNode | None:
        if len(tokens) > 2:
            return None
        resolved = self._resolve_node(connection, task)
        return resolved if resolved.ambiguous else None

    def _reading_order_recommendations(
        self,
        connection: sqlite3.Connection,
        task: str,
        tokens: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        del task
        files_by_path = self._files_by_path(connection)
        config_paths = self._config_file_paths(connection)
        config_relevant = _task_mentions_config(tokens)
        recommendations_by_path: dict[str, dict[str, Any]] = {}

        for row in connection.execute("SELECT id, kind, path, label, metadata_json FROM nodes"):
            node = _node_payload(row)
            path = _node_path(node)
            if path is None or path not in files_by_path or _is_test_path(path):
                continue
            category = _file_category(path, node, config_paths)
            if category == "config" and not config_relevant:
                continue
            score, evidence, reason = _score_reading_order_node(node, tokens, category)
            if score <= 0:
                continue
            current = recommendations_by_path.get(path)
            if current is None:
                recommendations_by_path[path] = _reading_order_item(
                    path=path,
                    reason=reason,
                    confidence=_confidence_for_reading_score(score),
                    evidence=evidence,
                    category=category,
                    node=node,
                    score=score,
                )
                continue
            current["_score"] = int(current["_score"]) + score
            current["evidence"] = _merge_evidence(current["evidence"], evidence)
            current["confidence"] = _confidence_for_reading_score(int(current["_score"]))
            current["reason"] = _preferred_reading_reason(str(current["reason"]), reason)
            current["ranking_reason"] = _ranking_reason(str(current["reason"]))
            if _node_reading_priority(node) < _node_reading_priority(current["node"]):
                current["node"] = node

        primary = sorted(
            recommendations_by_path.values(),
            key=lambda item: (
                -int(item["_score"]),
                _FILE_RECOMMENDATION_KIND_PRIORITY.get(str(item["category"]), 100),
                str(item["path"]),
            ),
        )

        source_paths = [str(item["path"]) for item in primary if item["category"] == "source"]
        likely_tests = self._reading_order_tests(
            connection,
            source_paths=tuple(source_paths),
            tokens=tokens,
            files_by_path=files_by_path,
        )
        tests_by_source = _tests_by_source_path(likely_tests)
        ordered: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        for item in primary:
            path = str(item["path"])
            if path in seen_paths:
                continue
            ordered.append(_strip_internal_recommendation_fields(item))
            seen_paths.add(path)
            for test in tests_by_source.get(path, []):
                test_path = str(test["path"])
                if test_path in seen_paths:
                    continue
                ordered.append(_strip_internal_recommendation_fields(test))
                seen_paths.add(test_path)
        return ordered

    def _reading_order_tests(
        self,
        connection: sqlite3.Connection,
        *,
        source_paths: tuple[str, ...],
        tokens: tuple[str, ...],
        files_by_path: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        del tokens
        tests: list[dict[str, Any]] = []
        for source_path in source_paths:
            target_node_ids = self._node_ids_for_path(connection, source_path)
            dependents = self._impact_relationships(
                connection,
                target_node_ids,
                self._nodes_by_id(connection),
                direction="incoming",
            )
            for item in self._likely_tests(
                connection,
                target_path=source_path,
                target_node_ids=target_node_ids,
                files_by_path=files_by_path,
                dependent_relationships=dependents,
            ):
                tests.append(
                    _reading_order_item(
                        path=str(item["path"]),
                        reason="likely_related_test",
                        confidence=str(item["confidence"]),
                        evidence=[
                            *item["evidence"],
                            {"source": "related_test_edges", "target_path": source_path},
                        ],
                        category="test",
                        node=item.get("node"),
                        score=120
                        if str(item.get("resolution_strategy", "")).startswith("direct_import")
                        else 80,
                        source_path=source_path,
                        resolution_strategy=item.get("resolution_strategy"),
                    )
                )
        tests.sort(key=lambda item: (-int(item["_score"]), str(item["path"])))
        return _dedupe_reading_items(tests)

    def _reading_order_candidate_verification_commands(
        self,
        connection: sqlite3.Connection,
        *,
        tokens: tuple[str, ...],
        recommendations: list[dict[str, Any]],
        max_commands: int,
    ) -> list[dict[str, Any]]:
        if not _task_mentions_config(tokens):
            return []
        config_paths = self._config_file_paths(connection)
        related_paths = tuple(
            str(item["path"]) for item in recommendations if str(item["path"]) in config_paths
        )
        if not related_paths:
            related_paths = tuple(sorted(config_paths))
        return self._candidate_verification_commands(
            connection,
            related_config_paths=related_paths,
        )[:max_commands]

    def _config_file_paths(self, connection: sqlite3.Connection) -> set[str]:
        return {str(row["path"]) for row in connection.execute("SELECT path FROM config_files")}


def _empty_impact_data(
    *,
    target: str,
    resolved: _ResolvedNode,
    depth: int,
    max_results: int,
) -> dict[str, Any]:
    groups = _impact_groups(
        max_results=max_results,
        direct_affected=[],
        dependencies=[],
        dependents=[],
        likely_tests=[],
        related_docs=[],
        related_configs=[],
        risk_comments=[],
        candidate_commands=[],
    )
    return {
        "ambiguous": resolved.ambiguous,
        "candidate_verification_commands": [],
        "candidates": list(resolved.candidates),
        "caps": {"depth": depth, "max_results": max_results},
        "dependencies": [],
        "dependents": [],
        "direct_affected_files": [],
        "impact_groups": groups,
        "likely_affected_files": [],
        "likely_tests": [],
        "related_configs": [],
        "related_docs": [],
        "requested_target": target,
        "resolution": _resolution_payload(resolved),
        "risk_comments": [],
        "rollups": _impact_rollups(groups),
        "target": None,
        "truncated": _impact_truncation(groups, [], max_results),
    }


def _impact_groups(
    *,
    max_results: int,
    direct_affected: list[dict[str, Any]],
    dependencies: list[dict[str, Any]],
    dependents: list[dict[str, Any]],
    likely_tests: list[dict[str, Any]],
    related_docs: list[dict[str, Any]],
    related_configs: list[dict[str, Any]],
    risk_comments: list[dict[str, Any]],
    candidate_commands: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        "direct_affected_files": _impact_group(
            label="Target and likely dependent files",
            reason="Files to inspect first when planning an edit around the target.",
            items=direct_affected,
            max_results=max_results,
        ),
        "dependencies": _impact_group(
            label="Likely dependencies",
            reason="Files or symbols the target references through indexed graph relationships.",
            items=dependencies,
            max_results=max_results,
        ),
        "dependents": _impact_group(
            label="Likely dependents",
            reason="Files or symbols that reference the target through indexed graph relationships.",
            items=dependents,
            max_results=max_results,
        ),
        "likely_tests": _impact_group(
            label="Related tests",
            reason="Tests connected by direct references or deterministic path/name similarity; not coverage proof.",
            items=likely_tests,
            max_results=max_results,
        ),
        "related_docs": _impact_group(
            label="Related documentation",
            reason="Documentation files that link to or mention the target.",
            items=related_docs,
            max_results=max_results,
        ),
        "related_configs": _impact_group(
            label="Related configuration",
            reason="Configuration files that provide package, command, or entrypoint context for the target.",
            items=related_configs,
            max_results=max_results,
        ),
        "risk_comments": _impact_group(
            label="Risk notes",
            reason="Tagged comments on the target or likely dependent files.",
            items=risk_comments,
            max_results=max_results,
        ),
        "candidate_verification_commands": _impact_group(
            label="Candidate verification commands",
            reason="Declared lint, test, or typecheck commands recorded as candidates only; not run or auto-recommended.",
            items=candidate_commands,
            max_results=max_results,
        ),
    }


def _impact_group(
    *,
    label: str,
    reason: str,
    items: list[dict[str, Any]],
    max_results: int,
) -> dict[str, Any]:
    return {
        "items": items[:max_results],
        "label": label,
        "reason": reason,
        "total": len(items),
        "truncated": len(items) > max_results,
    }


def _impact_rollups(groups: dict[str, dict[str, Any]]) -> dict[str, Any]:
    counts = {name: int(group["total"]) for name, group in groups.items()}
    return {
        "counts": counts,
        "total_groups": len(groups),
        "total_items": sum(counts.values()),
        "truncated_groups": [name for name, group in groups.items() if group["truncated"]],
    }


def _impact_truncation(
    groups: dict[str, dict[str, Any]],
    likely_affected: list[dict[str, Any]],
    max_results: int,
) -> dict[str, bool]:
    return {
        **{name: bool(group["truncated"]) for name, group in groups.items()},
        "impact_groups": any(group["truncated"] for group in groups.values()),
        "likely_affected_files": len(likely_affected) > max_results,
    }


def _node_path(node: dict[str, Any] | None) -> str | None:
    if node is None or node.get("path") is None:
        return None
    path = str(node["path"])
    return path if path else None


def _target_file_items(
    files_by_path: dict[str, dict[str, Any]],
    target_path: str | None,
    target_node: dict[str, Any],
) -> list[dict[str, Any]]:
    if target_path is None or target_path not in files_by_path:
        return []
    return [
        _file_context_item(
            path=target_path,
            reason="target_file",
            confidence="high",
            evidence=[{"node_id": target_node["id"], "source": "target_resolution"}],
            node=target_node,
        )
    ]


def _relationship_file_item(item: dict[str, Any], *, reason: str) -> dict[str, Any]:
    return _file_context_item(
        path=str(item["path"]),
        reason=reason,
        confidence=str(item["confidence"]),
        evidence=item["evidence"],
        node=item.get("node"),
    )


def _file_context_item(
    *,
    path: str,
    reason: str,
    confidence: str,
    evidence: list[dict[str, Any]],
    node: dict[str, Any] | None = None,
    resolution_strategy: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "confidence": confidence,
        "evidence": evidence[:3],
        "path": path,
        "reason": reason,
    }
    if resolution_strategy is not None:
        item["resolution_strategy"] = resolution_strategy
    if node is not None:
        item["node"] = node
    return item


def _dedupe_file_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for item in items:
        path = str(item["path"])
        current = deduped.get(path)
        if current is None:
            deduped[path] = item
            continue
        if _confidence_rank(str(item["confidence"])) > _confidence_rank(str(current["confidence"])):
            current["confidence"] = item["confidence"]
            if "resolution_strategy" in item:
                current["resolution_strategy"] = item["resolution_strategy"]
        current["evidence"] = _merge_evidence(current["evidence"], item["evidence"])
    return list(deduped.values())


def _dedupe_relationships(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        key = (str(item["path"]), str(item["reason"]))
        current = deduped.get(key)
        if current is None:
            deduped[key] = item
            continue
        current["evidence"] = _merge_evidence(current["evidence"], item["evidence"])
        if _confidence_rank(str(item["confidence"])) > _confidence_rank(str(current["confidence"])):
            current["confidence"] = item["confidence"]
    relationships = list(deduped.values())
    relationships.sort(
        key=lambda item: (
            _relationship_sort_priority(str(item["reason"]), str(item["path"])),
            str(item["path"]),
        )
    )
    return relationships


def _preferred_node_for_path(
    nodes_by_id: dict[str, dict[str, Any]],
    path: str,
) -> dict[str, Any] | None:
    nodes = [node for node in nodes_by_id.values() if node.get("path") == path]
    if not nodes:
        return None
    return _preferred_path_node(nodes)


def _resolve_relative_import_path(
    importer_path: str,
    specifier: str,
    files_by_path: dict[str, dict[str, Any]],
) -> str | None:
    if not specifier.startswith("."):
        return None
    importer_parent = PurePosixPath(importer_path).parent
    normalized = PurePosixPath(importer_parent, specifier).as_posix()
    parts = PurePosixPath(normalized).parts
    collapsed: list[str] = []
    for part in parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not collapsed:
                return None
            collapsed.pop()
            continue
        collapsed.append(part)
    base = "/".join(collapsed)
    for candidate in _module_path_candidates(base):
        if candidate in files_by_path:
            return candidate
    return None


def _module_path_candidates(base: str) -> tuple[str, ...]:
    suffix = PurePosixPath(base).suffix
    if suffix:
        return (base,)
    extensions = (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs")
    return (
        *tuple(f"{base}{extension}" for extension in extensions),
        f"{base}/index.ts",
        f"{base}/index.js",
    )


def _edge_evidence(edge: dict[str, Any], *, direction: str, path: str) -> dict[str, Any]:
    evidence = {
        "direction": direction,
        "edge_id": edge["id"],
        "edge_kind": edge["kind"],
        "path": path,
        "source": "edges",
    }
    lines = edge.get("metadata", {}).get("lines")
    if lines:
        evidence["lines"] = lines
    return evidence


def _relationship_reason(edge_kind: str, direction: str) -> str:
    if direction == "incoming" and edge_kind == "IMPORTS":
        return "imports_target"
    if direction == "outgoing" and edge_kind == "IMPORTS":
        return "target_imports"
    if direction == "incoming" and edge_kind == "CALLS":
        return "calls_target"
    if direction == "outgoing" and edge_kind == "CALLS":
        return "target_calls"
    return "related_by_graph_edge"


def _related_test_reason(edge: dict[str, Any]) -> str:
    metadata = edge.get("metadata", {})
    reason = metadata.get("reason")
    if isinstance(reason, list):
        reasons = {str(item) for item in reason}
        if "direct_import_related_test" in reasons:
            return "direct_import_related_test"
        if "path_name_similarity" in reasons:
            return "path_name_similarity"
    return str(reason) if reason else "likely_related_test"


def _relationship_confidence(edge_kind: str) -> str:
    return "high" if edge_kind in _IMPACT_EDGE_KINDS else "medium"


def _relationship_sort_priority(reason: str, path: str) -> int:
    if _is_test_path(path):
        return 2
    if reason in {"imports_target", "calls_target"}:
        return 0
    return 1


def _is_test_path(path: str) -> bool:
    pure_path = PurePosixPath(path)
    parts = tuple(part.casefold() for part in pure_path.parts)
    stem_tokens = set(_meaningful_tokens(pure_path.stem))
    return (
        any(part in {"test", "tests", "spec", "specs"} for part in parts)
        or pure_path.name.casefold().startswith("test_")
        or pure_path.stem.casefold().endswith((".test", ".spec", "_test", "_spec"))
        or bool(stem_tokens & _TEST_PATH_TOKENS)
    )


def _shared_path_tokens(source_path: str, candidate_path: str) -> list[str]:
    source_name_tokens = set(_meaningful_tokens(PurePosixPath(source_path).stem))
    candidate_tokens = set(_meaningful_tokens(candidate_path))
    ignored = {"index", "src", "source", "test", "tests", "spec"}
    matched = sorted((source_name_tokens - ignored) & (candidate_tokens - ignored))
    return matched


def _doc_relationship_reason(edge_kind: str) -> str:
    if edge_kind == "LINKS_TO_FILE":
        return "doc_links_to_target"
    if edge_kind == "MENTIONS_FILE":
        return "doc_mentions_target"
    return "related_documentation"


def _is_documentation_path(path: str) -> bool:
    return PurePosixPath(path).suffix.casefold() in {".md", ".markdown", ".mdx"}


def _path_is_under(path: str, root: str) -> bool:
    if root == ".":
        return True
    return path == root or path.startswith(f"{root}/")


def _entrypoint_targets_path(target: str, path: str) -> bool:
    normalized_target = target.replace("\\", "/")
    return normalized_target == path or normalized_target.endswith(f"/{path}")


def _meaningful_tokens(value: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for token in _tokens(value):
        normalized = token[:-1] if len(token) > 3 and token.endswith("s") else token
        if normalized in _READING_ORDER_STOPWORDS:
            continue
        tokens.append(normalized)
    return tuple(dict.fromkeys(tokens))


def _task_mentions_config(tokens: tuple[str, ...]) -> bool:
    token_set = set(tokens)
    strong_config_tokens = _CONFIG_TASK_TOKENS - {"test"}
    if token_set & strong_config_tokens:
        return True
    return "test" in token_set and bool(token_set & {"command", "config", "package", "script"})


def _file_category(path: str, node: dict[str, Any], config_paths: set[str]) -> str:
    if _is_test_path(path):
        return "test"
    if path in config_paths or node["kind"] in _CONFIG_NODE_KINDS:
        return "config"
    if _is_documentation_path(path) or node["kind"] in _DOCUMENTATION_NODE_KINDS:
        return "documentation"
    if node["kind"] in _SOURCE_MODULE_KINDS or PurePosixPath(path).suffix.casefold() in {
        ".cjs",
        ".cts",
        ".js",
        ".jsx",
        ".mjs",
        ".mts",
        ".py",
        ".ts",
        ".tsx",
    }:
        return "source"
    return "other"


def _score_reading_order_node(
    node: dict[str, Any],
    tokens: tuple[str, ...],
    category: str,
) -> tuple[int, list[dict[str, Any]], str]:
    token_set = set(tokens)
    score = 0
    evidence: list[dict[str, Any]] = []
    scored_token_sets: set[tuple[str, ...]] = set()
    for field_name, field_value in _node_search_fields(node):
        field_tokens = set(_meaningful_tokens(field_value))
        matched = sorted(token_set & field_tokens)
        if not matched:
            continue
        match_key = tuple(matched)
        if match_key not in scored_token_sets:
            scored_token_sets.add(match_key)
            field_score = len(matched) * len(matched) * 20
            if token_set.issubset(field_tokens):
                field_score += 40
            if field_name in {"label", "metadata.name", "metadata.qualified_name"}:
                field_score += 25
            if field_name == "path":
                field_score += 15
            score += field_score
        evidence.append(
            {
                "field": field_name,
                "matched_tokens": matched,
                "node_id": node["id"],
                "path": node.get("path"),
                "source": "task_token_match",
            }
        )
    if score <= 0:
        return 0, [], "task_token_match"
    if node["kind"] in _SYMBOL_NODE_KINDS:
        score += 20
    if node["kind"] in _SOURCE_MODULE_KINDS:
        score += 10
    if category == "config":
        return score, evidence[:3], "config_matches_task"
    if category == "documentation":
        return score, evidence[:3], "documentation_matches_task"
    if node["kind"] in _SYMBOL_NODE_KINDS or node["kind"] in _SOURCE_MODULE_KINDS:
        return score, evidence[:3], "task_matches_symbols"
    return score, evidence[:3], "task_token_match"


def _confidence_for_reading_score(score: int) -> str:
    if score >= 160:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _reading_order_item(
    *,
    path: str,
    reason: str,
    confidence: str,
    evidence: list[dict[str, Any]],
    category: str,
    node: dict[str, Any] | None,
    score: int,
    source_path: str | None = None,
    resolution_strategy: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "_score": score,
        "category": category,
        "confidence": confidence,
        "evidence": evidence[:3],
        "node": node,
        "path": path,
        "reason": reason,
        "ranking_reason": _ranking_reason(reason),
    }
    if source_path is not None:
        item["source_path"] = source_path
    if resolution_strategy is not None:
        item["resolution_strategy"] = resolution_strategy
    return item


def _merge_evidence(
    first: list[dict[str, Any]],
    second: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for evidence in [*first, *second]:
        key = json.dumps(evidence, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        merged.append(evidence)
        if len(merged) >= 3:
            break
    return merged


def _preferred_reading_reason(current: str, candidate: str) -> str:
    priority = {
        "task_matches_symbols": 0,
        "config_matches_task": 1,
        "documentation_matches_task": 2,
        "task_token_match": 3,
    }
    return candidate if priority.get(candidate, 100) < priority.get(current, 100) else current


def _ranking_reason(reason: str) -> str:
    reasons = {
        "config_matches_task": "Task tokens matched indexed config or command metadata.",
        "documentation_matches_task": "Task tokens matched indexed documentation context.",
        "likely_related_test": "Likely related test from graph evidence.",
        "task_matches_symbols": "Task tokens matched indexed source symbols.",
        "task_token_match": "Task tokens matched indexed graph metadata.",
    }
    return reasons.get(reason, "Ranked from deterministic graph metadata.")


def _node_reading_priority(node: dict[str, Any] | None) -> int:
    if node is None:
        return 100
    if node["kind"] in _SYMBOL_NODE_KINDS:
        return 0
    if node["kind"] in _SOURCE_MODULE_KINDS:
        return 1
    if node["kind"] in {"MarkdownFile", "ConfigFile"}:
        return 2
    if node["kind"] == "File":
        return 3
    return 4


def _strip_internal_recommendation_fields(item: dict[str, Any]) -> dict[str, Any]:
    stripped = {
        key: value
        for key, value in item.items()
        if key not in {"_score", "category", "source_path"} and value is not None
    }
    return stripped


def _tests_by_source_path(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    tests: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        source_path = str(item.get("source_path") or "")
        if not source_path:
            continue
        tests.setdefault(source_path, []).append(item)
    return tests


def _dedupe_reading_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for item in items:
        path = str(item["path"])
        current = deduped.get(path)
        if current is None or int(item["_score"]) > int(current["_score"]):
            deduped[path] = item
    return list(deduped.values())


def _confidence_rank(confidence: str) -> int:
    return {"none": 0, "low": 1, "medium": 2, "high": 3}.get(confidence, 0)


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
    data["evidence"] = _decode_list(data.pop("evidence_json", None))
    return data


def _edge_payload(edge: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": edge["id"],
        "confidence": edge.get("confidence", "high"),
        "evidence": edge.get("evidence", []),
        "kind": edge["kind"],
        "metadata": edge.get("metadata", {}),
        "resolution_strategy": edge.get("resolution_strategy", "direct"),
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


def _decode_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    try:
        decoded = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return decoded if isinstance(decoded, list) else []


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


def _resolution_strategy_for_score(score: int) -> str:
    if score >= _EXACT_MATCH_SCORE:
        return "exact_reference"
    if score >= 500:
        return "structured_metadata_match"
    return "fuzzy_candidate"


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
        "resolution_strategy": resolved.resolution_strategy,
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
