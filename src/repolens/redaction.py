"""Shared redaction policy for RepoLens safety boundaries."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any

REDACTED_VALUE = "redacted"
REDACTED_COMMAND_VALUE = "<redacted>"
MAX_REDACTED_COMMAND_CHARS = 240
_SECRET_TEXT_VALUE = "<redacted>"

SECRET_FILE_NAMES = frozenset(
    {
        ".env",
        ".netrc",
        ".npmrc",
        ".pypirc",
        "credentials",
        "credentials.json",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "id_rsa",
        "known_hosts",
        "secrets.json",
    }
)
SECRET_SUFFIXES = frozenset({".jks", ".key", ".kdbx", ".keystore", ".p12", ".pem", ".pfx"})
SECRET_CONFIG_SUFFIXES = frozenset(
    {"", ".cfg", ".conf", ".env", ".ini", ".json", ".toml", ".txt", ".yaml", ".yml"}
)
SECRET_KEY_TOKENS = (
    "api_key",
    "apikey",
    "auth",
    "credential",
    "password",
    "passwd",
    "private_key",
    "secret",
    "token",
)
SECRET_NAME_TOKENS = ("credential", "password", "passwd", "private-key", "private_key", "secret")
SECRET_DIRECTORY_NAMES = frozenset({".secrets", "secrets"})
SAFE_METADATA_KEYS = frozenset({"approx_token_estimate_divisor", "approx_tokens"})
COMMAND_SECRET_OPTIONS = (
    "api-key",
    "apikey",
    "auth",
    "otp",
    "password",
    "passwd",
    "secret",
    "token",
)


def is_secret_key(key: str) -> bool:
    """Return whether a metadata key is high-risk for secret disclosure."""
    normalized = key.lower().replace("-", "_")
    if normalized in SAFE_METADATA_KEYS:
        return False
    return any(token in normalized for token in SECRET_KEY_TOKENS)


def is_secret_path(rel_path: str) -> bool:
    """Return whether a repo-relative path should be skipped before parsing."""
    parts = tuple(part.lower() for part in rel_path.split("/"))
    name = parts[-1]
    suffix = PurePosixPath(name).suffix.lower()
    stem = PurePosixPath(name).stem.lower()

    if name in SECRET_FILE_NAMES or name.startswith(".env."):
        return True
    if suffix in SECRET_SUFFIXES:
        return True
    if any(part in SECRET_DIRECTORY_NAMES for part in parts[:-1]):
        return True
    return suffix in SECRET_CONFIG_SUFFIXES and any(token in stem for token in SECRET_NAME_TOKENS)


def redact_command(command: str) -> str:
    """Redact obvious secret values from candidate commands while preserving command shape."""
    sanitized = command.strip()
    sanitized = re.sub(
        r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|AUTH|PRIVATE_KEY)[A-Z0-9_]*)=([^\s]+)",
        rf"\1={REDACTED_COMMAND_VALUE}",
        sanitized,
    )
    option_pattern = "|".join(re.escape(option) for option in COMMAND_SECRET_OPTIONS)
    sanitized = re.sub(
        rf"(?i)(--(?:{option_pattern})(?:=|\s+))([^\s]+)",
        lambda match: f"{match.group(1)}{REDACTED_COMMAND_VALUE}",
        sanitized,
    )
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    if len(sanitized) > MAX_REDACTED_COMMAND_CHARS:
        return f"{sanitized[: MAX_REDACTED_COMMAND_CHARS - 3]}..."
    return sanitized


def redact_text(text: str) -> str:
    """Redact obvious inline secret assignments from source-adjacent text previews."""
    key_token_pattern = (
        r"[A-Z0-9_.-]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API[_-]?KEY|AUTH|PRIVATE[_-]?KEY)"
        r"[A-Z0-9_.-]*"
    )
    sanitized = re.sub(
        rf"(?i)(\b{key_token_pattern}\b\s*=\s*)([^\s,;]+)",
        rf"\1{_SECRET_TEXT_VALUE}",
        text,
    )
    return re.sub(
        rf"(?i)([\"']?\b{key_token_pattern}\b[\"']?\s*:\s*)([\"'])([^\"']+)([\"'])",
        rf"\1\2{_SECRET_TEXT_VALUE}\4",
        sanitized,
    )


def redact_payload(value: Any, *, parent_key: str | None = None) -> Any:
    """Recursively redact secret-like metadata and command values from public payloads."""
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key)
            if is_secret_key(key_text):
                result[key_text] = REDACTED_VALUE
            elif key_text == "command" and isinstance(child, str):
                result[key_text] = redact_command(child)
            else:
                result[key_text] = redact_payload(child, parent_key=key_text)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_payload(child, parent_key=parent_key) for child in value]
    if isinstance(value, str) and parent_key == "command":
        return redact_command(value)
    return value
