# RepoLens

RepoLens describes a repository as a local, deterministic graph so coding assistants can inspect structure and plan safe read-only queries before editing.

## Language

**Impact Analysis**:
Graph-derived edit-planning context for a target, grouped by likely dependencies, dependents, tests, docs, configs, commands, and risks. It is not a claim about runtime reachability or execution certainty.
_Avoid_: Runtime impact, guaranteed affected files

**Context Pack**:
A bounded, task-scoped bundle of repository orientation that gives an assistant the smallest useful set of files, symbols, tests, docs, configs, commands, risks, reasons, and confidence signals needed before editing. It may use Impact Analysis as evidence, but it is broader than target-based impact and should orient by references and summaries rather than source snippets.
_Avoid_: Full context dump, source preview bundle, renamed impact analysis

**Context Pack ID**:
A deterministic identifier for a Context Pack, derived from the graph state, normalized task, focus hints, and budget parameters so follow-up queries can refer to the same scoped orientation without session memory.
_Avoid_: Session ID, random pack handle, persisted context snapshot

**Context Pack Schema Contract**:
The explicit assistant-facing shape of a Context Pack, including required fields, item kinds, support groups, budgets, truncation, handles, confidence, and envelope expectations. It should be changed deliberately rather than emerging accidentally from implementation.
_Avoid_: Implicit response shape, ad hoc pack payload

**Context Pack Ranking Contract**:
The deterministic rules for ordering Context Pack items from task matches, graph evidence, confidence, category priority, and stable tie-breakers. It must not depend on randomness, time, environment state, or AI reranking.
_Avoid_: Best-effort ordering, adaptive ranking, hidden scoring

**Item Handle**:
A safe deterministic reference to an item returned inside a Context Pack, used for follow-up expansion or relevance explanation. It must not expose raw task text, source content, secret-like values, or assistant session state.
_Avoid_: Serialized item payload, session handle, source-bearing handle

**Structural Summary**:
A deterministic summary of repository structure for a repo, package, directory, file, symbol, or test group, built from graph facts, relationships, reasons, and freshness signals rather than generated prose or source excerpts.
_Avoid_: AI summary, source excerpt, prose digest

**Context Budget**:
The bounded size contract for assistant-facing context, enforced with deterministic item and character caps and reported with approximate token estimates. It is not tied to a model-specific tokenizer.
_Avoid_: Exact token contract, unlimited context, model-specific budget

**Context Pack Evaluation**:
A local quality check for Context Packs using representative tasks, expected relevant files or tests where known, and deterministic metrics such as first-read hit rate, irrelevant file count, test inclusion, pack size, and expansion count.
_Avoid_: Telemetry, subjective-only dogfooding, hosted evaluation

**Deprioritized Context**:
Evidence-backed repository context that appears lower priority for the current task and may be inspected later if needed. It is not a claim that a file, package, or relationship is irrelevant or safe to ignore absolutely.
_Avoid_: Ignore list, irrelevant files, safe-to-skip proof, hard deprioritization

**Agent Guidance**:
Repository-authored instructions that constrain how assistants should work in the codebase. Context Packs may surface its presence as bounded metadata, but not as instruction text.
_Avoid_: Assistant prompt dump, hidden policy text

**Progressive Disclosure**:
The assistant workflow of starting with a small Context Pack and expanding selected items through bounded, reproducible follow-up queries. It should not require RepoLens to remember assistant session state.
_Avoid_: One-shot context dump, session-dependent expansion

**Task Matching**:
Deterministic matching from a natural-language task to graph facts using lexical normalization, indexed repository metadata, and graph expansion. Ambiguous or fuzzy matches remain candidates rather than asserted relationships.
_Avoid_: Semantic embedding match, AI intent classification, inferred synonym relationship

**First-Read File**:
A file recommended as one of the first places an assistant should inspect for a task, with attached reasons, confidence, relevant symbols, and supporting relationships. It is the primary ranked unit inside a Context Pack.
_Avoid_: Mixed-node rank item, guaranteed edit file

**Risk Signal**:
A graph-derived warning that a file or relationship may require extra care for a task, represented by location, category, reason, confidence, and evidence rather than source text. It is not proof that an edit is unsafe.
_Avoid_: Risk excerpt, guaranteed hazard, source comment dump

**Target Expansion**:
The bounded step that broadens a selected target to the directly contained analysis nodes needed for useful graph queries. It must not become traversal through parent containers or sibling nodes.
_Avoid_: Container traversal, sibling expansion

**MCP Response Envelope**:
The standard assistant-facing wrapper around every RepoLens MCP tool result, carrying the result, trust signals, freshness, limits, and any recoverable problem details in a predictable shape.
_Avoid_: Ad hoc MCP payload, raw tool result

**Selective Update**:
An update that reuses unchanged graph facts, reparses changed or new files, and removes stale facts for deleted or unparseable files. It remains bounded by safety checks that can require a full rebuild.
_Avoid_: Status-only update, blind full rebuild

**Redaction Policy**:
The bounded safety rule for removing obvious secrets from RepoLens artifacts, user-provided task text, generated handles, and assistant-facing output while preserving useful repository structure. It targets high-risk secret patterns rather than ordinary paths, package names, or symbol names.
_Avoid_: Blanket redaction, raw secret exposure

**Package Boundary**:
A repository area identified as a package or workspace from explicit package/config evidence. RepoLens does not treat conventional directory names alone as package boundaries.
_Avoid_: Monorepo folder guess, implicit workspace

**Dogfooding Report**:
A release-readiness record from running RepoLens on representative local repositories, capturing graph quality issues, resolver misses, performance problems, and user experience friction. It is paired with distilled regression fixtures rather than vendored repository snapshots.
_Avoid_: Vendored repo fixture, anecdotal test run

**Release Gate**:
The minimum evidence required before shipping a RepoLens version, including automated verification, install/build smoke checks, dogfooding results, and documented limitations. It does not imply package or container publishing automation.
_Avoid_: Publish pipeline, manual-only checklist

**Edge Contract**:
The trust and provenance model attached to graph relationships, including confidence, resolution strategy, and bounded evidence. Edge-specific metadata is separate from this contract.
_Avoid_: Hidden edge metadata, unproven relationship

**Canonical Graph Hash**:
A deterministic hash of the stable structural graph contract for a repository. It excludes volatile run metadata, file-system metadata, absolute paths, export formatting, and line-only movement.
_Avoid_: Artifact hash, timestamp-sensitive hash

**Graph Validation**:
The check that generated graph artifacts satisfy hard structural and safety invariants before replacing the previous graph. Expected incompleteness is reported as quality warnings rather than corruption.
_Avoid_: Best-effort write, completeness guarantee

**Resolution Strategy**:
The canonical reason RepoLens believes a relationship or candidate connects two repository facts. Successful strategies may support graph edges; fuzzy strategies remain candidates only.
_Avoid_: Resolver status, arbitrary strategy name

**Local Resolution**:
Deterministic resolution of a reference to a scanner-approved file or symbol inside the analyzed repository. It does not emulate runtime loaders, installed environments, or framework-specific magic.
_Avoid_: Runtime resolution, environment-dependent import

**Related Test**:
A test file connected to a target by direct reference or deterministic path/name similarity. The relationship is confidence-scored and does not prove full behavioral coverage.
_Avoid_: Covering test, guaranteed regression test

**Candidate Verification Command**:
A declared repository command that may help a human or assistant verify work after review. RepoLens records it as not run and does not recommend automatic execution.
_Avoid_: Recommended command, executed check

**No Whole-Source Disclosure**:
The safety guarantee that RepoLens does not expose complete source files through artifacts or MCP tools. Scanner-approved text search may read live files but returns only bounded sanitized previews.
_Avoid_: No source reads, full-file MCP read

**Update Benchmark**:
A relative performance check comparing selective update against a full rebuild on a representative fixture. It demonstrates speedup without promising a fixed wall-clock time across machines.
_Avoid_: Absolute update SLA, anecdotal timing

**Parser Backend**:
An optional extraction implementation behind the same RepoLens graph contract. Alternative parser backends must not define the release value or destabilize the default parser path.
_Avoid_: Tree-sitter release, parser rewrite
