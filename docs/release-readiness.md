# RepoLens MCP v0.3 Release Readiness

This checklist is for manual dogfooding and release prep. It does not publish to PyPI or a Docker registry. Use `docs/release-checklist.md` as the final release gate checklist and `docs/changelog-template.md` for release notes.

## Human Checkpoint

Before treating release-facing docs as final, a human maintainer must confirm:

- Project and distribution name: `repolens` / RepoLens MCP.
- License wording and whether a license file should be added before release.
- PyPI publishing remains deferred for v0.3.
- Docker registry publishing remains deferred for v0.3.
- Final README positioning and whether the README should target users, contributors, or both.
- Known limitations in `docs/known-limitations.md` reflect dogfooding outcomes and are acceptable for release.

## Local Verification Gate

Run from the repository root:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
```

## Isolated Native Install Smoke

Build and install the package in an isolated environment:

```bash
uv build
uv tool install --force dist/*.whl
repolens --help
repolens status .
uv tool uninstall repolens
```

Alternative `pipx` smoke if `pipx` is available:

```bash
uv build
pipx install --force dist/*.whl
repolens --help
pipx uninstall repolens
```

## Docker Build And Index Smoke

Build the local image:

```bash
docker build -t repolens:latest .
```

Run indexing without runtime network access and with the host user mapped, so `.repolens` files are not root-owned:

```bash
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$PWD:/workspace" repolens:latest index /workspace
test "$(stat -c '%u:%g' .repolens/graph.sqlite)" = "$(id -u):$(id -g)"
```

Check that status is read-like:

```bash
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$PWD:/workspace" repolens:latest status /workspace
```

## Docker MCP Smoke

Start the stdio MCP server through Docker with no runtime network access:

```bash
docker run --rm -i --network none --user "$(id -u):$(id -g)" -v "$PWD:/workspace" repolens:latest mcp /workspace
```

Use an MCP client to list tools and call at least `graph_status`, `get_task_context`, `expand_context`, and `explain_relevance`.

## Context Pack CLI Smoke

Index a local repository, then request human and JSON Context Packs:

```bash
uv run repolens index .
uv run repolens context . "Document Context Pack workflow"
uv run repolens context . "Document Context Pack workflow" --json
```

Expected smoke result:

- `ok: true` after graph artifacts exist.
- `data.context_pack_id` is present.
- `data.first_read_files` is bounded by the default budget.
- `data.expansion_handles` references returned items only.
- Output contains repo-relative paths and structural metadata, not source snippets.
- Candidate verification commands, when present, are marked not run.

## Context Pack Evaluation

Run the release-blocking fixture suite:

```bash
uv run repolens evaluate-context
uv run repolens evaluate-context --json
```

The JSON command exits non-zero when the expectation-based release gate fails. The report covers direct symbol tasks, test-focused tasks, docs/config tasks, broad tasks, ambiguity, no matches, focus hints, stale graphs, secret redaction, stale pack IDs, and no-source-disclosure negatives.

Latest local evidence for issue #87 on 2026-06-24:

- `uv run repolens evaluate-context --json`: `ok: true`, release gate passed, 11/11 cases passed.
- Metrics reported include first-read hit rate, irrelevant file count, test inclusion, pack size, expansion count, and safety negative outcomes across Context Pack, `suggest_reading_order`, and lexical baselines.
- `uv run repolens index .`: indexed 154 eligible files and wrote ignored local `.repolens/` artifacts.
- `uv run repolens context . "Document Context Pack workflow" --json`: `ok: true`, confidence `medium`, returned `context_pack_id`, First-Read Files, likely tests, Agent Guidance metadata, expansion handles, freshness, limits, and truncation metadata with no source snippets.
- Direct follow-up smoke for MCP-backed service functions: `get_task_context_ok=True`, `expand_context_ok=True`, `explain_relevance_ok=True` for a returned First-Read File handle.

## OpenCode Dogfood

- Copy the shape from `docs/opencode-mcp.example.jsonc` into a local OpenCode config outside this repository.
- Replace `1000:1000` with your host user and group IDs from `id -u` and `id -g`.
- Replace `/absolute/path/to/repo` with the absolute path to the repository being indexed.
- Confirm OpenCode can list the RepoLens tools.
- Ask the assistant to call `graph_status` before relying on graph context.

## Dogfooding Reports

- Follow `docs/dogfood/README.md` for dogfooding reports and fixture policy.
- Commit dated reports under `docs/dogfood/`.
- Commit only distilled regression fixtures under `tests/fixtures/dogfood/`; do not commit `.repolens/` artifacts or vendored third-party repository snapshots.
- v0.3 release remains blocked on full verification and Context Pack Evaluation passing before release, even when dogfooding reports are complete.

## Scope Guard

Do not add these as part of v0.3 release prep unless a maintainer opens a separate issue:

- PyPI publishing.
- Docker registry publishing.
- Dependabot or dependency update automation.
- Contributor pre-commit hook setup.
- Runtime network calls during indexing or MCP serving.
- Embeddings, LLM-generated summaries, telemetry, hosted evaluation, or persisted Context Pack sessions.
- Source snippets, code bodies, function signatures, paragraph excerpts, raw comment text, or raw Agent Guidance instruction text in Context Pack output.
