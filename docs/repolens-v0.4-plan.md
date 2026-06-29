# RepoLens MCP v0.4 Plan

## Theme

```text
Make RepoLens trustworthy across package/workspace repositories.
```

## Why v0.4 Exists

v0.3 made RepoLens the assistant's context budget manager through deterministic, bounded Context Packs. v0.3.1 patched artifact usability by making the default `graph-index.md` a bounded navigation artifact instead of a large Markdown dump.

The next release should improve the graph facts that Context Packs depend on. Context Pack quality now depends less on output shape and more on whether RepoLens can represent real repository structure accurately enough for assistant orientation.

Current project limitations point to the same gaps:

- JavaScript and TypeScript workspace package resolution is still partial.
- Package Boundary handling needs more real-repository confidence.
- Docs/config-only repositories still produce shallow impact and context.
- Candidate Verification Command classification is conservative.
- Evaluation coverage should expand beyond the release-blocking v0.3 fixtures.

## Release Goal

v0.4 should make RepoLens Context Packs more accurate on real package/workspace repositories while preserving the local-first, deterministic, metadata-only safety model.

Success means:

- workspace package imports are resolved from explicit package/config evidence;
- package ownership appears in Context Packs only when backed by graph evidence;
- docs and config tasks receive better graph-derived orientation;
- candidate verification commands are classified more usefully while remaining not run;
- expanded evaluation fixtures prove the improvements and guard against regressions;
- no whole-source disclosure, embeddings, runtime package execution, or assistant session persistence is introduced.

## Resolved Design Decisions

- Package Identity, Workspace Membership, Package Ownership, Package Dependency, Local Resolution, and Relationship Candidates are separate evidence concepts.
- Ambiguous package, workspace, import, and ownership relationships are stored as bounded Relationship Candidates with evidence labels, not as graph edges.
- Graph Quality Warnings are structured metadata records with stable codes and bounded metadata; they are distinct from Risk Signals and Graph Validation failures.
- JavaScript and TypeScript workspaces are the v0.4 P0 resolver target. Existing Python package/config behavior should be regression-protected, not expanded into new Python workspace semantics unless evaluation exposes a safety issue.
- `package.json` `workspaces` and `pnpm-workspace.yaml`/`.yml` are the P0 JavaScript workspace declaration sources. Other tool-specific workspace declarations are future work unless surfaced as warnings.
- Workspace declarations are scope evidence. Confirmed Workspace Membership requires matching explicit package identity evidence.
- Named private root packages create root Package Identity and Package Ownership boundaries. Unnamed package manifests provide config facts but not package identity or ownership.
- Clean nested package boundaries use the nearest explicit package root for Package Ownership. Collisions, duplicate identities, and conflicting evidence remain unresolved candidates.
- Workspace package imports resolve to scanner-approved entrypoint files only when explicit package entrypoint evidence supports that target. Missing or complex entrypoints remain candidates/warnings.
- TypeScript alias resolution is scoped to the applicable `tsconfig.json` directory subtree. Conflicting package identity and alias evidence becomes candidates/warnings unless the evidence converges on the same target.
- Package-to-package dependency edges are created only when manifest dependency evidence uniquely matches a local Package Identity. Dependency type is preserved as metadata, not runtime reachability.
- Lockfiles are supporting evidence only. They do not establish local package ownership without explicit package boundary evidence.
- Candidate Verification Commands keep their existing purpose classification and add a separate Command Risk Bucket. Risky or external signals dominate bucket classification, and commands remain marked not run.
- Docs/config orientation remains structured metadata only: paths, doc kind, heading metadata, links, mentions, package references, related configs, command buckets, ownership facts, and warning codes. It must not expose paragraph excerpts, raw comments, raw instructions, raw config values, or source snippets.
- Context Pack package/workspace facts should attach to relevant items or surface as bounded candidates/warnings. Context Packs should not include a default package inventory dump.
- Evaluation gates should remain expectation-based per scenario, with baseline comparisons kept as reporting evidence.
- Graph schema changes should require a fresh index rather than migration of local `.repolens/` cache artifacts. Context Pack contract/version changes should bump the pack version so stale pack IDs fail cleanly.

## P0 Scope

### Workspace And Package Boundary Hardening

- Resolve JavaScript and TypeScript workspace package imports from explicit `package.json`, workspace, package-manager workspace config, package dependency, package entrypoint, or scoped `tsconfig.json` alias evidence.
- Represent package ownership from graph facts in Context Packs without inferring ownership from conventional directory names alone.
- Preserve ambiguity when multiple package candidates match.
- Add fixtures for monorepo package boundaries and workspace imports.

### Package Evidence Model And Ambiguity Contract

- Define package identity, workspace membership, ownership confidence, ambiguity, and warning types before resolver implementation.
- Treat `package.json` `name` as primary package identity evidence.
- Treat root workspace declarations and package-manager workspace config as workspace scope evidence; confirmed membership also requires matching package identity evidence.
- Treat `tsconfig.json` `paths` and `baseUrl` as alias-resolution evidence within the configured scope.
- Treat lockfile entries as supporting dependency/package evidence, not primary local package ownership evidence. Explicit lockfile mappings to local workspace paths can support candidates or membership evidence, but ownership still requires explicit package boundary evidence.
- Separate import resolution from package ownership: an import may resolve to a file or module while ownership remains evidence-backed, ambiguous, or unknown.
- For ambiguous import/package relationships, do not emit a definitive graph edge; emit candidates with evidence labels, record a graph-quality warning, and allow Context Packs to mention the ambiguity without choosing a winner.

### Resolver Quality Improvements

- Harden deterministic local resolution for JavaScript and TypeScript imports.
- Improve TypeScript path alias handling when explicit `tsconfig.json` evidence exists.
- Keep unresolved and ambiguous relationships as candidates or warnings, not false graph edges.
- Surface graph-quality warnings for unsupported resolver cases.

### Docs And Config Impact Context

- Improve Context Packs for docs/config tasks where source graph evidence is weak.
- Connect Markdown path mentions, config references, package files, and command facts more usefully.
- Keep output orientation-only: no paragraph excerpts, source snippets, raw comments, or raw Agent Guidance text.
- Limit docs/config support to structured facts such as mentioned paths, referenced package names, related config files, candidate commands, nearby ownership/package facts, and graph-quality warnings.

### Candidate Verification Command Quality

- Improve classification for common verification commands such as `make verify`, `make test`, `npm test`, and `pytest`.
- Keep Candidate Verification Commands marked as found and not run.
- Do not recommend automatic command execution.
- Preserve conservative handling for deploy, publish, and destructive commands.
- Use explicit command risk buckets such as `verification_likely`, `quality_check_likely`, `build_likely`, `risky_or_external`, and `unknown`.

### Expanded Evaluation Corpora

- Promote the previous v0.3 P1 evaluation-corpus follow-up into v0.4 P0 scope.
- Add fixtures for monorepos, workspace package imports, docs/config tasks, unresolved aliases, ambiguous package ownership, and command classification.
- Continue comparing Context Packs against `suggest_reading_order` and a lexical baseline.
- Keep release gates expectation-based rather than universal numeric thresholds.

## Out Of Scope

Do not include the following in v0.4 unless a maintainer explicitly changes the product boundary:

- browser UI or graph visualization;
- hosted service, telemetry, or hosted evaluation;
- embeddings, vector search, or LLM-generated graph facts;
- write-capable MCP tools;
- runtime package-manager, bundler, framework, or compiler execution during indexing or Context Pack generation;
- runtime package registry lookups;
- deep semantic call graphs, control-flow graphs, data-flow graphs, or taint analysis;
- persisted Context Pack sessions or server-side assistant memory;
- source snippets, code bodies, function signatures, paragraph excerpts, raw comments, or raw Agent Guidance instruction text in assistant-facing output.

## Suggested Issue Slices

1. v0.4 roadmap, release gates, and non-goals.
2. Define package/workspace evidence model, Relationship Candidates, Graph Quality Warning codes, and contract fixtures.
3. Resolve JavaScript and TypeScript workspace package imports and local package dependencies from explicit evidence.
4. Harden TypeScript `tsconfig.json` `paths` and `baseUrl` resolution within explicit config scope.
5. Surface package/workspace ownership, ambiguity candidates, and graph-quality warnings in query and Context Pack output.
6. Improve docs/config task orientation without excerpts or raw config values.
7. Classify Candidate Verification Commands with separate purpose and Command Risk Bucket fields, without execution.
8. Expand v0.4 evaluation fixtures, baseline reporting, and expectation gates.
9. Update v0.4 docs, known limitations, and release readiness.

## Release Criteria

v0.4 should not be cut until there is evidence that:

- package identity, workspace membership, ownership confidence, ambiguity, and warning contracts are documented and tested;
- workspace package imports resolve correctly when explicit package/config evidence exists;
- local package dependencies resolve only when manifest dependency evidence uniquely matches a local Package Identity;
- unresolved and ambiguous package imports fail safely with candidates or warnings;
- graph-quality warning codes are structured, bounded, and surfaced without brittle prose-only assertions;
- Context Packs include package/workspace ownership only when evidence-backed;
- docs/config-focused tasks produce useful bounded orientation without source excerpts;
- common verification commands are classified by purpose and Command Risk Bucket and remain marked not run;
- new package/workspace/candidate/warning fields pass no-whole-source-disclosure negative tests;
- expanded Context Pack Evaluation fixtures pass their expectation gates;
- existing v0.3/v0.3.1 Context Pack and artifact-budget behavior does not regress;
- at least one real JS/TS workspace dogfooding report has been captured and any important findings have been distilled into fixtures or known limitations;
- full verification passes.

Recommended verification gate:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
uv run repolens evaluate-context --json
uv build --out-dir /tmp/repolens-dist --clear
```

## Follow-Up Track

After v0.4, consider a smaller adoption-focused release:

```text
RepoLens v0.4.1 or v0.5: Make RepoLens easy to install and adopt.
```

Potential scope:

- PyPI publishing preparation;
- Docker registry publishing preparation;
- installed CLI smoke tests in release CI;
- MCP setup polish;
- clearer assistant setup templates.

This should follow graph-quality work unless installation and setup are the current adoption blocker. Better distribution will expose graph-quality gaps to more users, so v0.4 should harden real-repository accuracy first.
