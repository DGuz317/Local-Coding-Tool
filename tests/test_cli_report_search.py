from __future__ import annotations

import json

from typer.testing import CliRunner

from repolens.cli import app

runner = CliRunner()


def test_report_reads_existing_report_unless_regeneration_is_requested(tmp_path):
    _write_text(tmp_path / "app.py", "def app():\n    return 1\n")
    index_result = runner.invoke(app, ["index", str(tmp_path)])
    assert index_result.exit_code == 0

    report_path = tmp_path / ".repolens" / "graph-report.md"
    report_path.write_text("custom report\n", encoding="utf-8")

    default_result = runner.invoke(app, ["report", str(tmp_path)])

    assert default_result.exit_code == 0
    assert default_result.output == "custom report\n"
    assert report_path.read_text(encoding="utf-8") == "custom report\n"

    regenerate_result = runner.invoke(app, ["report", str(tmp_path), "--regenerate"])

    assert regenerate_result.exit_code == 0
    assert "# RepoLens Graph Report" in regenerate_result.output
    assert "custom report" not in regenerate_result.output
    assert report_path.read_text(encoding="utf-8") == regenerate_result.output


def test_search_uses_scan_policy_and_returns_capped_sanitized_json_matches(tmp_path):
    _write_text(tmp_path / ".gitignore", "ignored.py\n")
    _write_text(
        tmp_path / "src" / "app.py",
        "Alpha target \x1b[31mred\nalpha second\nalpha third\nalpha fourth\n",
    )
    _write_text(tmp_path / ".env", "alpha secret\n")
    _write_text(tmp_path / "ignored.py", "alpha ignored\n")

    result = runner.invoke(
        app,
        ["search", str(tmp_path), "alpha", "--max-results", "3", "--json"],
    )

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    matches = envelope["data"]["matches"]

    assert envelope["ok"] is True
    assert envelope["data"]["case_sensitive"] is False
    assert envelope["data"]["match_count"] == 3
    assert envelope["data"]["total_matches"] == 4
    assert envelope["data"]["truncated"] is True
    assert envelope["data"]["scanned_files"] == 2
    assert envelope["data"]["skipped_paths"] == 2
    assert [match["path"] for match in matches] == ["src/app.py", "src/app.py", "src/app.py"]
    assert [match["line"] for match in matches] == [1, 2, 3]
    assert "\x1b" not in matches[0]["preview"]
    assert ".env" not in {match["path"] for match in matches}
    assert "ignored.py" not in {match["path"] for match in matches}
    assert envelope["limits"]["max_results"] == 3


def test_search_requires_non_empty_query(tmp_path):
    _write_text(tmp_path / "app.py", "alpha\n")

    result = runner.invoke(app, ["search", str(tmp_path), " ", "--json"])

    assert result.exit_code == 1
    envelope = json.loads(result.output)
    assert envelope["ok"] is False
    assert envelope["error"] == {"message": "empty_query"}


def test_search_supports_case_sensitive_mode(tmp_path):
    _write_text(tmp_path / "app.py", "Alpha\nalpha\n")

    default_result = runner.invoke(app, ["search", str(tmp_path), "alpha", "--json"])
    case_sensitive_result = runner.invoke(
        app,
        ["search", str(tmp_path), "alpha", "--case-sensitive", "--json"],
    )

    assert default_result.exit_code == 0
    assert case_sensitive_result.exit_code == 0
    default_envelope = json.loads(default_result.output)
    case_sensitive_envelope = json.loads(case_sensitive_result.output)
    assert default_envelope["data"]["total_matches"] == 2
    assert case_sensitive_envelope["data"]["case_sensitive"] is True
    assert case_sensitive_envelope["data"]["total_matches"] == 1
    assert case_sensitive_envelope["data"]["matches"][0]["line"] == 2


def test_search_truncates_long_previews_without_whole_file_output(tmp_path):
    line = f"{'a' * 200}needle{'b' * 200}"
    _write_text(tmp_path / "app.py", f"{line}\n")

    result = runner.invoke(app, ["search", str(tmp_path), "needle", "--json"])

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    match = envelope["data"]["matches"][0]

    assert match["preview"] != line
    assert len(match["preview"]) <= envelope["limits"]["preview_chars"]
    assert match["preview_truncated_before"] is True
    assert match["preview_truncated_after"] is True
    assert line not in result.output


def _write_text(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
