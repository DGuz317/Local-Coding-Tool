# RepoLens Domain Context

RepoLens describes a repository as a local, evidence-backed code intelligence graph so coding assistants and developers can understand, plan, review, and eventually act on repository knowledge without losing provenance or safety boundaries.

## Purpose

This file defines the shared product language for RepoLens planning, issues, ADRs, and implementation discussions. It is a glossary and boundary document, not a release plan, API specification, or approval to implement every future layer.

Use versioned planning documents under `docs/` for release scope. Use this file to keep those plans consistent about what RepoLens terms mean, what each term avoids, and where deterministic graph facts end before semantic prototypes, AI Proposals, or active workflows begin.

## Planning Status

Terms involving Code Intelligence Engine, AI Proposal Layer, AI Proposal, Semantic Analysis Prototype, Active Workflow, Graph Store Seam, Assistant Preflight, Framework Route Hint, and related future layers are proposed planning language until accepted by the relevant ADR and version tracker. They do not loosen current implementation guardrails.

## Glossary

**Code Intelligence Engine**:
A local system that helps assistants and developers understand, plan, review, and safely act on repository knowledge. In RepoLens, it is broader than assistant preflight but remains grounded in evidence-backed repository facts.
_Avoid_: Static preflight helper, hosted code intelligence service

**Deterministic Graph Foundation**:
The trusted layer of RepoLens facts derived from local repository evidence with stable provenance, ordering, and safety boundaries. Higher-level semantic, AI-assisted, or active workflow features may build on it but must not silently replace it.
_Avoid_: Deterministic-only product ceiling, AI-generated ground truth

**Impact Analysis**:
Graph-derived edit-planning context for a target, grouped by likely dependencies, dependents, tests, docs, configs, commands, and risks. Future semantic facts may add evidence, but Impact Analysis is still not a claim about runtime reachability, execution certainty, or guaranteed affected files.
_Avoid_: Runtime impact, guaranteed affected files

**Semantic Analysis Prototype**:
A narrow, evidence-backed experiment that derives deeper code relationships such as control-flow or lexical binding facts for a bounded language and scope before promoting the model across RepoLens. The first intended slice is Python function-level CFG plus local binding facts in an experimental semantic namespace, not a complete cross-language semantic graph or default traversal input.
_Avoid_: Full semantic graph, runtime behavior proof

**Call Chain Fact**:
Source-free structural metadata that preserves the receiver and method chain of a fluent or chained call expression. It is an extraction fact, not proof that RepoLens has resolved framework or library runtime semantics.
_Avoid_: Framework semantic edge, ORM behavior proof

**Context Pack**:
A bounded, task-scoped bundle of repository orientation that gives an assistant the smallest useful set of files, symbols, tests, docs, configs, commands, risks, reasons, and confidence signals needed before editing. Default Context Packs remain deterministic; semantic prototype facts or AI Proposals may appear only through opt-in enrichment sections or separate tools with explicit provenance.
_Avoid_: Full context dump, source preview bundle, renamed impact analysis

**Assistant Preflight**:
A single bounded orientation step an assistant runs before broad file reads or edits, combining graph freshness, task context, warnings, first-read files, likely tests, and candidate commands. It is a user-facing workflow built on RepoLens facts, not an AI reasoning layer.
_Avoid_: Autonomous planning agent, source-reading substitute

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

**AI Proposal Layer**:
The optional v0.8 layer that asks an explicitly configured AI provider to explain, review, rank, or propose from bounded RepoLens metadata while keeping every result outside the trusted deterministic graph.
_Avoid_: Chatbot product layer, default AI dependency, AI-owned graph

**AI Proposal Contract**:
The stable output boundary for AI-derived material, including proposal kind, proposal schema version, provider/model provenance, input boundary, source-disclosure status, evidence references, confidence labels, warnings, limitations, input packer version, redaction policy version, input digest, graph schema version, and Canonical Graph Hash. It must make the distinction between deterministic evidence and AI interpretation visible to callers without persisting raw AI input by default.
_Avoid_: Free-form AI prose, hidden provider metadata, unlabeled generated output, raw prompt archive

**AI Proposal**:
A labeled, optional AI-derived suggestion, explanation, ranking, review proposal, patch plan, convention proposal, deterministic fact opportunity, ownership hypothesis, or task-intent proposal that is not part of the trusted deterministic graph. It may inform deterministic extractor/resolver changes or regression fixtures, but it does not become graph truth through direct promotion.
_Avoid_: Confirmed graph fact, hidden AI inference, unlabeled summary

**Context Pack Summary Proposal**:
A labeled AI Proposal that summarizes an existing Context Pack from bounded RepoLens metadata and approved context. It is separate from Structural Summary, must not mirror source bodies, and must not change Context Pack ID, ranking, or deterministic graph facts.
_Avoid_: Structural Summary, source digest, confirmed graph fact, hidden reranking

**Architecture Explanation Proposal**:
A labeled AI Proposal that explains how a repository area, package, file group, or Context Pack fits into the broader system using deterministic evidence references and explicit limitations. It is explanatory orientation, not a source of new graph relationships.
_Avoid_: Architecture fact, runtime behavior proof, undocumented ownership claim

**AI Input Boundary**:
The default rule that optional AI features consume bounded RepoLens metadata and approved Context Pack output rather than raw source text. Source text may be used only through an explicit scoped approval path and must not be persisted as raw AI artifact content.
_Avoid_: Silent source upload, source-mirroring AI cache, default raw-code prompt

**AI Provider Boundary**:
The rule that AI features are disabled by default and make no hidden network calls. External providers may be used only through explicit local configuration, with credentials supplied by environment variables, credential values kept out of RepoLens config and artifacts, provider errors redacted, and provider/model provenance attached to AI Proposal output.
_Avoid_: Built-in hosted dependency, hidden telemetry, artifact-stored credential, provider fallback

**AI Proposal Persistence Boundary**:
The rule that AI Proposals are returned ephemerally by default. Saving AI Proposal artifacts requires an explicit save option and saved proposals must pass Artifact Safety Audit without storing raw source-bearing inputs, credentials, or unredacted provider errors.
_Avoid_: Implicit AI cache, source-bearing proposal archive, automatic `.repolens` accumulation

**Ownership Hypothesis**:
A labeled AI Proposal or candidate explanation about which package or area may be responsible for a path when definitive Package Ownership evidence is unavailable. It is not Package Ownership and must not participate in definitive ownership traversal.
_Avoid_: Likely ownership, inferred package owner, AI-owned package

**Convention Proposal**:
A labeled AI Proposal that suggests a repository convention, such as likely test placement, area naming, documentation location, or review pattern, from bounded RepoLens metadata. It must not silently change deterministic task matching, Context Pack ranking, resolver behavior, ownership, or graph traversal.
_Avoid_: Deterministic convention rule, hidden ranking input, inferred resolver behavior

**Deterministic Fact Opportunity**:
A labeled AI Proposal that describes a possible missing or improved deterministic graph fact, relationship, warning, or fixture opportunity. It is a candidate for future human review and deterministic implementation, not a traversable edge or trusted artifact fact.
_Avoid_: AI-promoted graph edge, low-confidence fact, hidden graph mutation

**Docs/Config Orientation**:
Structured metadata that helps an assistant navigate documentation and configuration tasks through paths, links, mentions, package references, commands, ownership facts, and warnings. It excludes paragraph excerpts, raw comments, raw instruction text, and raw configuration value dumps.
_Avoid_: Documentation excerpt, config preview, instruction dump

**Context Budget**:
The bounded size contract for assistant-facing context, enforced with deterministic item and character caps and reported with approximate token estimates. It is not tied to a model-specific tokenizer.
_Avoid_: Exact token contract, unlimited context, model-specific budget

**Context Pack Evaluation**:
A local quality check for Context Packs using representative tasks, expected relevant files or tests where known, and deterministic metrics such as first-read hit rate, irrelevant file count, test inclusion, pack size, and expansion count.
_Avoid_: Telemetry, subjective-only dogfooding, hosted evaluation

**Local Savings Metric**:
A deterministic evaluation measure that compares RepoLens orientation output against a local baseline such as lexical search, using fixture expectations or dogfood-derived cases. It estimates avoided exploration cost; it is not telemetry or a universal productivity score.
_Avoid_: Hosted analytics, exact token savings claim, productivity metric

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

**Intent Proposal**:
A labeled AI Proposal that suggests alternate task interpretations, query expansions, or likely search terms for opt-in enrichment. It must not silently change default Task Matching, Context Pack ranking, or Context Pack IDs.
_Avoid_: Default task match, AI-ranked context, hidden query expansion

**First-Read File**:
A file recommended as one of the first places an assistant should inspect for a task, with attached reasons, confidence, relevant symbols, and supporting relationships. It is the primary ranked unit inside a Context Pack.
_Avoid_: Mixed-node rank item, guaranteed edit file

**Risk Signal**:
A graph-derived warning that a file or relationship may require extra care for a task, represented by location, category, reason, confidence, and evidence rather than source text. It is not proof that an edit is unsafe.
_Avoid_: Risk excerpt, guaranteed hazard, source comment dump

**Local Dependency Risk Signal**:
A Risk Signal derived from local repository evidence such as manifests, lockfiles, package relationships, ambiguous workspace dependencies, or risky scripts. It is not an external vulnerability advisory or package-registry lookup.
_Avoid_: Vulnerability scan, hosted advisory lookup, dependency risk score

**Taint Candidate**:
An experimental Risk Signal that a configured local source may influence a configured local sink through evidence such as reaching-definition or data-flow facts. It is not a vulnerability finding or external security advisory.
_Avoid_: Confirmed vulnerability, security scanner finding, advisory match

**Target Expansion**:
The bounded step that broadens a selected target to the directly contained analysis nodes needed for useful graph queries. It must not become traversal through parent containers or sibling nodes.
_Avoid_: Container traversal, sibling expansion

**MCP Response Envelope**:
The standard assistant-facing wrapper around every RepoLens MCP tool result, carrying the result, trust signals, freshness, limits, and any recoverable problem details in a predictable shape.
_Avoid_: Ad hoc MCP payload, raw tool result

**Local Service API**:
A framework-independent internal service boundary used by RepoLens CLI and MCP surfaces. It is not an HTTP server, hosted API, browser UI, or public network interface.
_Avoid_: HTTP API, hosted service, UI backend

**Selective Update**:
An update that reuses unchanged graph facts, reparses changed or new files, and removes stale facts for deleted or unparseable files. It remains bounded by safety checks that can require a full rebuild.
_Avoid_: Status-only update, blind full rebuild

**Branch-Aware Freshness**:
Graph freshness context that accounts for the Git branch and commit associated with the indexed artifacts. It can support explicit branch comparison metadata, but it does not imply automatic multi-branch graph storage.
_Avoid_: Multi-branch graph index, hidden branch checkout

**Local Change Review Proposal**:
A local read-only AI Proposal that reviews an explicit branch, diff, changed-path set, or graph snapshot comparison using RepoLens facts. It may include review proposals, test gap proposals, related tests, candidate verification commands, risks, and graph warnings, but it does not post remote PR comments, call hosting-provider APIs, run commands, mutate branches, or assert confirmed defects.
_Avoid_: GitHub bot review, remote PR mutation, hosted review service, automatic command execution, confirmed defect report

**Redaction Policy**:
The bounded safety rule for removing obvious secrets from RepoLens artifacts, user-provided task text, generated handles, and assistant-facing output while preserving useful repository structure. It targets high-risk secret patterns rather than ordinary paths, package names, or symbol names.
_Avoid_: Blanket redaction, raw secret exposure

**Package Boundary**:
A repository area identified as a package or workspace from explicit package/config evidence. RepoLens does not treat conventional directory names alone as package boundaries.
_Avoid_: Monorepo folder guess, implicit workspace

**Package Identity**:
A package's explicit name and ecosystem as declared by repository package or configuration evidence. It identifies a package fact without proving which files the package owns.
_Avoid_: Folder name identity, inferred package name

**Workspace Membership**:
An explicit relationship showing that a package belongs to a workspace because workspace configuration and package identity evidence agree. A workspace declaration alone is scope evidence, not confirmed ownership or membership.
_Avoid_: Monorepo convention, workspace guess

**Workspace Package Import**:
A package-style import whose target may be a local workspace package when explicit package and workspace evidence supports that relationship. If package entrypoint evidence is missing or ambiguous, RepoLens treats the relationship as candidate orientation rather than guessing a file.
_Avoid_: External-only package import, convention-guessed local import

**Package Entrypoint Evidence**:
Explicit package metadata that identifies a package-facing file without executing package-manager, bundler, framework, or runtime resolution. Complex or environment-specific entrypoint rules remain candidate context rather than definitive Local Resolution.
_Avoid_: Runtime entrypoint, bundler-resolved entrypoint

**Framework Route Hint**:
Bounded framework-specific orientation that identifies likely apps, routes, handlers, or entrypoints from local source/config evidence without emulating framework runtime behavior. Concrete framework support is dogfood-driven, and hints may become graph edges only when the source-to-symbol relationship is deterministic and explicit.
_Avoid_: Runtime route resolution, framework-emulated edge

**Package Reference**:
An exact graph-backed mention of a known package identity or declared dependency in documentation or configuration metadata. It provides navigation context without surrounding prose or raw configuration values.
_Avoid_: Fuzzy package mention, semantic entity extraction

**Package Dependency**:
An explicit manifest relationship from one package identity to another package name. It becomes a local package relationship only when the dependency name uniquely matches a local Package Identity.
_Avoid_: Folder-inferred dependency, lockfile-only local dependency

**Lockfile Evidence**:
Supporting package or dependency metadata from a lockfile. It can strengthen package relationship evidence but does not establish local package ownership without explicit package boundary evidence.
_Avoid_: Lockfile-owned package, primary ownership proof

**Package Ownership**:
An evidence-backed relationship between a repository path and the package boundary that owns it. The nearest explicit package root owns paths in a clean nested boundary chain; conflicting or colliding candidates stay unresolved rather than choosing a definitive owner.
_Avoid_: Nearest-folder ownership, import-implied ownership

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
A deterministic hash of the stable structural graph contract for a repository. It excludes volatile run metadata, file-system metadata, absolute paths, export formatting, line-only movement, and experimental-only facts that have not been promoted into the stable contract.
_Avoid_: Artifact hash, timestamp-sensitive hash

**Graph Store Seam**:
A narrow high-level internal boundary around RepoLens graph lifecycle, metadata, and query entry points that allows future storage experiments without changing the assistant-facing artifact contract. It is not a table-level abstraction and does not imply multiple supported graph stores.
_Avoid_: Public multi-store API, table abstraction, immediate storage migration

**Graph Validation**:
The check that generated graph artifacts satisfy hard structural and safety invariants before replacing the previous graph. Expected incompleteness is reported as quality warnings rather than corruption.
_Avoid_: Best-effort write, completeness guarantee

**Graph Quality Warning**:
A recoverable structured metadata notice that graph facts are incomplete, ambiguous, or limited by unsupported repository structure. It uses stable warning codes and bounded metadata; it does not mean the graph artifact is corrupt or that the user's code is risky.
_Avoid_: Validation failure, risk signal, corrupt graph

**Resolution Strategy**:
The canonical reason RepoLens believes a relationship or candidate connects two repository facts. Successful strategies may support graph edges; fuzzy strategies remain candidates only.
_Avoid_: Resolver status, arbitrary strategy name

**Resolver Evidence Taxonomy**:
An ordered set of resolver strategies that classifies how strong the evidence is for a relationship. It exposes stable strategy labels, evidence labels, outcome classes, and coarse confidence while keeping numeric weights internal; it does not allow a later or fuzzier strategy to become definitive by default.
_Avoid_: First-match resolver cascade, best-guess graph edge, public numeric resolver score

**Relationship Candidate**:
A bounded, evidence-labeled possible relationship that is useful for orientation but not trusted enough to become a graph edge. It may be surfaced in Context Packs without participating in definitive traversal or ownership claims.
_Avoid_: Low-confidence edge, hidden maybe-edge

**Local Resolution**:
Deterministic resolution of a reference to a scanner-approved file or symbol inside the analyzed repository. It does not emulate runtime loaders, installed environments, or framework-specific magic.
_Avoid_: Runtime resolution, environment-dependent import

**Alias Resolution Scope**:
The explicit configuration boundary within which an import alias may be used for Local Resolution. Alias evidence outside the applicable scope remains candidate context rather than a global rule.
_Avoid_: Global alias table, framework magic alias

**Related Test**:
A test file connected to a target by direct reference or deterministic path/name similarity. The relationship is confidence-scored and does not prove full behavioral coverage.
_Avoid_: Covering test, guaranteed regression test

**Test Gap Proposal**:
A labeled AI Proposal or evaluation finding that suggests a likely missing verification path from bounded RepoLens evidence. It does not prove that coverage is absent or that a specific test must be written.
_Avoid_: Missing-test fact, coverage proof, required test

**Candidate Verification Command**:
A declared repository command that may help a human or assistant verify work after review. RepoLens records it as not run and does not recommend automatic execution.
_Avoid_: Recommended command, executed check

**Command Risk Bucket**:
A conservative classification of a Candidate Verification Command's likely verification usefulness and execution risk. It is separate from command purpose and does not make the command safe to run automatically.
_Avoid_: Auto-run approval, command recommendation

**Active Workflow**:
An explicitly enabled local workflow that can propose edits, compare branches, or run approved commands outside the default read-only MCP surface. It requires per-action approval and auditable plans; it must not treat Candidate Verification Commands as automatic execution requests.
_Avoid_: Default MCP write tool, automatic command execution

**Patch Plan Proposal**:
A labeled AI Proposal that outlines a possible implementation sequence, target files to inspect, tests to update, risk notes, and candidate verification commands before any file write occurs. It is planning output only in v0.8; producing apply-ready diffs, writing files, or running commands belongs to an explicitly approved Active Workflow surface.
_Avoid_: Automatic edit, default MCP patch, unreviewed write, apply-ready v0.8 diff

**Workflow Approval**:
An explicit user decision for one proposed file write or command execution after reviewing a dry-run plan. It is not blanket approval for a session, and high-risk commands require exact-command override rather than inheriting approval from a broader plan.
_Avoid_: Session permission, implicit command approval, plan-wide execution grant

**Command Execution Boundary**:
The future Active Workflow rule that approved commands run in the user's local environment with conservative risk classification and explicit approval. RepoLens does not imply sandboxing, and known deploy, publish, destructive, or external-side-effect commands are denied by default unless exactly overridden.
_Avoid_: Sandboxed guarantee, automatic verification run, safe-by-class command

**No Whole-Source Disclosure**:
The safety guarantee that RepoLens does not expose complete source files through artifacts or MCP tools. Scanner-approved text search may read live files but returns only bounded sanitized previews.
_Avoid_: No source reads, full-file MCP read

**Artifact Safety Audit**:
A local deterministic check that RepoLens-generated artifacts and representative assistant-facing envelopes obey disclosure, redaction, size, path, and not-run command invariants. It is not a general-purpose source secret scanner.
_Avoid_: Secret scanner, hosted audit, source compliance scan

**Update Benchmark**:
A relative performance check comparing selective update against a full rebuild on a representative fixture. It demonstrates speedup without promising a fixed wall-clock time across machines.
_Avoid_: Absolute update SLA, anecdotal timing

**Performance Escalation Gate**:
The rule that parse caches, worker pools, and similar indexing-performance complexity are added only when benchmark or dogfood evidence shows current indexing blocks adoption or correctness workflows.
_Avoid_: Premature parallelism, speculative cache layer

**Parser Backend**:
An optional extraction implementation behind the same RepoLens graph contract. Alternative parser backends must not define the release value or destabilize the default parser path.
_Avoid_: Tree-sitter release, parser rewrite

**Parser Backend Contract**:
The stable boundary that says which graph facts a parser backend must produce, how parser status is reported, and how experimental extraction proves parity before it can affect default behavior. Parity means preserving stable fact types, safe output behavior, and equivalent deterministic identities where feasible; richer facts require explicit contract additions and fixtures.
_Avoid_: Parser implementation, grammar migration
