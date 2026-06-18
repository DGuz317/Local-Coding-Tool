"""Safe raw text search over scanner-approved repository files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from repolens.scanner import ScanError, ScanResult, scan_repository

SEARCH_DEFAULT_MAX_RESULTS = 20
SEARCH_MAX_RESULTS_LIMIT = 100
SEARCH_PREVIEW_CHARS = 160


class RepoLensSearchError(RuntimeError):
    """Raised when raw text search cannot run safely."""


@dataclass(frozen=True)
class TextSearchMatch:
    """One raw text search match with a bounded, sanitized preview."""

    path: str
    line: int
    column: int
    preview: str
    preview_truncated_before: bool
    preview_truncated_after: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "column": self.column,
            "line": self.line,
            "path": self.path,
            "preview": self.preview,
            "preview_truncated_after": self.preview_truncated_after,
            "preview_truncated_before": self.preview_truncated_before,
        }


@dataclass(frozen=True)
class TextSearchResult:
    """Raw text search result and limit metadata for CLI output."""

    root: Path
    query: str
    case_sensitive: bool
    scan: ScanResult
    matches: tuple[TextSearchMatch, ...]
    total_matches: int
    max_results: int
    preview_chars: int
    warnings: tuple[str, ...] = ()

    @property
    def truncated(self) -> bool:
        return len(self.matches) < self.total_matches

    def to_cli_data(self) -> dict[str, object]:
        return {
            "case_sensitive": self.case_sensitive,
            "match_count": len(self.matches),
            "matches": [match.to_dict() for match in self.matches],
            "preview_chars": self.preview_chars,
            "query": self.query,
            "repo_path": str(self.root),
            "scanned_files": len(self.scan.files),
            "skipped_paths": len(self.scan.skipped),
            "total_matches": self.total_matches,
            "truncated": self.truncated,
        }


def search_raw_text(
    repo_path: Path | str,
    query: str,
    *,
    case_sensitive: bool = False,
    max_results: int = SEARCH_DEFAULT_MAX_RESULTS,
    preview_chars: int = SEARCH_PREVIEW_CHARS,
) -> TextSearchResult:
    """Search live scanner-approved files for a literal raw text query."""
    if not query.strip():
        raise RepoLensSearchError("empty_query")
    if max_results < 1 or max_results > SEARCH_MAX_RESULTS_LIMIT:
        raise RepoLensSearchError("max_results_out_of_range")
    if preview_chars < 1:
        raise RepoLensSearchError("preview_chars_out_of_range")

    try:
        scan = scan_repository(repo_path)
    except ScanError as exc:
        raise RepoLensSearchError(str(exc)) from exc

    needle = query if case_sensitive else query.casefold()
    matches: list[TextSearchMatch] = []
    total_matches = 0
    warnings: list[str] = []

    for scanned_file in scan.files:
        path = scan.root / scanned_file.path
        try:
            with path.open("r", encoding="utf-8", errors="replace", newline="") as file:
                for line_number, line in enumerate(file, start=1):
                    haystack = line if case_sensitive else line.casefold()
                    offset = 0
                    while True:
                        index = haystack.find(needle, offset)
                        if index == -1:
                            break
                        total_matches += 1
                        if len(matches) < max_results:
                            matches.append(
                                _build_match(
                                    scanned_file.path,
                                    line_number=line_number,
                                    line=line,
                                    match_start=index,
                                    query_length=len(query),
                                    preview_chars=preview_chars,
                                )
                            )
                        offset = index + max(len(needle), 1)
        except OSError:
            warnings.append(f"Skipped unreadable file during search: {scanned_file.path}")

    return TextSearchResult(
        root=scan.root,
        query=query,
        case_sensitive=case_sensitive,
        scan=scan,
        matches=tuple(matches),
        total_matches=total_matches,
        max_results=max_results,
        preview_chars=preview_chars,
        warnings=tuple(warnings),
    )


def _build_match(
    path: str,
    *,
    line_number: int,
    line: str,
    match_start: int,
    query_length: int,
    preview_chars: int,
) -> TextSearchMatch:
    line = line.rstrip("\r\n")
    match_end = min(len(line), match_start + query_length)
    if len(line) <= preview_chars:
        preview_start = 0
        preview_end = len(line)
    else:
        context_chars = max((preview_chars - max(query_length, 1)) // 2, 0)
        preview_start = max(0, match_start - context_chars)
        preview_end = min(len(line), preview_start + preview_chars)
        if preview_end - preview_start < preview_chars:
            preview_start = max(0, preview_end - preview_chars)
        if match_end > preview_end:
            preview_end = min(len(line), match_end)
            preview_start = max(0, preview_end - preview_chars)

    preview = _sanitize_preview(line[preview_start:preview_end])
    return TextSearchMatch(
        path=path,
        line=line_number,
        column=match_start + 1,
        preview=preview,
        preview_truncated_before=preview_start > 0,
        preview_truncated_after=preview_end < len(line),
    )


def _sanitize_preview(preview: str) -> str:
    return "".join(char if 32 <= ord(char) < 127 or ord(char) >= 160 else " " for char in preview)
