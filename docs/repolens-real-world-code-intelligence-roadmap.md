# RepoLens Real-World Code Intelligence Roadmap

Status: draft planning document until v0.4 release signoff and v0.5 tracker acceptance.

## Context

The earlier RepoLens direction focused heavily on deterministic, local, read-only behavior. That was appropriate for the early product foundation, especially v0.1 through v0.4.

However, if RepoLens is intended to become a real-world application, the deterministic/read-only model should be treated as the foundation, not the ceiling.

```text
v0.1-v0.4 = deterministic/read-only foundation
v0.5+     = real-world code intelligence platform
```

RepoLens should evolve from a safe assistant preflight tool into a broader local code intelligence engine for AI assistants and developers.

The v0.5 step remains assistant-first. Developer-facing workflows become first-class gradually through diagnostics, reports, local PR review, and approved active workflows.

This roadmap is planning-only until the v0.4 package/workspace release receives maintainer signoff. It should guide v0.5+ issue design without mixing new implementation work into the v0.4 release-hardening path.

Resolved planning decisions:

```text
- v0.5 theme: Code Intelligence Foundation, with Assistant Preflight as the main user-facing feature.
- Storage: add a narrow high-level internal Graph Store Seam while keeping SQLite as the artifact contract.
- Parser: formalize the Parser Backend Contract in v0.5; defer real Tree-sitter JS/TS extraction to v0.6.
- Parser parity: preserve stable fact types and safe output behavior before adding richer facts.
- Experimental-only parser facts do not affect the stable Canonical Graph Hash or default Context Pack IDs until promoted through a schema/contract change.
- Resolver: treat CodeGraph-style strategies as a Resolver Evidence Taxonomy, not a first-match guessing cascade.
- Frameworks: start with Framework Route Hints, not full runtime framework resolution.
- Semantic analysis: prototype Python function-level CFG plus local binding facts first.
- Semantic prototype facts stay in an experimental namespace until promoted by evaluation evidence.
- AI: keep AI Proposal output separate from trusted deterministic graph facts.
- Active workflows: keep default MCP read-only; use a separate opt-in local workflow surface.
- Interfaces: near-term surfaces are CLI, stdio MCP, and internal Local Service APIs only.
```

## Updated Product Principle

RepoLens should not remain only a static preflight helper.

It should become a layered system:

```text
Layer 1: deterministic graph foundation
Layer 2: semantic/code-intelligence analysis
Layer 3: AI-assisted reasoning
Layer 4: optional active workflows
```

The deterministic layer still matters because it provides the trusted ground-truth substrate. Real-world usefulness comes from the higher layers built on top of it.

## What Changes for a Real-World Application

### 1. GitNexus Becomes More Important Earlier

Previously, most GitNexus-style ideas were deferred. For a real-world application, that is too conservative.

GitNexus has the most advanced analysis stack among the three references:

- Control Flow Graph construction;
- reaching definitions;
- taint analysis;
- Kuzu graph storage;
- worker-pool parsing;
- parse cache;
- scope resolution;
- multi-branch indexing;
- PR swarm review.

For RepoLens, the priority should become:

```text
- CFG
- scope resolution
- data-flow / reaching definitions
- taint/source-sink analysis
- branch-aware freshness and explicit branch comparison metadata
- parse cache when benchmarks show a concrete need
- worker-pool indexing when parser throughput blocks adoption
- optional PR review workflow
```

This moves RepoLens from an assistant context tool toward a real code intelligence engine.

### 2. CodeGraph Remains the Practical Resolver Model

CodeGraph should provide the practical foundation for extraction, resolution, storage, context building, and impact analysis.

Take from CodeGraph:

```text
- language extractor as config
- Tree-sitter parser backend
- resolver evidence taxonomy inspired by the 10-strategy cascade
- import resolution
- path/workspace/package resolution
- framework route hints before framework-specific runtime resolution
- call-chain preservation before chained-call semantic resolution
- context ranking engine
- impact/blast-radius traversal
```

The 10-strategy resolution cascade matters because real applications are messy. Imports are ambiguous, frameworks hide edges, chained calls matter, and plain AST extraction is not enough. In RepoLens, the cascade should classify evidence strength first. Later or fuzzier strategies may produce Relationship Candidates and Graph Quality Warnings unless they satisfy explicit evidence rules for definitive graph edges.

Example chain that RepoLens should eventually understand:

```python
User.objects.filter(active=True).select_related("profile").get(id=user_id)
```

A shallow parser may only see `get()`. A useful code intelligence engine needs to preserve and resolve the full chain.

RepoLens should first preserve a source-free Call Chain Fact. Resolving that chain into Django, SQLAlchemy, or other framework/library semantics should remain candidate or hint output until fixture evidence proves the relationship is deterministic.

### 3. Graphify Becomes the Product and Integration Model

Graphify is strongest as an assistant-facing product and integration surface.

Take from Graphify:

```text
- clean staged pipeline
- MCP server ergonomics
- assistant skill files later, after MCP/CLI preflight stabilizes
- community detection later, after graph facts are richer
- repo-level analysis reports
- multiple export/adoption paths
- simple graph traversal tools
```

Graphify's staged architecture remains a good product skeleton:

```text
detect → extract → build → resolve → cluster → analyze → export
```

RepoLens should not copy every Graphify export format or add clustering before evidence shows it improves guidance. It should first copy the assistant-first product shape and staged pipeline.

## New RepoLens Target Architecture

```text
RepoLens
  ├── Parser Layer
  │   ├── Python AST
  │   ├── Tree-sitter JS/TS
  │   ├── dogfood-gated Tree-sitter language expansion
  │   └── evidence-gated parser cache
  │
  ├── Semantic Graph Layer
  │   ├── files
  │   ├── symbols
  │   ├── imports / exports
  │   ├── packages / workspaces
  │   ├── routes / entrypoints
  │   ├── configs / commands
  │   └── docs / tests
  │
  ├── Resolver Layer
  │   ├── same-file resolution
  │   ├── import resolution
  │   ├── package/workspace resolution
  │   ├── framework route hints
  │   ├── call-chain preservation
  │   ├── framework resolution candidates
  │   ├── chained-call resolution candidates
  │   └── type/scope-aware resolution
  │
  ├── Advanced Analysis Layer
  │   ├── CFG
  │   ├── reaching definitions
  │   ├── data-flow
  │   ├── experimental taint candidates
  │   ├── local dependency risk signals
  │   └── branch/PR impact
  │
  ├── AI Layer
  │   ├── AI Summaries
  │   ├── convention inference
  │   ├── local PR review reports
  │   ├── architecture Q&A
  │   ├── patch planning
  │   └── optional AI Proposals
  │
  ├── Active Workflow Layer
  │   ├── generate patch plans
  │   ├── produce diff proposals
  │   ├── run approved commands
  │   ├── compare branches
  │   ├── produce local PR review reports
  │   └── produce reports
  │
  │   Note: active workflows are opt-in local workflows, not default MCP write tools.
  │
  └── Interfaces
      ├── MCP
      ├── CLI
      └── internal local service APIs
```

## Deterministic Becomes Core, Not Ceiling

Use this model:

```text
Deterministic facts:
- file paths
- symbols
- imports
- call edges
- package relationships
- parser evidence
- config facts

Probabilistic / AI facts:
- AI Summaries
- intent and query expansion proposals
- ownership proposals
- convention inference
- risk explanation
- patch strategy
- local PR review findings
- test gap proposals
```

The rule should be:

```text
AI can enrich, explain, rank, propose, and review.
The trusted graph stores deterministic evidence and provenance.
AI output remains a labeled AI Proposal; trusted graph facts require deterministic extractor/resolver changes and tests, not direct AI promotion.
AI inputs default to bounded RepoLens metadata and approved Context Pack output, not raw source text.
AI is disabled by default; external providers require explicit user configuration and provider/model provenance.
Default Context Packs remain deterministic; AI and experimental semantic output require opt-in enrichment or separate tools.
```

This allows RepoLens to become more powerful without corrupting the trusted graph foundation.

## Storage Direction

For a conservative local MCP tool, SQLite is enough.

For a real-world application, RepoLens should introduce a storage abstraction now:

```text
Graph Store Seam
  ├── SQLite-backed implementation now
  └── Kuzu evaluation later, only when a concrete query need exists
```

This avoids hard-coding the product around SQLite-only assumptions.

Kuzu is relevant because Cypher-style path queries, branch-scoped graph queries, and data-flow paths are more natural in a property graph database.

Recommended direction:

```text
v0.5-v0.6: SQLite remains the artifact contract; add only a narrow internal seam
v0.7+: evaluate Kuzu only if branch/data-flow path queries create concrete pressure
```

Do not migrate storage immediately unless there is a concrete query or scale problem that SQLite cannot handle.

Kuzu evaluation should require measured fixture or dogfood evidence for a release-relevant branch, data-flow, or path query. Architectural preference alone is not sufficient.

## Revised Roadmap

### v0.5 — Code Intelligence Foundation

Instead of only assistant preflight, v0.5 should become:

```text
v0.5: Code Intelligence Foundation
```

Include:

```text
- Assistant Preflight as the main user-facing workflow
- Parser Backend Contract and parity fixtures
- Resolver Evidence Taxonomy
- narrow Graph Store Seam
- MCP context improvements
- focus_hints / budget controls
- artifact safety audit
- local savings metrics in Context Pack Evaluation
```

Goal:

```text
Prepare RepoLens for real-world parser, resolver, graph, and AI expansion without breaking the current foundation, while proving value through one bounded preflight workflow.
```

### v0.6 — Real Parser + Resolver Upgrade

Borrow heavily from CodeGraph.

```text
- Tree-sitter JS/TS
- preserve Call Chain Facts
- import alias resolution through the resolver evidence taxonomy
- workspace/package resolution
- dogfood-driven Framework Route Hint contract and first fixture
- chained-call resolution candidates
- better Impact Analysis evidence without runtime certainty claims
```

Goal:

```text
Improve RepoLens' ability to understand real application structure, especially JS/TS workspaces and framework-heavy codebases.
```

### v0.7 — GitNexus-Style Semantic Analysis

Borrow from GitNexus.

```text
- Python function-level CFG prototype
- lexical binding facts for local names
- explicit experimental query/evaluation surface
- reaching definitions after CFG + bindings
- data-flow edges after reaching definitions
- experimental taint source/sink registry and candidates after data-flow
- branch-aware freshness and explicit branch comparison metadata
```

Goal:

```text
Move from structural code graph to semantic code intelligence through a narrow Python-first CFG + binding prototype before reaching definitions, data-flow, taint, or broad cross-language expansion.
```

### v0.8 — AI-Assisted Layer

Add optional LLM features without making the core graph dependent on AI.

```text
- optional AI Summaries as AI Proposals
- convention inference
- architecture explanations
- local PR review reports
- patch plans
- graph fact proposals marked as AI Proposals, not confirmed graph facts
```

Goal:

```text
Let AI enrich and explain graph facts while keeping deterministic evidence, provenance, and promotion boundaries clear.
```

### v0.9 — Active Workflows

Add controlled active behavior.

```text
- optional command execution with per-action approval
- patch plans and diff proposals before file writes
- branch comparison
- local PR review mode
- CI/test recommendation
- opt-in local workflow surface outside default read-only MCP
```

Goal:

```text
Move from code intelligence to assisted development workflows.
```

Default MCP remains read-only. Candidate Verification Commands remain discovered commands with `run: false`; they are not automatic execution requests.

Approval means a dry-run plan plus explicit per-action approval for each file write or command execution. Higher-risk commands require an exact-command override rather than inheriting approval from a broader plan.

RepoLens should not promise command sandboxing in this roadmap. Approved commands run in the user's local environment; known deploy, publish, destructive, or external-side-effect commands are denied by default unless exactly overridden.

## Updated Priority From the Three Repositories

```text
1. CodeGraph: practical extraction, resolution, context, impact
2. GitNexus: semantic analysis, data-flow, branch-aware intelligence
3. Graphify: assistant/product integration, MCP ergonomics, reports, skills
```

This is different from a purely safe MCP preflight roadmap. For a real-world application, CodeGraph and GitNexus should drive the core engine, while Graphify should guide the product and assistant integration experience.

## What RepoLens Should Not Over-Focus On

Do not over-focus on:

```text
- deterministic-only behavior as the product ceiling
- report generation as the final product
- shallow static graph only
- SQLite-only assumptions
- regex-only JS/TS parsing
- assistant preflight as the whole product
```

Those were good constraints for early versions. They should not permanently restrict the application.

## What RepoLens Should Still Preserve

Even as RepoLens becomes more powerful, preserve these principles:

```text
- local-first operation
- evidence-backed graph facts
- clear provenance
- explicit confidence levels
- safe defaults
- default read-only MCP
- no hidden telemetry
- AI-generated output is labeled as AI Proposal output
- active workflows require explicit opt-in and per-action approval
- generated artifacts avoid leaking secrets/source mirrors
```

The product can become more capable without becoming unsafe or opaque.

## Bottom Line

RepoLens should become:

```text
A local code intelligence engine for AI assistants and developers.
```

It should start from deterministic graph facts, add semantic analysis, then add optional AI and active workflows with provenance and approval.

The target is not only:

```text
"Tell the assistant what files to read first."
```

The larger target is:

```text
"Understand the repo deeply enough to help plan, review, explain, and safely execute real development work."
```
