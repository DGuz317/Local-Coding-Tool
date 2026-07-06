"""Parser backend interface for stable and experimental extraction paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TypeAlias

from repolens.config_index import ConfigIndex, extract_config_index
from repolens.documentation_index import DocumentationIndex, extract_documentation_index
from repolens.javascript_index import (
    JavaScriptIndex,
    bounded_javascript_parser_provenance,
    extract_javascript_index,
    extract_javascript_index_with_tree_sitter,
    tree_sitter_javascript_availability,
)
from repolens.python_index import PythonIndex, extract_python_index
from repolens.scanner import ScannedFile


@dataclass(frozen=True)
class ParserBackendContract:
    """Hash and identity contract shared by parser backend implementations."""

    stable_fact_groups: tuple[str, ...]
    experimental_fact_policy: str
    default_backend: str


PARSER_BACKEND_CONTRACT = ParserBackendContract(
    stable_fact_groups=("python", "javascript", "config", "documentation", "parser_status_by_path"),
    experimental_fact_policy=(
        "experimental_facts are parser research output only; they are excluded from stable "
        "Canonical Graph Hash and default Context Pack identity until a contract change "
        "promotes them into stable_fact_groups."
    ),
    default_backend="tree_sitter_js_ts",
)


@dataclass(frozen=True)
class ParserIndexes:
    """All graph fact indexes produced by one parser backend run."""

    python: PythonIndex
    javascript: JavaScriptIndex
    config: ConfigIndex
    documentation: DocumentationIndex
    parser_status_by_path: dict[str, str]
    experimental_facts: tuple[dict[str, Any], ...] = ()
    parser_backend_warnings: tuple[str, ...] = ()
    extractor_provenance: dict[str, Any] | None = None

    def stable_contract_projection(self) -> "ParserIndexes":
        """Return only facts covered by the stable graph/hash contract."""
        return ParserIndexes(
            python=self.python,
            javascript=self.javascript,
            config=self.config,
            documentation=self.documentation,
            parser_status_by_path=dict(self.parser_status_by_path),
            parser_backend_warnings=self.parser_backend_warnings,
            extractor_provenance=self.extractor_provenance,
        )


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
            extractor_provenance={
                "javascript": bounded_javascript_parser_provenance().to_metadata()
            },
        )


class TreeSitterJavaScriptParserBackend:
    """Default backend that uses Tree-sitter JS/TS when optional support is present."""

    name = "tree_sitter_js_ts"
    experimental = False

    def extract(self, root: Path, files: tuple[ScannedFile, ...]) -> ParserIndexes:
        availability = tree_sitter_javascript_availability()
        if availability.support is None:
            stable = StableParserBackend().extract(root, files)
            return ParserIndexes(
                python=stable.python,
                javascript=stable.javascript,
                config=stable.config,
                documentation=stable.documentation,
                parser_status_by_path=stable.parser_status_by_path,
                parser_backend_warnings=(availability.warning,) if availability.warning else (),
                extractor_provenance=stable.extractor_provenance,
            )

        python_index = extract_python_index(root, files)
        javascript_index = extract_javascript_index_with_tree_sitter(
            root, files, availability.support
        )
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
            extractor_provenance={"javascript": availability.support.provenance.to_metadata()},
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


def resolve_parser_backend(parser_backend: ParserBackendOption = "default") -> ParserBackend:
    """Return a concrete backend for an explicit parser backend option."""
    if isinstance(parser_backend, str):
        if parser_backend == "stable":
            return StableParserBackend()
        if parser_backend in {"default", "tree_sitter_js_ts"}:
            return TreeSitterJavaScriptParserBackend()
        if parser_backend == "experimental":
            return ExperimentalParserBackend()
        raise ValueError("unsupported_parser_backend")
    return parser_backend


def extract_with_parser_backend(
    root: Path,
    files: tuple[ScannedFile, ...],
    parser_backend: ParserBackendOption = "default",
) -> ParserIndexes:
    """Extract indexes, falling back only for explicit experimental backend failures."""
    backend = resolve_parser_backend(parser_backend)
    try:
        return backend.extract(root, files).stable_contract_projection()
    except Exception:
        if backend.experimental:
            return StableParserBackend().extract(root, files)
        raise


def default_parser_backend_provenance() -> dict[str, Any]:
    """Return current default parser provenance without reading repository files."""
    availability = tree_sitter_javascript_availability()
    if availability.support is None:
        return {"javascript": bounded_javascript_parser_provenance().to_metadata()}
    return {"javascript": availability.support.provenance.to_metadata()}
