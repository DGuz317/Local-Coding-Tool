"""JavaScript and TypeScript import extraction for RepoLens graph facts."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from repolens.scanner import ScannedFile

JAVASCRIPT_EXTRACTOR_VERSION = "issue-7a-javascript-imports-v1"

JAVASCRIPT_SOURCE_SUFFIXES = frozenset(
    {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"}
)

NODE_BUILTIN_MODULES = frozenset(
    {
        "assert",
        "assert/strict",
        "async_hooks",
        "buffer",
        "child_process",
        "cluster",
        "console",
        "constants",
        "crypto",
        "dgram",
        "diagnostics_channel",
        "dns",
        "dns/promises",
        "domain",
        "events",
        "fs",
        "fs/promises",
        "http",
        "http2",
        "https",
        "inspector",
        "module",
        "net",
        "os",
        "path",
        "path/posix",
        "path/win32",
        "perf_hooks",
        "process",
        "punycode",
        "querystring",
        "readline",
        "readline/promises",
        "repl",
        "stream",
        "stream/consumers",
        "stream/promises",
        "stream/web",
        "string_decoder",
        "test",
        "timers",
        "timers/promises",
        "tls",
        "tty",
        "url",
        "util",
        "util/types",
        "v8",
        "vm",
        "wasi",
        "worker_threads",
        "zlib",
    }
)

STATIC_IMPORT_FROM_PATTERN = re.compile(
    r"^\s*import\s+(?:type\s+)?(?P<clause>.+?)\s+from\s*"
    r"(?P<quote>['\"])(?P<specifier>[^'\"]+)(?P=quote)"
)
SIDE_EFFECT_IMPORT_PATTERN = re.compile(
    r"^\s*import\s*(?P<quote>['\"])(?P<specifier>[^'\"]+)(?P=quote)"
)


@dataclass(frozen=True)
class JavaScriptModuleFact:
    """A scanner-approved JS/TS file represented as a source module."""

    path: str
    node_id: str
    module_name: str
    extension: str
    parser_status: str


@dataclass(frozen=True)
class JavaScriptImportFact:
    """A JS/TS import-like statement classified by package root."""

    id: str
    path: str
    module_node_id: str
    kind: str
    specifier: str
    root_name: str | None
    classification: str
    line: int


@dataclass(frozen=True)
class JavaScriptPackageFact:
    """An observed JS/TS package or Node built-in import root."""

    id: str
    name: str
    classification: str


@dataclass(frozen=True)
class JavaScriptIndex:
    """All JS/TS import facts extracted for one scan result."""

    modules: tuple[JavaScriptModuleFact, ...]
    imports: tuple[JavaScriptImportFact, ...]
    packages: tuple[JavaScriptPackageFact, ...]

    @property
    def parser_status_by_path(self) -> dict[str, str]:
        return {module.path: module.parser_status for module in self.modules}


def extract_javascript_index(root: Path, files: tuple[ScannedFile, ...]) -> JavaScriptIndex:
    """Extract deterministic JS/TS import facts from scanner-approved source files only."""
    javascript_files = tuple(
        file for file in sorted(files, key=lambda item: item.path) if _is_javascript(file)
    )
    modules: list[JavaScriptModuleFact] = []
    imports: list[JavaScriptImportFact] = []
    observed_packages: set[tuple[str, str]] = set()

    for scanned_file in javascript_files:
        path = scanned_file.path
        module_node_id = javascript_module_node_id(path)
        modules.append(
            JavaScriptModuleFact(
                path=path,
                node_id=module_node_id,
                module_name=_module_name(path),
                extension=PurePosixPath(path).suffix.lower(),
                parser_status="parsed",
            )
        )
        try:
            source = _read_scanner_approved_text(root, path)
        except OSError:
            modules[-1] = JavaScriptModuleFact(
                path=path,
                node_id=module_node_id,
                module_name=_module_name(path),
                extension=PurePosixPath(path).suffix.lower(),
                parser_status="parse_error",
            )
            continue

        imports_for_file = _extract_imports(path, module_node_id, source)
        imports.extend(imports_for_file)
        for import_fact in imports_for_file:
            if import_fact.root_name is not None:
                observed_packages.add((import_fact.classification, import_fact.root_name))

    packages = tuple(
        JavaScriptPackageFact(
            id=javascript_package_node_id(name, classification),
            name=name,
            classification=classification,
        )
        for classification, name in sorted(observed_packages)
    )
    return JavaScriptIndex(
        modules=tuple(sorted(modules, key=lambda fact: fact.path)),
        imports=tuple(sorted(imports, key=lambda fact: (fact.path, fact.line, fact.id))),
        packages=packages,
    )


def javascript_module_node_id(path: str) -> str:
    return f"javascript_module:{path}"


def javascript_package_node_id(name: str, classification: str) -> str:
    return f"javascript_package:{classification}:{name}"


def _is_javascript(file: ScannedFile) -> bool:
    return PurePosixPath(file.path).suffix.lower() in JAVASCRIPT_SOURCE_SUFFIXES


def _read_scanner_approved_text(root: Path, path: str) -> str:
    resolved_root = root.resolve(strict=True)
    source_path = resolved_root / PurePosixPath(path)
    source_path.resolve(strict=False).relative_to(resolved_root)
    return source_path.read_text(encoding="utf-8", errors="replace")


def _module_name(path: str) -> str:
    return PurePosixPath(path).with_suffix("").as_posix()


def _extract_imports(
    path: str, module_node_id: str, source: str
) -> tuple[JavaScriptImportFact, ...]:
    facts: list[JavaScriptImportFact] = []
    id_counts: Counter[str] = Counter()
    for line_number, line in enumerate(_strip_comments_preserving_strings(source), start=1):
        static_import = _static_import_fact(path, module_node_id, line, line_number, id_counts)
        if static_import is not None:
            facts.append(static_import)

        for specifier in _literal_call_specifiers(line, "require"):
            facts.append(
                _import_fact(path, module_node_id, "require", specifier, line_number, id_counts)
            )
        for specifier in _literal_call_specifiers(line, "import"):
            facts.append(
                _import_fact(
                    path,
                    module_node_id,
                    "dynamic_import",
                    specifier,
                    line_number,
                    id_counts,
                )
            )
    return tuple(facts)


def _static_import_fact(
    path: str,
    module_node_id: str,
    line: str,
    line_number: int,
    id_counts: Counter[str],
) -> JavaScriptImportFact | None:
    match = STATIC_IMPORT_FROM_PATTERN.match(line)
    if match is not None:
        return _import_fact(
            path,
            module_node_id,
            _static_import_kind(match.group("clause")),
            match.group("specifier"),
            line_number,
            id_counts,
        )

    match = SIDE_EFFECT_IMPORT_PATTERN.match(line)
    if match is not None:
        return _import_fact(
            path,
            module_node_id,
            "side_effect_import",
            match.group("specifier"),
            line_number,
            id_counts,
        )
    return None


def _static_import_kind(clause: str) -> str:
    normalized = " ".join(clause.split())
    if normalized.startswith("* as "):
        return "namespace_import"
    if normalized.startswith("{") or "{" in normalized:
        return "named_import"
    return "default_import"


def _import_fact(
    path: str,
    module_node_id: str,
    kind: str,
    specifier: str,
    line: int,
    id_counts: Counter[str],
) -> JavaScriptImportFact:
    root_name, classification = _classify_specifier(specifier)
    key = "|".join((path, kind, specifier, str(line)))
    id_counts[key] += 1
    suffix = "" if id_counts[key] == 1 else f"#{id_counts[key]}"
    return JavaScriptImportFact(
        id=f"javascript_import:{path}:{_short_hash(key)}{suffix}",
        path=path,
        module_node_id=module_node_id,
        kind=kind,
        specifier=specifier,
        root_name=root_name,
        classification=classification,
        line=line,
    )


def _classify_specifier(specifier: str) -> tuple[str | None, str]:
    if specifier.startswith((".", "/")):
        return None, "local_unresolved"

    node_builtin = _node_builtin_name(specifier)
    if node_builtin is not None:
        return node_builtin, "node_builtin"

    return _package_root(specifier), "third_party"


def _node_builtin_name(specifier: str) -> str | None:
    if specifier.startswith("node:"):
        return specifier.removeprefix("node:")
    if specifier in NODE_BUILTIN_MODULES:
        return specifier
    root = specifier.split("/", maxsplit=1)[0]
    if root in NODE_BUILTIN_MODULES:
        return root
    return None


def _package_root(specifier: str) -> str:
    parts = specifier.split("/")
    if specifier.startswith("@") and len(parts) >= 2:
        return "/".join(parts[:2])
    return parts[0]


def _strip_comments_preserving_strings(source: str) -> tuple[str, ...]:
    lines: list[str] = []
    in_block_comment = False
    for raw_line in source.splitlines():
        line: list[str] = []
        quote: str | None = None
        escaped = False
        index = 0
        while index < len(raw_line):
            character = raw_line[index]
            next_character = raw_line[index + 1] if index + 1 < len(raw_line) else ""

            if in_block_comment:
                if character == "*" and next_character == "/":
                    in_block_comment = False
                    line.extend("  ")
                    index += 2
                else:
                    line.append(" ")
                    index += 1
                continue

            if quote is not None:
                line.append(character)
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    quote = None
                index += 1
                continue

            if character in {"'", '"', "`"}:
                quote = character
                line.append(character)
                index += 1
                continue
            if character == "/" and next_character == "*":
                in_block_comment = True
                line.extend("  ")
                index += 2
                continue
            if character == "/" and next_character == "/":
                line.extend(" " for _ in range(len(raw_line) - index))
                break

            line.append(character)
            index += 1
        lines.append("".join(line))
    return tuple(lines)


def _literal_call_specifiers(line: str, function_name: str) -> tuple[str, ...]:
    specifiers: list[str] = []
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(line):
        character = line[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            index += 1
            continue
        if character in {"'", '"', "`"}:
            quote = character
            index += 1
            continue
        if _matches_callable_token(line, function_name, index):
            parsed = _parse_literal_call(line, index + len(function_name))
            if parsed is not None:
                specifier, end_index = parsed
                specifiers.append(specifier)
                index = end_index
                continue
        index += 1
    return tuple(specifiers)


def _matches_callable_token(line: str, token: str, index: int) -> bool:
    if not line.startswith(token, index):
        return False
    before = line[index - 1] if index > 0 else ""
    after_index = index + len(token)
    after = line[after_index] if after_index < len(line) else ""
    return not _is_identifier_or_member_character(
        before
    ) and not _is_identifier_or_member_character(after)


def _is_identifier_or_member_character(character: str) -> bool:
    return character == "." or character == "$" or _is_identifier_character(character)


def _is_identifier_character(character: str) -> bool:
    return character == "_" or character.isalnum()


def _parse_literal_call(line: str, index: int) -> tuple[str, int] | None:
    index = _skip_whitespace(line, index)
    if index >= len(line) or line[index] != "(":
        return None
    index = _skip_whitespace(line, index + 1)
    if index >= len(line) or line[index] not in {"'", '"'}:
        return None

    parsed_string = _parse_string_literal(line, index)
    if parsed_string is None:
        return None
    specifier, index = parsed_string
    index = _skip_whitespace(line, index)
    if index >= len(line) or line[index] != ")":
        return None
    return specifier, index + 1


def _parse_string_literal(line: str, index: int) -> tuple[str, int] | None:
    quote = line[index]
    index += 1
    value: list[str] = []
    escaped = False
    while index < len(line):
        character = line[index]
        if escaped:
            value.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == quote:
            return "".join(value), index + 1
        else:
            value.append(character)
        index += 1
    return None


def _skip_whitespace(line: str, index: int) -> int:
    while index < len(line) and line[index].isspace():
        index += 1
    return index


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
