"""Python structure extraction for RepoLens graph facts."""

from __future__ import annotations

import ast
import builtins
import hashlib
import io
import re
import sys
import tokenize
import tomllib
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from repolens.scanner import ScannedFile

PYTHON_EXTRACTOR_VERSION = "issue-38-python-local-import-resolution-v1"

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
TAG_PATTERN = re.compile(
    rf"^({'|'.join(sorted(TAG_NAMES))})\b(?:\s*[:\-]\s*|\s+)?(.*)$",
    re.IGNORECASE,
)
STDLIB_MODULE_NAMES = frozenset(sys.stdlib_module_names) | frozenset(sys.builtin_module_names)
BUILTIN_NAMES = frozenset(dir(builtins))


@dataclass(frozen=True)
class PythonModuleFact:
    """A scanner-approved Python file represented as a Python module."""

    path: str
    node_id: str
    module_name: str
    package_root: str | None
    parser_status: str
    docstring_summary: str | None


@dataclass(frozen=True)
class PythonSymbolFact:
    """A Python class, function, or method discovered from valid AST."""

    id: str
    path: str
    module_node_id: str
    parent_id: str | None
    kind: str
    name: str
    qualified_name: str
    start_line: int
    end_line: int
    docstring_summary: str | None
    decorators: tuple[str, ...]
    bases: tuple[str, ...]


@dataclass(frozen=True)
class PythonImportFact:
    """A Python import statement classified by package root."""

    id: str
    path: str
    module_node_id: str
    kind: str
    module: str
    imported_name: str | None
    alias: str | None
    root_name: str
    classification: str
    level: int
    line: int


@dataclass(frozen=True)
class PythonPackageFact:
    """An observed or inferred Python package/import root."""

    id: str
    name: str
    classification: str
    inferred: bool


@dataclass(frozen=True)
class PythonTaggedCommentFact:
    """A tagged Python comment extracted without mirroring full source."""

    id: str
    path: str
    module_node_id: str
    attached_node_id: str
    tag: str
    text: str
    line: int


@dataclass(frozen=True)
class PythonParseErrorFact:
    """A nonfatal Python syntax/read error fact for one file."""

    id: str
    path: str
    module_node_id: str
    message: str
    line: int | None
    column: int | None


@dataclass(frozen=True)
class PythonCallFact:
    """A conservative same-module direct call between Python symbols."""

    id: str
    path: str
    caller_id: str
    callee_id: str
    callee_name: str
    line: int
    confidence: str


@dataclass(frozen=True)
class PythonIndex:
    """All Python facts extracted for one scan result."""

    modules: tuple[PythonModuleFact, ...]
    symbols: tuple[PythonSymbolFact, ...]
    imports: tuple[PythonImportFact, ...]
    packages: tuple[PythonPackageFact, ...]
    tagged_comments: tuple[PythonTaggedCommentFact, ...]
    parse_errors: tuple[PythonParseErrorFact, ...]
    calls: tuple[PythonCallFact, ...]

    @property
    def parser_status_by_path(self) -> dict[str, str]:
        return {module.path: module.parser_status for module in self.modules}


@dataclass(frozen=True)
class _SymbolExtraction:
    facts: tuple[PythonSymbolFact, ...]
    node_by_symbol_id: dict[str, ast.AST]


def extract_python_index(root: Path, files: tuple[ScannedFile, ...]) -> PythonIndex:
    """Extract deterministic Python facts from scanner-approved ``.py`` files only."""
    python_files = tuple(
        file for file in sorted(files, key=lambda item: item.path) if _is_python(file)
    )
    local_roots = _infer_local_import_roots(root, files, python_files)

    modules: list[PythonModuleFact] = []
    symbols: list[PythonSymbolFact] = []
    imports: list[PythonImportFact] = []
    tagged_comments: list[PythonTaggedCommentFact] = []
    parse_errors: list[PythonParseErrorFact] = []
    calls: list[PythonCallFact] = []
    observed_packages: dict[tuple[str, str], bool] = {}

    for scanned_file in python_files:
        path = scanned_file.path
        module_node_id = python_module_node_id(path)
        module_name = _module_name(path)
        package_root = _package_root(path)

        try:
            source = _read_scanner_approved_text(root, path)
        except OSError as exc:
            module = PythonModuleFact(
                path=path,
                node_id=module_node_id,
                module_name=module_name,
                package_root=package_root,
                parser_status="parse_error",
                docstring_summary=None,
            )
            modules.append(module)
            parse_errors.append(
                PythonParseErrorFact(
                    id=python_parse_error_node_id(path),
                    path=path,
                    module_node_id=module_node_id,
                    message=f"read_error: {exc.__class__.__name__}",
                    line=None,
                    column=None,
                )
            )
            continue

        comment_candidates = _extract_tagged_comment_candidates(path, module_node_id, source)
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError as exc:
            modules.append(
                PythonModuleFact(
                    path=path,
                    node_id=module_node_id,
                    module_name=module_name,
                    package_root=package_root,
                    parser_status="parse_error",
                    docstring_summary=None,
                )
            )
            parse_errors.append(
                PythonParseErrorFact(
                    id=python_parse_error_node_id(path),
                    path=path,
                    module_node_id=module_node_id,
                    message=exc.msg,
                    line=exc.lineno,
                    column=exc.offset,
                )
            )
            tagged_comments.extend(
                _finalize_tagged_comments(comment_candidates, module_node_id, ())
            )
            continue

        modules.append(
            PythonModuleFact(
                path=path,
                node_id=module_node_id,
                module_name=module_name,
                package_root=package_root,
                parser_status="parsed",
                docstring_summary=_first_sentence(ast.get_docstring(tree)),
            )
        )

        symbol_extraction = _extract_symbols(path, module_node_id, tree)
        symbols.extend(symbol_extraction.facts)
        imports_for_file = _extract_imports(path, module_node_id, tree, local_roots)
        imports.extend(imports_for_file)
        calls.extend(_extract_calls(path, symbol_extraction))
        tagged_comments.extend(
            _finalize_tagged_comments(comment_candidates, module_node_id, symbol_extraction.facts)
        )

        for import_fact in imports_for_file:
            if import_fact.root_name:
                observed_packages[(import_fact.classification, import_fact.root_name)] = False

    for local_root in local_roots:
        observed_packages.setdefault(("local", local_root), True)

    packages = tuple(
        PythonPackageFact(
            id=python_package_node_id(name, classification),
            name=name,
            classification=classification,
            inferred=inferred,
        )
        for (classification, name), inferred in sorted(observed_packages.items())
    )
    return PythonIndex(
        modules=tuple(sorted(modules, key=lambda fact: fact.path)),
        symbols=tuple(sorted(symbols, key=lambda fact: (fact.path, fact.qualified_name, fact.id))),
        imports=tuple(sorted(imports, key=lambda fact: (fact.path, fact.line, fact.id))),
        packages=packages,
        tagged_comments=tuple(
            sorted(tagged_comments, key=lambda fact: (fact.path, fact.line, fact.id))
        ),
        parse_errors=tuple(sorted(parse_errors, key=lambda fact: fact.path)),
        calls=tuple(sorted(calls, key=lambda fact: (fact.path, fact.line, fact.id))),
    )


def python_module_node_id(path: str) -> str:
    return f"python_module:{path}"


def python_package_node_id(name: str, classification: str) -> str:
    return f"python_package:{classification}:{name}"


def python_parse_error_node_id(path: str) -> str:
    return f"python_parse_error:{path}"


def _is_python(file: ScannedFile) -> bool:
    return PurePosixPath(file.path).suffix == ".py"


def _read_scanner_approved_text(root: Path, path: str) -> str:
    resolved_root = root.resolve(strict=True)
    source_path = resolved_root / PurePosixPath(path)
    source_path.resolve(strict=False).relative_to(resolved_root)
    return source_path.read_text(encoding="utf-8", errors="replace")


def _infer_local_import_roots(
    root: Path,
    files: tuple[ScannedFile, ...],
    python_files: tuple[ScannedFile, ...],
) -> tuple[str, ...]:
    roots: set[str] = set()
    for scanned_file in python_files:
        path = PurePosixPath(scanned_file.path)
        parts = path.parts
        if not parts:
            continue

        if parts[-1] == "__init__.py" and len(parts) >= 2:
            roots.add(parts[1] if parts[0] == "src" and len(parts) >= 3 else parts[0])
            continue

        if len(parts) == 1:
            roots.add(path.stem)
        elif parts[0] == "src" and len(parts) >= 2:
            roots.add(PurePosixPath(*parts[1:]).parts[0].removesuffix(".py"))
        else:
            roots.add(parts[0])

    roots.discard("__init__")
    roots.update(_pyproject_local_roots(root, files, roots))
    return tuple(sorted(root_name for root_name in roots if _is_identifier_root(root_name)))


def _pyproject_local_roots(
    root: Path,
    files: tuple[ScannedFile, ...],
    existing_roots: set[str],
) -> tuple[str, ...]:
    if not any(file.path == "pyproject.toml" for file in files):
        return ()
    try:
        data = tomllib.loads(_read_scanner_approved_text(root, "pyproject.toml"))
    except (OSError, tomllib.TOMLDecodeError):
        return ()

    project = data.get("project")
    if not isinstance(project, dict):
        return ()
    name = project.get("name")
    if not isinstance(name, str):
        return ()

    candidates = {name, name.replace("-", "_")}
    return tuple(sorted(candidate for candidate in candidates if candidate in existing_roots))


def _is_identifier_root(value: str) -> bool:
    return value.isidentifier()


def _module_name(path: str) -> str:
    parts = list(PurePosixPath(path).with_suffix("").parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else "__init__"


def _package_root(path: str) -> str | None:
    module_name = _module_name(path)
    if module_name == "__init__":
        return None
    return module_name.split(".", maxsplit=1)[0]


def _extract_symbols(path: str, module_node_id: str, tree: ast.Module) -> _SymbolExtraction:
    facts: list[PythonSymbolFact] = []
    node_by_symbol_id: dict[str, ast.AST] = {}
    id_counts: Counter[str] = Counter()

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fact = _symbol_fact(path, module_node_id, None, node, id_counts)
            facts.append(fact)
            node_by_symbol_id[fact.id] = node
        elif isinstance(node, ast.ClassDef):
            class_fact = _symbol_fact(path, module_node_id, None, node, id_counts)
            facts.append(class_fact)
            node_by_symbol_id[class_fact.id] = node
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_fact = _symbol_fact(
                        path,
                        module_node_id,
                        class_fact,
                        child,
                        id_counts,
                    )
                    facts.append(method_fact)
                    node_by_symbol_id[method_fact.id] = child

    return _SymbolExtraction(facts=tuple(facts), node_by_symbol_id=node_by_symbol_id)


def _symbol_fact(
    path: str,
    module_node_id: str,
    parent: PythonSymbolFact | None,
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
    id_counts: Counter[str],
) -> PythonSymbolFact:
    if isinstance(node, ast.ClassDef):
        kind = "class"
    elif parent is not None and isinstance(node, ast.AsyncFunctionDef):
        kind = "async_method"
    elif parent is not None:
        kind = "method"
    elif isinstance(node, ast.AsyncFunctionDef):
        kind = "async_function"
    else:
        kind = "function"

    qualified_name = node.name if parent is None else f"{parent.qualified_name}.{node.name}"
    symbol_id = _symbol_node_id(path, qualified_name, id_counts)
    bases = node.bases if isinstance(node, ast.ClassDef) else ()
    return PythonSymbolFact(
        id=symbol_id,
        path=path,
        module_node_id=module_node_id,
        parent_id=None if parent is None else parent.id,
        kind=kind,
        name=node.name,
        qualified_name=qualified_name,
        start_line=node.lineno,
        end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
        docstring_summary=_first_sentence(ast.get_docstring(node)),
        decorators=tuple(
            decorator_name
            for decorator_name in (_expression_name(item) for item in node.decorator_list)
            if decorator_name is not None
        ),
        bases=tuple(
            base_name
            for base_name in (_expression_name(item) for item in bases)
            if base_name is not None
        ),
    )


def _symbol_node_id(path: str, qualified_name: str, id_counts: Counter[str]) -> str:
    key = f"{path}:{qualified_name}"
    id_counts[key] += 1
    suffix = "" if id_counts[key] == 1 else f"#{id_counts[key]}"
    return f"python_symbol:{path}:{qualified_name}{suffix}"


def _expression_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _expression_name(node.value)
        return None if base is None else f"{base}.{node.attr}"
    if isinstance(node, ast.Call):
        return _expression_name(node.func)
    if isinstance(node, ast.Subscript):
        return _expression_name(node.value)
    return None


def _extract_imports(
    path: str,
    module_node_id: str,
    tree: ast.Module,
    local_roots: tuple[str, ...],
) -> tuple[PythonImportFact, ...]:
    collector = _ImportCollector(path, module_node_id, local_roots)
    collector.visit(tree)
    return tuple(collector.facts)


class _ImportCollector(ast.NodeVisitor):
    def __init__(self, path: str, module_node_id: str, local_roots: tuple[str, ...]) -> None:
        self.path = path
        self.module_node_id = module_node_id
        self.local_roots = frozenset(local_roots)
        self.facts: list[PythonImportFact] = []
        self.id_counts: Counter[str] = Counter()

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            root_name = alias.name.split(".", maxsplit=1)[0]
            self.facts.append(
                PythonImportFact(
                    id=self._import_id("import", alias.name, None, alias.asname),
                    path=self.path,
                    module_node_id=self.module_node_id,
                    kind="import",
                    module=alias.name,
                    imported_name=None,
                    alias=alias.asname,
                    root_name=root_name,
                    classification=_classify_import(root_name, 0, self.local_roots),
                    level=0,
                    line=node.lineno,
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        module = node.module or ""
        root_name = _from_import_root(module, node.names, node.level)
        classification = _classify_import(root_name, node.level, self.local_roots)
        for alias in node.names:
            self.facts.append(
                PythonImportFact(
                    id=self._import_id("from", module, alias.name, alias.asname),
                    path=self.path,
                    module_node_id=self.module_node_id,
                    kind="from",
                    module=module,
                    imported_name=alias.name,
                    alias=alias.asname,
                    root_name=root_name,
                    classification=classification,
                    level=node.level,
                    line=node.lineno,
                )
            )

    def _import_id(
        self,
        kind: str,
        module: str,
        imported_name: str | None,
        alias: str | None,
    ) -> str:
        key = "|".join((self.path, kind, module, imported_name or "", alias or ""))
        self.id_counts[key] += 1
        suffix = "" if self.id_counts[key] == 1 else f"#{self.id_counts[key]}"
        return f"python_import:{self.path}:{_short_hash(key)}{suffix}"


def _from_import_root(module: str, names: list[ast.alias], level: int) -> str:
    if module:
        return module.split(".", maxsplit=1)[0]
    if level > 0 and names:
        return names[0].name.split(".", maxsplit=1)[0]
    return ""


def _classify_import(root_name: str, level: int, local_roots: frozenset[str]) -> str:
    if level > 0 or root_name in local_roots:
        return "local"
    if root_name in STDLIB_MODULE_NAMES or root_name in BUILTIN_NAMES:
        return "stdlib"
    return "third_party"


def _extract_calls(path: str, symbol_extraction: _SymbolExtraction) -> tuple[PythonCallFact, ...]:
    module_symbols_by_name: dict[str, list[PythonSymbolFact]] = defaultdict(list)
    for symbol in symbol_extraction.facts:
        if symbol.parent_id is None and symbol.kind in {"async_function", "class", "function"}:
            module_symbols_by_name[symbol.name].append(symbol)

    unique_targets = {
        name: symbols[0] for name, symbols in module_symbols_by_name.items() if len(symbols) == 1
    }
    calls: list[PythonCallFact] = []
    id_counts: Counter[str] = Counter()
    callable_kinds = {"async_function", "async_method", "function", "method"}

    for caller in symbol_extraction.facts:
        if caller.kind not in callable_kinds:
            continue
        node = symbol_extraction.node_by_symbol_id[caller.id]
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        collector = _DirectCallCollector()
        for statement in node.body:
            collector.visit(statement)
        for call_name, line in collector.calls:
            callee = unique_targets.get(call_name)
            if callee is None:
                continue
            key = "|".join((path, caller.id, callee.id, call_name))
            id_counts[key] += 1
            suffix = "" if id_counts[key] == 1 else f"#{id_counts[key]}"
            calls.append(
                PythonCallFact(
                    id=f"python_call:{path}:{_short_hash(key)}{suffix}",
                    path=path,
                    caller_id=caller.id,
                    callee_id=callee.id,
                    callee_name=call_name,
                    line=line,
                    confidence="high",
                )
            )
    return tuple(calls)


class _DirectCallCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if isinstance(node.func, ast.Name):
            self.calls.append((node.func.id, node.lineno))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        return


@dataclass(frozen=True)
class _CommentCandidate:
    path: str
    module_node_id: str
    tag: str
    text: str
    line: int


def _extract_tagged_comment_candidates(
    path: str,
    module_node_id: str,
    source: str,
) -> tuple[_CommentCandidate, ...]:
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        comments = (
            (token.start[0], token.string.lstrip("#").strip())
            for token in tokens
            if token.type == tokenize.COMMENT
        )
        return tuple(
            candidate
            for line, text in comments
            if (candidate := _comment_candidate(path, module_node_id, line, text)) is not None
        )
    except tokenize.TokenError:
        return tuple(
            candidate
            for line, text in _fallback_comment_lines(source)
            if (candidate := _comment_candidate(path, module_node_id, line, text)) is not None
        )


def _fallback_comment_lines(source: str) -> tuple[tuple[int, str], ...]:
    comments: list[tuple[int, str]] = []
    for line_number, raw_line in enumerate(source.splitlines(), start=1):
        stripped = raw_line.lstrip()
        if stripped.startswith("#"):
            comments.append((line_number, stripped.lstrip("#").strip()))
    return tuple(comments)


def _comment_candidate(
    path: str,
    module_node_id: str,
    line: int,
    text: str,
) -> _CommentCandidate | None:
    match = TAG_PATTERN.match(text)
    if match is None:
        return None
    return _CommentCandidate(
        path=path,
        module_node_id=module_node_id,
        tag=match.group(1).upper(),
        text=match.group(2).strip(),
        line=line,
    )


def _finalize_tagged_comments(
    candidates: tuple[_CommentCandidate, ...],
    module_node_id: str,
    symbols: tuple[PythonSymbolFact, ...],
) -> tuple[PythonTaggedCommentFact, ...]:
    comments: list[PythonTaggedCommentFact] = []
    id_counts: Counter[str] = Counter()
    for candidate in candidates:
        attached_node_id = _attached_node_id(candidate.line, module_node_id, symbols)
        key = "|".join((candidate.path, candidate.tag, candidate.text, attached_node_id))
        id_counts[key] += 1
        suffix = "" if id_counts[key] == 1 else f"#{id_counts[key]}"
        comments.append(
            PythonTaggedCommentFact(
                id=f"python_comment:{candidate.path}:{_short_hash(key)}{suffix}",
                path=candidate.path,
                module_node_id=candidate.module_node_id,
                attached_node_id=attached_node_id,
                tag=candidate.tag,
                text=candidate.text,
                line=candidate.line,
            )
        )
    return tuple(comments)


def _attached_node_id(
    line: int,
    module_node_id: str,
    symbols: tuple[PythonSymbolFact, ...],
) -> str:
    containing_symbols = [
        symbol for symbol in symbols if symbol.start_line <= line <= symbol.end_line
    ]
    if not containing_symbols:
        return module_node_id
    return sorted(
        containing_symbols,
        key=lambda symbol: (symbol.end_line - symbol.start_line, symbol.id),
    )[0].id


def _first_sentence(docstring: str | None) -> str | None:
    if docstring is None:
        return None
    normalized = " ".join(docstring.strip().split())
    if not normalized:
        return None
    for index, character in enumerate(normalized):
        if character in ".!?":
            return normalized[: index + 1]
    return normalized


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
