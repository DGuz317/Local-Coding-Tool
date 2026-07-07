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

SEMANTIC_SCHEMA_VERSION = 3
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
PYTHON_BINDING_EVIDENCE_LABELS = (
    "scanner:eligible_file",
    "semantic:skeleton",
    "python:ast",
    "semantic:python_lexical_bindings",
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
    bindings: tuple[dict[str, object], ...] = ()
    warnings: tuple[str, ...] = ()

    def to_cli_data(self) -> dict[str, object]:
        return {
            "artifact_freshness": self.artifact_freshness,
            "artifact_status": self.artifact_status.to_cli_data(),
            "experimental_status": self.experimental_status or SEMANTIC_EXPERIMENTAL_STATUS,
            "facts": {
                "calls": [],
                "bindings": list(self.bindings),
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
                    _json_value(_python_binding_facts(root, file, backend.name)),
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
                    control_flow_json,
                    bindings_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            bindings=_row_bindings(row),
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
        bindings=_row_bindings(row),
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
            control_flow_json TEXT NOT NULL,
            bindings_json TEXT NOT NULL
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
                control_flow_json,
                bindings_json
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


def _python_binding_facts(
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
                "scope": _scope_metadata(file.path, "module", "<module>", None, tree_node=None),
                "warnings": ["python_bindings_parse_failed"],
                "evidence_labels": list(PYTHON_BINDING_EVIDENCE_LABELS),
                "confidence": SEMANTIC_CONFIDENCE,
                "provenance": _binding_provenance(parser_backend),
            }
        ]

    tracer = _BindingTracer(file.path, parser_backend)
    return tracer.trace(tree)


class _BindingTracer:
    def __init__(self, source_path: str, parser_backend: str) -> None:
        self.source_path = source_path
        self.parser_backend = parser_backend

    def trace(self, tree: ast.Module) -> list[dict[str, object]]:
        facts = [self._scope_fact("module", "<module>", tree.body, None)]
        for statement in tree.body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                facts.append(self._function_scope_fact(statement))
        return [fact for fact in facts if _binding_scope_has_content(fact)]

    def _function_scope_fact(
        self, function: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> dict[str, object]:
        fact = self._scope_fact("function", function.name, function.body, function)
        parameters = [
            _definition_entry(argument.arg, "parameter", argument)
            for argument in _arguments(function)
        ]
        fact["parameters"] = parameters
        fact["definitions"] = sorted(
            [*parameters, *_binding_entries(fact, "definitions")], key=_binding_entry_sort_key
        )
        fact["resolved_names"] = _resolved_reference_entries(fact)
        fact["unresolved_names"] = _unresolved_reference_entries(fact)
        if isinstance(function, ast.AsyncFunctionDef):
            fact["warnings"] = sorted(
                [*_binding_warnings_from_fact(fact), "unsupported_async_function"]
            )
        return fact

    def _scope_fact(
        self,
        scope_kind: str,
        scope_name: str,
        statements: list[ast.stmt],
        scope_node: ast.AST | None,
    ) -> dict[str, object]:
        definitions: list[dict[str, object]] = []
        references: list[dict[str, object]] = []
        warnings: list[str] = []
        for statement in statements:
            definitions.extend(_definition_entries(statement))
            references.extend(_reference_entries(statement))
            warnings.extend(_binding_warnings(statement))
        assigned_names = [item for item in definitions if item["kind"] == "assignment"]
        imported_names = [item for item in definitions if item["kind"] == "import"]
        fact: dict[str, object] = {
            "source_path": self.source_path,
            "scope": _scope_metadata(
                self.source_path, scope_kind, scope_name, statements, tree_node=scope_node
            ),
            "definitions": sorted(definitions, key=_binding_entry_sort_key),
            "parameters": [],
            "assigned_names": sorted(assigned_names, key=_binding_entry_sort_key),
            "imported_names": sorted(imported_names, key=_binding_entry_sort_key),
            "references": sorted(references, key=_binding_entry_sort_key),
            "resolved_names": [],
            "unresolved_names": [],
            "warnings": sorted(set(warnings)),
            "confidence": SEMANTIC_CONFIDENCE,
            "evidence_labels": list(PYTHON_BINDING_EVIDENCE_LABELS),
            "provenance": _binding_provenance(self.parser_backend),
        }
        fact["resolved_names"] = _resolved_reference_entries(fact)
        fact["unresolved_names"] = _unresolved_reference_entries(fact)
        return fact


def _definition_entries(statement: ast.stmt) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    if isinstance(statement, ast.Import):
        for alias in statement.names:
            entries.append(_definition_entry(_imported_name(alias), "import", statement))
        return entries
    if isinstance(statement, ast.ImportFrom):
        for alias in statement.names:
            if alias.name != "*":
                entries.append(_definition_entry(_imported_name(alias), "import", statement))
        return entries
    if isinstance(statement, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.For, ast.AsyncFor)):
        targets = _assignment_targets(statement)
        return [_definition_entry(name, "assignment", node) for name, node in targets]
    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
        entries.append(_definition_entry(statement.name, "function", statement))
    return entries


def _reference_entries(statement: ast.stmt) -> list[dict[str, object]]:
    references: list[dict[str, object]] = []
    for node in _iter_binding_nodes(statement):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            references.append(_reference_entry(node.id, node))
    return references


def _binding_warnings(statement: ast.stmt) -> list[str]:
    warnings: list[str] = []
    for node in _iter_binding_nodes(statement):
        if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
            warnings.append("unresolved_star_import")
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            warnings.append("dynamic_binding_unresolved")
    return warnings


def _iter_binding_nodes(statement: ast.stmt) -> list[ast.AST]:
    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [statement]
    nodes: list[ast.AST] = []
    stack: list[ast.AST] = [statement]
    while stack:
        node = stack.pop()
        nodes.append(node)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            children = [child for child in ast.iter_child_nodes(node) if child is not node.func]
        else:
            children = list(ast.iter_child_nodes(node))
        for child in reversed(children):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            stack.append(child)
    return nodes


def _assignment_targets(statement: ast.stmt) -> list[tuple[str, ast.AST]]:
    targets: list[ast.AST] = []
    if isinstance(statement, ast.Assign):
        targets.extend(statement.targets)
    elif isinstance(statement, ast.AnnAssign):
        targets.append(statement.target)
    elif isinstance(statement, ast.AugAssign):
        targets.append(statement.target)
    elif isinstance(statement, (ast.For, ast.AsyncFor)):
        targets.append(statement.target)
    names: list[tuple[str, ast.AST]] = []
    for target in targets:
        names.extend(_target_names(target))
    return names


def _target_names(node: ast.AST) -> list[tuple[str, ast.AST]]:
    if isinstance(node, ast.Name):
        return [(node.id, node)]
    if isinstance(node, (ast.Tuple, ast.List)):
        names: list[tuple[str, ast.AST]] = []
        for element in node.elts:
            names.extend(_target_names(element))
        return names
    return []


def _arguments(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.arg]:
    args = [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]
    if function.args.vararg is not None:
        args.append(function.args.vararg)
    if function.args.kwarg is not None:
        args.append(function.args.kwarg)
    return args


def _definition_entry(name: str, kind: str, node: ast.AST) -> dict[str, object]:
    return {"name": name, "kind": kind, "line_range": _line_range(node)}


def _reference_entry(name: str, node: ast.AST) -> dict[str, object]:
    return {"name": name, "kind": "reference", "line_range": _line_range(node)}


def _imported_name(alias: ast.alias) -> str:
    if alias.asname is not None:
        return alias.asname
    return alias.name.split(".", 1)[0]


def _resolved_reference_entries(fact: dict[str, object]) -> list[dict[str, object]]:
    defined = {str(item["name"]) for item in _binding_entries(fact, "definitions")}
    return sorted(
        [
            {**reference, "resolution": "local_definition"}
            for reference in _binding_entries(fact, "references")
            if str(reference["name"]) in defined
        ],
        key=_binding_entry_sort_key,
    )


def _unresolved_reference_entries(fact: dict[str, object]) -> list[dict[str, object]]:
    defined = {str(item["name"]) for item in _binding_entries(fact, "definitions")}
    return sorted(
        [
            {**reference, "resolution": "unresolved"}
            for reference in _binding_entries(fact, "references")
            if str(reference["name"]) not in defined
        ],
        key=_binding_entry_sort_key,
    )


def _binding_scope_has_content(fact: dict[str, object]) -> bool:
    return any(
        fact[key]
        for key in (
            "definitions",
            "parameters",
            "assigned_names",
            "imported_names",
            "references",
            "warnings",
        )
    )


def _binding_entries(fact: dict[str, object], key: str) -> list[dict[str, object]]:
    value = fact.get(key, [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _binding_warnings_from_fact(fact: dict[str, object]) -> list[str]:
    value = fact.get("warnings", [])
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _binding_entry_sort_key(item: dict[str, object]) -> tuple[int, int, str, str]:
    line_range = item.get("line_range", {})
    start = _line_range_number(line_range, "start", 0)
    end = _line_range_number(line_range, "end", start)
    return (start, end, str(item.get("kind", "")), str(item.get("name", "")))


def _line_range_number(value: object, key: str, default: int) -> int:
    if not isinstance(value, dict):
        return default
    candidate = value.get(key, default)
    return candidate if isinstance(candidate, int) else default


def _scope_metadata(
    source_path: str,
    kind: str,
    name: str,
    statements: list[ast.stmt] | None,
    *,
    tree_node: ast.AST | None,
) -> dict[str, object]:
    if tree_node is not None:
        line_range = _line_range(tree_node)
    elif statements:
        line_range = {
            "start": min(_line_range(statement)["start"] for statement in statements),
            "end": max(_line_range(statement)["end"] for statement in statements),
        }
    else:
        line_range = {"start": 1, "end": 1}
    return {
        "identity": f"{source_path}:{name}:{line_range['start']}-{line_range['end']}",
        "kind": kind,
        "name": name,
        "line_range": line_range,
    }


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
        self.loop_stack: list[str] = []
        self.entry_id = self._add_node("entry", function)
        self.counter += 1
        self.exit_id = f"exit:{self.counter:04d}"
        if isinstance(function, ast.AsyncFunctionDef):
            self.warnings.append("unsupported_async_function")

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
            elif isinstance(statement, (ast.For, ast.While)):
                loop_id = self._add_node("loop", statement)
                for source_id, edge_kind in current:
                    self._add_edge(source_id, loop_id, edge_kind)
                self.loop_stack.append(loop_id)
                body_finals = self._sequence(statement.body, [(loop_id, "loop_body")])
                self.loop_stack.pop()
                for source_id, edge_kind in body_finals:
                    self._add_edge(source_id, loop_id, edge_kind)
                if statement.orelse:
                    self.warnings.append("unsupported_loop_else")
                current = [(loop_id, "loop_exit")]
            elif isinstance(statement, ast.Break):
                break_id = self._add_node("break", statement)
                for source_id, edge_kind in current:
                    self._add_edge(source_id, break_id, edge_kind)
                if self.loop_stack:
                    self._add_edge(break_id, self.loop_stack[-1], "loop_exit")
                else:
                    self.warnings.append("unsupported_break_outside_loop")
                current = []
            elif isinstance(statement, ast.Continue):
                continue_id = self._add_node("continue", statement)
                for source_id, edge_kind in current:
                    self._add_edge(source_id, continue_id, edge_kind)
                if self.loop_stack:
                    self._add_edge(continue_id, self.loop_stack[-1], "continue_loop")
                else:
                    self.warnings.append("unsupported_continue_outside_loop")
                current = []
            elif isinstance(statement, ast.Return):
                return_id = self._add_node("return", statement)
                for source_id, edge_kind in current:
                    self._add_edge(source_id, return_id, edge_kind)
                self._add_edge(return_id, self.exit_id, "next")
                current = []
            elif isinstance(statement, ast.Raise):
                raise_id = self._add_node("raise", statement)
                for source_id, edge_kind in current:
                    self._add_edge(source_id, raise_id, edge_kind)
                self._add_edge(raise_id, self.exit_id, "next")
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
    if isinstance(node, ast.Expr) and _contains_uncertain_expression(node):
        return True
    return isinstance(
        node,
        (
            ast.AsyncFor,
            ast.Try,
            ast.With,
            ast.AsyncWith,
            ast.Match,
        ),
    )


def _contains_uncertain_expression(node: ast.AST) -> bool:
    return any(isinstance(child, (ast.Await, ast.Yield, ast.YieldFrom)) for child in ast.walk(node))


def _has_cfg_relevant_node(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        isinstance(
            node,
            (
                ast.If,
                ast.For,
                ast.While,
                ast.Break,
                ast.Continue,
                ast.Return,
                ast.Raise,
                ast.Yield,
                ast.YieldFrom,
            ),
        )
        or (isinstance(node, ast.stmt) and _unsupported_statement(node))
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


def _binding_provenance(parser_backend: str) -> dict[str, object]:
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


def _row_bindings(row: sqlite3.Row | None) -> tuple[dict[str, object], ...]:
    if row is None:
        return ()
    try:
        payload = json.loads(str(row["bindings_json"]))
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
