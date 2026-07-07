# RepoLens v0.7 Release Tracker

Issue: #180

Status: approved scope and release gates for v0.7 implementation.

References:

- `AGENTS.md`
- `CONTEXT.md`
- `docs/adr/0006-layered-code-intelligence-engine.md`
- `docs/repolens-real-world-code-intelligence-roadmap.md`
- `docs/repolens-v0.6-release-tracker.md`
- `docs/known-limitations.md`

## Theme

```text
RepoLens v0.7: Python Semantic Analysis Prototype
```

RepoLens v0.7 is a narrow Python-first semantic analysis prototype. It proves that RepoLens can derive source-free function-level control-flow and lexical binding metadata while keeping the trusted stable graph deterministic, portable, and source-safe.

## Goal

Move RepoLens from structural repository metadata toward deeper code intelligence without promoting semantic facts into the default trusted graph.

v0.7 should demonstrate that experimental Python semantic facts can be:

- derived deterministically from local source during indexing or explicit debug inspection;
- stored separately from stable graph facts;
- inspected through a JSON-first CLI surface;
- evaluated with expectation-based fixtures;
- audited for source and secret disclosure;
- excluded from default assistant-facing identity and output until explicitly promoted.

## Approved Scope

v0.7 accepts these implementation slices:

- Python function-level control-flow graph facts for bounded, supported constructs;
- Python lexical binding facts for local names, imports, parameters, assignments, and references where deterministic evidence exists;
- structured semantic warnings for unsupported, uncertain, dynamic, or intentionally skipped constructs;
- a separate semantic artifact store, preferably `.repolens/semantic.sqlite`;
- an optional deterministic `semantic.jsonl` debug and evaluation export;
- `repolens semantic-inspect` as the primary inspection and evaluation surface;
- deterministic semantic fixture evaluation for CFG, binding, warnings, and no-disclosure checks;
- artifact audit coverage proving semantic artifacts do not mirror source code;
- documentation of supported facts, limitations, and release gates.

Optional Context Pack semantic hints may be included only if the semantic schema proves stable enough. They are not required for v0.7 release readiness.

## Experimental Semantic Fact Contract

Semantic facts are experimental metadata outside the trusted stable graph contract.

They must be:

- source-free;
- deterministic;
- opt-in for assistant-facing use;
- stored outside stable `graph.sqlite`;
- portable across machines through repo-relative POSIX paths;
- explicit about unsupported, uncertain, or unresolved constructs.

Semantic facts may include compact metadata such as file path, function identity, stable semantic IDs, line ranges, CFG block IDs, CFG edge kinds, local binding names, binding roles, reference roles, provenance labels, warning codes, and confidence categories.

Semantic facts must not include source snippets, code bodies, raw comments, full expressions, function signatures, raw docstrings, raw string literals, raw config values, raw secrets, absolute host paths, or large document excerpts.

## Artifact Rules

Semantic facts must live outside stable `graph.sqlite`. The preferred store is:

```text
.repolens/semantic.sqlite
```

The semantic store is an experimental artifact. It must not be required for stable graph reads, default MCP tools, stable graph validation, or Context Pack identity.

An optional `semantic.jsonl` file may exist only as a deterministic debug and evaluation export. It must be bounded, source-free, and audit-covered. It is not the stable semantic database contract.

Semantic facts are explicitly excluded from:

- Canonical Graph Hash;
- default Context Pack IDs;
- stable graph validation;
- default MCP output;
- default Assistant Preflight output;
- default Context Pack output.

Promotion into any stable graph or default assistant-facing contract requires a later explicit tracker decision, schema contract update, and regression tests.

## CLI Contract

`semantic-inspect` is the primary v0.7 debugging and evaluation surface.

By default, `semantic-inspect` reads indexed semantic artifacts:

```bash
uv run repolens semantic-inspect path/to/file.py --json
```

If indexed semantic artifacts are missing, stale, or incompatible, the command must report artifact status and freshness rather than silently parsing live source.

Live source parsing is allowed only through explicit debug mode:

```bash
uv run repolens semantic-inspect path/to/file.py --from-source --json
```

`--from-source` is a non-persistent live parse mode for debugging. It must not update `graph.sqlite`, `.repolens/semantic.sqlite`, Canonical Graph Hash inputs, default Context Pack IDs, or default MCP output.

## Dependency Order

Approved issue flow:

```text
#180 -> semantic fact contract and storage slice
#180 -> semantic-inspect CLI slice
semantic fact contract and storage slice -> Python CFG and binding extraction slices
Python CFG and binding extraction slices -> deterministic semantic evaluation slice
semantic-inspect CLI slice, semantic evaluation slice -> docs, artifact audit, and release readiness slice
optional Context Pack semantic hints -> only after schema and audit evidence are stable
```

Only unblocked implementation issues should receive `ready-for-agent`. Optional Context Pack enrichment must not block v0.7 if the CLI and evaluation path proves the semantic layer safely enough.

## Non-Goals

Do not add these in v0.7 unless a maintainer explicitly changes the product boundary:

- data-flow analysis;
- taint analysis;
- reaching definitions beyond bounded lexical binding facts;
- whole-program semantic analysis;
- Kuzu implementation or public multi-store support;
- AI-generated graph facts, AI summaries, embeddings, or vector search;
- active workflows, command execution, or write-capable MCP tools;
- JS/TS semantic analysis;
- cross-language semantic analysis;
- runtime framework behavior;
- package-manager, bundler, compiler, or framework execution during indexing;
- hosted services, telemetry, browser UI, or graph visualization;
- default MCP semantic output;
- source-code mirroring in artifacts or assistant-facing output.

## Release Gates

v0.7 can ship without optional Context Pack semantic hints if all required gates pass:

- `semantic-inspect` reads indexed semantic artifacts by default and reports missing, stale, or incompatible artifacts explicitly;
- `--from-source` is explicit, non-persistent, and isolated from stable graph artifacts and default assistant-facing identity;
- semantic facts are stored separately from stable graph facts, preferably in `.repolens/semantic.sqlite`;
- deterministic Python CFG and lexical binding evaluation passes for committed fixtures;
- unsupported or uncertain constructs produce warnings, unresolved statuses, or unsupported markers instead of guessed facts;
- semantic facts remain excluded from Canonical Graph Hash, default Context Pack IDs, stable graph validation, default MCP output, default Assistant Preflight output, and default Context Pack output;
- artifact audit proves semantic artifacts and assistant-facing output contain no source snippets, code bodies, function signatures, raw comments, raw docstrings, raw string literals, raw secrets, raw Agent Guidance text, or absolute host paths;
- relevant local verification commands pass before release readiness.

Before v0.7 release readiness, run the relevant verification gate:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
uv run repolens evaluate-context --json
uv run repolens audit-artifacts . --json
uv build --out-dir /tmp/repolens-dist --clear
```

Release approval is satisfied only when the required semantic CLI, artifact separation, deterministic evaluation, stable identity exclusion, and artifact no-disclosure checks are documented with passing evidence. Optional Context Pack semantic enrichment may defer to a later v0.7.x or v0.8 slice without blocking v0.7.
