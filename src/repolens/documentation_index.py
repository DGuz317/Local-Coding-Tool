"""Markdown, documentation, and tagged comment extraction for RepoLens graph facts."""

from __future__ import annotations

import hashlib
import posixpath
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from repolens.scanner import ScannedFile

DOCUMENTATION_EXTRACTOR_VERSION = "issue-9-markdown-comments-docs-agent-guidance-v1"

MARKDOWN_SUFFIXES = frozenset({".md", ".markdown", ".mdx"})
JAVASCRIPT_SOURCE_SUFFIXES = frozenset(
    {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"}
)
HASH_COMMENT_SUFFIXES = frozenset({".sh", ".bash", ".zsh", ".yaml", ".yml", ".toml"})
HASH_COMMENT_NAMES = frozenset({"dockerfile", "gnumakefile", "makefile"})
AGENT_INSTRUCTION_NAMES = frozenset({"AGENTS.md", "CLAUDE.md", "GEMINI.md"})
TAG_NAMES = frozenset(
    {
        "DEPRECATED",
        "FIXME",
        "HACK",
        "NOTE",
        "PERF",
        "QUESTION",
        "RISK",
        "SECURITY",
        "TODO",
        "WARNING",
    }
)

HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
FENCE_START_PATTERN = re.compile(r"^\s*(`{3,}|~{3,})\s*(.*?)\s*$")
INLINE_LINK_PATTERN = re.compile(r"!?\[([^\]]*)\]\(([^)\s]+)(?:\s+[^)]*)?\)")
HTML_COMMENT_PATTERN = re.compile(r"<!--(.*?)-->", re.DOTALL)
TAG_PATTERN = re.compile(
    rf"^({'|'.join(sorted(TAG_NAMES))})\b(?:\s*[:\-]\s*|\s+)?(.*)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DocumentationMarkdownFileFact:
    """A scanner-approved Markdown-like file classified for assistant orientation."""

    path: str
    node_id: str
    doc_kind: str
    importance: str
    parser_status: str
    title: str | None
    intro: str | None


@dataclass(frozen=True)
class MarkdownHeadingFact:
    """A Markdown heading with a deterministic file-scoped anchor."""

    id: str
    path: str
    document_node_id: str
    heading_id: str
    level: int
    text: str
    line: int


@dataclass(frozen=True)
class MarkdownLinkFact:
    """A relative Markdown link resolved to an existing scanner-approved file."""

    id: str
    path: str
    document_node_id: str
    label: str
    target_path: str
    target_fragment: str | None
    line: int


@dataclass(frozen=True)
class MarkdownPathMentionFact:
    """An exact Markdown path mention resolved to an existing scanner-approved file."""

    id: str
    path: str
    document_node_id: str
    mentioned_path: str
    target_path: str
    line: int


@dataclass(frozen=True)
class MarkdownCodeFenceFact:
    """Code fence metadata without the code block body."""

    id: str
    path: str
    document_node_id: str
    language: str | None
    info_string: str
    start_line: int
    end_line: int | None


@dataclass(frozen=True)
class DocumentationTaggedCommentFact:
    """A tagged non-Python text comment extracted without routine comments."""

    id: str
    path: str
    tag: str
    text: str
    line: int
    language: str
    syntax: str


@dataclass(frozen=True)
class SkillFact:
    """Basic metadata from a scanner-approved skill manifest."""

    id: str
    path: str
    name: str
    description: str | None


@dataclass(frozen=True)
class DocumentationIndex:
    """All documentation and non-Python tagged comment facts for one scan result."""

    markdown_files: tuple[DocumentationMarkdownFileFact, ...]
    headings: tuple[MarkdownHeadingFact, ...]
    links: tuple[MarkdownLinkFact, ...]
    path_mentions: tuple[MarkdownPathMentionFact, ...]
    code_fences: tuple[MarkdownCodeFenceFact, ...]
    tagged_comments: tuple[DocumentationTaggedCommentFact, ...]
    skills: tuple[SkillFact, ...]

    @property
    def parser_status_by_path(self) -> dict[str, str]:
        return {markdown.path: markdown.parser_status for markdown in self.markdown_files}


@dataclass(frozen=True)
class _MarkdownExtraction:
    title: str | None
    intro: str | None
    headings: tuple[MarkdownHeadingFact, ...]
    links: tuple[MarkdownLinkFact, ...]
    path_mentions: tuple[MarkdownPathMentionFact, ...]
    code_fences: tuple[MarkdownCodeFenceFact, ...]
    tagged_comments: tuple[DocumentationTaggedCommentFact, ...]


@dataclass(frozen=True)
class _FenceState:
    marker: str
    info_string: str
    language: str | None
    start_line: int


@dataclass(frozen=True)
class _RawComment:
    line: int
    text: str
    syntax: str


def extract_documentation_index(root: Path, files: tuple[ScannedFile, ...]) -> DocumentationIndex:
    """Extract deterministic docs, guidance, and non-Python tagged comment facts."""
    sorted_files = tuple(sorted(files, key=lambda item: item.path))
    file_paths = frozenset(file.path for file in sorted_files)
    markdown_files: list[DocumentationMarkdownFileFact] = []
    headings: list[MarkdownHeadingFact] = []
    links: list[MarkdownLinkFact] = []
    path_mentions: list[MarkdownPathMentionFact] = []
    code_fences: list[MarkdownCodeFenceFact] = []
    tagged_comments: list[DocumentationTaggedCommentFact] = []
    skills: list[SkillFact] = []

    for scanned_file in sorted_files:
        path = scanned_file.path
        try:
            source = _read_scanner_approved_text(root, path)
        except OSError:
            if _is_markdown(path):
                markdown_files.append(_markdown_file_fact(path, None, None, "parse_error"))
            continue

        if _is_markdown(path):
            extraction = _extract_markdown(path, source, file_paths)
            markdown_files.append(
                _markdown_file_fact(path, extraction.title, extraction.intro, "parsed")
            )
            headings.extend(extraction.headings)
            links.extend(extraction.links)
            path_mentions.extend(extraction.path_mentions)
            code_fences.extend(extraction.code_fences)
            tagged_comments.extend(extraction.tagged_comments)
            skill = _extract_skill(path, source)
            if skill is not None:
                skills.append(skill)
            continue

        tagged_comments.extend(_extract_non_markdown_tagged_comments(path, source))

    return DocumentationIndex(
        markdown_files=tuple(sorted(markdown_files, key=lambda fact: fact.path)),
        headings=tuple(sorted(headings, key=lambda fact: (fact.path, fact.line, fact.id))),
        links=tuple(sorted(links, key=lambda fact: (fact.path, fact.line, fact.id))),
        path_mentions=tuple(
            sorted(
                path_mentions, key=lambda fact: (fact.path, fact.line, fact.target_path, fact.id)
            )
        ),
        code_fences=tuple(sorted(code_fences, key=lambda fact: (fact.path, fact.start_line))),
        tagged_comments=tuple(
            sorted(tagged_comments, key=lambda fact: (fact.path, fact.line, fact.id))
        ),
        skills=tuple(sorted(skills, key=lambda fact: (fact.name, fact.path))),
    )


def documentation_file_node_id(path: str) -> str:
    return f"documentation_file:{path}"


def markdown_heading_node_id(path: str, heading_id: str) -> str:
    return f"markdown_heading:{path}:{heading_id}"


def markdown_code_fence_node_id(path: str, key: str, occurrence: int) -> str:
    suffix = "" if occurrence == 1 else f"#{occurrence}"
    return f"markdown_code_fence:{path}:{_short_hash(key)}{suffix}"


def documentation_tagged_comment_node_id(path: str, key: str, occurrence: int) -> str:
    suffix = "" if occurrence == 1 else f"#{occurrence}"
    return f"documentation_comment:{path}:{_short_hash(key)}{suffix}"


def skill_node_id(name: str, path: str) -> str:
    return f"skill:{name}:{_short_hash(path)}"


def _is_markdown(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in MARKDOWN_SUFFIXES


def _read_scanner_approved_text(root: Path, path: str) -> str:
    resolved_root = root.resolve(strict=True)
    source_path = resolved_root / PurePosixPath(path)
    source_path.resolve(strict=False).relative_to(resolved_root)
    return source_path.read_text(encoding="utf-8", errors="replace")


def _markdown_file_fact(
    path: str,
    title: str | None,
    intro: str | None,
    parser_status: str,
) -> DocumentationMarkdownFileFact:
    return DocumentationMarkdownFileFact(
        path=path,
        node_id=documentation_file_node_id(path),
        doc_kind=_doc_kind(path),
        importance=_importance(path),
        parser_status=parser_status,
        title=title,
        intro=intro if _doc_kind(path) == "readme" else None,
    )


def _doc_kind(path: str) -> str:
    name = PurePosixPath(path).name
    if _is_skill_manifest(path):
        return "skill_manifest"
    if name.lower() in {"readme.md", "readme.markdown", "readme.mdx"}:
        return "readme"
    if _is_agent_instruction_file(path):
        return "agent_instructions"
    return "markdown"


def _importance(path: str) -> str:
    if _doc_kind(path) in {"agent_instructions", "readme", "skill_manifest"}:
        return "important"
    return "normal"


def _is_agent_instruction_file(path: str) -> bool:
    pure_path = PurePosixPath(path)
    if pure_path.name in AGENT_INSTRUCTION_NAMES:
        return True
    if path == ".github/copilot-instructions.md":
        return True
    if path.startswith(".cursor/rules/"):
        return True
    return path.startswith("docs/agents/")


def _is_skill_manifest(path: str) -> bool:
    pure_path = PurePosixPath(path)
    return pure_path.name == "SKILL.md" and "skills" in pure_path.parts


def _extract_markdown(
    path: str,
    source: str,
    file_paths: frozenset[str],
) -> _MarkdownExtraction:
    document_node_id = documentation_file_node_id(path)
    lines = source.splitlines()
    outside_fence_lines, code_fences = _extract_code_fences(path, document_node_id, lines)
    headings = _extract_headings(path, document_node_id, lines, outside_fence_lines)
    title = _first_h1_title(headings)
    intro = _readme_intro(path, lines, outside_fence_lines)
    links = _extract_links(path, document_node_id, lines, outside_fence_lines, file_paths)
    path_mentions = _extract_path_mentions(
        path,
        document_node_id,
        lines,
        outside_fence_lines,
        file_paths,
    )
    tagged_comments = _finalize_tagged_comments(
        path,
        "markdown",
        _extract_markdown_html_comments(source),
    )
    return _MarkdownExtraction(
        title=title,
        intro=intro,
        headings=headings,
        links=links,
        path_mentions=path_mentions,
        code_fences=code_fences,
        tagged_comments=tagged_comments,
    )


def _extract_code_fences(
    path: str,
    document_node_id: str,
    lines: list[str],
) -> tuple[set[int], tuple[MarkdownCodeFenceFact, ...]]:
    outside_fence_lines = set(range(1, len(lines) + 1))
    code_fences: list[MarkdownCodeFenceFact] = []
    id_counts: Counter[str] = Counter()
    fence: _FenceState | None = None

    for line_number, line in enumerate(lines, start=1):
        if fence is not None:
            outside_fence_lines.discard(line_number)
            if _is_fence_end(line, fence.marker):
                _append_code_fence(
                    path, document_node_id, fence, line_number, id_counts, code_fences
                )
                fence = None
            continue

        match = FENCE_START_PATTERN.match(line)
        if match is None:
            continue

        outside_fence_lines.discard(line_number)
        marker = match.group(1)
        info_string = match.group(2).strip()
        fence = _FenceState(
            marker=marker,
            info_string=info_string,
            language=_code_fence_language(info_string),
            start_line=line_number,
        )

    if fence is not None:
        _append_code_fence(path, document_node_id, fence, None, id_counts, code_fences)
    return outside_fence_lines, tuple(code_fences)


def _is_fence_end(line: str, marker: str) -> bool:
    stripped = line.strip()
    return stripped.startswith(marker[0] * len(marker))


def _append_code_fence(
    path: str,
    document_node_id: str,
    fence: _FenceState,
    end_line: int | None,
    id_counts: Counter[str],
    code_fences: list[MarkdownCodeFenceFact],
) -> None:
    key = "|".join((path, fence.info_string, fence.language or ""))
    id_counts[key] += 1
    code_fences.append(
        MarkdownCodeFenceFact(
            id=markdown_code_fence_node_id(path, key, id_counts[key]),
            path=path,
            document_node_id=document_node_id,
            language=fence.language,
            info_string=fence.info_string,
            start_line=fence.start_line,
            end_line=end_line,
        )
    )


def _code_fence_language(info_string: str) -> str | None:
    if not info_string:
        return None
    token = info_string.split(maxsplit=1)[0].strip("{}.").lower()
    return token or None


def _extract_headings(
    path: str,
    document_node_id: str,
    lines: list[str],
    outside_fence_lines: set[int],
) -> tuple[MarkdownHeadingFact, ...]:
    headings: list[MarkdownHeadingFact] = []
    slug_counts: Counter[str] = Counter()
    for line_number, line in enumerate(lines, start=1):
        if line_number not in outside_fence_lines:
            continue
        match = HEADING_PATTERN.match(line)
        if match is None:
            continue
        text = re.sub(r"\s+#+\s*$", "", match.group(2)).strip()
        if not text:
            continue
        base_slug = _heading_slug(text)
        slug_counts[base_slug] += 1
        heading_id = (
            base_slug
            if slug_counts[base_slug] == 1
            else f"{base_slug}-{slug_counts[base_slug] - 1}"
        )
        headings.append(
            MarkdownHeadingFact(
                id=markdown_heading_node_id(path, heading_id),
                path=path,
                document_node_id=document_node_id,
                heading_id=heading_id,
                level=len(match.group(1)),
                text=text,
                line=line_number,
            )
        )
    return tuple(headings)


def _heading_slug(text: str) -> str:
    normalized = text.strip().lower()
    normalized = re.sub(r"[`*_~]", "", normalized)
    normalized = re.sub(r"[^\w\s-]", "", normalized)
    normalized = re.sub(r"[\s-]+", "-", normalized).strip("-")
    return normalized or "section"


def _first_h1_title(headings: tuple[MarkdownHeadingFact, ...]) -> str | None:
    for heading in headings:
        if heading.level == 1:
            return heading.text
    return None


def _readme_intro(
    path: str,
    lines: list[str],
    outside_fence_lines: set[int],
) -> str | None:
    if _doc_kind(path) != "readme":
        return None

    paragraph: list[str] = []
    seen_title = False
    for line_number, line in enumerate(lines, start=1):
        if line_number not in outside_fence_lines:
            continue
        stripped = line.strip()
        if not stripped:
            if paragraph:
                break
            continue
        if HEADING_PATTERN.match(stripped):
            if paragraph:
                break
            seen_title = True
            continue
        if not seen_title:
            continue
        paragraph.append(stripped)
    if not paragraph:
        return None
    return _first_sentence(_plain_markdown_text(" ".join(paragraph)))


def _plain_markdown_text(value: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", value)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[`*_~]", "", text)
    return " ".join(text.split())


def _first_sentence(value: str) -> str | None:
    normalized = " ".join(value.strip().split())
    if not normalized:
        return None
    for index, character in enumerate(normalized):
        if character in ".!?":
            return normalized[: index + 1]
    return normalized[:240]


def _extract_links(
    path: str,
    document_node_id: str,
    lines: list[str],
    outside_fence_lines: set[int],
    file_paths: frozenset[str],
) -> tuple[MarkdownLinkFact, ...]:
    links: list[MarkdownLinkFact] = []
    id_counts: Counter[str] = Counter()
    for line_number, line in enumerate(lines, start=1):
        if line_number not in outside_fence_lines:
            continue
        for match in INLINE_LINK_PATTERN.finditer(line):
            resolved = _resolve_markdown_link(path, match.group(2), file_paths)
            if resolved is None:
                continue
            target_path, target_fragment = resolved
            label = _plain_markdown_text(match.group(1))
            key = "|".join((path, label, target_path, target_fragment or ""))
            id_counts[key] += 1
            suffix = "" if id_counts[key] == 1 else f"#{id_counts[key]}"
            links.append(
                MarkdownLinkFact(
                    id=f"markdown_link:{path}:{_short_hash(key)}{suffix}",
                    path=path,
                    document_node_id=document_node_id,
                    label=label,
                    target_path=target_path,
                    target_fragment=target_fragment,
                    line=line_number,
                )
            )
    return tuple(links)


def _resolve_markdown_link(
    source_path: str,
    href: str,
    file_paths: frozenset[str],
) -> tuple[str, str | None] | None:
    stripped = href.strip().strip("<>")
    parsed = urlsplit(stripped)
    if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith("/"):
        return None
    raw_path = unquote(parsed.path)
    parent = PurePosixPath(source_path).parent.as_posix()
    base = "" if parent == "." else parent
    target_path = posixpath.normpath(posixpath.join(base, raw_path))
    if target_path == "." or target_path == ".." or target_path.startswith("../"):
        return None
    if target_path not in file_paths:
        return None
    return target_path, parsed.fragment or None


def _extract_path_mentions(
    path: str,
    document_node_id: str,
    lines: list[str],
    outside_fence_lines: set[int],
    file_paths: frozenset[str],
) -> tuple[MarkdownPathMentionFact, ...]:
    mentions: list[MarkdownPathMentionFact] = []
    id_counts: Counter[str] = Counter()
    mentionable_paths = tuple(sorted(file_paths, key=lambda item: (-len(item), item)))
    for line_number, line in enumerate(lines, start=1):
        if line_number not in outside_fence_lines:
            continue
        for target_path in mentionable_paths:
            for mentioned_path in _mentioned_path_variants(target_path):
                if not _contains_exact_path(line, mentioned_path):
                    continue
                key = "|".join((path, mentioned_path, target_path))
                id_counts[key] += 1
                suffix = "" if id_counts[key] == 1 else f"#{id_counts[key]}"
                mentions.append(
                    MarkdownPathMentionFact(
                        id=f"markdown_path_mention:{path}:{_short_hash(key)}{suffix}",
                        path=path,
                        document_node_id=document_node_id,
                        mentioned_path=mentioned_path,
                        target_path=target_path,
                        line=line_number,
                    )
                )
                break
    return tuple(mentions)


def _mentioned_path_variants(path: str) -> tuple[str, ...]:
    return (path, f"./{path}")


def _contains_exact_path(line: str, path: str) -> bool:
    pattern = re.compile(rf"(?<![\w./-]){re.escape(path)}(?![\w/-])")
    return pattern.search(line) is not None


def _extract_markdown_html_comments(source: str) -> tuple[_RawComment, ...]:
    comments: list[_RawComment] = []
    for match in HTML_COMMENT_PATTERN.finditer(source):
        start_line = source.count("\n", 0, match.start()) + 1
        comments.extend(_block_comment_lines(match.group(1), start_line, "html"))
    return tuple(comments)


def _extract_non_markdown_tagged_comments(
    path: str,
    source: str,
) -> tuple[DocumentationTaggedCommentFact, ...]:
    language = _comment_language(path)
    if language is None:
        return ()
    if language == "javascript":
        raw_comments = _slash_comment_lines(source)
    else:
        raw_comments = _hash_comment_lines(source)
    return _finalize_tagged_comments(path, language, raw_comments)


def _comment_language(path: str) -> str | None:
    pure_path = PurePosixPath(path)
    suffix = pure_path.suffix.lower()
    if suffix in JAVASCRIPT_SOURCE_SUFFIXES:
        return "javascript"
    if suffix in HASH_COMMENT_SUFFIXES or pure_path.name.lower() in HASH_COMMENT_NAMES:
        return "shell" if suffix in {".sh", ".bash", ".zsh"} else "config"
    return None


def _slash_comment_lines(source: str) -> tuple[_RawComment, ...]:
    comments: list[_RawComment] = []
    index = 0
    line_number = 1
    string_quote: str | None = None
    escaped = False
    block_start_line: int | None = None
    block_chars: list[str] = []

    while index < len(source):
        character = source[index]
        next_character = source[index + 1] if index + 1 < len(source) else ""

        if block_start_line is not None:
            if character == "*" and next_character == "/":
                comments.extend(
                    _block_comment_lines("".join(block_chars), block_start_line, "block")
                )
                block_start_line = None
                block_chars = []
                index += 2
                continue
            block_chars.append(character)
            if character == "\n":
                line_number += 1
            index += 1
            continue

        if string_quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == string_quote:
                string_quote = None
            if character == "\n":
                line_number += 1
            index += 1
            continue

        if character in {"'", '"', "`"}:
            string_quote = character
            index += 1
            continue
        if character == "/" and next_character == "/":
            end_index = source.find("\n", index + 2)
            if end_index == -1:
                end_index = len(source)
            comments.append(
                _RawComment(
                    line=line_number,
                    text=source[index + 2 : end_index].strip(),
                    syntax="line",
                )
            )
            index = end_index
            continue
        if character == "/" and next_character == "*":
            block_start_line = line_number
            block_chars = []
            index += 2
            continue
        if character == "\n":
            line_number += 1
        index += 1

    if block_start_line is not None:
        comments.extend(_block_comment_lines("".join(block_chars), block_start_line, "block"))
    return tuple(comments)


def _block_comment_lines(text: str, start_line: int, syntax: str) -> tuple[_RawComment, ...]:
    comments: list[_RawComment] = []
    for offset, raw_line in enumerate(text.splitlines() or [text]):
        cleaned = raw_line.strip()
        if cleaned.startswith("*"):
            cleaned = cleaned[1:].strip()
        if cleaned:
            comments.append(_RawComment(line=start_line + offset, text=cleaned, syntax=syntax))
    return tuple(comments)


def _hash_comment_lines(source: str) -> tuple[_RawComment, ...]:
    comments: list[_RawComment] = []
    for line_number, raw_line in enumerate(source.splitlines(), start=1):
        stripped = raw_line.lstrip()
        if stripped.startswith("#"):
            comments.append(
                _RawComment(line=line_number, text=stripped.lstrip("#").strip(), syntax="hash")
            )
    return tuple(comments)


def _finalize_tagged_comments(
    path: str,
    language: str,
    raw_comments: tuple[_RawComment, ...],
) -> tuple[DocumentationTaggedCommentFact, ...]:
    comments: list[DocumentationTaggedCommentFact] = []
    id_counts: Counter[str] = Counter()
    for raw_comment in raw_comments:
        match = TAG_PATTERN.match(raw_comment.text)
        if match is None:
            continue
        tag = match.group(1).upper()
        text = match.group(2).strip()
        key = "|".join((path, tag, text, language, raw_comment.syntax))
        id_counts[key] += 1
        comments.append(
            DocumentationTaggedCommentFact(
                id=documentation_tagged_comment_node_id(path, key, id_counts[key]),
                path=path,
                tag=tag,
                text=text,
                line=raw_comment.line,
                language=language,
                syntax=raw_comment.syntax,
            )
        )
    return tuple(comments)


def _extract_skill(path: str, source: str) -> SkillFact | None:
    if not _is_skill_manifest(path):
        return None
    metadata_lines = _manifest_metadata_lines(source)
    name = _manifest_value(metadata_lines, "name") or PurePosixPath(path).parent.name
    description = _manifest_value(metadata_lines, "description")
    return SkillFact(
        id=skill_node_id(name, path),
        path=path,
        name=name,
        description=description,
    )


def _manifest_metadata_lines(source: str) -> tuple[str, ...]:
    lines = tuple(source.splitlines())
    if not lines or lines[0].strip() != "---":
        return lines[:80]
    collected: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            return tuple(collected)
        collected.append(line)
    return lines[:80]


def _manifest_value(lines: tuple[str, ...], key: str) -> str | None:
    prefix = f"{key}:"
    for line in lines:
        normalized = line.strip().lstrip("#").strip()
        if normalized.lower().startswith(prefix):
            value = normalized[len(prefix) :].strip()
            return value or None
    return None


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
