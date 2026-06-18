"""Read-only stdio MCP server for RepoLens."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from repolens.query import GraphQueryService
from repolens.text_search import (
    SEARCH_DEFAULT_MAX_RESULTS,
    SEARCH_MAX_RESULTS_LIMIT,
    SEARCH_PREVIEW_CHARS,
    RepoLensSearchError,
    search_raw_text,
)

MCP_STATUS_TTL_SECONDS = 2.0
MCP_TEXT_SEARCH_MAX_RESULTS = SEARCH_MAX_RESULTS_LIMIT
MCP_TOOL_NAMES = (
    "repo_summary",
    "graph_status",
    "get_graph_report",
    "search_graph",
    "search_text",
    "get_node",
    "get_neighbors",
    "shortest_path",
    "impact_analysis",
    "suggest_reading_order",
    "list_entrypoints",
)


class RepoLensMcpTools:
    """Read-only RepoLens tool facade with MCP-specific envelope metadata."""

    def __init__(
        self, repo_path: Path | str, *, status_ttl_seconds: float = MCP_STATUS_TTL_SECONDS
    ):
        self.repo_path = Path(repo_path)
        self.query = GraphQueryService(repo_path)
        self.status_ttl_seconds = status_ttl_seconds
        self._status_cached_at = 0.0
        self._status_cache: dict[str, Any] | None = None

    def repo_summary(
        self,
        max_entrypoints: int = 10,
        max_commands: int = 10,
        max_modules: int = 20,
        max_important_files: int = 20,
    ) -> dict[str, Any]:
        return self._mcp_envelope(
            self.query.repo_summary(
                max_entrypoints=max_entrypoints,
                max_commands=max_commands,
                max_modules=max_modules,
                max_important_files=max_important_files,
            )
        )

    def graph_status(self, max_changed_files: int = 20) -> dict[str, Any]:
        now = time.monotonic()
        if (
            self._status_cache is not None
            and now - self._status_cached_at < self.status_ttl_seconds
        ):
            return self._mcp_envelope(self._status_cache, cached=True)

        result = self.query.graph_status(max_changed_files=max_changed_files)
        result = self._missing_status_as_error(result)
        self._status_cache = result
        self._status_cached_at = now
        return self._mcp_envelope(result, cached=False)

    def get_graph_report(self, max_chars: int = 20_000) -> dict[str, Any]:
        status = self._missing_status_as_error(self.query.graph_status())
        if status["ok"] is False:
            return self._mcp_envelope(status)
        return self._mcp_envelope(self.query.get_graph_report(max_chars=max_chars))

    def search_graph(self, query: str, max_results: int = 20, offset: int = 0) -> dict[str, Any]:
        return self._mcp_envelope(
            self.query.search_graph(query, max_results=max_results, offset=offset)
        )

    def search_text(
        self,
        query: str,
        case_sensitive: bool = False,
        max_results: int = SEARCH_DEFAULT_MAX_RESULTS,
    ) -> dict[str, Any]:
        limits = {
            "max_results": min(max(max_results, 1), MCP_TEXT_SEARCH_MAX_RESULTS),
            "preview_chars": SEARCH_PREVIEW_CHARS,
        }
        try:
            result = search_raw_text(
                self.repo_path,
                query,
                case_sensitive=case_sensitive,
                max_results=limits["max_results"],
            )
        except RepoLensSearchError as exc:
            return _mcp_error(
                code=str(exc) or exc.__class__.__name__,
                message="Raw text search could not be completed.",
                limits=limits,
            )

        data = result.to_cli_data()
        limits["max_file_size_bytes"] = result.scan.max_file_size_bytes
        return self._mcp_envelope(
            {
                "confidence": "high",
                "data": data,
                "evidence": [{"source": "scanner_approved_files", "tool": "search_text"}],
                "limits": limits,
                "ok": True,
                "pagination": {
                    "limit": result.max_results,
                    "offset": 0,
                    "returned": len(result.matches),
                    "total": result.total_matches,
                    "truncated": result.truncated,
                },
                "warnings": list(result.warnings),
            }
        )

    def get_node(
        self,
        reference: str | None = None,
        node_id: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        return self._mcp_envelope(
            self.query.get_node(reference=reference, node_id=node_id, query=query)
        )

    def get_neighbors(
        self,
        reference: str | None = None,
        node_id: str | None = None,
        query: str | None = None,
        depth: int = 1,
        direction: str = "both",
        edge_kinds: list[str] | None = None,
        max_results: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        return self._mcp_envelope(
            self.query.get_neighbors(
                reference=reference,
                node_id=node_id,
                query=query,
                depth=depth,
                direction=direction,
                edge_kinds=edge_kinds,
                max_results=max_results,
                offset=offset,
            )
        )

    def shortest_path(
        self,
        source: str,
        target: str,
        max_depth: int = 6,
        edge_kinds: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._mcp_envelope(
            self.query.shortest_path(
                source,
                target,
                max_depth=max_depth,
                edge_kinds=edge_kinds,
            )
        )

    def impact_analysis(self, target: str, depth: int = 1, max_results: int = 20) -> dict[str, Any]:
        return self._mcp_envelope(
            self.query.impact_analysis(target, depth=depth, max_results=max_results)
        )

    def suggest_reading_order(self, task: str, max_files: int = 7) -> dict[str, Any]:
        return self._mcp_envelope(self.query.suggest_reading_order(task, max_files=max_files))

    def list_entrypoints(
        self,
        kind: str | None = None,
        max_results: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        return self._mcp_envelope(
            self.query.list_entrypoints(kind=kind, max_results=max_results, offset=offset)
        )

    def _mcp_envelope(
        self, envelope: dict[str, Any], *, cached: bool | None = None
    ) -> dict[str, Any]:
        result = dict(envelope)
        data = result.get("data")
        pagination = result.get("pagination")
        freshness = _freshness_from_envelope(result)
        truncation = _truncation_from_payload(data, pagination)

        result.setdefault("data", {})
        result.setdefault("limits", {})
        result.setdefault("warnings", [])
        result.setdefault("ok", False)
        result["freshness"] = freshness
        result["truncation"] = truncation
        if cached is not None:
            result["freshness"]["status_cache"] = {
                "cached": cached,
                "ttl_seconds": self.status_ttl_seconds,
            }
        return result

    def _missing_status_as_error(self, envelope: dict[str, Any]) -> dict[str, Any]:
        data = envelope.get("data")
        if not isinstance(data, dict) or data.get("reason") != "missing_graph_artifacts":
            return envelope
        result = dict(envelope)
        result["ok"] = False
        result["data"] = {}
        result["error"] = {
            "code": "missing_graph_artifacts",
            "message": "RepoLens graph artifacts are missing. Run repolens index for this repository.",
            "missing_artifacts": data.get("missing_artifacts", []),
            "recommended_action": data.get("recommended_action"),
            "status": data.get("status"),
        }
        return result


def create_mcp_server(repo_path: Path | str) -> FastMCP:
    """Create the stdio-capable FastMCP server with exactly the v0.1 read-only tools."""
    tools = RepoLensMcpTools(repo_path)
    server = FastMCP("RepoLens", json_response=True)

    @server.tool()
    def repo_summary(
        max_entrypoints: int = 10,
        max_commands: int = 10,
        max_modules: int = 20,
        max_important_files: int = 20,
    ) -> dict[str, Any]:
        """Return high-level graph metadata for this repository."""
        return tools.repo_summary(max_entrypoints, max_commands, max_modules, max_important_files)

    @server.tool()
    def graph_status(max_changed_files: int = 20) -> dict[str, Any]:
        """Return live RepoLens graph artifact status using a short TTL cache."""
        return tools.graph_status(max_changed_files)

    @server.tool()
    def get_graph_report(max_chars: int = 20_000) -> dict[str, Any]:
        """Return the generated graph report artifact with capped text."""
        return tools.get_graph_report(max_chars)

    @server.tool()
    def search_graph(query: str, max_results: int = 20, offset: int = 0) -> dict[str, Any]:
        """Search structured graph metadata without reading source text."""
        return tools.search_graph(query, max_results, offset)

    @server.tool()
    def search_text(
        query: str,
        case_sensitive: bool = False,
        max_results: int = SEARCH_DEFAULT_MAX_RESULTS,
    ) -> dict[str, Any]:
        """Search scanner-approved live text with capped previews."""
        return tools.search_text(query, case_sensitive, max_results)

    @server.tool()
    def get_node(
        reference: str | None = None,
        node_id: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Return a graph node by ID, path, or unambiguous query."""
        return tools.get_node(reference, node_id, query)

    @server.tool()
    def get_neighbors(
        reference: str | None = None,
        node_id: str | None = None,
        query: str | None = None,
        depth: int = 1,
        direction: str = "both",
        edge_kinds: list[str] | None = None,
        max_results: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return bounded neighboring graph relationships around one node."""
        return tools.get_neighbors(
            reference, node_id, query, depth, direction, edge_kinds, max_results, offset
        )

    @server.tool()
    def shortest_path(
        source: str,
        target: str,
        max_depth: int = 6,
        edge_kinds: list[str] | None = None,
    ) -> dict[str, Any]:
        """Find a bounded graph path between two resolved references."""
        return tools.shortest_path(source, target, max_depth, edge_kinds)

    @server.tool()
    def impact_analysis(target: str, depth: int = 1, max_results: int = 20) -> dict[str, Any]:
        """Return deterministic read-only impact context for a graph target."""
        return tools.impact_analysis(target, depth, max_results)

    @server.tool()
    def suggest_reading_order(task: str, max_files: int = 7) -> dict[str, Any]:
        """Suggest a bounded file reading order for a natural-language task."""
        return tools.suggest_reading_order(task, max_files)

    @server.tool()
    def list_entrypoints(
        kind: str | None = None,
        max_results: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List detected entrypoints with evidence and pagination."""
        return tools.list_entrypoints(kind, max_results, offset)

    return server


def run_mcp_server(repo_path: Path | str) -> None:
    """Run RepoLens MCP over stdio without writing application output to stdout."""
    create_mcp_server(repo_path).run(transport="stdio")


def _freshness_from_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data")
    if not isinstance(data, dict):
        return {"fresh": None, "status": "unknown"}
    if "fresh" in data or "status" in data:
        return {
            "fresh": data.get("fresh"),
            "status": data.get("status", "unknown"),
        }
    error = envelope.get("error")
    if isinstance(error, dict) and error.get("code") == "missing_graph_artifacts":
        return {"fresh": False, "status": error.get("status", "missing")}
    return {"fresh": None, "status": "unknown"}


def _truncation_from_payload(data: Any, pagination: Any) -> dict[str, Any]:
    truncated = False
    fields: list[str] = []
    if isinstance(pagination, dict) and pagination.get("truncated") is True:
        truncated = True
        fields.append("pagination")
    if isinstance(data, dict):
        data_truncated = data.get("truncated")
        if isinstance(data_truncated, bool):
            truncated = truncated or data_truncated
            if data_truncated:
                fields.append("data")
        elif isinstance(data_truncated, dict):
            truncated_fields = [key for key, value in data_truncated.items() if value]
            truncated = truncated or bool(truncated_fields)
            fields.extend(truncated_fields)
    return {"fields": sorted(set(fields)), "truncated": truncated}


def _mcp_error(*, code: str, message: str, limits: dict[str, Any]) -> dict[str, Any]:
    return {
        "confidence": "none",
        "data": {},
        "error": {"code": code, "message": message},
        "evidence": [],
        "freshness": {"fresh": None, "status": "unknown"},
        "limits": limits,
        "ok": False,
        "truncation": {"fields": [], "truncated": False},
        "warnings": [],
    }
