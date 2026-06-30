# Dogfooding Reports

Dogfooding Reports are release-readiness records for running RepoLens on local repositories and small distilled fixtures. They capture graph quality issues, false positives, false negatives, known limitations, and actionable regressions without committing `.repolens/` artifacts or vendored third-party snapshots.

## Required Coverage

- RepoLens on itself.
- At least one local Python repository.
- At least one local JS/TS repository or distilled local JS/TS fixture when no suitable local repository is available.
- At least one mixed docs/config repository or distilled local mixed docs/config fixture.

## Process

1. Run `uv run repolens index <repo-or-fixture> --json`.
2. Inspect `<repo-or-fixture>/.repolens/graph-report.md` locally.
3. Record summary counts, graph quality findings, false positives, false negatives, known limitations, and candidate regressions in a dated report under this directory.
4. Commit only the report and any distilled fixture under `tests/fixtures/dogfood/`.
5. Do not commit `.repolens/`, generated graph exports, or third-party repository snapshots.

## Distilled Fixtures

- `tests/fixtures/dogfood/python-local-imports`: small Python package plus test import path.
- `tests/fixtures/dogfood/js-ts-workspace`: tiny TypeScript workspace with a local workspace package, package ownership evidence, scoped alias evidence, and relative import.
- `tests/fixtures/dogfood/mixed-docs-config`: documentation, assistant guidance, YAML config, and Makefile commands.

Package/workspace findings must be promoted to a P0 bug when they create unsafe assistant guidance or unusable release-blocking workflows. Otherwise, document them as known limitations, relationship candidates, graph-quality warnings, or follow-up issues.
