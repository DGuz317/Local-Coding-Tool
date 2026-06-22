"""Shared stdio-discipline assertions for MCP tests."""

from __future__ import annotations

from typing import Any


def assert_no_stdout(capsys: Any) -> None:
    """Assert a direct MCP tool call did not write application output to stdout."""
    assert capsys.readouterr().out == ""
