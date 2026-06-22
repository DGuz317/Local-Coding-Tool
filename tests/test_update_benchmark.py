from __future__ import annotations

import json

from typer.testing import CliRunner

from repolens.benchmark import generate_update_benchmark_fixture
from repolens.cli import app

runner = CliRunner()


def test_update_benchmark_fixture_generation_is_deterministic(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"

    generate_update_benchmark_fixture(first, file_count=3)
    generate_update_benchmark_fixture(second, file_count=3)

    assert _fixture_files(first) == _fixture_files(second)


def test_benchmark_update_reports_relative_evidence_without_wall_clock_claim(tmp_path):
    result = runner.invoke(
        app,
        [
            "benchmark-update",
            "--fixture-path",
            str(tmp_path / "fixture"),
            "--file-count",
            "3",
            "--changed-file-count",
            "1",
            "--json",
        ],
    )

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    data = envelope["data"]
    assert envelope["ok"] is True
    assert envelope["limits"] == {"fixed_wall_clock_claim": False}
    assert data["file_count"] == 3
    assert data["changed_file_count"] == 1
    assert data["selective_update_seconds"] > 0
    assert data["full_rebuild_seconds"] > 0
    assert data["relative_speedup"]["basis"] == ("full_rebuild_seconds / selective_update_seconds")
    assert data["relative_speedup"]["fixed_wall_clock_claim"] is False
    assert isinstance(data["relative_speedup"]["factor"], float)
    assert data["selective_update"]["changed_paths"] == ["src/benchpkg/module_0000.py"]


def test_benchmark_update_refuses_non_empty_fixture_path(tmp_path):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "existing.txt").write_text("keep me\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["benchmark-update", "--fixture-path", str(fixture), "--file-count", "1", "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.output)["error"] == {"message": "fixture_path_not_empty"}
    assert (fixture / "existing.txt").read_text(encoding="utf-8") == "keep me\n"


def _fixture_files(root):
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
