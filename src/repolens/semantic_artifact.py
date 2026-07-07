"""Experimental semantic artifact skeleton outside the stable graph contract."""

from __future__ import annotations

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

SEMANTIC_SCHEMA_VERSION = 1
SEMANTIC_STORE_FILENAME = "semantic.sqlite"
SEMANTIC_STORE_PATH = f"{ARTIFACT_DIR_NAME}/{SEMANTIC_STORE_FILENAME}"
SEMANTIC_BACKEND = "semantic_skeleton"
SEMANTIC_EXPERIMENTAL_STATUS = "experimental"
SEMANTIC_CONFIDENCE = "candidate"
SEMANTIC_EVIDENCE_LABELS = ("scanner:eligible_file", "semantic:skeleton")


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
                    experimental_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
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
                    )
                    for file in sorted(scan.files, key=lambda item: item.path)
                    if _language_for_path(file.path) in {"python", "javascript", "typescript"}
                ],
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
            experimental_status TEXT NOT NULL
        ) WITHOUT ROWID;
        """
    )


def _read_metadata(path: Path) -> dict[str, str]:
    with sqlite3.connect(path) as connection:
        return {
            str(key): str(value)
            for key, value in connection.execute("SELECT key, value FROM metadata")
        }


def _source_fingerprint(files: tuple[ScannedFile, ...]) -> str:
    payload = [(file.path, file.size_bytes) for file in sorted(files, key=lambda item: item.path)]
    return hashlib.sha256(_json_value(payload).encode("utf-8")).hexdigest()


def _language_for_path(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix == ".py":
        return "python"
    if suffix in {".ts", ".tsx", ".mts", ".cts"}:
        return "typescript"
    if suffix in JAVASCRIPT_SOURCE_SUFFIXES:
        return "javascript"
    return "unsupported"


def _json_value(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
