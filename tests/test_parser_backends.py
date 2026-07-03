from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import repolens.parser_backends as parser_backends
from repolens.context_pack import get_task_context
from repolens.graph import inspect_graph_artifacts
from repolens.indexer import index_repository
from repolens.javascript_index import (
    JavaScriptParserProvenance,
    TreeSitterJavaScriptAvailability,
    TreeSitterJavaScriptSupport,
)
from repolens.parser_backends import (
    PARSER_BACKEND_CONTRACT,
    ParserBackend,
    ParserIndexes,
    StableParserBackend,
)
from repolens.scanner import ScannedFile


class FailingExperimentalBackend:
    name = "experimental-fixture"
    experimental = True

    def extract(self, root: Path, files: tuple[ScannedFile, ...]) -> ParserIndexes:
        raise RuntimeError("optional parser backend unavailable")


class ExperimentalFactsBackend:
    name = "experimental-facts-fixture"
    experimental = True

    def extract(self, root: Path, files: tuple[ScannedFile, ...]) -> ParserIndexes:
        stable = StableParserBackend().extract(root, files)
        return ParserIndexes(
            python=stable.python,
            javascript=stable.javascript,
            config=stable.config,
            documentation=stable.documentation,
            parser_status_by_path=stable.parser_status_by_path,
            experimental_facts=(
                {
                    "backend": self.name,
                    "fact": "tree_sitter_candidate_symbol",
                    "path": "app.py",
                },
            ),
        )


def test_parser_backend_contract_documents_stable_hash_boundary():
    assert PARSER_BACKEND_CONTRACT.default_backend == "tree_sitter_js_ts"
    assert PARSER_BACKEND_CONTRACT.stable_fact_groups == (
        "python",
        "javascript",
        "config",
        "documentation",
        "parser_status_by_path",
    )
    assert "excluded from stable Canonical Graph Hash" in (
        PARSER_BACKEND_CONTRACT.experimental_fact_policy
    )


def test_default_parser_backend_falls_back_to_stable_outputs_with_warning(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.ts").write_text('import dep from "pkg";\n', encoding="utf-8")

    monkeypatch.setattr(
        parser_backends,
        "tree_sitter_javascript_availability",
        lambda: TreeSitterJavaScriptAvailability(
            None,
            "parser_backend:tree_sitter_js_ts_unavailable:test",
        ),
    )

    default_result = index_repository(tmp_path)
    default_graph = json.loads((tmp_path / default_result.graph_exports[0]).read_text())
    default_hash = _canonical_graph_hash(tmp_path)

    stable_result = index_repository(tmp_path, parser_backend="stable")
    stable_graph = json.loads((tmp_path / stable_result.graph_exports[0]).read_text())
    stable_hash = _canonical_graph_hash(tmp_path)

    assert default_graph["javascript"] == stable_graph["javascript"]
    assert default_hash == stable_hash
    assert default_graph["parser_backend"]["warnings"] == [
        "parser_backend:tree_sitter_js_ts_unavailable:test"
    ]

    index_repository(tmp_path)
    status = inspect_graph_artifacts(tmp_path)
    assert "parser_backend:tree_sitter_js_ts_unavailable:test" in status.warnings


def test_default_parser_backend_uses_tree_sitter_when_available(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.ts").write_text(
        'import dep from "pkg";\nexport function run() { return dep; }\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        parser_backends,
        "tree_sitter_javascript_availability",
        lambda: TreeSitterJavaScriptAvailability(_fake_tree_sitter_support()),
    )

    result = index_repository(tmp_path)
    graph = json.loads((tmp_path / result.graph_exports[0]).read_text())

    assert graph["javascript"]["imports"][0]["specifier"] == "pkg"
    assert graph["javascript"]["symbols"][0]["name"] == "run"
    assert graph["parser_backend"]["warnings"] == []
    provenance = graph["parser_backend"]["provenance"]
    assert provenance["javascript"] == {
        "backend_name": "tree_sitter_js_ts",
        "javascript_grammar_version": "grammar-js-test",
        "parser_package_version": "parser-test",
        "promoted_fact_schema_version": "javascript-promoted-facts-v1",
        "typescript_grammar_version": "grammar-ts-test",
    }


def test_experimental_facts_are_excluded_from_stable_hash_and_context_identity(tmp_path):
    (tmp_path / "app.py").write_text(
        "def run():\n    return 1\n",
        encoding="utf-8",
    )

    index_repository(tmp_path)
    stable_hash = _canonical_graph_hash(tmp_path)
    stable_pack = get_task_context(tmp_path, "change app run")

    index_repository(tmp_path, parser_backend=ExperimentalFactsBackend())
    experimental_hash = _canonical_graph_hash(tmp_path)
    experimental_pack = get_task_context(tmp_path, "change app run")

    assert experimental_hash == stable_hash
    assert experimental_pack["data"]["context_pack_id"] == stable_pack["data"]["context_pack_id"]
    assert "experimental-facts-fixture" not in (tmp_path / ".repolens" / "graph.json").read_text(
        encoding="utf-8"
    )


def test_experimental_parser_backend_failure_is_nonfatal(tmp_path):
    (tmp_path / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")

    index_repository(tmp_path, parser_backend=FailingExperimentalBackend())

    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        modules = list(
            connection.execute(
                """
                SELECT module_name, parser_status
                FROM python_modules
                ORDER BY module_name
                """
            )
        )

    assert modules == [("app", "parsed")]


def _canonical_graph_hash(root: Path) -> str:
    with sqlite3.connect(root / ".repolens" / "graph.sqlite") as connection:
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'canonical_graph_hash'"
        ).fetchone()
    assert row is not None
    return str(row[0])


def _fake_tree_sitter_support(*, has_error: bool = False) -> TreeSitterJavaScriptSupport:
    class FakeParser:
        def __init__(self, language):
            self.language = language

        def parse(self, source: bytes):
            return SimpleNamespace(root_node=SimpleNamespace(has_error=has_error))

    return TreeSitterJavaScriptSupport(
        parser_class=FakeParser,
        language_class=object,
        javascript_language="javascript",
        typescript_language="typescript",
        tsx_language="tsx",
        provenance=JavaScriptParserProvenance(
            backend_name="tree_sitter_js_ts",
            parser_package_version="parser-test",
            javascript_grammar_version="grammar-js-test",
            typescript_grammar_version="grammar-ts-test",
            promoted_fact_schema_version="javascript-promoted-facts-v1",
        ),
    )


def _accept_backend(backend: ParserBackend) -> ParserBackend:
    return backend


_accept_backend(FailingExperimentalBackend())
_accept_backend(ExperimentalFactsBackend())
