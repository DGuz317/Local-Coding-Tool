from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from repolens.indexer import index_repository
from repolens.parser_backends import ParserBackend, ParserIndexes
from repolens.scanner import ScannedFile


class FailingExperimentalBackend:
    name = "experimental-fixture"
    experimental = True

    def extract(self, root: Path, files: tuple[ScannedFile, ...]) -> ParserIndexes:
        raise RuntimeError("optional parser backend unavailable")


def test_default_parser_backend_matches_stable_outputs(tmp_path):
    (tmp_path / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")

    default_result = index_repository(tmp_path)
    default_graph = json.loads((tmp_path / default_result.graph_exports[0]).read_text())
    default_hash = _canonical_graph_hash(tmp_path)

    stable_result = index_repository(tmp_path, parser_backend="stable")
    stable_graph = json.loads((tmp_path / stable_result.graph_exports[0]).read_text())
    stable_hash = _canonical_graph_hash(tmp_path)

    assert default_graph == stable_graph
    assert default_hash == stable_hash


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


def _accept_backend(backend: ParserBackend) -> ParserBackend:
    return backend


_accept_backend(FailingExperimentalBackend())
