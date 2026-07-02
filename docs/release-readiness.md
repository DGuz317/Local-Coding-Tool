# RepoLens MCP v0.5 Release Readiness

This checklist is for manual dogfooding and release prep. It does not publish to PyPI or a Docker registry. Use `docs/release-checklist.md` as the final release gate checklist and `docs/changelog-template.md` for release notes.

v0.5 release readiness is about a stable Assistant Preflight adoption path. Assistants should call preflight before broad file reads, then use the returned first-read files, likely tests, warnings, freshness, budget metadata, and candidate commands as orientation only.

v0.4 release readiness is about trust in package/workspace repositories. The package/workspace evidence must show that RepoLens preserves uncertainty through Relationship Candidates, Graph Quality Warnings, unresolved statuses, and known limitations instead of inventing package facts.

## Human Checkpoint

Before treating release-facing docs as final, a human maintainer must confirm:

- Project and distribution name: `repolens` / RepoLens MCP.
- License wording and whether a license file should be added before release.
- PyPI publishing remains deferred for v0.5 unless a maintainer opens an explicit release issue.
- Docker registry publishing remains deferred for v0.5 unless a maintainer opens an explicit release issue.
- Assistant client config examples for OpenCode, Claude Desktop, and Cursor-style MCP are accurate for the current CLI command shape.
- Final README positioning and whether the README should target users, contributors, or both.
- Known limitations in `docs/known-limitations.md` reflect dogfooding outcomes and are acceptable for release.
- v0.4 maintainer release judgment for issue #128 remains recorded as the v0.5 prerequisite.
- Final v0.5 maintainer release judgment is recorded before v0.5 is cut.

## Local Verification Gate

Run from the repository root:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
uv run repolens evaluate-context --json
uv run repolens index . --json
uv run repolens audit-artifacts . --json
uv build --out-dir /tmp/repolens-dist --clear
```

The CI release gate also runs the v0.4 package/workspace regression subset: `tests/test_config_index.py`, `tests/test_javascript_index.py`, and `tests/test_query_service.py`.

## v0.4 Assistant-Facing Documentation

The v0.4 assistant-facing contract uses these domain terms:

- Package Identity: an explicit local package name from supported package metadata, not a directory-name guess.
- Workspace Membership: a Package Identity inside explicit workspace scope.
- Package Ownership: the nearest evidence-backed package root for a file.
- Local Resolution: deterministic import-to-file resolution from local source/config evidence.
- Relationship Candidate: bounded metadata for plausible, ambiguous, or unresolved package/workspace/import relationships; not a graph edge.
- Graph Quality Warning: structured warning metadata for incomplete, ambiguous, unsupported, or unresolved graph facts.
- Candidate Verification Command: a found command with `run: false`, purpose metadata, and a separate command risk bucket.

Context Packs may surface package/workspace ownership facts, relationship candidates, graph-quality warning codes, docs/config orientation, related package references, and command risk buckets as structured metadata only. They must not include source snippets, code bodies, function signatures, raw config values, raw comments, raw Agent Guidance text, paragraph excerpts, or absolute host paths.

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

## Assistant Preflight Adoption Smoke

Run setup diagnostics before connecting an assistant:

```bash
uv run repolens --help
uv run repolens index /absolute/path/to/repo
uv run repolens status /absolute/path/to/repo
uv run repolens preflight /absolute/path/to/repo "Check setup readiness" --json
```

Expected smoke result:

- `assistant_preflight_version` is present.
- Graph freshness is included.
- First-read files, likely tests, warnings, confidence, limits, truncation, and budget controls are bounded.
- Candidate verification commands, when present, are marked found and `run: false`.
- Output contains repo-relative paths and structural metadata, not source snippets.

Use an MCP client to list tools and call `assistant_preflight` before broad file reads. OpenCode, Claude Desktop, and Cursor-style config examples live in `docs/assistant-usage-guide.md` and the README.

## Docker Preflight Smoke

Build and exercise a local image without registry publishing:

```bash
docker build -t repolens:latest .
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$PWD:/workspace" repolens:latest index /workspace
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$PWD:/workspace" repolens:latest preflight /workspace "Check Docker setup" --json
```

This smoke must not push an image, publish a package, or require runtime network access.

## PyPI Readiness Smoke

Build and install a local wheel without publishing:

```bash
uv build --out-dir /tmp/repolens-dist --clear
uv tool install --force /tmp/repolens-dist/*.whl
repolens --help
repolens preflight /absolute/path/to/repo "Check wheel setup" --json
uv tool uninstall repolens
```

This checks local packaging readiness only. Publishing to PyPI remains deferred unless a maintainer opens an explicit release issue.

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

Latest local evidence for issue #149 on 2026-07-02:

- Blocker status: #139, #140, #141, #142, #143, #144, #145, #146, #147, and #148 are closed before final readiness judgment.
- Assistant-facing docs: README and `docs/assistant-usage-guide.md` explain CLI `preflight`, MCP `assistant_preflight`, deterministic focus hints and budget controls, stale or missing graph handling, candidate commands found but not run, and source-disclosure limitations.
- Dogfood evidence: `docs/dogfood/2026-07-02-v0.5-dogfood-evaluation-pack.md` covers JS/TS workspace, Python package, docs-heavy, config-heavy, ambiguous import, stale graph, and package/workspace scenarios.
- Local savings metrics: `uv run repolens evaluate-context --json` reports fixture-derived estimates only; they are not telemetry, exact model-token claims, or universal productivity scores.
- Artifact audit evidence: `uv run repolens audit-artifacts . --json` checks generated `.repolens/` artifacts and representative preflight output for source snippet leakage, absolute host paths, raw secrets, raw Agent Guidance mirroring, bounded artifact size, candidate commands not run, and MCP/preflight contract preservation.
- Full verification gate: passed in this branch. `uv run pytest` passed 192/192 tests. `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy src/repolens` passed. `uv run repolens evaluate-context --json` returned `ok: true`, release gate passed, 23/23 total cases passed, 22/22 release-blocking cases passed, and 4/4 Assistant Preflight dogfood cases passed. Local savings summary reported 22 files avoided vs lexical search, 10 likely irrelevant files avoided, 31 candidate commands marked not run, and 1 stale graph risk case. `uv run repolens index . --json` prepared root artifacts for audit with 206 eligible files and 19 skipped paths. `uv run repolens audit-artifacts . --json` returned `ok: true`, audited 8 artifacts, and reported 0 violations. `uv build --out-dir /tmp/repolens-dist --clear` built `repolens-0.5.0.tar.gz` and `repolens-0.5.0-py3-none-any.whl`.
- Maintainer release judgment: approved for v0.5 release after the full verification gate passes. Publishing to PyPI or a Docker registry remains deferred unless a separate maintainer-approved release issue is opened.

Latest local evidence for issue #128 on 2026-06-30:

- `uv run repolens evaluate-context --json`: `ok: true`, release gate passed, 19/19 cases passed, including v0.4 package/workspace, unresolved alias warning, ambiguous workspace import candidate, docs/config orientation, command risk bucket, v0.3.1 regression, and no-source-disclosure cases.
- `uv run repolens index tests/fixtures/dogfood/js-ts-workspace --json`: `ok: true`, indexed 9 eligible files, skipped `.repolens/` as generated artifacts.
- `uv run repolens context tests/fixtures/dogfood/js-ts-workspace "Trace @dog/lib workspace import and package ownership" --json`: `ok: true`, confidence `medium`, surfaced evidence-backed package boundaries for `@dog/app` and `@dog/lib`, and returned candidate verification commands with `run: false`, `verification_likely`, and `quality_check_likely` risk buckets.
- Full verification gate: passed in this branch with `uv run pytest` at 170/170 tests passed, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src/repolens`, `uv run repolens evaluate-context --json`, and `uv build --out-dir /tmp/repolens-dist --clear`.
- Maintainer release judgment: pending HITL approval for issue #128.

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
- The v0.4 JS/TS workspace report is `docs/dogfood/2026-06-30-v0.4-js-ts-workspace.md`.
- v0.4 release remains blocked on full verification, Context Pack Evaluation passing, and explicit maintainer release judgment, even when dogfooding reports are complete.

## Scope Guard

Do not add these as part of v0.4 release prep unless a maintainer opens a separate issue:

- PyPI publishing.
- Docker registry publishing.
- Dependabot or dependency update automation.
- Contributor pre-commit hook setup.
- Runtime network calls during indexing or MCP serving.
- Embeddings, LLM-generated summaries, telemetry, hosted evaluation, or persisted Context Pack sessions.
- Source snippets, code bodies, function signatures, paragraph excerpts, raw comment text, or raw Agent Guidance instruction text in Context Pack output.
