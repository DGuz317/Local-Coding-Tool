# v0.8 AI Proposals

RepoLens v0.8 includes an optional AI Proposal Layer for explanations and plans derived from bounded repository metadata. AI Proposals are labeled interpretations, not deterministic RepoLens facts.

## Disabled by default

AI is disabled unless each request explicitly enables it. A request without `--enable-ai` returns a structured `disabled` result. Enabling AI without naming both a provider and model returns a structured `unavailable` result. RepoLens does not select a default provider, fall back to another provider, or make a hidden provider or network call.

Normal indexing, graph queries, Context Packs, Assistant Preflight, and other MCP tools remain deterministic and do not require an AI provider.

## Provider setup and provenance

Every request must explicitly provide all three options:

```bash
uv run repolens create-ai-proposal /path/to/repo context_pack_summary \
  "Explain the authentication context" \
  --enable-ai \
  --provider test \
  --model context-pack-summary-v1 \
  --json
```

The v0.8 implementation supports only the local deterministic `test` provider. It exists to exercise the proposal contract and does not demonstrate external model quality. Unsupported provider names return `unavailable`; RepoLens never falls back to `test` or another provider.

Provider credentials, when a provider needs them, must be supplied through environment variables rather than command arguments or stored credential values. The local test provider recognizes `REPOLENS_AI_TEST_PROVIDER_TOKEN` for credential-boundary testing:

```bash
export REPOLENS_AI_TEST_PROVIDER_TOKEN="<local-test-value>"
```

RepoLens records only the environment variable name and whether it is present. It does not include the value in configuration, provider metadata, MCP or CLI output, saved proposal artifacts, or provider errors. Do not put credential values in RepoLens configuration or task text.

Every available proposal reports the explicitly selected provider and model in `provider` and `provenance`, together with proposal/input schema versions, redaction policy version, input digest, graph schema version, and relevant deterministic evidence references. This metadata identifies how the interpretation was produced without persisting the raw provider input.

## AI input boundary

The default provider input is bounded RepoLens metadata, including approved Context Pack fields, graph nodes and relationships, paths, symbols, evidence labels, warnings, confidence, line ranges, and candidate commands marked as not run. Input is packed deterministically, redacted, size-bounded, and identified by an `input_digest`.

The default input excludes:

- whole source files and source bodies;
- source snippets, raw comments, and raw Agent Guidance text;
- raw secrets and credential values;
- large raw document excerpts;
- raw provider error payloads.

The digest supports auditing; it is not a persisted copy of the prompt or raw input. An AI Proposal must not be treated as a source-reading substitute.

## Trust boundary

AI Proposals live outside the Deterministic Graph Foundation. Generating, returning, or saving one does not change:

- deterministic graph facts or graph traversal;
- Canonical Graph Hash;
- Context Pack IDs;
- Context Pack ranking or Task Matching;
- resolver behavior or Resolution Strategies;
- Package Ownership.

Proposal output distinguishes deterministic evidence from AI interpretation and includes confidence, warnings, and limitations. AI output cannot be promoted directly into a graph fact. A proposed fact requires a deterministic extractor or resolver change, evidence-backed fixtures, and normal review.

## Persistence and Artifact Safety Audit

Proposals are ephemeral by default. Without `--save`, RepoLens returns the proposal and does not create an AI Proposal artifact.

Saving requires an explicit option on that request:

```bash
uv run repolens create-ai-proposal /path/to/repo context_pack_summary \
  "Explain the authentication context" \
  --enable-ai --provider test --model context-pack-summary-v1 \
  --save --json
```

Saved proposals are written under `.repolens/ai-proposals/` and immediately checked by Artifact Safety Audit. The audit checks proposal labels and kind, input digest, provider/model provenance, safe source-disclosure metadata, credential-like provider configuration, unredacted provider errors, output labels, and artifact size. A saved proposal that fails its safety checks is reported as a failure.

To include existing saved proposals in a later audit, opt in explicitly:

```bash
uv run repolens audit-artifacts /path/to/repo --include-ai-proposals --json
```

Artifact Safety Audit is a bounded artifact-contract check, not a general secret scanner. Treat `.repolens/` as private local metadata and review it before sharing.

## Supported proposal kinds and limitations

### Context Pack Summary Proposal

`context_pack_summary` requires the task used to deterministically rebuild a Context Pack. An optional `--context-pack-id` must match that rebuilt pack.

It summarizes the bounded Context Pack metadata and evidence references. It is not a Structural Summary, does not mirror source bodies, cannot add missing repository evidence, and cannot rerank or modify the Context Pack. Sparse, stale, ambiguous, or truncated pack evidence limits the proposal.

### Architecture Explanation Proposal

`architecture_explanation` requires an unambiguous `--target` or a task-backed Context Pack:

```bash
uv run repolens create-ai-proposal /path/to/repo architecture_explanation \
  "Explain this area" --target src/repolens/ai_proposal.py \
  --enable-ai --provider test --model architecture-explanation-v1 --json
```

It explains indexed nodes, bounded neighbors, impact metadata, Relationship Candidates, and Graph Quality Warnings. It does not create architecture, dependency, ownership, route, or runtime facts. Missing semantic fact types stay missing, and unresolved or ambiguous targets return an unavailable result rather than a guessed explanation.

### Patch Plan Proposal

`patch_plan` requires a task-backed Context Pack and may include a target:

```bash
uv run repolens create-ai-proposal /path/to/repo patch_plan \
  "Document AI Proposal boundaries" --target docs/ai-proposals.md \
  --enable-ai --provider test --model patch-plan-v1 --json
```

It may propose files to inspect, an edit sequence, related tests, docs/config risks, and Candidate Verification Commands. It is planning metadata only. It does not produce an apply-ready diff, write project files, mutate branches, execute commands, apply patches, or post remote comments. Candidate commands remain not run and may be incomplete when graph evidence is sparse.

## Deferred beyond v0.8

v0.8 does not include Local Change Review, Convention, Deterministic Fact Opportunity, Ownership Hypothesis, Intent, or Test Gap proposal types. It also does not include provider fallback, broad external-provider support, raw-source prompting, remote PR review, or autonomous agents.

Active Workflow is deferred to v0.9. File writes outside explicit proposal-artifact saving, apply-ready patches, patch application, branch mutation, and command execution require a future separately enabled workflow with per-action approval. The read-only MCP surface does not gain those capabilities in v0.8.
