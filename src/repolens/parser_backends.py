"""Parser backend interface for stable and experimental extraction paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeAlias

from repolens.config_index import ConfigIndex, extract_config_index
from repolens.documentation_index import DocumentationIndex, extract_documentation_index
from repolens.javascript_index import JavaScriptIndex, extract_javascript_index
from repolens.python_index import PythonIndex, extract_python_index
from repolens.scanner import ScannedFile


@dataclass(frozen=True)
class ParserIndexes:
    """All graph fact indexes produced by one parser backend run."""

    python: PythonIndex
    javascript: JavaScriptIndex
    config: ConfigIndex
    documentation: DocumentationIndex
    parser_status_by_path: dict[str, str]


class ParserBackend(Protocol):
    """A parser backend that produces the stable RepoLens graph contract."""

    name: str
    experimental: bool

    def extract(self, root: Path, files: tuple[ScannedFile, ...]) -> ParserIndexes:
        """Extract graph indexes from scanner-approved files only."""


ParserBackendOption: TypeAlias = str | ParserBackend


class StableParserBackend:
    """Default parser backend based on RepoLens' stable built-in extractors."""

    name = "stable"
    experimental = False

    def extract(self, root: Path, files: tuple[ScannedFile, ...]) -> ParserIndexes:
        python_index = extract_python_index(root, files)
        javascript_index = extract_javascript_index(root, files)
        config_index = extract_config_index(root, files)
        documentation_index = extract_documentation_index(root, files)
        parser_status_by_path = {
            **python_index.parser_status_by_path,
            **javascript_index.parser_status_by_path,
            **config_index.parser_status_by_path,
            **documentation_index.parser_status_by_path,
        }
        return ParserIndexes(
            python=python_index,
            javascript=javascript_index,
            config=config_index,
            documentation=documentation_index,
            parser_status_by_path=parser_status_by_path,
        )


class ExperimentalParserBackend:
    """Optional parser backend experiment that must not destabilize indexing."""

    name = "experimental"
    experimental = True

    def extract(self, root: Path, files: tuple[ScannedFile, ...]) -> ParserIndexes:
        try:
            __import__("tree_sitter")
        except ImportError:
            return StableParserBackend().extract(root, files)

        # Tree-sitter grammars are intentionally optional for v0.2; until a grammar-backed
        # implementation is available, the experiment preserves the stable graph contract.
        return StableParserBackend().extract(root, files)


def resolve_parser_backend(parser_backend: ParserBackendOption = "stable") -> ParserBackend:
    """Return a concrete backend for an explicit parser backend option."""
    if isinstance(parser_backend, str):
        if parser_backend == "stable":
            return StableParserBackend()
        if parser_backend == "experimental":
            return ExperimentalParserBackend()
        raise ValueError("unsupported_parser_backend")
    return parser_backend


def extract_with_parser_backend(
    root: Path,
    files: tuple[ScannedFile, ...],
    parser_backend: ParserBackendOption = "stable",
) -> ParserIndexes:
    """Extract indexes, falling back only for explicit experimental backend failures."""
    backend = resolve_parser_backend(parser_backend)
    try:
        return backend.extract(root, files)
    except Exception:
        if backend.experimental:
            return StableParserBackend().extract(root, files)
        raise
