# RepoLens v0.3.1 CI Verification Plan

## Purpose

RepoLens v0.3.1 focuses on artifact usability, especially preventing generated outputs such as `graph-index.md` from becoming too large for humans or AI assistants to load.

The CI gate should prove two things:

1. The source checkout is healthy.
2. The built package works as an installed CLI and still supports v0.3 Context Pack workflows.

The existing four checks are necessary, but they are not enough for v0.3.1 release readiness.

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
```

Those checks prove test health, linting, formatting, and typing. They do not prove that the project builds, installs, or works as a real CLI package.

---

## Recommended v0.3.1 CI Gate

Use this release gate:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
uv run pytest
uv build --out-dir <temp-build-output> --clear
```

Then copy a fixture to a temp directory and run package smoke tests from the built wheel:

```bash
repolens --help
repolens index <temp-fixture-path>
repolens status <temp-fixture-path> --json
repolens context <temp-fixture-path> "Find auth-related files" --json
```

Then run v0.3/v0.3.1 product checks:

```bash
uv run repolens evaluate-context --manifest tests/fixtures/context_pack/evaluation_manifest.json --json
```

If a large-output fixture exists, also run:

```bash
uv run repolens index tests/fixtures/large-output
uv run repolens status tests/fixtures/large-output --json
uv run repolens context tests/fixtures/large-output "Find auth-related files" --json
```

---

## Why `uv build` Belongs In CI

`uv build --out-dir <temp-build-output> --clear` verifies that RepoLens can be packaged successfully without mixing fresh artifacts with stale wheels from a previous build.

It catches problems that normal tests may miss, such as:

- missing package files;
- broken project metadata;
- incorrect package discovery;
- missing console script configuration;
- build backend issues;
- files required at runtime but not included in the wheel.

A project can pass `pytest` but still fail to build or install correctly. For a CLI tool, that is a release blocker.

---

## Why Installed CLI Smoke Belongs In CI

`uv run repolens ...` tests the source checkout.

Installed CLI smoke tests the real package users will run.

The CI should verify this path:

```text
source checkout -> build wheel -> install wheel into clean environment -> run repolens CLI
```

This proves the built package is usable outside the development checkout.

Minimum installed smoke:

```bash
repolens --help
repolens index <fixture-or-repo-path>
```

Recommended installed smoke for v0.3.1:

```bash
repolens --help
repolens index <fixture-or-repo-path>
repolens status <fixture-or-repo-path> --json
repolens context <fixture-or-repo-path> "Find auth-related files" --json
```

---

## Evaluation Is Not A Build Test

`repolens evaluate-context` and `uv build` test different things.

| Check | Purpose |
|---|---|
| `uv build --out-dir <temp-build-output> --clear` | Confirms the project can be packaged. |
| Installed CLI smoke | Confirms the built wheel works as a real CLI. |
| `repolens evaluate-context` | Confirms Context Packs are useful, bounded, and safe. |
| Large-output smoke | Confirms v0.3.1 artifact-size behavior does not regress. |

Do not replace `uv build` with evaluation.

Evaluation is a product-quality check. Build is a packaging check.

Both belong in release CI.

---

## Recommended GitHub Actions Workflow Shape

Use two layers:

1. Source checkout verification.
2. Built package verification.

Example:

```yaml
name: CI

on:
  push:
    branches:
      - main
      - feature/repolens-v0.3
      - feature/repolens-v0.3.1
  pull_request:
    branches:
      - main
      - feature/repolens-v0.3
      - feature/repolens-v0.3.1

jobs:
  release-gate:
    name: Release Gate
    runs-on: ubuntu-latest

    steps:
      - name: Check out repository
        uses: actions/checkout@v7

      - name: Set up Python
        uses: actions/setup-python@v6
        with:
          python-version: "3.11"

      - name: Set up uv
        uses: astral-sh/setup-uv@v8.2.0
        with:
          enable-cache: true

      - name: Install dependencies
        run: uv sync --all-extras --dev --locked

      - name: Run Ruff lint
        run: uv run ruff check .

      - name: Run Ruff format check
        run: uv run ruff format --check .

      - name: Run mypy
        run: uv run mypy src/repolens

      - name: Run tests
        run: uv run pytest

      - name: Run Context Pack evaluation
        run: uv run repolens evaluate-context --manifest tests/fixtures/context_pack/evaluation_manifest.json --json

      - name: Build package
        run: uv build --out-dir "${RUNNER_TEMP}/repolens-dist" --clear

      - name: Create clean install environment
        run: python -m venv /tmp/repolens-smoke

      - name: Install built wheel
        run: /tmp/repolens-smoke/bin/python -m pip install "${RUNNER_TEMP}"/repolens-dist/*.whl

      - name: Smoke installed CLI
        run: |
          smoke_parent="${RUNNER_TEMP}/repolens-fixtures"
          smoke_fixture="${smoke_parent}/happy-path"
          mkdir -p "${smoke_parent}"
          cp -R tests/fixtures/context_pack/happy-path "${smoke_fixture}"

          /tmp/repolens-smoke/bin/repolens --help
          /tmp/repolens-smoke/bin/repolens index "${smoke_fixture}"
          /tmp/repolens-smoke/bin/repolens status "${smoke_fixture}" --json
          /tmp/repolens-smoke/bin/repolens context "${smoke_fixture}" "Find auth-related files" --json
```

Adjust fixture paths to match the actual repository.

---

## v0.3.1 Large-Output Verification

The core large-output checks already belong in pytest, and this repository has generated large-repository coverage in `tests/test_cli_index.py`.

If v0.3.1 adds a persistent large-output fixture, add a separate smoke section:

```yaml
      - name: v0.3.1 large-output index smoke
        run: uv run repolens index tests/fixtures/large-output

      - name: v0.3.1 large-output status smoke
        run: uv run repolens status tests/fixtures/large-output --json

      - name: v0.3.1 large-output context smoke
        run: uv run repolens context tests/fixtures/large-output "Find auth-related files" --json
```

The most important large-output checks should still live in pytest, not only shell commands.

Recommended pytest cases:

```python
def test_graph_index_md_is_bounded_for_large_repo_fixture(...):
    ...


def test_graph_index_reports_truncation_counts(...):
    ...


def test_graph_sqlite_keeps_full_data_when_markdown_is_capped(...):
    ...


def test_context_pack_still_works_after_graph_index_truncation(...):
    ...
```

Expected assertions:

```python
assert graph_index_path.stat().st_size <= MAX_GRAPH_INDEX_BYTES
assert "Showing" in graph_index_text
assert "truncated" in graph_index_text.lower()
assert sqlite_symbol_count > rendered_symbol_count
```

These tests prove that v0.3.1 limits generated Markdown output without losing the full graph data stored in SQLite.

---

## Branch Trigger Recommendation

For v0.3.1 development, CI should run on:

```yaml
branches:
  - main
  - feature/repolens-v0.3
  - feature/repolens-v0.3.1
```

If v0.3 is no longer active, this is enough:

```yaml
branches:
  - main
  - feature/repolens-v0.3.1
```

Do not leave the workflow targeting only old release branches such as `feature/repolens-v0.2`.

---

## Local Development vs Release CI

For ordinary local development, this is usually enough:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
```

For release readiness, use the fuller gate:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
uv run repolens evaluate-context --manifest tests/fixtures/context_pack/evaluation_manifest.json --json
uv build --out-dir /tmp/repolens-dist --clear
```

Then test the installed wheel:

```bash
python -m venv /tmp/repolens-smoke
/tmp/repolens-smoke/bin/python -m pip install /tmp/repolens-dist/*.whl
SMOKE_PARENT=/tmp/repolens-fixtures
SMOKE_FIXTURE="${SMOKE_PARENT}/happy-path"
mkdir -p "${SMOKE_PARENT}"
cp -R tests/fixtures/context_pack/happy-path "${SMOKE_FIXTURE}"
/tmp/repolens-smoke/bin/repolens --help
/tmp/repolens-smoke/bin/repolens index "${SMOKE_FIXTURE}"
/tmp/repolens-smoke/bin/repolens status "${SMOKE_FIXTURE}" --json
/tmp/repolens-smoke/bin/repolens context "${SMOKE_FIXTURE}" "Find auth-related files" --json
```

---

## Final Recommendation

For v0.3.1, the CI should include:

- Ruff lint.
- Ruff format check.
- mypy.
- pytest.
- Context Pack evaluation.
- `uv build`.
- installed wheel CLI smoke.
- large-output artifact smoke if the fixture exists.

The four baseline checks are good for daily development, but they are not enough for a release focused on artifact usability and assistant context savings.
