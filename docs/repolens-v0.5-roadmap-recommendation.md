# RepoLens v0.5 Roadmap Recommendation

Status: draft planning document until v0.4 release signoff and v0.5 tracker acceptance.

## Recommended Next Version Theme

**v0.5: Code Intelligence Foundation — one cheap, safe, bounded Assistant Preflight workflow backed by parser, resolver, graph-store, evaluation, and artifact-safety contracts.**

This theme keeps RepoLens aligned with its core product goal: reduce repeated assistant repository exploration while preparing the engine for real parser, resolver, graph, semantic, and AI expansion. v0.5 should remain local-first, deterministic by default, read-only through MCP, bounded, and safe.

v0.5 remains assistant-first. Developer-facing commands should support setup, audit, evaluation, and debugging, while richer developer workflows such as architecture reports and local PR review reports come later.

## Finish Before v0.5

Before starting v0.5 feature work, finish a small v0.4.1 release-hardening pass.

### v0.4.1 Scope

Do not add new product behavior in v0.4.1. Keep it focused on release readiness.

Required release gate:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
uv run repolens evaluate-context
uv build
```

Additional required work:

1. Run at least one real JS/TS workspace dogfood report.
2. Update docs still referencing v0.3, especially `docs/assistant-usage-guide.md`.
3. Verify package/workspace graph behavior against the v0.4 acceptance criteria.
4. Cut v0.4 as the **“trustworthy package/workspace graph”** release.

## What To Add In v0.5

### 1. Code Intelligence Foundation Contracts

Add the internal contracts needed before v0.6+ parser/resolver/storage expansion:

- Parser Backend Contract and parity fixtures;
- Resolver Evidence Taxonomy;
- narrow Graph Store Seam that keeps SQLite as the artifact contract;
- default-deterministic Context Pack behavior with opt-in enrichment reserved for later;
- explicit exclusions for Tree-sitter implementation, Kuzu, AI Proposals, active workflows, and HTTP/UI in v0.5.

Goal:

> Make future expansion deliberate without destabilizing the v0.4 graph and Context Pack contracts.

### 2. Assistant Preflight Tool

This should be the highest-value v0.5 feature.

Add one MCP and CLI flow that combines:

- `graph_status`
- `get_task_context`
- warnings
- first-read files
- likely tests
- candidate commands
- stale graph risk
- artifact safety warnings

Suggested CLI command:

```bash
repolens preflight "task description"
```

Suggested MCP tool:

```text
assistant_preflight
```

Goal:

> Give the assistant one cheap, bounded context call before it starts broad file reads.

Expected output should include:

- graph freshness status;
- task-relevant context pack summary;
- recommended first files to open;
- likely related tests;
- relevant commands discovered but not run;
- warnings and limitations;
- confidence/evidence metadata;
- truncation and budget metadata.

### 3. Better MCP Controls

Expose `focus_hints` and budget controls through MCP `get_task_context` and/or `assistant_preflight`, not only through the Python service.

Example MCP input:

```json
{
  "task": "Update auth session expiry behavior",
  "focus_hints": ["src/auth/session.py", "tests/auth"],
  "budget": {
    "max_first_read_files": 8,
    "max_items_per_support_group": 5,
    "max_total_chars": 12000,
    "include_tests": true,
    "include_commands": true
  }
}
```

This helps assistants ask precise questions such as:

> “I am probably editing `src/auth/session.py`; give me only tight context.”

The result should reduce unnecessary repo scanning while still surfacing enough context to avoid wrong edits.

### 4. Local Savings Metrics

Extend the existing local evaluation runner first, rather than adding a standalone command immediately:

```bash
repolens evaluate-context
```

Report fields:

- files avoided versus lexical search baseline;
- Context Pack size;
- first-read file count;
- likely irrelevant file count;
- likely token savings;
- stale graph risk;
- commands found but not run;
- warnings included;
- whether output stayed within budget.

Goal:

> Prove RepoLens’ core value: cheaper, faster, safer assistant work.

### 5. Artifact Safety Audit

Add an artifact audit command:

```bash
repolens audit-artifacts /repo
```

The audit should verify:

- no source snippets are copied into artifacts;
- no absolute host paths are exposed;
- no raw secrets are present;
- no raw Agent Guidance text is mirrored;
- no oversized graph artifacts are produced;
- candidate commands are clearly marked as discovered but not run;
- MCP outputs obey the response contract;
- stale warnings, confidence, evidence, limits, and truncation metadata are present where expected.

This should become a v0.5 release gate.

### 6. Install And Adoption Polish

Add practical adoption improvements:

- setup diagnostics such as `repolens doctor` if accepted by the tracker;
- PyPI publishing readiness checks;
- Docker image smoke test;
- copy-paste MCP configs for OpenCode;
- copy-paste MCP configs for Claude Desktop;
- copy-paste MCP configs for Cursor-style clients;
- clearer docs saying assistants should call RepoLens first.

Do not ship assistant skill files in v0.5. Treat them as later adoption artifacts after the preflight API stabilizes across clients.

Do not let publishing polish block the core v0.5 feature if preflight is ready first.

### 7. Real-Repo Evaluation Pack

Expand evaluation from small fixtures to dogfood-derived scenarios without vendoring large repositories.

Recommended scenarios:

- JS/TS monorepo;
- Python package repository;
- docs-heavy repository;
- config-heavy repository;
- ambiguous imports;
- stale graph update flow;
- workspace package import flow;
- artifact safety audit flow.

The goal is not broad benchmark coverage yet. The goal is to catch real assistant-preflight misses.

## What Not To Add Yet

Do not add these in v0.5:

- embeddings or vector search;
- browser UI;
- hosted service;
- telemetry;
- write-capable MCP tools;
- runtime package-manager, bundler, compiler, or framework execution;
- LLM-generated graph facts;
- AI Proposals or AI Summary features;
- real Tree-sitter JS/TS extraction;
- Kuzu or public multi-store support;
- parse cache or worker-pool indexing without benchmark evidence;
- HTTP API or HTTP MCP serving;
- active workflows or command execution;
- assistant memory or session persistence;
- broad framework/language expansion unless dogfood data proves it is necessary.

## Suggested v0.5 Issue Breakdown

Each issue should include short slice-specific guardrails and link to `AGENTS.md`, `docs/adr/0006-layered-code-intelligence-engine.md`, and this roadmap. Do not paste the entire global boundary list into every issue.

Acceptance criteria should be observable checkboxes grouped around contract/docs updates, tests or fixture expectations, CLI/MCP behavior where applicable, safety/no-disclosure preservation, and focused verification commands. Avoid implementation-step checklists unless the step itself is externally observable.

Verification should be focused per slice: list the relevant pytest target, `uv run ruff check .`, and `uv run ruff format --check .` when files change. Type-affecting code should also list `uv run mypy src/repolens`. The final HITL release-readiness slice should run the full gate, including `uv run pytest`, `uv run repolens evaluate-context --json`, artifact audit, and build.

If these slices are published to GitHub, use a `v0.5` milestone when available. Label Issue 1 and Issue 12 as HITL/release-gate, label Issues 2 through 11 as AFK, and apply `ready-for-agent` only after v0.4 signoff and the dependency chain permits the slice.

### 1. v0.5 Roadmap, Release Gates, And Non-Goals

**Type:** HITL  
**Blocked by:** None  
**Purpose:** Tracker and scope-control issue.

This issue should define:

- v0.5 release theme;
- release gates;
- accepted features;
- explicit non-goals;
- docs that must be updated;
- dogfood/evaluation expectations.

### 2. Parser Backend Contract And Experimental Hash Gate

**Type:** AFK  
**Blocked by:** Issue 1  
**Purpose:** Define and test-lock Parser Backend Contract parity before real Tree-sitter implementation.

Should include:

- Parser Backend Contract and parity expectations;
- Canonical Graph Hash behavior for experimental-only facts;
- parser status and no-disclosure expectations;
- narrow tests or contract modules for behavior that already exists;
- no real Tree-sitter JS/TS extraction in v0.5.

### 3. Resolver Evidence Taxonomy Contract With Candidate Outcome Tracer

**Type:** AFK  
**Blocked by:** Issue 1  
**Purpose:** Define and test-lock resolver outcome labels without introducing best-guess graph edges.

Should include:

- stable strategy labels and evidence labels;
- outcome classes for edge, candidate, unresolved, unsupported, and ambiguous cases;
- coarse confidence only, with numeric weights kept internal;
- at least one tracer expectation proving ambiguous evidence remains a Relationship Candidate and Graph Quality Warning.

### 4. High-Level Graph Store Seam Smoke

**Type:** AFK  
**Blocked by:** Issue 1  
**Purpose:** Define and smoke-test the narrow high-level storage seam while keeping SQLite as the artifact contract.

Should include:

- graph lifecycle, metadata, and query-entry boundaries;
- no table-level abstraction;
- no public multi-store API;
- no Kuzu implementation;
- smoke coverage proving existing query/artifact behavior stays unchanged.

### 5. Assistant Preflight Contract With Focus And Budget Controls

**Type:** AFK  
**Blocked by:** Issues 1, 2, and 3  
**Purpose:** Define the CLI/MCP output contract before implementation.

Should include:

- response envelope;
- graph freshness section;
- first-read files section;
- likely tests section;
- candidate commands section;
- warnings and limits section;
- evidence and confidence fields;
- deterministic focus hint and budget controls;
- default-deterministic Context Pack behavior with opt-in enrichment reserved for later;
- golden fixture outputs.

### 6. Implement `repolens preflight` CLI

**Type:** AFK  
**Blocked by:** Issue 5  
**Purpose:** Add the user-facing CLI flow.

The CLI should combine:

- graph status;
- task context;
- first-read files;
- likely tests;
- candidate commands;
- warnings;
- budget metadata.

### 7. Expose MCP `assistant_preflight`

**Type:** AFK  
**Blocked by:** Issues 5 and 6  
**Purpose:** Expose the same preflight service through MCP.

Requirements:

- read-only behavior;
- capped output;
- structured response envelope;
- stale graph warnings;
- no source-file reading beyond existing graph/artifact contracts;
- deterministic output.

### 8. Add Local Savings Metrics To `evaluate-context`

**Type:** AFK  
**Blocked by:** Issues 5 and 6  
**Purpose:** Extend `evaluate-context` with local evidence that RepoLens reduces exploration cost.

Should report:

- files avoided;
- Context Pack size;
- likely irrelevant file count;
- estimated token savings;
- stale graph risk;
- commands found but not run.

### 9. Add Artifact Safety Audit

**Type:** AFK  
**Blocked by:** Issues 6 and 7  
**Purpose:** Add `repolens audit-artifacts` and safety tests.

Audit should detect:

- source snippet leakage;
- absolute host paths;
- raw secrets;
- oversized artifacts;
- raw Agent Guidance mirroring;
- MCP contract violations.

### 10. Install And Adoption Polish

**Type:** AFK  
**Blocked by:** Issues 6 and 7  
**Purpose:** Make v0.5 easier to use in real assistant workflows.

Should include:

- setup diagnostics if accepted by the tracker;
- Docker smoke test;
- PyPI readiness check;
- OpenCode MCP config example;
- Claude Desktop MCP config example;
- Cursor-style MCP config example.

### 11. Dogfood Evaluation Pack

**Type:** AFK  
**Blocked by:** Issues 6, 7, 8, and 9  
**Purpose:** Validate preflight behavior on realistic scenarios.

Scenarios:

- JS/TS workspace;
- Python package;
- docs-heavy repo;
- config-heavy repo;
- ambiguous import task;
- stale graph task;
- package/workspace graph task.

### 12. v0.5 Docs, Dogfooding, And Release Readiness

**Type:** HITL  
**Blocked by:** Issues 2 through 11  
**Purpose:** Update assistant-facing docs and make the final release judgment.

Docs should clearly explain:

- assistants should call preflight first;
- how to use CLI preflight;
- how to use MCP preflight;
- what preflight does not guarantee;
- how stale graph warnings should be handled;
- how candidate commands should be interpreted.

Release readiness should include full verification, dogfood evidence, artifact audit evidence, and maintainer signoff.

## Draft v0.5 Issue Bodies

### Issue 1: v0.5 Roadmap, Release Gates, And Non-Goals

**Type:** HITL  
**Blocked by:** None

#### What to build

Approve the v0.5 scope as Code Intelligence Foundation with Assistant Preflight as the main user-facing workflow. Define release gates, accepted slices, dependency order, and non-goals before any AFK implementation starts.

#### Guardrails

This is planning and release-scope work only. Do not implement v0.5 behavior in this slice. Keep v0.4 release signoff as a prerequisite for v0.5 implementation.

#### Acceptance criteria

- [ ] v0.5 theme, accepted features, non-goals, and release gates are documented.
- [ ] The dependency order for Issues 2 through 12 is approved.
- [ ] The plan links to `AGENTS.md`, ADR 0006, and the v0.5 roadmap.
- [ ] The plan explicitly keeps default MCP read-only and AI/active workflow features out of v0.5.

#### Verification

- Documentation review only.

### Issue 2: Parser Backend Contract And Experimental Hash Gate

**Type:** AFK  
**Blocked by:** Issue 1

#### What to build

Define and test-lock the Parser Backend Contract so future Tree-sitter work can prove parity without destabilizing stable graph facts, Canonical Graph Hash, or Context Pack IDs.

#### Guardrails

Do not implement real Tree-sitter JS/TS extraction. Do not let experimental-only facts affect the stable Canonical Graph Hash or default Context Pack IDs.

#### Acceptance criteria

- [ ] Parser Backend Contract parity expectations are documented or encoded in a contract module.
- [ ] Existing stable parser behavior remains the default.
- [ ] Experimental-only facts are excluded from stable hash and default Context Pack identity until promoted by a contract change.
- [ ] Tests cover parser status, fallback behavior, and hash stability expectations.

#### Verification

- `uv run pytest tests/test_parser_backends.py`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src/repolens` if code types change.

### Issue 3: Resolver Evidence Taxonomy Contract With Candidate Outcome Tracer

**Type:** AFK  
**Blocked by:** Issue 1

#### What to build

Define resolver strategy labels and outcome classes so richer resolution can classify evidence without turning fuzzy matches into graph edges.

#### Guardrails

Do not expose public numeric resolver scores. Do not add best-guess graph edges. Ambiguous evidence must remain candidates plus warnings.

#### Acceptance criteria

- [ ] Resolver Evidence Taxonomy labels and outcome classes are documented or encoded in a contract module.
- [ ] Public output uses stable labels, evidence labels, outcome classes, and coarse confidence only.
- [ ] A tracer fixture proves ambiguous evidence becomes a Relationship Candidate and Graph Quality Warning, not a definitive edge.
- [ ] Existing package/workspace resolution behavior remains regression-protected.

#### Verification

- Focused resolver/package-workspace pytest target added by the slice.
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src/repolens` if code types change.

### Issue 4: High-Level Graph Store Seam Smoke

**Type:** AFK  
**Blocked by:** Issue 1

#### What to build

Introduce or document a narrow high-level Graph Store Seam around graph lifecycle, metadata, and query entry points while preserving `.repolens/graph.sqlite` as the artifact contract.

#### Guardrails

Do not create a table-level abstraction, public multi-store API, Kuzu implementation, or artifact path change.

#### Acceptance criteria

- [ ] The Graph Store Seam boundary is documented or represented by a narrow internal interface.
- [ ] SQLite remains the only concrete graph store and the complete graph artifact contract.
- [ ] Existing graph build, status, export, and query behavior remains unchanged.
- [ ] Smoke tests prove query-service reads and artifact replacement still work through the new seam or documented boundary.

#### Verification

- `uv run pytest tests/test_graph_store.py tests/test_query_service.py`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src/repolens` if code types change.

### Issue 5: Assistant Preflight Contract With Focus And Budget Controls

**Type:** AFK  
**Blocked by:** Issues 1, 2, and 3

#### What to build

Define the Assistant Preflight contract shared by CLI and MCP, including graph freshness, task context, first-read files, likely tests, candidate commands, warnings, deterministic focus hints, and deterministic budget controls.

#### Guardrails

Do not implement AI enrichment, semantic prototype output, source snippets, model-specific token budgets, or write-capable MCP behavior.

#### Acceptance criteria

- [ ] Assistant Preflight schema is documented with envelope, freshness, limits, evidence, warnings, and truncation metadata.
- [ ] Focus hints and budget controls use deterministic item/character caps rather than model-specific token budgets.
- [ ] Golden fixture expectations cover happy path, stale graph, broad task, ambiguity, no match, candidate commands, and no-source-disclosure behavior.
- [ ] Default Context Pack behavior remains deterministic and opt-in enrichment is reserved for later.

#### Verification

- Focused Context Pack/preflight contract pytest target added by the slice.
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src/repolens` if code types change.

### Issue 6: Implement `repolens preflight` CLI

**Type:** AFK  
**Blocked by:** Issue 5

#### What to build

Add the user-facing CLI command that gives assistants one bounded orientation call before broad file reads or edits.

#### Guardrails

Do not run candidate commands, read source beyond existing graph/context contracts, or add AI/semantic enrichment.

#### Acceptance criteria

- [ ] `repolens preflight` returns graph freshness, task context summary, first-read files, likely tests, candidate commands, warnings, confidence/evidence, and budget metadata.
- [ ] JSON and human output follow the preflight contract.
- [ ] Missing or stale graph states return bounded actionable output.
- [ ] Candidate Verification Commands remain marked discovered and not run.

#### Verification

- Focused CLI preflight pytest target added by the slice.
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src/repolens` if code types change.

### Issue 7: Expose MCP `assistant_preflight`

**Type:** AFK  
**Blocked by:** Issues 5 and 6

#### What to build

Expose the same Assistant Preflight service through the default read-only stdio MCP server.

#### Guardrails

Default MCP remains read-only. Do not add write tools, command execution, source snippets, AI enrichment, or active workflow behavior.

#### Acceptance criteria

- [ ] MCP `assistant_preflight` returns the standard MCP Response Envelope.
- [ ] MCP input supports deterministic focus hints and budget controls from the contract.
- [ ] MCP output stays capped, deterministic, source-safe, and consistent with CLI behavior.
- [ ] MCP missing-graph and stale-graph behavior is tested.

#### Verification

- Focused MCP/preflight pytest target added by the slice.
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src/repolens` if code types change.

### Issue 8: Add Local Savings Metrics To `evaluate-context`

**Type:** AFK  
**Blocked by:** Issues 5 and 6

#### What to build

Extend Context Pack Evaluation with deterministic Local Savings Metrics that compare RepoLens output against a local baseline such as lexical search.

#### Guardrails

Do not add telemetry, hosted evaluation, exact model-token claims, or productivity scoring.

#### Acceptance criteria

- [ ] Evaluation output includes local baseline comparison fields such as files avoided, first-read hit rate, likely irrelevant file count, pack size, approximate token estimate, stale graph risk, and not-run command count.
- [ ] Metrics are deterministic for committed fixtures.
- [ ] Human output explains that savings are estimates, not universal productivity claims.
- [ ] Existing release-blocking evaluation cases remain protected.

#### Verification

- `uv run pytest tests/test_context_evaluation.py`
- `uv run repolens evaluate-context --json`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src/repolens` if code types change.

### Issue 9: Add Artifact Safety Audit

**Type:** AFK  
**Blocked by:** Issues 6 and 7

#### What to build

Add a local artifact audit command that checks generated RepoLens artifacts and representative assistant-facing envelopes for disclosure and safety invariants.

#### Guardrails

Do not build a general-purpose source secret scanner. Do not upload artifacts or inspect outside the analysis root.

#### Acceptance criteria

- [ ] `repolens audit-artifacts` checks for source snippet leakage, absolute host paths, raw secret-like values, raw Agent Guidance mirroring, oversized artifacts, and MCP contract violations.
- [ ] Candidate commands are verified as discovered but not run.
- [ ] Audit output is deterministic, local, and machine-readable with a human summary.
- [ ] Negative fixtures prove audit failures are reported clearly.

#### Verification

- Focused artifact audit pytest target added by the slice.
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src/repolens` if code types change.

### Issue 10: Install And Adoption Polish

**Type:** AFK  
**Blocked by:** Issues 6 and 7

#### What to build

Improve assistant adoption and local setup around the preflight workflow.

#### Guardrails

Do not publish packages, create hosted services, ship assistant skill files, or add HTTP/UI surfaces in v0.5.

#### Acceptance criteria

- [ ] Setup diagnostics are documented or implemented if explicitly accepted by the tracker.
- [ ] Docker smoke and PyPI readiness checks are documented or automated without publishing.
- [ ] OpenCode, Claude Desktop, and Cursor-style MCP config examples are updated for preflight.
- [ ] Docs explain assistants should call preflight before broad file reads.

#### Verification

- Focused CLI/docs tests added by the slice where applicable.
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src/repolens` if code types change.

### Issue 11: Dogfood Evaluation Pack

**Type:** AFK  
**Blocked by:** Issues 6, 7, 8, and 9

#### What to build

Add dogfood-derived evaluation evidence for realistic preflight scenarios without vendoring large repositories.

#### Guardrails

Do not commit `.repolens` artifacts, vendored third-party repositories, or source excerpts. Distill dogfood findings into minimal fixtures.

#### Acceptance criteria

- [ ] Dogfood scenarios cover JS/TS workspace, Python package, docs-heavy, config-heavy, ambiguous import, stale graph, and package/workspace tasks.
- [ ] Findings are captured in dated dogfood reports and distilled fixtures or known limitations.
- [ ] Evaluation includes preflight, local savings metrics, and artifact audit evidence where relevant.
- [ ] v0.3/v0.4 safety regressions remain protected.

#### Verification

- `uv run repolens evaluate-context --json`
- Focused dogfood/evaluation pytest target added by the slice.
- `uv run ruff check .`
- `uv run ruff format --check .`

### Issue 12: v0.5 Docs, Dogfooding, And Release Readiness

**Type:** HITL  
**Blocked by:** Issues 2 through 11

#### What to build

Update release-facing docs and make the final human judgment on whether v0.5 is ready to cut.

#### Guardrails

Do not broaden v0.5 scope during release readiness. Any AI, active workflow, Tree-sitter implementation, Kuzu, HTTP/UI, or write-capable MCP work requires a separate post-v0.5 issue.

#### Acceptance criteria

- [ ] Assistant-facing docs explain CLI and MCP preflight, deterministic budget controls, stale graph handling, candidate commands, and limitations.
- [ ] Release readiness records full verification, dogfood evidence, local savings metrics, artifact audit results, and known limitations.
- [ ] README remains accurate for shipped behavior only.
- [ ] Maintainer release judgment is recorded.

#### Verification

- `uv run pytest`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src/repolens`
- `uv run repolens evaluate-context --json`
- `uv run repolens audit-artifacts . --json`
- `uv build --out-dir /tmp/repolens-dist --clear`

## Suggested Roadmap

### v0.4.1

Release hardening, docs update, dogfood report, full release gate.

### v0.5

Code Intelligence Foundation contracts, Assistant Preflight, MCP ergonomics, local savings metrics, artifact safety audit.

### v0.6

Tree-sitter JS/TS, call-chain preservation, resolver upgrades, and framework route hints only after v0.5 contracts and dogfood data identify concrete misses.

## Final Recommendation

Proceed with this sequence:

```text
v0.4.1 = harden and release v0.4
v0.5   = Code Intelligence Foundation + Assistant Preflight + MCP controls + Savings Metrics + Artifact Audit
v0.6   = real parser/resolver upgrade based on contracts and dogfood misses
```

The highest-value user-facing feature is the **Assistant Preflight Tool**. The highest-value architectural work is the narrow foundation contract set that lets RepoLens expand without breaking the v0.4 trust model.

Do not add LLM-generated graph facts yet. v0.5 should first prove that deterministic RepoLens context can reliably reduce assistant file reads before introducing any model-dependent layer.
