# RepoLens v0.5 CI Plan

## Recommendation

For **v0.5 CI**, use a tiered CI setup:

```text
PR CI = fast correctness checks
Main/nightly CI = broader integration and dogfood checks
Release CI = full gate, build, Docker, MCP smoke, artifact safety
```

Do not make every PR run the full release gate. v0.5 adds context-pack/preflight behavior, artifact audit, and savings evaluation, so CI should protect those contracts without becoming too slow.

## v0.5 CI Goals

CI should prove:

1. Code quality stays clean.
2. Type, lint, and test gates pass.
3. Context Pack output is deterministic.
4. MCP response contracts do not regress.
5. Artifact safety audit passes.
6. CLI and MCP still work after packaging.
7. Docker smoke still works before release.

## Recommended CI Jobs

### 1. Fast PR Gate

Run on every pull request.

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
uv run pytest
```

Recommended job name:

```text
ci-fast
```

This should be the required branch-protection gate.

### 2. Contract Tests

Run on every PR if fast enough.

```bash
uv run pytest tests/contracts
```

This should cover:

```text
- get_task_context response shape
- deterministic Context Pack ordering
- MCP envelope fields
- stale warnings
- limits/truncation metadata
- confidence/evidence fields
- ambiguity behavior
- candidate commands marked not run
```

This matters because v0.5 is mainly an assistant-context contract release.

### 3. Artifact Safety Audit

Run on every PR if quick; otherwise run on main and release.

```bash
uv run repolens audit-artifacts tests/fixtures/minimal_repo
```

It should fail CI if generated artifacts contain:

```text
- raw source snippets where not allowed
- absolute host paths
- secret-like values
- raw agent guidance text
- oversized artifacts
- MCP contract violations
```

Artifact safety is important because RepoLens scans configs, commands, docs, agent instruction files, and possible secret-looking paths.

### 4. Context Evaluation / Savings Report

Run on PR for fixture cases. Run dogfood cases on main/nightly.

```bash
uv run repolens evaluate-context tests/fixtures/python_package
uv run repolens evaluate-context tests/fixtures/js_ts_workspace
```

For v0.5, this should check:

```text
- first-read file count
- support group caps
- approximate token estimate
- files avoided baseline
- deterministic ordering
- likely tests included when relevant
- stale graph risk reported
```

Do not make this depend on LLM output. It should be deterministic.

### 5. Build Smoke

Run on main and release tags.

```bash
uv build
```

Then install the wheel into a clean environment:

```bash
uv venv /tmp/repolens-smoke
uv pip install dist/*.whl
/tmp/repolens-smoke/bin/repolens --help
/tmp/repolens-smoke/bin/repolens status tests/fixtures/python_package
```

### 6. MCP Smoke

Run on PR if stable; otherwise run on main/release.

Minimum checks:

```text
- start stdio MCP server
- list tools
- call graph_status
- call get_task_context
- assert stdout discipline
- assert structured envelope
- assert read-only behavior
```

### 7. Docker Smoke

Run on main and release only, not every PR unless the Dockerfile changes.

```bash
docker build -t repolens:ci .
docker run --rm repolens:ci --help
docker run --rm -v "$PWD/tests/fixtures/python_package:/repo" repolens:ci index /repo
docker run --rm -v "$PWD/tests/fixtures/python_package:/repo" repolens:ci status /repo
```

## Suggested GitHub Actions Layout

```text
.github/workflows/
  ci.yml              # PR + main fast checks
  contracts.yml       # context/MCP/artifact contracts
  release-gate.yml    # manual/tag release gate
  docker-smoke.yml    # main/tag or Dockerfile changes
```

## Required Checks For PR Merge

Required:

```text
ci-fast
contract-tests
artifact-safety-audit
```

Optional but recommended on main:

```text
build-smoke
mcp-smoke
docker-smoke
dogfood-evaluation
```

## v0.5 Release Gate

Before cutting v0.5, require:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
uv run repolens evaluate-context tests/fixtures/python_package
uv run repolens evaluate-context tests/fixtures/js_ts_workspace
uv run repolens audit-artifacts tests/fixtures/python_package
uv build
```

Also require:

```text
- isolated wheel install smoke
- MCP stdio smoke
- Docker index/status smoke
- one real dogfood report
- docs updated for v0.5 get_task_context/preflight behavior
```

## Bottom Line

For v0.5, CI should protect the assistant context contract:

```text
get_task_context must stay deterministic by default,
bounded by item/character caps,
safe in artifacts,
honest about freshness,
and usable through CLI/MCP after packaging.
```
