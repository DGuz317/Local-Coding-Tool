from __future__ import annotations

import json
import sqlite3
from textwrap import dedent

from repolens.indexer import index_repository
from repolens.query import GraphQueryService


def test_related_test_edges_store_confidence_evidence_strategy_and_normalize_duplicates(tmp_path):
    _write_text(
        tmp_path / "src" / "auth" / "login.ts",
        "export function validateLogin() { return true; }\n",
    )
    _write_text(
        tmp_path / "src" / "auth" / "profile.ts",
        "export function profile() { return true; }\n",
    )
    _write_text(
        tmp_path / "tests" / "login.test.ts",
        dedent(
            """
            import { validateLogin } from "../src/auth/login";

            test("validates login", () => {
              expect(validateLogin()).toBe(true);
            });
            """
        ).lstrip(),
    )
    _write_text(
        tmp_path / "tests" / "profile.test.ts",
        "test('profile', () => expect(true).toBe(true));\n",
    )
    _write_text(
        tmp_path / "tests" / "billing.test.ts",
        "test('billing', () => expect(true).toBe(true));\n",
    )

    index_repository(tmp_path)
    service = GraphQueryService(tmp_path)

    edges = _related_test_edges(tmp_path)

    login_edge = edges[("src/auth/login.ts", "tests/login.test.ts")]
    assert login_edge["confidence"] == "high"
    assert login_edge["resolution_strategy"] == "direct_import+path_name_similarity"
    assert [item["kind"] for item in login_edge["evidence"]] == [
        "related_test_direct_import",
        "related_test_path_name_similarity",
    ]
    assert login_edge["evidence"][0]["line"] == 1
    assert login_edge["evidence"][1]["matched_tokens"] == ["login"]

    profile_edge = edges[("src/auth/profile.ts", "tests/profile.test.ts")]
    assert profile_edge["confidence"] == "medium"
    assert profile_edge["resolution_strategy"] == "path_name_similarity"
    assert profile_edge["evidence"] == [
        {
            "kind": "related_test_path_name_similarity",
            "matched_tokens": ["profile"],
            "source_path": "src/auth/profile.ts",
            "test_path": "tests/profile.test.ts",
        }
    ]

    assert ("src/auth/login.ts", "tests/billing.test.ts") not in edges

    impact = service.impact_analysis("src/auth/login.ts")
    assert impact["data"]["likely_tests"][0]["path"] == "tests/login.test.ts"
    assert impact["data"]["likely_tests"][0]["confidence"] == "high"
    assert impact["data"]["likely_tests"][0]["resolution_strategy"] == (
        "direct_import+path_name_similarity"
    )


def _related_test_edges(root) -> dict[tuple[str, str], dict]:
    with sqlite3.connect(root / ".repolens" / "graph.sqlite") as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT source.path AS source_path,
                   target.path AS test_path,
                   edge.confidence,
                   edge.resolution_strategy,
                   edge.evidence_json
            FROM edges AS edge
            JOIN nodes AS source ON source.id = edge.source_id
            JOIN nodes AS target ON target.id = edge.target_id
            WHERE edge.kind = 'RELATED_TEST'
            ORDER BY source.path, target.path
            """
        ).fetchall()
    return {
        (str(row["source_path"]), str(row["test_path"])): {
            "confidence": row["confidence"],
            "evidence": json.loads(row["evidence_json"]),
            "resolution_strategy": row["resolution_strategy"],
        }
        for row in rows
    }


def _write_text(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
