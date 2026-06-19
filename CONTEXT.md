# RepoLens

RepoLens describes a repository as a local, deterministic graph so coding assistants can inspect structure and plan safe read-only queries before editing.

## Language

**Impact Analysis**:
Graph-derived edit-planning context for a target, grouped by likely dependencies, dependents, tests, docs, configs, commands, and risks. It is not a claim about runtime reachability or execution certainty.
_Avoid_: Runtime impact, guaranteed affected files

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
The bounded safety rule for removing obvious secrets from RepoLens artifacts and assistant-facing output while preserving useful repository structure. It targets high-risk secret patterns rather than ordinary paths, package names, or symbol names.
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
