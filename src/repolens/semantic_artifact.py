"""Experimental semantic artifact skeleton outside the stable graph contract."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from repolens.javascript_index import JAVASCRIPT_SOURCE_SUFFIXES
from repolens.parser_backends import (
    ParserBackendOption,
    default_parser_backend_provenance,
    resolve_parser_backend,
)
from repolens.scanner import (
    ARTIFACT_DIR_NAME,
    ScanError,
    ScannedFile,
    ScanResult,
    scan_repository,
)

SEMANTIC_SCHEMA_VERSION = 2
SEMANTIC_STORE_FILENAME = "semantic.sqlite"
SEMANTIC_STORE_PATH = f"{ARTIFACT_DIR_NAME}/{SEMANTIC_STORE_FILENAME}"
SEMANTIC_BACKEND = "semantic_skeleton"
SEMANTIC_EXPERIMENTAL_STATUS = "experimental"
SEMANTIC_CONFIDENCE = "candidate"
SEMANTIC_EVIDENCE_LABELS = ("scanner:eligible_file", "semantic:skeleton")
PYTHON_CFG_EVIDENCE_LABELS = (
    "scanner:eligible_file",
    "semantic:skeleton",
    "python:ast",
    "semantic:python_branch_cfg",
)


class SemanticArtifactError(RuntimeError):
    """Raised when the experimental semantic artifact cannot be written."""


@dataclass(frozen=True)
class SemanticArtifactStatus:
    """Deterministic status for the experimental semantic artifact."""

    status: str
    reason: str
    artifact_path: str = SEMANTIC_STORE_PATH
    detected_schema_version: str | None = None
    supported_schema_version: int = SEMANTIC_SCHEMA_VERSION

    def to_cli_data(self) -> dict[str, object]:
        return {
            "artifact_path": self.artifact_path,
            "detected_schema_version": self.detected_schema_version,
            "reason": self.reason,
            "status": self.status,
            "supported_schema_version": self.supported_schema_version,
        }


@dataclass(frozen=True)
class SemanticInspectResult:
    """Source-free semantic artifact inspection for one repository file."""

    source_path: str
    artifact_status: SemanticArtifactStatus
    artifact_freshness: dict[str, object]
    source_language: str | None = None
    semantic_backend: str | None = None
    parser_backend: str | None = None
    experimental_status: str | None = None
    control_flow: tuple[dict[str, object], ...] = ()
    warnings: tuple[str, ...] = ()

    def to_cli_data(self) -> dict[str, object]:
        return {
            "artifact_freshness": self.artifact_freshness,
            "artifact_status": self.artifact_status.to_cli_data(),
            "experimental_status": self.experimental_status or SEMANTIC_EXPERIMENTAL_STATUS,
            "facts": {
                "calls": [],
                "control_flow": list(self.control_flow),
                "definitions": [],
                "imports": [],
                "relationships": [],
            },
            "limits": {
                "fact_set": "python_branch_cfg" if self.control_flow else "semantic_skeleton_empty",
                "source_snippets": 0,
            },
            "parser_backend": self.parser_backend,
            "schema_version": SEMANTIC_SCHEMA_VERSION,
            "semantic_backend": self.semantic_backend or SEMANTIC_BACKEND,
            "source_language": self.source_language,
            "source_path": self.source_path,
            "warnings": list(self.warnings),
        }


def write_semantic_artifact(
    root: Path,
    scan: ScanResult,
    *,
    parser_backend: ParserBackendOption = "default",
) -> str:
    """Write source-free experimental semantic metadata outside ``graph.sqlite``."""
    artifact_dir = root / ARTIFACT_DIR_NAME
    target = root / SEMANTIC_STORE_PATH
    backend = resolve_parser_backend(parser_backend)
    parser_provenance = default_parser_backend_provenance()
    temp_path: Path | None = None

    try:
        artifact_dir.mkdir(exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "wb",
            delete=False,
            dir=str(artifact_dir),
            prefix="semantic-",
            suffix=".sqlite.tmp",
        ) as temp_file:
            temp_path = Path(temp_file.name)

        with sqlite3.connect(temp_path) as connection:
            _create_schema(connection)
            metadata = {
                "artifact": "semantic",
                "experimental_status": SEMANTIC_EXPERIMENTAL_STATUS,
                "parser_backend": backend.name,
                "parser_backend_provenance_json": _json_value(parser_provenance),
                "schema_version": str(SEMANTIC_SCHEMA_VERSION),
                "semantic_backend": SEMANTIC_BACKEND,
                "source_fingerprint": _source_fingerprint(scan.files),
            }
            connection.executemany(
                "INSERT INTO metadata(key, value) VALUES (?, ?)",
                sorted(metadata.items()),
            )
            source_rows = [
                (
                    file.path,
                    _language_for_path(file.path),
                    SEMANTIC_BACKEND,
                    backend.name,
                    _json_value(
                        {
                            "parser_backend": backend.name,
                            "parser_backend_provenance": parser_provenance,
                            "semantic_backend": SEMANTIC_BACKEND,
                        }
                    ),
                    SEMANTIC_CONFIDENCE,
                    _json_value(SEMANTIC_EVIDENCE_LABELS),
                    SEMANTIC_EXPERIMENTAL_STATUS,
                    _json_value(_python_cfg_facts(root, file, backend.name)),
                )
                for file in sorted(scan.files, key=lambda item: item.path)
                if _language_for_path(file.path) in {"python", "javascript", "typescript"}
            ]
            connection.executemany(
                """
                INSERT INTO semantic_sources(
                    source_path,
                    source_language,
                    semantic_backend,
                    parser_backend,
                    provenance_json,
                    confidence,
                    evidence_labels_json,
                    experimental_status,
                    control_flow_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                source_rows,
            )
            connection.commit()
        os.replace(temp_path, target)
    except (OSError, sqlite3.Error) as exc:
        raise SemanticArtifactError("semantic_artifact_write_failed") from exc
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass

    return SEMANTIC_STORE_PATH


def inspect_semantic_artifact(root: Path) -> SemanticArtifactStatus:
    """Inspect the experimental semantic artifact without mutating artifacts."""
    artifact = root / SEMANTIC_STORE_PATH
    if not artifact.exists():
        return SemanticArtifactStatus(status="missing", reason="semantic_artifact_missing")
    if artifact.is_symlink():
        return SemanticArtifactStatus(status="unsupported", reason="semantic_artifact_is_symlink")

    try:
        metadata = _read_metadata(artifact)
    except sqlite3.Error:
        return SemanticArtifactStatus(status="unsupported", reason="semantic_artifact_unreadable")

    schema_version = metadata.get("schema_version")
    if schema_version != str(SEMANTIC_SCHEMA_VERSION):
        return SemanticArtifactStatus(
            status="unsupported",
            reason="semantic_schema_version_unsupported",
            detected_schema_version=schema_version,
        )

    try:
        scan = scan_repository(root)
    except ScanError:
        return SemanticArtifactStatus(
            status="stale",
            reason="semantic_live_scan_failed",
            detected_schema_version=schema_version,
        )

    if metadata.get("source_fingerprint") != _source_fingerprint(scan.files):
        return SemanticArtifactStatus(
            status="stale",
            reason="semantic_source_fingerprint_changed",
            detected_schema_version=schema_version,
        )

    return SemanticArtifactStatus(
        status="present",
        reason="semantic_artifact_current",
        detected_schema_version=schema_version,
    )


def inspect_semantic_source(root: Path, source_path: Path | str) -> SemanticInspectResult:
    """Read source-free semantic metadata for one file from indexed artifacts."""
    artifact_status = inspect_semantic_artifact(root)
    normalized_source_path = _normalize_source_path(root, source_path)
    warnings: list[str] = []
    artifact_freshness = _artifact_freshness(root)
    row = None
    if artifact_status.status in {"present", "stale"}:
        try:
            row = _read_semantic_source(root / SEMANTIC_STORE_PATH, normalized_source_path)
        except sqlite3.Error:
            row = None

    if artifact_status.status != "present":
        if artifact_status.status == "missing":
            warnings.append(
                "Semantic artifacts are missing; run repolens index with --experimental-semantic-artifact."
            )
        elif artifact_status.status == "stale":
            warnings.append(
                "Semantic artifacts are stale; re-index before relying on semantic facts."
            )
        else:
            warnings.append("Semantic artifacts cannot be inspected safely.")
        return SemanticInspectResult(
            source_path=normalized_source_path,
            artifact_status=artifact_status,
            artifact_freshness=artifact_freshness,
            source_language=str(row["source_language"]) if row is not None else None,
            semantic_backend=str(row["semantic_backend"]) if row is not None else None,
            parser_backend=str(row["parser_backend"]) if row is not None else None,
            experimental_status=str(row["experimental_status"]) if row is not None else None,
            control_flow=_row_control_flow(row),
            warnings=tuple(warnings),
        )

    if row is None:
        warnings.append("Requested source path is not present in indexed semantic artifacts.")
        return SemanticInspectResult(
            source_path=normalized_source_path,
            artifact_status=artifact_status,
            artifact_freshness=artifact_freshness,
            warnings=tuple(warnings),
        )

    return SemanticInspectResult(
        source_path=normalized_source_path,
        artifact_status=artifact_status,
        artifact_freshness=artifact_freshness,
        source_language=str(row["source_language"]),
        semantic_backend=str(row["semantic_backend"]),
        parser_backend=str(row["parser_backend"]),
        experimental_status=str(row["experimental_status"]),
        control_flow=_row_control_flow(row),
        warnings=tuple(warnings),
    )


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE semantic_sources (
            source_path TEXT PRIMARY KEY,
            source_language TEXT NOT NULL,
            semantic_backend TEXT NOT NULL,
            parser_backend TEXT NOT NULL,
            provenance_json TEXT NOT NULL,
            confidence TEXT NOT NULL,
            evidence_labels_json TEXT NOT NULL,
            experimental_status TEXT NOT NULL,
            control_flow_json TEXT NOT NULL
        ) WITHOUT ROWID;
        """
    )


def _read_metadata(path: Path) -> dict[str, str]:
    with sqlite3.connect(path) as connection:
        return {
            str(key): str(value)
            for key, value in connection.execute("SELECT key, value FROM metadata")
        }


def _read_semantic_source(artifact: Path, source_path: str) -> sqlite3.Row | None:
    with sqlite3.connect(artifact) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(
            """
            SELECT
                source_language,
                semantic_backend,
                parser_backend,
                experimental_status,
                control_flow_json
            FROM semantic_sources
            WHERE source_path = ?
            """,
            (source_path,),
        ).fetchone()


def _artifact_freshness(root: Path) -> dict[str, object]:
    artifact = root / SEMANTIC_STORE_PATH
    if not artifact.exists() or artifact.is_symlink():
        return {
            "fresh": False,
            "reason": "semantic_artifact_missing",
            "checked_without_live_parse": True,
            "recommended_action": "repolens index . --experimental-semantic-artifact",
        }

    try:
        metadata = _read_metadata(artifact)
    except sqlite3.Error:
        return {
            "fresh": False,
            "reason": "semantic_artifact_unreadable",
            "checked_without_live_parse": True,
            "recommended_action": "repolens index . --experimental-semantic-artifact",
        }

    schema_version = metadata.get("schema_version")
    if schema_version != str(SEMANTIC_SCHEMA_VERSION):
        return {
            "fresh": False,
            "reason": "semantic_schema_version_unsupported",
            "checked_without_live_parse": True,
            "detected_schema_version": schema_version,
            "recommended_action": "repolens index . --experimental-semantic-artifact",
        }

    try:
        scan = scan_repository(root)
    except ScanError:
        return {
            "fresh": False,
            "reason": "semantic_live_scan_failed",
            "checked_without_live_parse": True,
            "recommended_action": "repolens index . --experimental-semantic-artifact",
        }

    fresh = metadata.get("source_fingerprint") == _source_fingerprint(scan.files)
    return {
        "fresh": fresh,
        "reason": "semantic_artifact_current" if fresh else "semantic_source_fingerprint_changed",
        "checked_without_live_parse": True,
        "fingerprint_strategy": "eligible_path_and_size",
        "recommended_action": None
        if fresh
        else "repolens index . --experimental-semantic-artifact",
    }


def _source_fingerprint(files: tuple[ScannedFile, ...]) -> str:
    payload = [(file.path, file.size_bytes) for file in sorted(files, key=lambda item: item.path)]
    return hashlib.sha256(_json_value(payload).encode("utf-8")).hexdigest()


def _python_cfg_facts(
    root: Path, file: ScannedFile, parser_backend: str
) -> list[dict[str, object]]:
    if _language_for_path(file.path) != "python":
        return []
    try:
        tree = ast.parse((root / file.path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeError):
        return [
            {
                "source_path": file.path,
                "warnings": ["python_cfg_parse_failed"],
                "evidence_labels": list(PYTHON_CFG_EVIDENCE_LABELS),
                "confidence": SEMANTIC_CONFIDENCE,
                "provenance": _cfg_provenance(parser_backend),
            }
        ]

    facts = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _has_cfg_relevant_node(
            node
        ):
            facts.append(_build_function_cfg(file.path, node, parser_backend))
    return facts


def _build_function_cfg(
    source_path: str,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    parser_backend: str,
) -> dict[str, object]:
    builder = _CfgBuilder(source_path, function, parser_backend)
    builder.build(function.body)
    return builder.fact()


class _CfgBuilder:
    def __init__(
        self,
        source_path: str,
        function: ast.FunctionDef | ast.AsyncFunctionDef,
        parser_backend: str,
    ) -> None:
        self.source_path = source_path
        self.function = function
        self.parser_backend = parser_backend
        self.nodes: list[dict[str, object]] = []
        self.edges: list[dict[str, object]] = []
        self.warnings: list[str] = []
        self.counter = 0
        self.entry_id = self._add_node("entry", function)
        self.counter += 1
        self.exit_id = f"exit:{self.counter:04d}"

    def build(self, statements: list[ast.stmt]) -> None:
        finals = self._sequence(statements, [(self.entry_id, "next")])
        self._append_node(self.exit_id, "exit", self.function, [])
        for source_id, edge_kind in finals:
            self._add_edge(source_id, self.exit_id, edge_kind)

    def fact(self) -> dict[str, object]:
        return {
            "source_path": self.source_path,
            "function": {
                "identity": f"{self.source_path}:{self.function.name}:{self.function.lineno}-{self.function.end_lineno or self.function.lineno}",
                "name": self.function.name,
                "line_range": _line_range(self.function),
            },
            "nodes": self.nodes,
            "edges": sorted(
                self.edges,
                key=lambda item: (str(item["from"]), str(item["to"]), str(item["kind"])),
            ),
            "warnings": sorted(set(self.warnings)),
            "confidence": SEMANTIC_CONFIDENCE,
            "evidence_labels": list(PYTHON_CFG_EVIDENCE_LABELS),
            "provenance": _cfg_provenance(self.parser_backend),
        }

    def _sequence(
        self,
        statements: list[ast.stmt],
        incoming: list[tuple[str, str]],
    ) -> list[tuple[str, str]]:
        current = incoming
        for statement in statements:
            if isinstance(statement, ast.If):
                branch_id = self._add_node("branch", statement)
                for source_id, edge_kind in current:
                    self._add_edge(source_id, branch_id, edge_kind)
                if _unsupported_branch_condition(statement.test):
                    unsupported_id = self._add_node("unsupported", statement)
                    self._add_edge(branch_id, unsupported_id, "next")
                    self.warnings.append("unsupported_dynamic_branch_condition")
                true_finals = self._sequence(statement.body, [(branch_id, "true_branch")])
                false_finals = (
                    self._sequence(statement.orelse, [(branch_id, "false_branch")])
                    if statement.orelse
                    else [(branch_id, "false_branch")]
                )
                current = true_finals + false_finals
            elif isinstance(statement, ast.Return):
                return_id = self._add_node("return", statement)
                for source_id, edge_kind in current:
                    self._add_edge(source_id, return_id, edge_kind)
                self._add_edge(return_id, self.exit_id, "next")
                current = []
            elif _unsupported_statement(statement):
                unsupported_id = self._add_node("unsupported", statement)
                for source_id, edge_kind in current:
                    self._add_edge(source_id, unsupported_id, edge_kind)
                self.warnings.append(f"unsupported_statement:{type(statement).__name__}")
                current = [(unsupported_id, "next")]
        return current

    def _add_node(self, kind: str, node: ast.AST) -> str:
        self.counter += 1
        node_id = f"{kind}:{self.counter:04d}"
        warnings = []
        if kind == "unsupported":
            warnings.append("unsupported_cfg_node")
        self._append_node(node_id, kind, node, warnings)
        return node_id

    def _append_node(self, node_id: str, kind: str, node: ast.AST, warnings: list[str]) -> None:
        self.nodes.append(
            {
                "id": node_id,
                "kind": kind,
                "line_range": _line_range(node),
                "confidence": SEMANTIC_CONFIDENCE,
                "evidence_labels": list(PYTHON_CFG_EVIDENCE_LABELS),
                "provenance": _cfg_provenance(self.parser_backend),
                "warnings": warnings,
            }
        )

    def _add_edge(self, source_id: str, target_id: str, kind: str) -> None:
        self.edges.append({"from": source_id, "to": target_id, "kind": kind})


def _unsupported_branch_condition(node: ast.AST) -> bool:
    return any(
        isinstance(child, (ast.Call, ast.Await, ast.Yield, ast.YieldFrom, ast.NamedExpr))
        for child in ast.walk(node)
    )


def _unsupported_statement(node: ast.stmt) -> bool:
    return isinstance(
        node,
        (
            ast.For,
            ast.AsyncFor,
            ast.While,
            ast.Try,
            ast.With,
            ast.AsyncWith,
            ast.Match,
            ast.Raise,
        ),
    )


def _has_cfg_relevant_node(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        isinstance(node, ast.If) or (isinstance(node, ast.stmt) and _unsupported_statement(node))
        for node in ast.walk(function)
    )


def _line_range(node: ast.AST) -> dict[str, int]:
    start = getattr(node, "lineno", 1) or 1
    end = getattr(node, "end_lineno", start) or start
    return {"start": int(start), "end": int(end)}


def _cfg_provenance(parser_backend: str) -> dict[str, object]:
    return {
        "semantic_backend": SEMANTIC_BACKEND,
        "parser_backend": parser_backend,
        "source": "python_ast",
    }


def _row_control_flow(row: sqlite3.Row | None) -> tuple[dict[str, object], ...]:
    if row is None:
        return ()
    try:
        payload = json.loads(str(row["control_flow_json"]))
    except (KeyError, TypeError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, list):
        return ()
    return tuple(item for item in payload if isinstance(item, dict))


def _language_for_path(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix == ".py":
        return "python"
    if suffix in {".ts", ".tsx", ".mts", ".cts"}:
        return "typescript"
    if suffix in JAVASCRIPT_SOURCE_SUFFIXES:
        return "javascript"
    return "unsupported"


def _normalize_source_path(root: Path, source_path: Path | str) -> str:
    path = Path(source_path)
    if path.is_absolute():
        try:
            path = path.resolve().relative_to(root.resolve())
        except ValueError:
            return path.name
    normalized = PurePosixPath(path.as_posix()).as_posix()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized or "."


def _json_value(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
