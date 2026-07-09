from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from repolens.cli import app

runner = CliRunner()


def test_create_ai_proposal_cli_json_matches_service_and_does_not_write_artifacts(tmp_path):
    _write_text(tmp_path / "src" / "app.py", "def alpha():\n    return 1\n")
    before_paths = _repo_paths(tmp_path)
    task = "Summarize the bounded context pack"

    result = runner.invoke(
        app,
        [
            "create-ai-proposal",
            str(tmp_path),
            "context_pack_summary",
            task,
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    cli_envelope = json.loads(result.output)
    from repolens.ai_proposal import create_ai_proposal

    service_envelope = create_ai_proposal(
        tmp_path,
        kind="context_pack_summary",
        task=task,
    )
    assert cli_envelope == service_envelope
    assert cli_envelope["ok"] is True
    assert cli_envelope["data"]["status"] == "disabled"
    assert cli_envelope["data"]["kind"] == "context_pack_summary"
    assert cli_envelope["data"]["provider"] == {
        "configured": False,
        "name": None,
        "model": None,
    }
    assert cli_envelope["data"]["safety"] == {
        "provider_called": False,
        "network_accessed": False,
        "file_written": False,
        "command_executed": False,
        "patch_applied": False,
        "remote_posted": False,
    }
    assert _repo_paths(tmp_path) == before_paths
    assert not (tmp_path / ".repolens").exists()


def _repo_paths(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in root.rglob("*")}


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
