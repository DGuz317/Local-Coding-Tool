# Python TDD Notes

Use these notes when applying the TDD skill to Python projects.

## Test runner

Prefer `pytest`.

Tests should verify behavior through public interfaces:

- CLI commands
- service-layer functions/classes
- generated files/artifacts
- returned data structures
- observable filesystem effects

Avoid testing private helpers directly unless there is no practical public seam yet.

## CLI tests

For Typer CLIs, prefer testing through the CLI boundary.

Use `typer.testing.CliRunner` for fast CLI behavior tests.

Example:

```python
from typer.testing import CliRunner

from repolens.cli import app

runner = CliRunner()

def test_status_reports_missing_graph(tmp_path):
    result = runner.invoke(app, ["status", str(tmp_path)])

    assert result.exit_code == 0
    assert "missing" in result.output.lower()
    assert not (tmp_path / ".repolens").exists()