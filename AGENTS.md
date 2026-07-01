# [AGENTS.md](http://AGENTS.md)

## Project Overview

RepoLens MCP is a local-first repository intelligence backend for AI coding assistants.

The tool indexes a repository, builds deterministic graph artifacts under `.repolens`, and exposes read-only MCP tools so assistants can understand repo structure, related files, likely impact, candidate verification commands, and bounded Context Packs before opening source files.

RepoLens must remain:

- deterministic;
- local-first;
- metadata-oriented;
- safe by default;
- read-only through MCP;
- useful for reducing assistant token usage and file exploration.

## Agent skills

### Issue tracker

Issues and PRDs are tracked in GitHub Issues for this repo. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the default triage role labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, and `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repo using root `CONTEXT.md` and root `docs/adr/`. See `docs/agents/domain.md`.

## Current Release Focus: v0.5

v0.5 theme:

```text
Code Intelligence Foundation: one cheap, safe, bounded Assistant Preflight workflow backed by parser, resolver, graph-store, evaluation, and artifact-safety contracts.
```

The main implementation goal is to give assistants one deterministic, read-only preflight workflow before broad repository reads while defining the internal contracts needed for future parser, resolver, graph, semantic, and AI expansion.

v0.5 work should improve:

- Parser Backend Contract and experimental hash boundaries;
- Resolver Evidence Taxonomy and candidate outcome tracing;
- narrow high-level Graph Store Seam while keeping SQLite as the artifact contract;
- Assistant Preflight contract, CLI, and MCP tool;
- deterministic focus hints and budget controls;
- local savings metrics in `evaluate-context`;
- artifact safety audit;
- install and adoption polish after preflight stabilizes;
- dogfood evaluation pack and final release readiness evidence.



## Non-Negotiable Product Boundaries

Do not add any of the following unless a maintainer explicitly changes the product boundary:

- hosted service;
- telemetry;
- browser UI or graph visualization;
- embeddings or vector search;
- LLM-generated graph facts;
- runtime package-manager, bundler, compiler, or framework execution during indexing;
- runtime package registry lookups;
- write-capable MCP tools;
- persisted assistant sessions or server-side assistant memory;
- whole-source disclosure;
- source snippets;
- code bodies;
- function signatures in assistant-facing Context Pack output;
- paragraph excerpts;
- raw comments;
- raw Agent Guidance instruction text.

RepoLens may emit compact metadata, paths, node names, evidence labels, line ranges, warnings, and bounded orientation facts.

## v0.4 Evidence Rules

Prefer being incomplete over being wrong.

Package/workspace ownership must only appear when backed by explicit graph evidence.

Acceptable evidence sources include:

- `package.json` package identity;
- workspace declarations;
- package manager workspace config;
- explicit local package entrypoint metadata;
- supported lockfile evidence only when it clearly maps to local workspace packages;
- scoped `tsconfig.json` `paths` and `baseUrl` evidence.

Do not infer package ownership from directory names alone.

Examples of unsafe inference:

```text
packages/foo -> package foo
apps/web -> package web
src/lib -> package lib
```

These may become candidates, but not definitive ownership facts, unless explicit package/config evidence supports them.

## Resolution Rules

When implementing or modifying resolvers:

- resolve only from deterministic local evidence;
- keep unresolved imports unresolved when evidence is insufficient;
- preserve ambiguous relationships as bounded candidates;
- emit graph-quality warnings for unsupported, ambiguous, or unresolved resolver cases;
- do not create false definitive graph edges;
- do not silently pick one candidate from multiple plausible matches.

Use this default behavior:

```text
unique explicit evidence -> graph edge
multiple plausible matches -> candidates + warning
unsupported pattern -> warning
no evidence -> unresolved
```



## Context Pack Rules

Context Packs are assistant-facing orientation artifacts, not source mirrors.

Context Packs may include:

- relevant files;
- package/workspace ownership facts;
- mentioned paths;
- related configs;
- package references;
- command metadata;
- graph-quality warnings;
- reasons and evidence labels;
- bounded reading order.

Context Packs must not include:

- source code snippets;
- code bodies;
- raw Markdown paragraphs;
- raw config values when unnecessary;
- raw comments;
- raw Agent Guidance text;
- large Markdown dumps.

For docs/config tasks, prefer structured metadata such as:

```text
mentioned path -> resolved file
config file -> related package/tool/command
package reference -> evidence-backed package node or candidate
command -> found/not run + risk bucket
warning -> unresolved/ambiguous/unsupported case
```



## Candidate Verification Command Rules

RepoLens finds commands. It does not run them.

All Candidate Verification Commands must remain clearly marked as:

```text
found: true
run: false
```

Classify command risk separately from command purpose.

Recommended risk buckets:

```text
verification_likely
quality_check_likely
build_likely
risky_or_external
unknown
```

Examples:

```text
pytest                 -> verification_likely
uv run pytest          -> verification_likely
npm test               -> verification_likely
make test              -> verification_likely
make verify            -> verification_likely
ruff check .           -> quality_check_likely
mypy src/repolens      -> quality_check_likely
npm run build          -> build_likely
uv build               -> build_likely
npm publish            -> risky_or_external
docker push            -> risky_or_external
terraform apply        -> risky_or_external
unknown custom command -> unknown
```

Do not recommend automatic execution of deploy, publish, release, destructive, infrastructure-mutating, or external side-effect commands.

## Issue Workflow

Work one GitHub issue slice at a time.

Do not start a blocked issue.

Expected v0.5 issue flow:

```text
#138 -> #139
#138 -> #140
#138 -> #141
#139, #140 -> #142
#142 -> #143
#143 -> #144
#143 -> #145
#143, #144 -> #146
#143, #144 -> #147
#143, #144, #145, #146 -> #148
#139, #140, #141, #142, #143, #144, #145, #146, #147, #148 -> #149
```

Issue #138 and Issue #149 are HITL slices.

Issue #138 defines the v0.5 scope, dependency order, release gates, and non-goals. Downstream implementation should not proceed until #138 is merged and accepted.

v0.4 release signoff remains a prerequisite for AFK v0.5 implementation work. Issue #128 records that signoff and must stay complete before #139 through #148 are treated as unblocked.

Use `ready-for-agent` only when an issue is unblocked and has complete acceptance criteria.

## Implementation Style

Keep changes small and vertical.

Prefer:

- explicit contracts;
- typed data structures;
- deterministic ordering;
- narrow fixtures;
- expectation-based tests;
- simple explainable algorithms;
- warning/candidate output over guessing.

Avoid:

- broad refactors;
- hidden behavior changes;
- new runtime dependencies without justification;
- large parser rewrites;
- speculative framework support;
- source-content mirroring;
- changing public artifact shape without tests.

CLI handlers should stay thin. Put reusable behavior in framework-independent services.

MCP tools must remain read-only.

Generated artifacts must be deterministic and portable across machines.

Use repo-relative POSIX paths in artifacts and MCP responses.

Do not expose absolute paths unless they are internal-only.

## Testing Expectations

Add or update tests for every behavior change.

v0.5 tests should cover:

- parser backend parity and experimental hash boundaries;
- resolver evidence taxonomy and outcome labels;
- relationship candidates and graph-quality warnings for ambiguous evidence;
- high-level graph-store seam smoke behavior;
- Assistant Preflight CLI and MCP response contracts;
- deterministic focus hints and budget limits;
- graph freshness, stale graph, no match, broad task, and ambiguity cases;
- candidate commands discovered but not run;
- local savings metrics and explanation of estimates;
- artifact audit disclosure and safety failures;
- Context Pack and preflight no-disclosure behavior;
- v0.3, v0.3.1, and v0.4 regression protection.

Prefer fixture repositories that are minimal and purpose-built.

Tests should assert observable behavior, not incidental implementation details.

## Verification Commands

Run focused tests while developing.

Before considering a v0.5 implementation slice complete, run the relevant subset of:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
```

Before release readiness, the full recommended gate is:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
uv run repolens evaluate-context --json
uv build --out-dir /tmp/repolens-dist --clear
```

If a command cannot be run in the current environment, report it clearly with the reason.

## Documentation Expectations

Update docs when behavior changes.

For v0.5, docs should clearly explain:

- assistants should call preflight before broad file reads;
- CLI and MCP preflight usage;
- deterministic focus hints and budget controls;
- graph freshness and stale graph handling;
- candidate commands as discovered but not run;
- local savings metrics as estimates, not telemetry or universal productivity claims;
- artifact audit behavior and disclosure boundaries;
- Context Pack and preflight disclosure boundaries;
- known limitations.

Known limitations are acceptable. Silent overclaiming is not.

## Security And Privacy Rules

RepoLens must not read or emit secret-like files.

Do not add unsafe include-secret behavior.

Sanitize command strings and metadata that may contain credentials.

Do not expose raw `.env`, key, token, credential, or secret-like content.

Do not introduce network calls during normal indexing or Context Pack generation.

Do not introduce telemetry.

## Git And PR Rules

Keep commits scoped to the issue.

Use concise area-prefixed commit messages, for example:

```text
resolver: add workspace package candidate warnings
context: omit raw config values from docs packs
eval: add ambiguous package ownership fixture
commands: classify risky verification candidates
```

Do not mix unrelated cleanup with feature work.

A final agent response or PR summary should include:

- what changed;
- why it changed;
- how it affects RepoLens flow;
- tests run;
- tests not run, with reasons;
- known risks or follow-ups.



## Default Decision Rule

When evidence is incomplete, preserve uncertainty.

Use:

```text
candidate
warning
unresolved
unsupported
```

instead of inventing a definitive graph fact.

RepoLens should help assistants open fewer files while trusting the graph more.
