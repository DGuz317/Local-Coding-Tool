# [AGENTS.md](http://AGENTS.md)

## Project Goal

RepoLens MCP creates local repository knowledge for AI assistants so they can understand a codebase faster, open fewer files, and reduce token consumption.

The project indexes source repositories, builds deterministic graph artifacts, and exposes read-only assistant-facing tools for repository orientation, related-file discovery, impact hints, context packs, and candidate verification commands.

RepoLens should remain:

- local-first;
- deterministic;
- metadata-oriented;
- safe by default;
- read-only through MCP;
- useful before broad source-code reads.

Prioritize strong support for these language ecosystems first:

- Python;
- JavaScript and TypeScript.

Support for other languages should be incremental, evidence-backed, and should not weaken Python or JS/TS behavior.

## Product Boundaries

Do not add these unless a maintainer explicitly changes the product direction:

- hosted services;
- telemetry;
- browser UI or graph visualization;
- embeddings or vector search;
- LLM-generated graph facts;
- package registry lookups during indexing;
- runtime package-manager, bundler, compiler, or framework execution during indexing;
- write-capable MCP tools;
- persisted assistant sessions or server-side assistant memory;
- source-code mirroring in assistant-facing output.

Assistant-facing outputs may include compact metadata, paths, node names, evidence labels, line ranges, warnings, and bounded orientation facts. They must not include whole source files, source snippets, code bodies, raw comments, raw secrets, or large raw document excerpts.

## Agent Skills

Use the repo agent guidance under `docs/agents/` when working with issues, domain docs, or triage:

- Issue tracker: GitHub Issues, described in `docs/agents/issue-tracker.md`.
- Triage labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, and `wontfix`, described in `docs/agents/triage-labels.md`.
- Domain docs: root `CONTEXT.md` and `docs/adr/`, described in `docs/agents/domain.md`.

Use specialized skills when they match the task:

- `triage`: create, classify, and move issues through the triage workflow.
- `to-prd`: turn a conversation or plan into a PRD.
- `to-issues`: break a plan or PRD into independently grabbable issues.
- `diagnose`: reproduce and debug reported failures.
- `tdd`: implement behavior through red-green-refactor.
- `review`: review changes against standards and issue requirements.
- `zoom-out`: explain how a code area fits into the broader system.
- `improve-codebase-architecture`: find architecture and maintainability opportunities.

Prefer one focused issue or implementation slice at a time.

## Implementation Rules

Keep changes small, vertical, and evidence-backed.

Prefer:

- explicit contracts;
- typed data structures;
- deterministic ordering;
- narrow fixtures;
- expectation-based tests;
- simple explainable algorithms;
- warnings, candidates, and unresolved states over guessing.

Avoid:

- broad refactors mixed with feature work;
- hidden behavior changes;
- new runtime dependencies without justification;
- speculative language or framework support;
- changing public artifact shapes without tests.

When evidence is incomplete, preserve uncertainty instead of inventing definitive facts. Use `candidate`, `warning`, `unresolved`, or `unsupported` as appropriate.

MCP tools must remain read-only. Generated artifacts must be deterministic and portable across machines. Use repo-relative POSIX paths in artifacts and MCP responses.

## Testing And Verification

Add or update tests for behavior changes.

Run focused tests while developing. Before considering a code slice complete, run the relevant subset of:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
```

Before release readiness, run the full gate when feasible:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
uv run repolens evaluate-context --json
uv build --out-dir /tmp/repolens-dist --clear
```

If a command cannot be run, report the reason clearly.

## Branch, Commit, PR, And Issue Workflow

Use `develop` as the integration branch unless the maintainer specifies another base branch.

For each issue:

1. Sync the local `develop` branch.
2. Create a dedicated issue branch from `develop`.
3. Use a clear branch name, such as `issue-123-short-description` or `feature/123-short-description`.
4. Implement the smallest complete slice that satisfies the issue.
5. Run relevant verification commands.
6. Commit only the intended files.
7. Use a concise area-prefixed commit message, such as `resolver: add ambiguous import warnings`.
8. Push the issue branch.
9. Open a pull request targeting `develop`.
10. After review and passing checks, merge the pull request into `develop`.
11. Confirm the issue is resolved and close it.

Do not mix unrelated cleanup with issue work. Do not start blocked issues. Do not close an issue until the merged work satisfies the acceptance criteria or the maintainer agrees to close it.

## Pull Request Description

Every PR description should include:

- linked issue;
- summary of what changed;
- why the change was made;
- how it affects RepoLens behavior or assistant workflow;
- tests run;
- tests not run, with reasons;
- known risks or follow-ups.

Use closing keywords only when the PR fully resolves the issue, for example:

```text
Closes #123
```

After the PR is merged, verify the linked issue is closed. If it is not closed automatically, close it manually with a short note explaining that the work was merged.