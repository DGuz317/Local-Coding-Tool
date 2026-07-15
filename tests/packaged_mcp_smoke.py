"""Exercise the installed wheel's first-use MCP workflow in a clean environment."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def _call_preflight(
    executable: Path, repo_path: Path, task: str, guard_path: Path
) -> dict[str, Any]:
    server_env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    server_env["PYTHONPATH"] = str(guard_path)
    server = StdioServerParameters(
        command=str(executable),
        args=["mcp", str(repo_path)],
        env=server_env,
    )
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "assistant_preflight",
                arguments={
                    "task": task,
                    "focus_hints": ["src/auth/login.py"],
                    "max_first_read_files": 1,
                    "max_items_per_support_group": 1,
                    "max_candidate_verification_commands": 1,
                    "max_total_chars": 8_000,
                },
            )
    if result.structuredContent is None:
        raise AssertionError("assistant_preflight returned no structured content")
    return result.structuredContent


def _assert_bounded(envelope: dict[str, Any], repo: Path) -> None:
    assert envelope["ok"] is True, envelope
    assert envelope["freshness"]["fresh"] is True
    assert envelope["limits"]["max_total_chars"] == 8_000
    assert len(envelope["data"]["first_read_files"]) <= 1
    assert len(envelope["data"]["likely_tests"]) <= 1
    assert len(json.dumps(envelope, sort_keys=True)) <= 12_000
    rendered = json.dumps(envelope, sort_keys=True)
    assert str(repo) not in rendered
    assert "password == expected_password" not in rendered
    assert all(
        command.get("run") is False
        for command in envelope["data"]["candidate_verification_commands"]
    )


async def _run(executable: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="repolens-packaged-mcp-") as directory:
        root = Path(directory)
        guard_path = root / "runtime-guard"
        guard_path.mkdir()
        (guard_path / "sitecustomize.py").write_text(
            "import sys\n"
            "def _guard(event, args):\n"
            "    if event in {'socket.connect', 'socket.getaddrinfo', "
            "'subprocess.Popen', 'os.system'}:\n"
            "        raise RuntimeError(f'forbidden first-use side effect: {event}')\n"
            "sys.addaudithook(_guard)\n",
            encoding="utf-8",
        )
        repo = root / "sample-repo"
        nested = repo / "src" / "auth"
        tests = repo / "tests"
        nested.mkdir(parents=True)
        tests.mkdir()
        (repo / ".git").mkdir()
        (repo / "pyproject.toml").write_text(
            '[project]\nname = "sample-repo"\nversion = "0.1.0"\n', encoding="utf-8"
        )
        login = nested / "login.py"
        login.write_text(
            "def login(password, expected_password):\n    return password == expected_password\n",
            encoding="utf-8",
        )
        (tests / "test_login.py").write_text(
            "from src.auth.login import login\n\ndef test_login():\n    assert login('a', 'a')\n",
            encoding="utf-8",
        )

        first = await _call_preflight(executable, nested, "Fix login validation", guard_path)
        _assert_bounded(first, repo)
        assert first["data"]["graph_lifecycle"]["update"]["outcome"] == "initialized"
        assert (repo / ".repolens" / "graph.sqlite").is_file()

        login.write_text(
            "def login(password, expected_password):\n"
            "    return bool(password) and password == expected_password\n",
            encoding="utf-8",
        )
        refreshed = await _call_preflight(executable, nested, "Fix login validation", guard_path)
        _assert_bounded(refreshed, repo)
        assert refreshed["data"]["graph_lifecycle"]["update"]["outcome"] in {
            "updated",
            "rebuilt",
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repolens", required=True, type=Path)
    args = parser.parse_args()
    asyncio.run(_run(args.repolens.resolve()))
    print("packaged MCP first-use smoke passed")


if __name__ == "__main__":
    main()
