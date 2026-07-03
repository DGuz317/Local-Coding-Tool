# RepoLens v0.6 Release Tracker

Issue: #162

Status: proposed scope for v0.6 implementation after maintainer approval.

References:

- `AGENTS.md`
- `CONTEXT.md`
- `docs/adr/0006-layered-code-intelligence-engine.md`
- `docs/repolens-real-world-code-intelligence-roadmap.md`
- `docs/repolens-v0.5-release-tracker.md`
- `docs/known-limitations.md`
- `docs/repolens-v0.6-issue-breakdown-feedback.md`

## Theme

```text
Real JS/TS Parser And Resolver Upgrade: parser-backed JS/TS structure, richer resolver evidence, bounded framework hints, and better assistant orientation without runtime certainty or source disclosure.
```

RepoLens v0.6 should make JavaScript and TypeScript application structure meaningfully more accurate by replacing shallow regex-oriented extraction with a real parser-backed path and by upgrading resolver evidence while preserving the v0.5 safety model.

## Goal

Improve RepoLens' ability to understand real JS/TS workspaces and framework-heavy repositories without claiming runtime certainty.

v0.6 should improve Assistant Preflight and Context Packs for JS/TS tasks with richer deterministic metadata:

- parser-backed JS/TS modules, imports, exports, and top-level symbols;
- source-free Call Chain Facts;
- better import, export, alias, and workspace resolution outcomes;
- bounded Framework Route Hints;
- clearer Relationship Candidates and Graph Quality Warnings;
- improved Impact Analysis evidence for assistant orientation.

## v0.6 Maintainer Decisions

- Create one parent tracker issue plus all 8 child implementation and release issues.
- Child issues remain blocked until their listed dependencies complete.
- Use Next.js App Router as the first concrete Framework Route Hint fixture.
- Keep the Framework Route Hint contract generic and deterministic.
- Use Tree-sitter JS/TS as the default parser backend when dependency and grammar support are available.
- Fall back to the legacy bounded JS/TS scanner when Tree-sitter is unavailable, and emit a clear parser-backend warning.
- Promote only source-free structural parser facts into the stable graph contract.
- Keep experimental parser-only facts out of Canonical Graph Hash and default Context Pack IDs until explicitly promoted.
- Do not add AI graph facts, embeddings, Kuzu, CFG/data-flow, active workflows, command execution, or write-capable MCP tools in v0.6.

## Stable JS/TS Parser Fact Contract

v0.6 must define which Tree-sitter-extracted JS/TS facts are promoted into the stable graph contract.

Stable facts may include:

- repo-relative file path;
- language and extension;
- parser backend status;
- parser backend name, parser package version, grammar version where available, and promoted fact schema version;
- import/export fact kind;
- normalized import target or package root;
- top-level symbol kind and name;
- source-free line range metadata;
- evidence label and confidence category.

Stable facts must not include:

- source snippets;
- full source expressions;
- function signatures;
- raw comments;
- raw config values;
- full import lines;
- code bodies;
- absolute host paths.

Assistant-facing output may include normalized package names, repo-relative paths, normalized import targets, and route paths derived from file structure. It must not include full source expressions, full import lines, string-literal source snippets, raw config values, or code bodies.

Experimental parser-only facts must remain excluded from Canonical Graph Hash and default Context Pack IDs until explicitly promoted by a tracker decision and covered by contract tests.

Parser or promoted fact schema changes must force reparse of affected JS/TS files.

## Framework Route Hint Contract

Framework Route Hints are deterministic assistant-orientation metadata derived from local file, config, and parser evidence.

They are not runtime route proof, framework emulation, compiler output, bundler output, or package-manager resolution.

The first v0.6 fixture targets Next.js App Router patterns, including:

- `app/**/page.tsx` as likely page route hints;
- `app/**/layout.tsx` as likely layout/app-shell hints;
- `app/api/**/route.ts` as likely API route handler hints.

Route hints should include:

- repo-relative path;
- normalized route path derived from file structure where possible;
- evidence labels;
- confidence category;
- line range when parser-backed evidence is available;
- warning metadata for ambiguous or unsupported patterns.

Route hints must not become definitive runtime route edges unless future evidence is explicit, deterministic, and separately approved.

## Success Criteria

v0.6 is successful when RepoLens can index representative JS/TS workspaces and framework-shaped fixtures with better parser-backed orientation while preserving all v0.5 disclosure, artifact, and read-only guarantees.

Release success requires evidence that:

- Tree-sitter JS/TS extraction produces stable parser-backed facts for supported source files;
- current stable JS/TS behavior is preserved or deliberately changed with fixture coverage;
- Parser Backend Contract still protects Canonical Graph Hash and Context Pack IDs from unpromoted experimental facts;
- Call Chain Facts are source-free structural metadata and not framework semantic claims;
- import alias, export, re-export, CommonJS, TypeScript path alias, and workspace package resolver outcomes use stable evidence and outcome labels;
- ambiguous or unsupported resolver cases produce Relationship Candidates and Graph Quality Warnings instead of definitive edges;
- Next.js App Router route hints are deterministic hints only, not runtime framework emulation;
- Assistant Preflight and Context Packs improve JS/TS first-read files, related tests, warnings, and impact context;
- generated artifacts and assistant-facing output still contain no source snippets, code bodies, function signatures, raw comments, raw config values, raw Agent Guidance text, or absolute host paths;
- default MCP remains read-only and does not execute commands.

## Accepted Features

v0.6 accepts these slices:

- v0.6 roadmap, release gates, dependency order, and non-goals;
- Tree-sitter JS/TS backend behind the Parser Backend Contract;
- parser parity fixtures for current JS/TS modules, imports, exports, top-level symbols, and line ranges;
- source-free Call Chain Facts;
- resolver upgrade for JS/TS import/export/alias/workspace outcomes;
- Relationship Candidate and Graph Quality Warning coverage for ambiguous JS/TS resolution;
- generic Framework Route Hint contract with a Next.js App Router fixture;
- Impact Analysis and Assistant Preflight ranking improvements from richer JS/TS evidence;
- Context Pack Evaluation cases for parser/resolver improvements;
- artifact audit and no-disclosure regression coverage for new facts;
- v0.6 docs, dogfooding, and release readiness.

## Dependency Order

Approved issue flow:

```text
#162 -> #163
#162 -> #164
#163, #164 -> #165
#164 -> #166
#165, #166 -> #167
#165, #166 -> #168
#167, #168 -> #169
#163, #164, #165, #166, #167, #168, #169 -> #170
```

Only unblocked implementation issues should receive `ready-for-agent`.

Issue #162 is the HITL scope-control issue. Issues #163 through #169 are AFK implementation or evaluation slices. Issue #170 is the final HITL release-readiness slice.

## Child Issues

| Issue | Title | Type | Blocked by |
| --- | --- | --- | --- |
| #163 | Add Tree-sitter JS/TS Parser Backend | AFK | #162 |
| #164 | Test-Lock JS/TS Parser Parity And Stable Fact Promotion | AFK | #162 |
| #165 | Add Source-Free Call Chain Facts | AFK | #163, #164 |
| #166 | Upgrade JS/TS Resolver Outcomes For Imports, Exports, Aliases, And Workspaces | AFK | #164 |
| #167 | Add Framework Route Hint Contract And Next.js App Router Fixture | AFK | #165, #166 |
| #168 | Improve Impact Analysis And Preflight With v0.6 JS/TS Evidence | AFK | #165, #166 |
| #169 | Add v0.6 Dogfood And Context Evaluation Pack | AFK | #167, #168 |
| #170 | v0.6 Docs, Artifact Safety, And Release Readiness | HITL | #163 through #169 |

## Non-Goals

Do not add these in v0.6 unless a maintainer explicitly changes the product boundary:

- hosted service;
- telemetry;
- browser UI or graph visualization;
- embeddings or vector search;
- write-capable MCP tools;
- runtime package-manager, bundler, compiler, framework, or test execution during indexing, Context Pack generation, preflight, or artifact audit;
- runtime package registry lookups;
- LLM-generated graph facts;
- AI Proposals or AI Summary features;
- CFG, reaching definitions, data-flow, or taint analysis;
- Kuzu implementation or public multi-store support;
- parse cache or worker-pool indexing without measured parser throughput pressure and separate approval;
- HTTP API or HTTP MCP serving;
- active workflows or command execution;
- assistant memory or persisted assistant sessions;
- broad framework or language expansion beyond the approved Next.js App Router fixture;
- full framework runtime resolution;
- definitive graph edges from ambiguous aliases, framework conventions, chained calls, or folder-name package guesses;
- source snippets, code bodies, function signatures, raw comments, paragraph excerpts, raw config values, raw Agent Guidance instruction text, or absolute host paths in assistant-facing output.

## Release Gates

Before v0.6 release readiness, run the full verification gate:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
uv run repolens evaluate-context --json
uv run repolens audit-artifacts . --json
uv build --out-dir /tmp/repolens-dist --clear
```

The release gate must include:

- parser backend regression coverage;
- JS/TS parser parity coverage;
- parser provenance and parser-version freshness coverage;
- resolver evidence taxonomy coverage;
- call-chain no-disclosure coverage;
- Next.js App Router route hint coverage;
- Impact Analysis and Assistant Preflight evaluation coverage;
- artifact audit evidence;
- dogfood evidence;
- bounded local parser timing and file-count evidence;
- known limitations update;
- regression coverage for v0.3, v0.3.1, v0.4, and v0.5 safety contracts.

## Maintainer Checkpoints

This tracker is the v0.6 scope-control checkpoint. Maintainer approval is required before AFK implementation slices receive `ready-for-agent`.

After #162 is merged and accepted, downstream v0.6 slices may be unblocked according to the dependency order above.
