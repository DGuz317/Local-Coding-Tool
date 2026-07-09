"""Local disclosure and safety audit for generated RepoLens artifacts."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repolens.context_pack import get_assistant_preflight
from repolens.context_pack_contract import (
    ASSISTANT_PREFLIGHT_REQUIRED_TOP_LEVEL_FIELDS,
    ASSISTANT_PREFLIGHT_VERSION,
    FORBIDDEN_CONTEXT_PACK_FIELD_NAMES,
    MCP_ENVELOPE_REQUIRED_FIELDS,
    ContextPackDisclosureError,
    guard_context_pack_output,
)
from repolens.graph import GRAPH_STORE_FILENAME
from repolens.scanner import ARTIFACT_DIR_NAME

ARTIFACT_AUDIT_VERSION = "0.5.artifact-audit.v1"
DEFAULT_MAX_ARTIFACT_BYTES = 10_000_000
_TEXT_ARTIFACT_SUFFIXES = frozenset({".json", ".jsonl", ".md", ".txt"})
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b[A-Z0-9_.-]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API[_-]?KEY|AUTH|PRIVATE[_-]?KEY)"
    r"[A-Z0-9_.-]*\b\s*[:=]\s*(?![<]?redacted[>]?\b)[^\s,;]+"
)
_ABSOLUTE_PATH_RE = re.compile(r"(?:^|[\s\"'])/(?:home|Users)/[^\s\"']+")
_SOURCE_LIKE_BODY_RE = re.compile(
    r"(?s)(?:^|\n)\s*(?:def|class|function|const|let|var)\s+[A-Za-z0-9_$]+[^\n]+[{:]"
)
_RAW_AGENT_GUIDANCE_RE = re.compile(
    r"(?i)(?:Non-Negotiable Product Boundaries|Instructions from:|<mcp_instructions>)"
)
_RAW_AGENT_GUIDANCE_MIN_CHARS = 200
_SEMANTIC_FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "function_body",
        "function_signature",
        "raw_condition_text",
        "raw_expression_text",
        "raw_value",
        "source_snippet",
        "source_text",
    }
)


@dataclass(frozen=True)
class ArtifactAuditViolation:
    """One deterministic artifact audit failure."""

    check: str
    location: str
    message: str
    severity: str = "error"

    def to_dict(self) -> dict[str, str]:
        return {
            "check": self.check,
            "location": self.location,
            "message": self.message,
            "severity": self.severity,
        }


class RepoLensArtifactAuditError(RuntimeError):
    """Raised when the audit cannot safely inspect local RepoLens artifacts."""


def audit_artifacts(
    repo_path: Path | str,
    *,
    max_artifact_bytes: int = DEFAULT_MAX_ARTIFACT_BYTES,
) -> dict[str, Any]:
    """Audit generated artifacts and representative assistant-facing output."""
    try:
        root = Path(repo_path).resolve(strict=True)
    except OSError as exc:
        raise RepoLensArtifactAuditError("analysis_root_not_found") from exc
    if not root.is_dir():
        raise RepoLensArtifactAuditError("analysis_root_not_directory")
    if ARTIFACT_DIR_NAME in root.parts:
        raise RepoLensArtifactAuditError("analysis_root_is_repolens_artifact_dir")

    artifact_dir = root / ARTIFACT_DIR_NAME
    if artifact_dir.is_symlink():
        raise RepoLensArtifactAuditError("artifact_dir_is_symlink")
    if not artifact_dir.exists():
        raise RepoLensArtifactAuditError("missing_artifact_dir")
    if not artifact_dir.is_dir():
        raise RepoLensArtifactAuditError("artifact_dir_not_directory")

    violations: list[ArtifactAuditViolation] = []
    audited_artifacts: list[str] = []
    artifact_paths = _artifact_paths(root, artifact_dir)
    for artifact_path in artifact_paths:
        rel_path = _repo_relative(root, artifact_path)
        audited_artifacts.append(rel_path)
        violations.extend(_audit_artifact_path(root, artifact_path, max_artifact_bytes))

    violations.extend(_audit_representative_preflight(root))

    checks = {
        "absolute_host_paths": True,
        "artifact_boundary": True,
        "call_chain_facts_source_free": True,
        "candidate_commands_not_run": True,
        "mcp_contract": True,
        "oversized_artifacts": True,
        "raw_agent_guidance_mirroring": True,
        "raw_secret_like_values": True,
        "source_snippet_leakage": True,
    }
    deduped_violations = _dedupe_violations(violations)
    violation_dicts = [violation.to_dict() for violation in deduped_violations]
    return {
        "data": {
            "artifact_audit_version": ARTIFACT_AUDIT_VERSION,
            "artifact_dir": ARTIFACT_DIR_NAME,
            "audited_artifacts": audited_artifacts,
            "checks": checks,
            "summary": {
                "artifact_count": len(audited_artifacts),
                "passed": not deduped_violations,
                "violation_count": len(deduped_violations),
            },
            "violations": violation_dicts,
        },
        "limits": {"max_artifact_bytes": max_artifact_bytes},
        "ok": not deduped_violations,
        "warnings": [],
    }


def human_artifact_audit(envelope: Mapping[str, Any]) -> str:
    """Return a compact human-readable audit summary."""
    data = _mapping(envelope.get("data"))
    summary = _mapping(data.get("summary"))
    lines = ["RepoLens Artifact Audit:"]
    lines.append(f"Status: {'passed' if envelope.get('ok') else 'failed'}")
    lines.append(f"Artifacts audited: {summary.get('artifact_count', 0)}")
    lines.append(f"Violations: {summary.get('violation_count', 0)}")
    violations = _sequence(data.get("violations"))
    if violations:
        lines.append("Failures:")
        for violation in violations:
            item = _mapping(violation)
            lines.append(f"- {item.get('check')}: {item.get('location')} - {item.get('message')}")
    return "\n".join(lines) + "\n"


def _artifact_paths(root: Path, artifact_dir: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    for path in artifact_dir.rglob("*"):
        paths.append(path)
    return tuple(sorted(paths, key=lambda path: _repo_relative(root, path)))


def _audit_artifact_path(
    root: Path, artifact_path: Path, max_artifact_bytes: int
) -> list[ArtifactAuditViolation]:
    rel_path = _repo_relative(root, artifact_path)
    violations: list[ArtifactAuditViolation] = []
    if artifact_path.is_symlink():
        return [
            ArtifactAuditViolation(
                check="artifact_boundary",
                location=rel_path,
                message="artifact is a symlink and was not followed",
            )
        ]
    if artifact_path.is_dir():
        return []
    if not _is_within(root, artifact_path):
        return [
            ArtifactAuditViolation(
                check="artifact_boundary",
                location=rel_path,
                message="artifact path escapes the analysis root",
            )
        ]

    try:
        size_bytes = artifact_path.stat().st_size
    except OSError:
        return [
            ArtifactAuditViolation(
                check="artifact_boundary",
                location=rel_path,
                message="artifact metadata could not be read",
            )
        ]
    if size_bytes > max_artifact_bytes:
        violations.append(
            ArtifactAuditViolation(
                check="oversized_artifacts",
                location=rel_path,
                message=f"artifact size {size_bytes} exceeds limit {max_artifact_bytes}",
            )
        )

    if artifact_path.name == GRAPH_STORE_FILENAME or artifact_path.suffix.lower() == ".sqlite":
        violations.extend(_audit_sqlite_artifact(root, artifact_path))
    elif (
        artifact_path.suffix.lower() in _TEXT_ARTIFACT_SUFFIXES
        or artifact_path.name == ".gitignore"
    ):
        try:
            text = artifact_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            violations.append(
                ArtifactAuditViolation(
                    check="artifact_boundary",
                    location=rel_path,
                    message="text artifact is not valid UTF-8",
                )
            )
        except OSError:
            violations.append(
                ArtifactAuditViolation(
                    check="artifact_boundary",
                    location=rel_path,
                    message="text artifact could not be read",
                )
            )
        else:
            violations.extend(
                _audit_text_blob(text, rel_path, root=root, check_agent_guidance=False)
            )
            if artifact_path.suffix.lower() == ".json":
                violations.extend(_audit_json_text(text, rel_path, root=root))
            elif artifact_path.suffix.lower() == ".jsonl":
                violations.extend(_audit_jsonl_text(text, rel_path, root=root))
    return violations


def _audit_sqlite_artifact(root: Path, artifact_path: Path) -> list[ArtifactAuditViolation]:
    rel_path = _repo_relative(root, artifact_path)
    violations: list[ArtifactAuditViolation] = []
    try:
        with sqlite3.connect(f"file:{artifact_path}?mode=ro", uri=True) as connection:
            table_rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            ).fetchall()
            for (table_name,) in table_rows:
                column_rows = connection.execute(
                    f"PRAGMA table_info({_quote_identifier(table_name)})"
                ).fetchall()
                if table_name == "javascript_call_chains":
                    violations.extend(_audit_call_chain_columns(column_rows, rel_path))
                text_columns = [
                    str(row[1])
                    for row in column_rows
                    if "TEXT" in str(row[2]).upper() or str(row[2]).upper() == ""
                ]
                for column in sorted(text_columns):
                    rows = connection.execute(
                        f"SELECT {_quote_identifier(column)} "
                        f"FROM {_quote_identifier(table_name)} "
                        f"WHERE {_quote_identifier(column)} IS NOT NULL "
                        f"ORDER BY {_quote_identifier(column)}"
                    ).fetchall()
                    for row_index, (value,) in enumerate(rows):
                        if isinstance(value, str):
                            location = f"{rel_path}:{table_name}.{column}[{row_index}]"
                            violations.extend(_audit_text_blob(value, location, root=root))
                            violations.extend(_audit_value(column, value, location, root=root))
    except sqlite3.Error as exc:
        violations.append(
            ArtifactAuditViolation(
                check="artifact_boundary",
                location=rel_path,
                message=f"sqlite artifact could not be read: {exc.__class__.__name__}",
            )
        )
    return violations


def _audit_call_chain_columns(
    column_rows: Sequence[Sequence[Any]], rel_path: str
) -> list[ArtifactAuditViolation]:
    violations: list[ArtifactAuditViolation] = []
    forbidden_fragments = ("source", "snippet", "expression", "body", "signature", "comment")
    for row in column_rows:
        column_name = str(row[1])
        if any(fragment in column_name.lower() for fragment in forbidden_fragments):
            violations.append(
                ArtifactAuditViolation(
                    check="call_chain_facts_source_free",
                    location=f"{rel_path}:javascript_call_chains.{column_name}",
                    message="call-chain fact column appears source-bearing",
                )
            )
    return violations


def _audit_json_text(text: str, rel_path: str, *, root: Path) -> list[ArtifactAuditViolation]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return [
            ArtifactAuditViolation(
                check="artifact_boundary",
                location=rel_path,
                message="JSON artifact could not be parsed",
            )
        ]
    violations = list(_audit_payload(payload, location=rel_path, root=root))
    if isinstance(payload, Mapping) and "ok" in payload:
        violations.extend(_audit_mcp_envelope(payload, location=rel_path))
    return violations


def _audit_jsonl_text(text: str, rel_path: str, *, root: Path) -> list[ArtifactAuditViolation]:
    violations: list[ArtifactAuditViolation] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            violations.append(
                ArtifactAuditViolation(
                    check="artifact_boundary",
                    location=f"{rel_path}:{line_number}",
                    message="JSONL artifact line could not be parsed",
                )
            )
            continue
        violations.extend(_audit_payload(payload, location=f"{rel_path}:{line_number}", root=root))
    return violations


def _audit_representative_preflight(root: Path) -> list[ArtifactAuditViolation]:
    envelope = get_assistant_preflight(root, "Audit RepoLens artifact safety")
    violations = list(_audit_mcp_envelope(envelope, location="assistant_preflight"))
    violations.extend(_audit_payload(envelope, location="assistant_preflight", root=root))
    try:
        guard_context_pack_output(envelope)
    except ContextPackDisclosureError as exc:
        for violation in exc.violations:
            violations.append(
                ArtifactAuditViolation(
                    check="mcp_contract",
                    location=f"assistant_preflight:{violation}",
                    message="representative assistant envelope failed disclosure guard",
                )
            )
    return violations


def _audit_mcp_envelope(
    envelope: Mapping[str, Any], *, location: str
) -> Iterable[ArtifactAuditViolation]:
    for field in MCP_ENVELOPE_REQUIRED_FIELDS:
        if field not in envelope:
            yield ArtifactAuditViolation(
                check="mcp_contract",
                location=f"{location}.{field}",
                message="required MCP envelope field is missing",
            )
    if envelope.get("ok") is not True:
        yield ArtifactAuditViolation(
            check="mcp_contract",
            location=location,
            message="representative assistant preflight did not return a successful envelope",
        )
        return
    data = _mapping(envelope.get("data"))
    if data.get("assistant_preflight_version") != ASSISTANT_PREFLIGHT_VERSION:
        yield ArtifactAuditViolation(
            check="mcp_contract",
            location=f"{location}.data.assistant_preflight_version",
            message="assistant preflight version is missing or unsupported",
        )
    for field in ASSISTANT_PREFLIGHT_REQUIRED_TOP_LEVEL_FIELDS:
        if field not in data:
            yield ArtifactAuditViolation(
                check="mcp_contract",
                location=f"{location}.data.{field}",
                message="required assistant preflight field is missing",
            )
    for index, command in enumerate(_sequence(data.get("candidate_verification_commands"))):
        mapped = _mapping(command)
        if mapped.get("found") is not True:
            yield ArtifactAuditViolation(
                check="candidate_commands_not_run",
                location=f"{location}.data.candidate_verification_commands[{index}].found",
                message="candidate command is not marked as discovered",
            )
        if mapped.get("run") is not False or mapped.get("not_run") is not True:
            yield ArtifactAuditViolation(
                check="candidate_commands_not_run",
                location=f"{location}.data.candidate_verification_commands[{index}].run",
                message="candidate command must remain discovered-only and not run",
            )
        if mapped.get("auto_run_recommended") is not False:
            yield ArtifactAuditViolation(
                check="candidate_commands_not_run",
                location=f"{location}.data.candidate_verification_commands[{index}].auto_run_recommended",
                message="candidate command must not recommend automatic execution",
            )


def _audit_payload(value: Any, *, location: str, root: Path) -> Iterable[ArtifactAuditViolation]:
    if isinstance(value, Mapping):
        yield from _audit_candidate_command(value, location=location)
        for key, child in value.items():
            key_text = str(key)
            child_location = f"{location}.{key_text}"
            if key_text in FORBIDDEN_CONTEXT_PACK_FIELD_NAMES:
                yield ArtifactAuditViolation(
                    check="source_snippet_leakage",
                    location=child_location,
                    message="forbidden source-bearing field is present",
                )
            if key_text in _SEMANTIC_FORBIDDEN_FIELD_NAMES:
                yield ArtifactAuditViolation(
                    check="semantic_outputs_source_free",
                    location=child_location,
                    message="forbidden semantic source-bearing field is present",
                )
            yield from _audit_value(key_text, child, child_location, root=root)
            yield from _audit_payload(child, location=child_location, root=root)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            yield from _audit_payload(child, location=f"{location}[{index}]", root=root)
    elif isinstance(value, str):
        yield from _audit_text_blob(value, location, root=root)


def _audit_value(
    key: str, value: Any, location: str, *, root: Path
) -> Iterable[ArtifactAuditViolation]:
    if not isinstance(value, str):
        return
    if key.lower() in FORBIDDEN_CONTEXT_PACK_FIELD_NAMES:
        yield ArtifactAuditViolation(
            check="source_snippet_leakage",
            location=location,
            message="forbidden source-bearing field is present",
        )
    yield from _audit_text_blob(value, location, root=root)


def _audit_candidate_command(
    value: Mapping[str, Any], *, location: str
) -> Iterable[ArtifactAuditViolation]:
    kind = value.get("kind")
    looks_like_candidate = kind == "candidate_verification_command"
    if not looks_like_candidate:
        return
    if value.get("found") is not True:
        yield ArtifactAuditViolation(
            check="candidate_commands_not_run",
            location=f"{location}.found",
            message="candidate command is not marked as discovered",
        )
    if value.get("run") is not False or value.get("not_run") is not True:
        yield ArtifactAuditViolation(
            check="candidate_commands_not_run",
            location=f"{location}.run",
            message="candidate command must remain discovered-only and not run",
        )
    if value.get("auto_run_recommended") is not False:
        yield ArtifactAuditViolation(
            check="candidate_commands_not_run",
            location=f"{location}.auto_run_recommended",
            message="candidate command must not recommend automatic execution",
        )


def _audit_text_blob(
    text: str, location: str, *, root: Path, check_agent_guidance: bool = True
) -> Iterable[ArtifactAuditViolation]:
    root_text = root.as_posix()
    if root_text and root_text in text:
        yield ArtifactAuditViolation(
            check="absolute_host_paths",
            location=location,
            message="absolute analysis-root path is present",
        )
    elif _ABSOLUTE_PATH_RE.search(text):
        yield ArtifactAuditViolation(
            check="absolute_host_paths",
            location=location,
            message="absolute host path is present",
        )
    if _SECRET_ASSIGNMENT_RE.search(text):
        yield ArtifactAuditViolation(
            check="raw_secret_like_values",
            location=location,
            message="raw secret-like assignment is present",
        )
    if _SOURCE_LIKE_BODY_RE.search(text):
        yield ArtifactAuditViolation(
            check="source_snippet_leakage",
            location=location,
            message="source-like body text is present",
        )
    if (
        check_agent_guidance
        and len(text) >= _RAW_AGENT_GUIDANCE_MIN_CHARS
        and _RAW_AGENT_GUIDANCE_RE.search(text)
    ):
        yield ArtifactAuditViolation(
            check="raw_agent_guidance_mirroring",
            location=location,
            message="raw Agent Guidance text appears to be mirrored",
        )


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _dedupe_violations(
    violations: Sequence[ArtifactAuditViolation],
) -> tuple[ArtifactAuditViolation, ...]:
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[ArtifactAuditViolation] = []
    for violation in violations:
        key = (violation.check, violation.location, violation.message, violation.severity)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(violation)
    return tuple(deduped)


def _repo_relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _is_within(root: Path, path: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root)
    except ValueError:
        return False
    return True


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()
