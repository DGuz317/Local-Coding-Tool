from __future__ import annotations

import json

from repolens.mcp_envelope import (
    MCP_MAX_EVIDENCE_ITEMS,
    MCP_MAX_WARNING_ITEMS,
    cap_mcp_response,
    mcp_error,
    mcp_from_query_envelope,
    mcp_graph_unavailable_error,
    mcp_success,
    pagination_metadata,
    truncation_metadata,
)


def test_mcp_success_contract_includes_standard_shape_and_bounded_metadata():
    result = mcp_success(
        data={"value": 1},
        evidence=[{"source": str(index)} for index in range(MCP_MAX_EVIDENCE_ITEMS + 2)],
        warnings=[f"warning {index}" for index in range(MCP_MAX_WARNING_ITEMS + 2)],
    )

    assert set(result) == {
        "confidence",
        "data",
        "evidence",
        "freshness",
        "limits",
        "ok",
        "truncation",
        "warnings",
    }
    assert result["ok"] is True
    assert result["data"] == {"value": 1}
    assert result["freshness"] == {"fresh": None, "status": "unknown"}
    assert result["truncation"] == {"fields": [], "truncated": False}
    assert len(result["evidence"]) == MCP_MAX_EVIDENCE_ITEMS + 1
    assert result["evidence"][-1] == {"omitted": 2, "reason": "mcp_metadata_limit"}
    assert len(result["warnings"]) == MCP_MAX_WARNING_ITEMS + 1
    assert result["warnings"][-1] == "2 additional warnings omitted."


def test_mcp_error_contract_includes_structured_error_shape():
    result = mcp_error(
        code="empty_query",
        message="Query must not be empty.",
        details={"recommended_action": "Provide a query."},
        limits={"max_results": 20},
    )

    assert result["ok"] is False
    assert result["data"] == {}
    assert result["error"] == {
        "code": "empty_query",
        "message": "Query must not be empty.",
        "recommended_action": "Provide a query.",
    }
    assert result["limits"]["max_results"] == 20
    assert result["truncation"] == {"fields": [], "truncated": False}


def test_graph_unavailable_error_uses_actionable_standard_shape():
    result = mcp_graph_unavailable_error(
        code="missing_graph_artifacts",
        missing_artifacts=[".repolens/graph.sqlite"],
        recommended_action="repolens index .",
        status="stale",
    )

    assert result["ok"] is False
    assert result["freshness"] == {"fresh": False, "status": "stale"}
    assert result["error"] == {
        "code": "missing_graph_artifacts",
        "message": "RepoLens graph artifacts are missing. Run repolens index for this repository.",
        "missing_artifacts": [".repolens/graph.sqlite"],
        "recommended_action": "repolens index .",
        "status": "stale",
    }


def test_query_envelope_contract_derives_truncation_pagination_and_freshness():
    result = mcp_from_query_envelope(
        {
            "confidence": "medium",
            "data": {"fresh": False, "status": "stale", "truncated": {"items": True}},
            "evidence": [],
            "limits": {"max_results": 1},
            "ok": True,
            "pagination": pagination_metadata(limit=1, offset=0, returned=1, total=2),
            "warnings": ["Graph artifacts may be stale; file metadata changed since indexing."],
        },
        cached=False,
        status_ttl_seconds=2.0,
    )

    assert result["freshness"] == {
        "fresh": False,
        "status": "stale",
        "status_cache": {"cached": False, "ttl_seconds": 2.0},
    }
    assert result["pagination"] == {
        "limit": 1,
        "offset": 0,
        "returned": 1,
        "total": 2,
        "truncated": True,
    }
    assert result["truncation"] == {"fields": ["items", "pagination"], "truncated": True}
    assert result["warnings"] == [
        "Graph artifacts may be stale; file metadata changed since indexing."
    ]


def test_response_cap_omits_data_before_returning_unbounded_payload():
    result = cap_mcp_response(
        {
            "confidence": "high",
            "data": {"text": "x" * 10_000},
            "evidence": [],
            "freshness": {"fresh": None, "status": "unknown"},
            "limits": {},
            "ok": True,
            "truncation": truncation_metadata(),
            "warnings": [],
        },
        max_response_bytes=1_000,
    )

    assert len(json.dumps(result).encode("utf-8")) <= 1_000
    assert result["data"] == {"omitted_due_to_response_cap": True}
    assert result["limits"] == {"response_max_bytes": 1000}
    assert result["truncation"] == {"fields": ["response"], "truncated": True}
