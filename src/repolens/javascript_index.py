"""JavaScript and TypeScript structure extraction for RepoLens graph facts."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from repolens.scanner import ScannedFile

JAVASCRIPT_EXTRACTOR_VERSION = "issue-39-js-ts-relative-import-resolution-v1"

JAVASCRIPT_SOURCE_SUFFIXES = frozenset(
    {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"}
)
JAVASCRIPT_RESOLUTION_SUFFIXES = (
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mts",
    ".cts",
    ".mjs",
    ".cjs",
)
TYPESCRIPT_CONFIG_NAMES = frozenset({"jsconfig.json", "tsconfig.json"})

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
IDENTIFIER_PATTERN = r"[A-Za-z_$][A-Za-z0-9_$]*"
EXPORT_PREFIX_PATTERN = r"(?:export\s+(?:default\s+)?)?"
FUNCTION_DECLARATION_PATTERN = re.compile(
    rf"^\s*{EXPORT_PREFIX_PATTERN}(?:async\s+)?function(?:\s*\*)?\s+"
    rf"(?P<name>{IDENTIFIER_PATTERN})\b"
)
CLASS_DECLARATION_PATTERN = re.compile(
    rf"^\s*{EXPORT_PREFIX_PATTERN}class\s+(?P<name>{IDENTIFIER_PATTERN})\b"
)
INTERFACE_DECLARATION_PATTERN = re.compile(
    rf"^\s*(?:export\s+)?interface\s+(?P<name>{IDENTIFIER_PATTERN})\b"
)
TYPE_ALIAS_PATTERN = re.compile(rf"^\s*(?:export\s+)?type\s+(?P<name>{IDENTIFIER_PATTERN})\s*=")
ARROW_CONST_PATTERN = re.compile(
    rf"^\s*(?:export\s+)?const\s+(?P<name>{IDENTIFIER_PATTERN})\s*"
    rf"(?::[^=]+)?=\s*(?:async\s*)?(?:<[^=>]+>\s*)?"
    rf"(?:\([^)]*\)|{IDENTIFIER_PATTERN})\s*=>"
)
EXPORT_FUNCTION_PATTERN = re.compile(
    rf"^\s*export\s+(?:default\s+)?(?:async\s+)?function(?:\s*\*)?\s+"
    rf"(?P<name>{IDENTIFIER_PATTERN})\b"
)
EXPORT_CLASS_PATTERN = re.compile(
    rf"^\s*export\s+(?:default\s+)?class\s+(?P<name>{IDENTIFIER_PATTERN})\b"
)
EXPORT_CONST_PATTERN = re.compile(rf"^\s*export\s+const\s+(?P<name>{IDENTIFIER_PATTERN})\b")
EXPORT_DEFAULT_PATTERN = re.compile(r"^\s*export\s+default\b(?P<body>.*)$")
EXPORT_LIST_PATTERN = re.compile(r"^\s*export\s*\{(?P<items>[^}]+)\}")
EXPORT_LIST_ITEM_PATTERN = re.compile(
    rf"^(?:type\s+)?(?P<local>{IDENTIFIER_PATTERN}|default)"
    rf"(?:\s+as\s+(?P<exported>{IDENTIFIER_PATTERN}|default))?$"
)
MODULE_EXPORTS_PATTERN = re.compile(r"^\s*module\.exports\s*=\s*(?P<rhs>.+?)\s*;?\s*$")
EXPORTS_PROPERTY_PATTERN = re.compile(
    rf"^\s*exports\.(?P<name>{IDENTIFIER_PATTERN})\s*=\s*(?P<rhs>.+?)\s*;?\s*$"
)
ASSIGNED_NAME_PATTERN = re.compile(rf"^(?P<name>{IDENTIFIER_PATTERN}(?:\.{IDENTIFIER_PATTERN})*)\b")
JS_KEYWORDS = frozenset({"async", "class", "function", "new", "return"})


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
    resolved_path: str | None
    resolution_status: str
    line: int


@dataclass(frozen=True)
class JavaScriptPackageFact:
    """An observed JS/TS package or Node built-in import root."""

    id: str
    name: str
    classification: str


@dataclass(frozen=True)
class JavaScriptSymbolFact:
    """An obvious top-level JS/TS symbol discovered by bounded scanning."""

    id: str
    path: str
    module_node_id: str
    kind: str
    name: str
    qualified_name: str
    line: int
    start_line: int
    end_line: int


@dataclass(frozen=True)
class JavaScriptExportFact:
    """A clear ES export statement without source body content."""

    id: str
    path: str
    module_node_id: str
    kind: str
    exported_name: str
    local_name: str | None
    line: int


@dataclass(frozen=True)
class JavaScriptCommonJSAssignmentFact:
    """A clear CommonJS export assignment without source body content."""

    id: str
    path: str
    module_node_id: str
    kind: str
    exported_name: str
    assigned_name: str | None
    line: int


@dataclass(frozen=True)
class JavaScriptIndex:
    """All JS/TS facts extracted for one scan result."""

    modules: tuple[JavaScriptModuleFact, ...]
    imports: tuple[JavaScriptImportFact, ...]
    packages: tuple[JavaScriptPackageFact, ...]
    symbols: tuple[JavaScriptSymbolFact, ...]
    exports: tuple[JavaScriptExportFact, ...]
    commonjs_assignments: tuple[JavaScriptCommonJSAssignmentFact, ...]

    @property
    def parser_status_by_path(self) -> dict[str, str]:
        return {module.path: module.parser_status for module in self.modules}


def extract_javascript_index(root: Path, files: tuple[ScannedFile, ...]) -> JavaScriptIndex:
    """Extract deterministic JS/TS facts from scanner-approved source files only."""
    javascript_files = tuple(
        file for file in sorted(files, key=lambda item: item.path) if _is_javascript(file)
    )
    javascript_paths = frozenset(file.path for file in javascript_files)
    alias_rules = _load_typescript_alias_rules(root, files)
    modules: list[JavaScriptModuleFact] = []
    imports: list[JavaScriptImportFact] = []
    symbols: list[JavaScriptSymbolFact] = []
    exports: list[JavaScriptExportFact] = []
    commonjs_assignments: list[JavaScriptCommonJSAssignmentFact] = []
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

        file_facts = _extract_file_facts(
            path,
            module_node_id,
            source,
            alias_rules,
            javascript_paths,
        )
        imports.extend(file_facts.imports)
        symbols.extend(file_facts.symbols)
        exports.extend(file_facts.exports)
        commonjs_assignments.extend(file_facts.commonjs_assignments)
        for import_fact in file_facts.imports:
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
        symbols=tuple(sorted(symbols, key=lambda fact: (fact.path, fact.qualified_name, fact.id))),
        exports=tuple(sorted(exports, key=lambda fact: (fact.path, fact.line, fact.id))),
        commonjs_assignments=tuple(
            sorted(commonjs_assignments, key=lambda fact: (fact.path, fact.line, fact.id))
        ),
    )


def javascript_module_node_id(path: str) -> str:
    return f"javascript_module:{path}"


def javascript_package_node_id(name: str, classification: str) -> str:
    return f"javascript_package:{classification}:{name}"


def javascript_symbol_node_id(path: str, kind: str, name: str) -> str:
    return f"javascript_symbol:{path}:{kind}:{name}"


def _is_javascript(file: ScannedFile) -> bool:
    return PurePosixPath(file.path).suffix.lower() in JAVASCRIPT_SOURCE_SUFFIXES


def _read_scanner_approved_text(root: Path, path: str) -> str:
    resolved_root = root.resolve(strict=True)
    source_path = resolved_root / PurePosixPath(path)
    source_path.resolve(strict=False).relative_to(resolved_root)
    return source_path.read_text(encoding="utf-8", errors="replace")


def _module_name(path: str) -> str:
    return PurePosixPath(path).with_suffix("").as_posix()


@dataclass(frozen=True)
class _TypeScriptAliasRule:
    alias_prefix: str
    target_prefixes: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class _ImportResolution:
    root_name: str | None
    classification: str
    resolved_path: str | None
    resolution_status: str


@dataclass(frozen=True)
class _JavaScriptFileFacts:
    imports: tuple[JavaScriptImportFact, ...]
    symbols: tuple[JavaScriptSymbolFact, ...]
    exports: tuple[JavaScriptExportFact, ...]
    commonjs_assignments: tuple[JavaScriptCommonJSAssignmentFact, ...]


def _extract_file_facts(
    path: str,
    module_node_id: str,
    source: str,
    alias_rules: tuple[_TypeScriptAliasRule, ...],
    javascript_paths: frozenset[str],
) -> _JavaScriptFileFacts:
    imports: list[JavaScriptImportFact] = []
    symbols: list[JavaScriptSymbolFact] = []
    exports: list[JavaScriptExportFact] = []
    commonjs_assignments: list[JavaScriptCommonJSAssignmentFact] = []
    import_id_counts: Counter[str] = Counter()
    symbol_id_counts: Counter[str] = Counter()
    export_id_counts: Counter[str] = Counter()
    commonjs_id_counts: Counter[str] = Counter()
    brace_depth = 0

    stripped_lines = tuple(_strip_comments_preserving_strings(source))
    for line_number, line in enumerate(stripped_lines, start=1):
        static_import = _static_import_fact(
            path,
            module_node_id,
            line,
            line_number,
            import_id_counts,
            alias_rules,
            javascript_paths,
        )
        if static_import is not None:
            imports.append(static_import)

        for specifier in _literal_call_specifiers(line, "require"):
            imports.append(
                _import_fact(
                    path,
                    module_node_id,
                    "require",
                    specifier,
                    line_number,
                    import_id_counts,
                    alias_rules,
                    javascript_paths,
                )
            )
        for specifier in _literal_call_specifiers(line, "import"):
            imports.append(
                _import_fact(
                    path,
                    module_node_id,
                    "dynamic_import",
                    specifier,
                    line_number,
                    import_id_counts,
                    alias_rules,
                    javascript_paths,
                )
            )

        if brace_depth == 0:
            symbol = _top_level_symbol_fact(
                path,
                module_node_id,
                line,
                line_number,
                _top_level_symbol_end_line(stripped_lines, line_number),
                symbol_id_counts,
            )
            if symbol is not None:
                symbols.append(symbol)
            exports.extend(
                _top_level_export_facts(
                    path,
                    module_node_id,
                    line,
                    line_number,
                    export_id_counts,
                )
            )
            commonjs_assignment = _commonjs_assignment_fact(
                path,
                module_node_id,
                line,
                line_number,
                commonjs_id_counts,
            )
            if commonjs_assignment is not None:
                commonjs_assignments.append(commonjs_assignment)

        brace_depth = max(0, brace_depth + _brace_delta_outside_strings(line))

    return _JavaScriptFileFacts(
        imports=tuple(imports),
        symbols=tuple(symbols),
        exports=tuple(exports),
        commonjs_assignments=tuple(commonjs_assignments),
    )


def _static_import_fact(
    path: str,
    module_node_id: str,
    line: str,
    line_number: int,
    id_counts: Counter[str],
    alias_rules: tuple[_TypeScriptAliasRule, ...],
    javascript_paths: frozenset[str],
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
            alias_rules,
            javascript_paths,
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
            alias_rules,
            javascript_paths,
        )
    return None


def _static_import_kind(clause: str) -> str:
    normalized = " ".join(clause.split())
    if normalized.startswith("* as "):
        return "namespace_import"
    if normalized.startswith("{") or "{" in normalized:
        return "named_import"
    return "default_import"


def _top_level_symbol_fact(
    path: str,
    module_node_id: str,
    line: str,
    line_number: int,
    end_line: int,
    id_counts: Counter[str],
) -> JavaScriptSymbolFact | None:
    for kind, pattern in (
        ("function", FUNCTION_DECLARATION_PATTERN),
        ("arrow_function", ARROW_CONST_PATTERN),
        ("class", CLASS_DECLARATION_PATTERN),
        ("interface", INTERFACE_DECLARATION_PATTERN),
        ("type_alias", TYPE_ALIAS_PATTERN),
    ):
        match = pattern.match(line)
        if match is not None:
            return _symbol_fact(
                path,
                module_node_id,
                kind,
                match.group("name"),
                line_number,
                end_line,
                id_counts,
            )
    return None


def _top_level_symbol_end_line(lines: tuple[str, ...], start_line: int) -> int:
    seen_opening_brace = False
    brace_depth = 0
    for line_number, line in enumerate(lines[start_line - 1 :], start=start_line):
        if not seen_opening_brace and _statement_ends_outside_strings(line):
            return start_line
        delta = _brace_delta_outside_strings(line)
        if _has_opening_brace_outside_strings(line):
            seen_opening_brace = True
        brace_depth += delta
        if seen_opening_brace and brace_depth <= 0:
            return line_number
    return start_line


def _symbol_fact(
    path: str,
    module_node_id: str,
    kind: str,
    name: str,
    line: int,
    end_line: int,
    id_counts: Counter[str],
) -> JavaScriptSymbolFact:
    key = "|".join((path, kind, name))
    id_counts[key] += 1
    suffix = "" if id_counts[key] == 1 else f"#{id_counts[key]}"
    return JavaScriptSymbolFact(
        id=f"{javascript_symbol_node_id(path, kind, name)}{suffix}",
        path=path,
        module_node_id=module_node_id,
        kind=kind,
        name=name,
        qualified_name=name,
        line=line,
        start_line=line,
        end_line=end_line,
    )


def _top_level_export_facts(
    path: str,
    module_node_id: str,
    line: str,
    line_number: int,
    id_counts: Counter[str],
) -> tuple[JavaScriptExportFact, ...]:
    facts: list[JavaScriptExportFact] = []
    if _is_default_export(line):
        facts.append(
            _export_fact(
                path,
                module_node_id,
                "default_export",
                "default",
                _default_export_local_name(line),
                line_number,
                id_counts,
            )
        )
        return tuple(facts)

    for kind, pattern in (
        ("function_export", EXPORT_FUNCTION_PATTERN),
        ("class_export", EXPORT_CLASS_PATTERN),
        ("const_export", EXPORT_CONST_PATTERN),
    ):
        match = pattern.match(line)
        if match is not None:
            name = match.group("name")
            facts.append(
                _export_fact(path, module_node_id, kind, name, name, line_number, id_counts)
            )
            return tuple(facts)

    facts.extend(_export_list_facts(path, module_node_id, line, line_number, id_counts))
    return tuple(facts)


def _is_default_export(line: str) -> bool:
    return EXPORT_DEFAULT_PATTERN.match(line) is not None


def _default_export_local_name(line: str) -> str | None:
    match = EXPORT_DEFAULT_PATTERN.match(line)
    if match is None:
        return None
    body = match.group("body").strip()
    function_match = re.match(
        rf"^(?:async\s+)?function(?:\s*\*)?\s+(?P<name>{IDENTIFIER_PATTERN})\b",
        body,
    )
    if function_match is not None:
        return function_match.group("name")
    class_match = re.match(rf"^class\s+(?P<name>{IDENTIFIER_PATTERN})\b", body)
    if class_match is not None:
        return class_match.group("name")

    name_match = ASSIGNED_NAME_PATTERN.match(body.rstrip(";").strip())
    if name_match is None:
        return None
    name = name_match.group("name")
    if name in JS_KEYWORDS:
        return None
    remainder = body.rstrip(";").strip()[name_match.end() :].strip()
    return name if not remainder else None


def _export_list_facts(
    path: str,
    module_node_id: str,
    line: str,
    line_number: int,
    id_counts: Counter[str],
) -> tuple[JavaScriptExportFact, ...]:
    match = EXPORT_LIST_PATTERN.match(line)
    if match is None:
        return ()

    facts: list[JavaScriptExportFact] = []
    for raw_item in match.group("items").split(","):
        item_match = EXPORT_LIST_ITEM_PATTERN.match(raw_item.strip())
        if item_match is None:
            continue
        local_name = item_match.group("local")
        exported_name = item_match.group("exported") or local_name
        facts.append(
            _export_fact(
                path,
                module_node_id,
                "named_export",
                exported_name,
                local_name,
                line_number,
                id_counts,
            )
        )
    return tuple(facts)


def _export_fact(
    path: str,
    module_node_id: str,
    kind: str,
    exported_name: str,
    local_name: str | None,
    line: int,
    id_counts: Counter[str],
) -> JavaScriptExportFact:
    key = "|".join((path, kind, exported_name))
    id_counts[key] += 1
    suffix = "" if id_counts[key] == 1 else f"#{id_counts[key]}"
    return JavaScriptExportFact(
        id=f"javascript_export:{path}:{kind}:{exported_name}{suffix}",
        path=path,
        module_node_id=module_node_id,
        kind=kind,
        exported_name=exported_name,
        local_name=local_name,
        line=line,
    )


def _commonjs_assignment_fact(
    path: str,
    module_node_id: str,
    line: str,
    line_number: int,
    id_counts: Counter[str],
) -> JavaScriptCommonJSAssignmentFact | None:
    module_exports = MODULE_EXPORTS_PATTERN.match(line)
    if module_exports is not None:
        return _commonjs_fact(
            path,
            module_node_id,
            "module_exports",
            "module.exports",
            _assigned_name(module_exports.group("rhs")),
            line_number,
            id_counts,
        )

    exports_property = EXPORTS_PROPERTY_PATTERN.match(line)
    if exports_property is None:
        return None
    exported_name = exports_property.group("name")
    return _commonjs_fact(
        path,
        module_node_id,
        "exports_property",
        exported_name,
        _assigned_name(exports_property.group("rhs")),
        line_number,
        id_counts,
    )


def _commonjs_fact(
    path: str,
    module_node_id: str,
    kind: str,
    exported_name: str,
    assigned_name: str | None,
    line: int,
    id_counts: Counter[str],
) -> JavaScriptCommonJSAssignmentFact:
    key = "|".join((path, kind, exported_name))
    id_counts[key] += 1
    suffix = "" if id_counts[key] == 1 else f"#{id_counts[key]}"
    return JavaScriptCommonJSAssignmentFact(
        id=f"javascript_commonjs:{path}:{kind}:{exported_name}{suffix}",
        path=path,
        module_node_id=module_node_id,
        kind=kind,
        exported_name=exported_name,
        assigned_name=assigned_name,
        line=line,
    )


def _assigned_name(rhs: str) -> str | None:
    normalized = rhs.strip().rstrip(";").strip()
    match = ASSIGNED_NAME_PATTERN.match(normalized)
    if match is None:
        return None
    name = match.group("name")
    if name in JS_KEYWORDS:
        return None
    remainder = normalized[match.end() :].strip()
    return name if not remainder else None


def _import_fact(
    path: str,
    module_node_id: str,
    kind: str,
    specifier: str,
    line: int,
    id_counts: Counter[str],
    alias_rules: tuple[_TypeScriptAliasRule, ...],
    javascript_paths: frozenset[str],
) -> JavaScriptImportFact:
    resolution = _resolve_import_specifier(path, specifier, alias_rules, javascript_paths)
    key = "|".join((path, kind, specifier, str(line)))
    id_counts[key] += 1
    suffix = "" if id_counts[key] == 1 else f"#{id_counts[key]}"
    return JavaScriptImportFact(
        id=f"javascript_import:{path}:{_short_hash(key)}{suffix}",
        path=path,
        module_node_id=module_node_id,
        kind=kind,
        specifier=specifier,
        root_name=resolution.root_name,
        classification=resolution.classification,
        resolved_path=resolution.resolved_path,
        resolution_status=resolution.resolution_status,
        line=line,
    )


def _resolve_import_specifier(
    source_path: str,
    specifier: str,
    alias_rules: tuple[_TypeScriptAliasRule, ...],
    javascript_paths: frozenset[str],
) -> _ImportResolution:
    if specifier.startswith("/"):
        return _ImportResolution(None, "local_unresolved", None, "unresolved_unsupported_absolute")

    if specifier.startswith("."):
        return _resolve_relative_specifier(source_path, specifier, javascript_paths)

    alias_resolution = _resolve_alias_specifier(specifier, alias_rules, javascript_paths)
    if alias_resolution is not None:
        return alias_resolution

    node_builtin = _node_builtin_name(specifier)
    if node_builtin is not None:
        return _ImportResolution(node_builtin, "node_builtin", None, "external")

    return _ImportResolution(_package_root(specifier), "third_party", None, "external")


def _resolve_relative_specifier(
    source_path: str,
    specifier: str,
    javascript_paths: frozenset[str],
) -> _ImportResolution:
    source_dir = PurePosixPath(source_path).parent.as_posix()
    if source_dir == ".":
        source_dir = ""
    base_path = _normalize_repo_path(source_dir, specifier)
    if base_path is None:
        return _ImportResolution(None, "local_unresolved", None, "unresolved_outside_root")

    candidate_paths = _module_path_candidates(base_path, javascript_paths)
    if len(candidate_paths) == 1:
        return _ImportResolution(
            None,
            "local_resolved",
            next(iter(candidate_paths)),
            "resolved_relative",
        )
    if len(candidate_paths) > 1:
        return _ImportResolution(None, "local_unresolved", None, "unresolved_ambiguous_relative")
    return _ImportResolution(None, "local_unresolved", None, "unresolved_missing_relative")


def _resolve_alias_specifier(
    specifier: str,
    alias_rules: tuple[_TypeScriptAliasRule, ...],
    javascript_paths: frozenset[str],
) -> _ImportResolution | None:
    matches = tuple(rule for rule in alias_rules if specifier.startswith(rule.alias_prefix))
    if not matches:
        return None

    if any(rule.status == "complex" for rule in matches):
        return _ImportResolution(None, "local_unresolved", None, "unresolved_complex_alias")

    candidate_paths: set[str] = set()
    for rule in matches:
        suffix = specifier.removeprefix(rule.alias_prefix)
        for target_prefix in rule.target_prefixes:
            candidate_paths.update(
                _module_path_candidates(_join_repo_path(target_prefix, suffix), javascript_paths)
            )

    if len(candidate_paths) == 1:
        return _ImportResolution(
            None,
            "local_resolved",
            next(iter(candidate_paths)),
            "resolved_alias",
        )
    if len(candidate_paths) > 1:
        return _ImportResolution(None, "local_unresolved", None, "unresolved_ambiguous_alias")
    return _ImportResolution(None, "local_unresolved", None, "unresolved_missing_alias")


def _load_typescript_alias_rules(
    root: Path,
    files: tuple[ScannedFile, ...],
) -> tuple[_TypeScriptAliasRule, ...]:
    rules: list[_TypeScriptAliasRule] = []
    config_files = tuple(
        file
        for file in sorted(files, key=lambda item: item.path)
        if PurePosixPath(file.path).name in TYPESCRIPT_CONFIG_NAMES
    )
    for config_file in config_files:
        config = _read_json_config(root, config_file.path)
        if not isinstance(config, dict):
            continue
        compiler_options = config.get("compilerOptions")
        if not isinstance(compiler_options, dict):
            continue
        paths = compiler_options.get("paths")
        if not isinstance(paths, dict):
            continue

        config_dir = PurePosixPath(config_file.path).parent.as_posix()
        if config_dir == ".":
            config_dir = ""
        base_url = compiler_options.get("baseUrl", ".")
        if not isinstance(base_url, str):
            base_url = "."

        for alias_pattern, target_patterns in sorted(paths.items()):
            if not isinstance(alias_pattern, str):
                continue
            alias_prefix = _simple_alias_prefix(alias_pattern)
            if alias_prefix is None:
                continue

            target_prefixes = _target_prefixes(config_dir, base_url, target_patterns)
            rules.append(
                _TypeScriptAliasRule(
                    alias_prefix=alias_prefix,
                    target_prefixes=target_prefixes,
                    status="deterministic" if len(target_prefixes) == 1 else "complex",
                )
            )
    return tuple(sorted(rules, key=lambda rule: (rule.alias_prefix, rule.target_prefixes)))


def _read_json_config(root: Path, path: str) -> object | None:
    try:
        text = _read_scanner_approved_text(root, path)
    except OSError:
        return None
    try:
        return json.loads(_strip_json_trailing_commas(_strip_json_comments(text)))
    except json.JSONDecodeError:
        return None


def _strip_json_comments(source: str) -> str:
    characters: list[str] = []
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(source):
        character = source[index]
        next_character = source[index + 1] if index + 1 < len(source) else ""
        if quote is not None:
            characters.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            index += 1
            continue

        if character in {'"', "'"}:
            quote = character
            characters.append(character)
            index += 1
            continue
        if character == "/" and next_character == "/":
            while index < len(source) and source[index] not in {"\n", "\r"}:
                characters.append(" ")
                index += 1
            continue
        if character == "/" and next_character == "*":
            characters.extend("  ")
            index += 2
            while index < len(source):
                if source[index] == "*" and index + 1 < len(source) and source[index + 1] == "/":
                    characters.extend("  ")
                    index += 2
                    break
                characters.append("\n" if source[index] in {"\n", "\r"} else " ")
                index += 1
            continue

        characters.append(character)
        index += 1
    return "".join(characters)


def _strip_json_trailing_commas(source: str) -> str:
    characters: list[str] = []
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(source):
        character = source[index]
        if quote is not None:
            characters.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            index += 1
            continue

        if character in {'"', "'"}:
            quote = character
            characters.append(character)
            index += 1
            continue
        if character == ",":
            lookahead = index + 1
            while lookahead < len(source) and source[lookahead].isspace():
                lookahead += 1
            if lookahead < len(source) and source[lookahead] in {"}", "]"}:
                characters.append(" ")
                index += 1
                continue

        characters.append(character)
        index += 1
    return "".join(characters)


def _simple_alias_prefix(pattern: str) -> str | None:
    normalized = pattern.replace("\\", "/")
    if normalized.count("*") != 1 or not normalized.endswith("*"):
        return None
    prefix = normalized[:-1]
    return prefix or None


def _target_prefixes(config_dir: str, base_url: str, target_patterns: object) -> tuple[str, ...]:
    if not isinstance(target_patterns, list) or len(target_patterns) != 1:
        return ()
    target_pattern = target_patterns[0]
    if not isinstance(target_pattern, str):
        return ()
    target_prefix = _simple_target_prefix(config_dir, base_url, target_pattern)
    return () if target_prefix is None else (target_prefix,)


def _simple_target_prefix(config_dir: str, base_url: str, pattern: str) -> str | None:
    normalized = pattern.replace("\\", "/")
    if normalized.count("*") != 1 or not normalized.endswith("*"):
        return None
    return _normalize_repo_path(config_dir, base_url, normalized[:-1])


def _normalize_repo_path(*parts: str) -> str | None:
    normalized_parts: list[str] = []
    for raw_part in parts:
        if not raw_part or raw_part == ".":
            continue
        posix_part = raw_part.replace("\\", "/")
        path = PurePosixPath(posix_part)
        if path.is_absolute():
            return None
        for part in path.parts:
            if part in {"", "."}:
                continue
            if part == "..":
                if not normalized_parts:
                    return None
                normalized_parts.pop()
                continue
            normalized_parts.append(part)
    return "/".join(normalized_parts)


def _join_repo_path(prefix: str, suffix: str) -> str:
    normalized_suffix = suffix.strip("/")
    if not prefix:
        return normalized_suffix
    if not normalized_suffix:
        return prefix
    return f"{prefix}/{normalized_suffix}"


def _module_path_candidates(base_path: str, javascript_paths: frozenset[str]) -> set[str]:
    candidates: set[str] = set()
    suffix = PurePosixPath(base_path).suffix.lower()
    if suffix in JAVASCRIPT_SOURCE_SUFFIXES:
        if base_path in javascript_paths:
            candidates.add(base_path)
        return candidates

    for extension in JAVASCRIPT_RESOLUTION_SUFFIXES:
        file_candidate = f"{base_path}{extension}"
        if file_candidate in javascript_paths:
            candidates.add(file_candidate)
        index_candidate = f"{base_path}/index{extension}"
        if index_candidate in javascript_paths:
            candidates.add(index_candidate)
    return candidates


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


def _brace_delta_outside_strings(line: str) -> int:
    delta = 0
    quote: str | None = None
    escaped = False
    for character in line:
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {"'", '"', "`"}:
            quote = character
        elif character == "{":
            delta += 1
        elif character == "}":
            delta -= 1
    return delta


def _has_opening_brace_outside_strings(line: str) -> bool:
    quote: str | None = None
    escaped = False
    for character in line:
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {"'", '"', "`"}:
            quote = character
        elif character == "{":
            return True
    return False


def _statement_ends_outside_strings(line: str) -> bool:
    quote: str | None = None
    escaped = False
    for character in line:
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {"'", '"', "`"}:
            quote = character
        elif character == ";":
            return True
    return False


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
