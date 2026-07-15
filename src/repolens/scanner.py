"""Safe repository file discovery for RepoLens."""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path

from repolens.redaction import is_secret_path

DEFAULT_MAX_FILE_SIZE_BYTES = 1_048_576
BINARY_SNIFF_BYTES = 8192

ARTIFACT_DIR_NAME = ".repolens"

BUILT_IN_EXCLUDED_DIRS = frozenset(
    {
        ".cache",
        ".eggs",
        ".git",
        ".gradle",
        ".hg",
        ".mypy_cache",
        ".next",
        ".nox",
        ".nuxt",
        ".parcel-cache",
        ".pytest_cache",
        ".repolens",
        ".ruff_cache",
        ".svn",
        ".svelte-kit",
        ".tox",
        ".turbo",
        ".venv",
        ".yarn",
        "__pycache__",
        "bower_components",
        "build",
        "coverage",
        "dist",
        "env",
        "generated",
        "graph-output",
        "graph-out",
        "graphify-out",
        "htmlcov",
        "node_modules",
        "out",
        "site",
        "target",
        "vendor",
        "venv",
    }
)

BINARY_MEDIA_ARCHIVE_SUFFIXES = frozenset(
    {
        ".7z",
        ".a",
        ".avi",
        ".avif",
        ".bin",
        ".bmp",
        ".bz2",
        ".class",
        ".db",
        ".dll",
        ".dmg",
        ".doc",
        ".docx",
        ".dylib",
        ".eot",
        ".exe",
        ".gif",
        ".gz",
        ".ico",
        ".iso",
        ".jar",
        ".jpeg",
        ".jpg",
        ".m4a",
        ".mkv",
        ".mov",
        ".mp3",
        ".mp4",
        ".o",
        ".ogg",
        ".otf",
        ".pdf",
        ".png",
        ".pyc",
        ".rar",
        ".sqlite",
        ".so",
        ".tar",
        ".tgz",
        ".tif",
        ".tiff",
        ".ttf",
        ".wasm",
        ".wav",
        ".webm",
        ".webp",
        ".whl",
        ".woff",
        ".woff2",
        ".xls",
        ".xlsx",
        ".xz",
        ".zip",
    }
)

GENERATED_FILE_SUFFIXES = frozenset({".map"})
GENERATED_FILE_NAME_SUFFIXES = (
    ".bundle.js",
    ".generated.js",
    ".generated.jsx",
    ".generated.ts",
    ".generated.tsx",
    ".min.css",
    ".min.js",
    "_generated.py",
    "_pb2.py",
    "_pb2_grpc.py",
)
UNSUPPORTED_SOURCE_SUFFIXES = frozenset(
    {
        ".c",
        ".cc",
        ".clj",
        ".cljs",
        ".coffee",
        ".cpp",
        ".cs",
        ".dart",
        ".ex",
        ".exs",
        ".fs",
        ".fsx",
        ".go",
        ".groovy",
        ".h",
        ".hpp",
        ".java",
        ".kt",
        ".kts",
        ".lua",
        ".m",
        ".mm",
        ".php",
        ".pl",
        ".rb",
        ".rs",
        ".scala",
        ".scm",
        ".swift",
        ".vb",
    }
)


class ScanError(ValueError):
    """Raised when a scan cannot start safely."""


@dataclass(frozen=True)
class ScannedFile:
    """An eligible file discovered under the analysis root."""

    path: str
    size_bytes: int

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "size_bytes": self.size_bytes}


@dataclass(frozen=True)
class SkippedPath:
    """A path skipped by the scan policy."""

    path: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "reason": self.reason}


@dataclass(frozen=True)
class ScanResult:
    """Result of a safe repository discovery pass."""

    root: Path
    files: tuple[ScannedFile, ...]
    skipped: tuple[SkippedPath, ...]
    max_file_size_bytes: int

    def to_artifact_dict(self) -> dict[str, object]:
        return {
            "analysis_root": ".",
            "artifact": "scan",
            "artifact_version": 1,
            "counts": {
                "eligible_files": len(self.files),
                "skipped_paths": len(self.skipped),
            },
            "files": [file.to_dict() for file in self.files],
            "limits": {"max_file_size_bytes": self.max_file_size_bytes},
            "scan_policy_version": 1,
            "skipped_paths": [skipped.to_dict() for skipped in self.skipped],
        }


@dataclass(frozen=True)
class _GitIgnoreRule:
    base_path: str
    pattern: str
    negated: bool
    directory_only: bool
    anchored: bool
    has_slash: bool

    def matches(self, rel_path: str, *, is_dir: bool) -> bool:
        if self.base_path:
            if rel_path == self.base_path:
                return False
            prefix = f"{self.base_path}/"
            if not rel_path.startswith(prefix):
                return False
            local_path = rel_path[len(prefix) :]
        else:
            local_path = rel_path

        if not local_path:
            return False

        if self.directory_only:
            return _matches_directory_pattern(
                local_path, self.pattern, self.has_slash or self.anchored
            )

        if self.has_slash or self.anchored:
            return fnmatch.fnmatchcase(local_path, self.pattern)

        return any(fnmatch.fnmatchcase(part, self.pattern) for part in local_path.split("/"))


def scan_repository(
    repo_path: Path | str,
    *,
    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
) -> ScanResult:
    """Discover eligible files under ``repo_path`` using the default safe scan policy."""
    root = _resolve_analysis_root(repo_path)
    files: list[ScannedFile] = []
    skipped: list[SkippedPath] = []

    def record_skip(path: Path, reason: str) -> None:
        skipped.append(SkippedPath(path=_repo_relative_path(root, path), reason=reason))

    def walk(directory: Path, gitignore_rules: tuple[_GitIgnoreRule, ...]) -> None:
        current_rules = (*gitignore_rules, *_load_gitignore_rules(root, directory))
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError:
            record_skip(directory, "unreadable")
            return

        for entry in entries:
            path = directory / entry.name

            if entry.is_symlink():
                reason = "symlink" if _is_contained(root, path) else "symlink_escapes_root"
                record_skip(path, reason)
                continue

            if not _is_contained(root, path):
                record_skip(path, "outside_analysis_root")
                continue

            rel_path = _repo_relative_path(root, path)

            if entry.name == ARTIFACT_DIR_NAME or rel_path.startswith(f"{ARTIFACT_DIR_NAME}/"):
                record_skip(path, "repolens_artifact_dir")
                continue

            if is_secret_path(rel_path):
                record_skip(path, "secret_path")
                continue

            try:
                is_dir = entry.is_dir(follow_symlinks=False)
                is_file = entry.is_file(follow_symlinks=False)
            except OSError:
                record_skip(path, "unreadable")
                continue

            if _is_ignored_by_gitignore(current_rules, rel_path, is_dir=is_dir):
                record_skip(path, "gitignore")
                continue

            if is_dir:
                if entry.name in BUILT_IN_EXCLUDED_DIRS:
                    record_skip(path, "excluded_directory")
                    continue
                walk(path, current_rules)
                continue

            if not is_file:
                record_skip(path, "special_file")
                continue

            if _is_generated_artifact_file(rel_path):
                record_skip(path, "generated_file")
                continue

            if Path(entry.name).suffix.lower() in UNSUPPORTED_SOURCE_SUFFIXES:
                record_skip(path, "unsupported_source")
                continue

            try:
                stat_result = entry.stat(follow_symlinks=False)
            except OSError:
                record_skip(path, "unreadable")
                continue

            if stat_result.st_size > max_file_size_bytes:
                record_skip(path, "oversized_file")
                continue

            if Path(entry.name).suffix.lower() in BINARY_MEDIA_ARCHIVE_SUFFIXES:
                record_skip(path, "binary_media_archive")
                continue

            binary_content = _has_binary_content(path)
            if binary_content is None:
                record_skip(path, "unreadable")
                continue
            if binary_content:
                record_skip(path, "binary_content")
                continue

            files.append(ScannedFile(path=rel_path, size_bytes=stat_result.st_size))

    walk(root, ())
    return ScanResult(
        root=root,
        files=tuple(sorted(files, key=lambda file: file.path)),
        skipped=tuple(sorted(skipped, key=lambda skipped_path: skipped_path.path)),
        max_file_size_bytes=max_file_size_bytes,
    )


def _resolve_analysis_root(repo_path: Path | str) -> Path:
    try:
        root = Path(repo_path).resolve(strict=True)
    except OSError as exc:
        raise ScanError("analysis_root_not_found") from exc

    if not root.is_dir():
        raise ScanError("analysis_root_not_directory")
    if ARTIFACT_DIR_NAME in root.parts:
        raise ScanError("analysis_root_is_repolens_artifact_dir")
    return root


def _repo_relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_contained(root: Path, path: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root)
    except ValueError:
        return False
    return True


def _load_gitignore_rules(root: Path, directory: Path) -> tuple[_GitIgnoreRule, ...]:
    gitignore_path = directory / ".gitignore"
    if (
        gitignore_path.is_symlink()
        or not gitignore_path.is_file()
        or not _is_contained(root, gitignore_path)
    ):
        return ()

    base_path = "" if directory == root else _repo_relative_path(root, directory)
    rules: list[_GitIgnoreRule] = []
    try:
        lines = gitignore_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ()

    for raw_line in lines:
        rule = _parse_gitignore_rule(raw_line, base_path)
        if rule is not None:
            rules.append(rule)
    return tuple(rules)


def _parse_gitignore_rule(raw_line: str, base_path: str) -> _GitIgnoreRule | None:
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("\\#"):
        line = line[1:]

    negated = line.startswith("!")
    if negated:
        line = line[1:].strip()
    if not line:
        return None

    directory_only = line.endswith("/")
    if directory_only:
        line = line.rstrip("/")

    anchored = line.startswith("/")
    if anchored:
        line = line.lstrip("/")

    if not line:
        return None

    return _GitIgnoreRule(
        base_path=base_path,
        pattern=line,
        negated=negated,
        directory_only=directory_only,
        anchored=anchored,
        has_slash="/" in line,
    )


def _is_ignored_by_gitignore(
    rules: tuple[_GitIgnoreRule, ...],
    rel_path: str,
    *,
    is_dir: bool,
) -> bool:
    ignored = False
    for rule in rules:
        if rule.matches(rel_path, is_dir=is_dir):
            ignored = not rule.negated
    return ignored


def _matches_directory_pattern(local_path: str, pattern: str, path_pattern: bool) -> bool:
    if path_pattern:
        return local_path == pattern or local_path.startswith(f"{pattern}/")
    return any(fnmatch.fnmatchcase(part, pattern) for part in local_path.split("/"))


def _is_generated_artifact_file(rel_path: str) -> bool:
    name = rel_path.rsplit("/", maxsplit=1)[-1].lower()
    return Path(name).suffix.lower() in GENERATED_FILE_SUFFIXES or name.endswith(
        GENERATED_FILE_NAME_SUFFIXES
    )


def _has_binary_content(path: Path) -> bool | None:
    try:
        with path.open("rb") as file:
            sample = file.read(BINARY_SNIFF_BYTES)
    except OSError:
        return None

    if not sample:
        return False
    if b"\0" in sample:
        return True

    allowed_control_bytes = {7, 8, 9, 10, 12, 13, 27}
    control_bytes = sum(1 for byte in sample if byte < 32 and byte not in allowed_control_bytes)
    return control_bytes / len(sample) > 0.30
