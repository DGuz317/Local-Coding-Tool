# RepoLens v0.8 Plan Review

Status: review feedback for `v0.8-plan.md`  
Review focus: product boundary, release scope, AI safety, deterministic graph integrity, MCP behavior, and issue sequencing.

## Overall Verdict

The v0.8 plan is strong and matches RepoLens' product direction.

I would approve the direction, with one important adjustment: **reduce the first v0.8 AI release scope** so the AI Proposal Layer is proven safely before adding higher-risk proposal types such as local PR review, convention inference, graph fact proposals, ownership hypotheses, or intent proposals.

Recommended positioning:

```text
v0.8 = optional AI proposals over bounded RepoLens metadata
v0.9 = approved active workflows and command/file-write surfaces
```

This is the right boundary.

RepoLens should continue to treat the deterministic graph, Context Pack IDs, graph hashes, resolver behavior, package ownership, and MCP read-only behavior as trusted deterministic surfaces. AI output should remain clearly labeled, optional, non-authoritative, and outside the trusted graph.

## What Is Strong

### 1. The v0.8 / v0.9 Boundary Is Correct

The plan correctly separates read-only AI assistance from active workflows.

Allowed in v0.8:

```text
- AI summaries
- architecture explanations
- local review proposals
- patch plan text
- graph fact opportunities
- test gap proposals
```

Not allowed in v0.8:

```text
- file writes
- command execution
- apply-ready patch execution
- MCP write tools
- automatic test execution
- remote PR mutation
- GitHub/GitLab bot comments
```

This boundary is important. It prevents RepoLens from moving too early from a safe code-intelligence tool into an agent runner.

### 2. AI Disabled By Default Is The Right Default

The plan correctly requires AI to be disabled by default and forbids hidden external provider calls.

This preserves the existing local-first, deterministic, no-surprise behavior that RepoLens has built through earlier versions.

Recommended rule to keep explicit:

```text
No configured provider means no AI call.
No provider fallback.
No hidden default model.
No silent network access.
```

### 3. The Metadata-Only Input Boundary Is Strong

The plan correctly uses bounded RepoLens metadata as default AI input instead of raw source files.

Allowed default inputs are appropriate:

```text
- repo-relative paths
- symbol names
- package identities
- relationship labels
- evidence labels
- line ranges
- graph warnings
- Context Pack item reasons
- candidate commands marked run=false
- bounded structural summaries
```

The default exclusions are also correct:

```text
- whole source files
- function/class bodies
- raw comments
- raw secret-like values
- large raw document excerpts
- raw agent guidance text
- raw configuration dumps
```

This keeps AI useful without turning RepoLens into a source mirroring or upload tool.

### 4. The AI Proposal Shape Is Directionally Correct

The required proposal fields are mostly right:

```text
kind
provider
model
input_boundary
source_disclosure
context_pack_id or target refs
evidence refs
confidence label
warnings
limitations
```

These fields make the trust boundary visible to both humans and assistants.

### 5. The Graph Fact Promotion Path Is Excellent

The proposed path is exactly right:

```text
AI Graph Fact Proposal
  -> human review
  -> distilled fixture
  -> deterministic extractor/resolver implementation
  -> tests
  -> stable graph fact only after contract change if needed
```

This prevents AI output from becoming graph truth by direct promotion.

## Main Risks

### 1. The First v0.8 Scope Is Too Broad

The current issue breakdown includes many proposal surfaces:

```text
- AI Summary
- Architecture Explanation
- Convention Inference
- Local PR Review Report
- Patch Plan Proposal
- Graph Fact Proposal
```

All are useful, but not all should ship in the first AI release.

The highest-risk proposal types are:

```text
- Convention Inference
- Local PR Review Report
- Graph Fact Proposal
- Ownership Proposal
- Intent Proposal
```

These can easily overclaim, imply unsupported semantics, or produce noisy findings before the core AI Proposal contract is battle-tested.

Recommendation: make the first AI release smaller.

### 2. Proposal Reproducibility Needs More Metadata

The current plan requires provider/model provenance, but it should also include digest and version metadata for auditability.

Every AI Proposal should include:

```text
proposal_schema_version
input_packer_version
redaction_policy_version
input_digest
context_pack_version, when applicable
graph_schema_version
canonical_graph_hash
```

This lets RepoLens prove what deterministic metadata boundary the AI saw without persisting raw AI input.

### 3. Persistence Rules Need To Be Explicit

The plan discusses AI Proposal artifacts and safety checks, but it should define whether proposals are saved by default.

Recommended rule:

```text
AI Proposals are returned ephemerally by default.
Persisting AI Proposal artifacts requires an explicit --save flag or equivalent option.
Saved proposals must pass Artifact Safety Audit.
```

This avoids `.repolens` accumulating AI-generated metadata unexpectedly.

### 4. Provider Credentials Need A Narrower Rule

The provider boundary should explicitly say how credentials are configured.

Recommended rule:

```text
Provider config must be local-only.
Environment variables may supply credentials.
RepoLens config may reference credential environment variable names.
RepoLens config must not store credential values.
```

Required negative tests:

```text
- provider API keys are never serialized into artifacts
- provider API keys are never returned through MCP
- provider API keys are never included in proposal metadata
- provider error payloads are redacted before returning to CLI/MCP
- .env-like credential values are never mirrored
```

### 5. Some Proposal Kind Names Should Be Safer

Current kind names are understandable, but some can imply more authority than intended.

Recommended naming changes:

```text
ai_summary                  -> context_pack_summary
architecture_explanation    -> architecture_explanation
convention_inference        -> convention_proposal
local_pr_review_finding     -> local_change_review_proposal
patch_plan                  -> patch_plan
graph_fact_proposal         -> deterministic_fact_opportunity
test_gap_proposal           -> test_gap_proposal
intent_proposal             -> task_intent_proposal
ownership_proposal          -> ownership_hypothesis
```

The most important rename is:

```text
graph_fact_proposal -> deterministic_fact_opportunity
```

This avoids implying that AI has created or discovered a trusted graph fact.

## Recommended v0.8 MVP Scope

Ship this as the first AI Proposal release:

```text
v0.8 = AI Proposal contract
     + AI provider boundary
     + metadata-only AI input packer
     + Context Pack Summary Proposal
     + Architecture Explanation Proposal
     + Patch Plan Proposal
     + Artifact Safety Audit for AI outputs
```

Defer these until after initial dogfood:

```text
- Local PR Review Report
- Convention Inference Proposal
- Graph Fact Proposal
- Ownership Proposal
- Intent Proposal
```

## Recommended P0 / P1 Split

### P0: Ship In v0.8

```text
1. AI Proposal contract
2. AI provider configuration boundary
3. Metadata-only AI input packer
4. Context Pack Summary Proposal
5. Architecture Explanation Proposal
6. Patch Plan Proposal
7. Artifact Safety Audit extension
8. Docs, dogfood, and release readiness
```

### P1: Follow-Up After v0.8

```text
- Convention Proposal
- Local Change Review Proposal
- Deterministic Fact Opportunity Proposal
- Test Gap Proposal
- Ownership Hypothesis
- Task Intent Proposal
```

## Revised Issue Breakdown

### Issue 1: v0.8 Roadmap, Release Gates, And Non-Goals

Type: HITL  
Blocked by: None

Purpose:

Define and approve the v0.8 scope before implementation starts.

Acceptance should confirm:

```text
- AI is disabled by default.
- AI uses bounded metadata by default.
- AI does not mutate graph facts.
- AI does not affect Canonical Graph Hash.
- AI does not affect Context Pack IDs or ranking.
- MCP remains read-only.
- No file writes, command execution, patch application, telemetry, embeddings, or hosted service behavior is introduced.
```

### Issue 2: AI Proposal Schema And Trust Boundary

Type: AFK  
Blocked by: Issue 1

Purpose:

Define the AI Proposal envelope and prove AI output remains separate from deterministic graph facts.

Acceptance should confirm:

```text
- AI Proposal type includes kind, provenance, input boundary, source disclosure, evidence refs, confidence, warnings, and limitations.
- Proposal includes proposal_schema_version, input_packer_version, redaction_policy_version, and input_digest.
- AI Proposals are excluded from graph traversal.
- Canonical Graph Hash excludes AI Proposal output.
- Tests prove AI output is labeled and separated from graph facts.
```

### Issue 3: AI Provider Configuration Boundary

Type: AFK  
Blocked by: Issue 2

Purpose:

Implement provider configuration states and credential safety.

Acceptance should confirm:

```text
- AI is disabled by default.
- Missing provider config returns a structured disabled/unavailable result.
- Provider/model provenance appears in every AI Proposal.
- Credentials are never serialized into artifacts, logs intended for assistant consumption, or MCP responses.
- Provider errors are redacted.
- Tests cover disabled, unconfigured, configured, and provider-error states.
```

### Issue 4: Metadata-Only AI Input Packer

Type: AFK  
Blocked by: Issues 2 and 3

Purpose:

Build the deterministic input packer that converts RepoLens metadata into bounded AI input.

Acceptance should confirm:

```text
- Input excludes source bodies, raw comments, raw secrets, raw agent guidance text, and large raw documents.
- Input includes bounded paths, symbols, relationships, warnings, confidence, evidence handles, Context Pack reasons, and not-run candidate commands.
- Input ordering is deterministic.
- Input has size limits.
- Input produces an input_digest.
- Tests prove redaction, deterministic ordering, and size limits.
```

### Issue 5: AI Proposal Service And Read-Only MCP Tool

Type: AFK  
Blocked by: Issue 4

Purpose:

Expose one narrow AI Proposal service to CLI and MCP.

Recommended internal shape:

```text
create_ai_proposal(kind, target, context_pack_id, task, options)
```

Recommended MCP shape:

```text
create_ai_proposal
```

Acceptance should confirm:

```text
- MCP remains read-only.
- MCP tool returns proposal data only.
- MCP tool does not run commands.
- MCP tool does not write files.
- MCP tool does not post remote comments.
- MCP tool does not apply patches.
- Disabled/unconfigured provider states return structured results.
```

### Issue 6: Context Pack Summary Proposal

Type: AFK  
Blocked by: Issue 5

Purpose:

Add the lowest-risk user-visible AI Proposal type.

Acceptance should confirm:

```text
- Output is AIProposal(kind=context_pack_summary).
- Output is distinct from deterministic Structural Summary.
- Context Pack ID and ranking do not change.
- Output separates deterministic evidence from AI interpretation.
- Output lists limitations and missing fact types.
- Tests prove deterministic Context Pack behavior is unchanged without AI.
```

### Issue 7: Architecture Explanation Proposal

Type: AFK  
Blocked by: Issue 5

Purpose:

Allow AI to explain repository areas, package boundaries, file groups, symbols, or Context Packs from bounded metadata.

Acceptance should confirm:

```text
- Output is AIProposal(kind=architecture_explanation).
- Output cites deterministic evidence refs.
- Output includes unresolved candidates and graph quality warnings.
- Output includes limitations.
- No ownership, dependency, route, runtime behavior, or graph facts are created.
```

### Issue 8: Patch Plan Proposal

Type: AFK  
Blocked by: Issue 5

Purpose:

Allow AI to produce read-only implementation plans without applying them.

Acceptance should confirm:

```text
- Output is AIProposal(kind=patch_plan).
- Plan includes goal, target files to inspect, suggested edit sequence, related tests, risk notes, and candidate verification commands marked run=false.
- Plan cannot be applied by RepoLens in v0.8.
- No command execution occurs.
- No file writes occur.
```

### Issue 9: Artifact Safety Audit For AI Proposals

Type: AFK  
Blocked by: Issues 6, 7, and 8

Purpose:

Extend Artifact Safety Audit to cover AI outputs.

Acceptance should confirm:

```text
- Audit checks AI Proposal labels.
- Audit checks provider/model provenance.
- Audit checks source-disclosure metadata.
- Audit checks redaction and bounded size.
- Audit fails on raw source mirroring.
- Audit fails on raw secrets.
- Audit fails on credential-like provider config in artifacts.
- Audit checks saved AI Proposal artifacts only when persistence is explicitly requested.
```

### Issue 10: v0.8 Docs, Dogfood, And Release Readiness

Type: HITL  
Blocked by: Issues 2 through 9

Purpose:

Make the final release judgment.

Acceptance should confirm:

```text
- Default no-AI behavior is unchanged.
- Context Pack IDs are unchanged when AI is disabled.
- Canonical Graph Hash is unchanged by AI Proposal generation.
- AI input packer is deterministic for the same graph/context input.
- AI Proposal envelopes satisfy schema contracts.
- Artifact Safety Audit covers AI Proposal output.
- Dogfood checks whether AI output helped without overclaiming.
- Documentation explains AI boundaries, provider setup, no-goals, and proposal limitations.
```

## Suggested CLI And MCP Shape

### Internal Service

```text
create_ai_proposal(kind, target, context_pack_id, task, options)
```

### CLI

```bash
repolens ai proposal --kind context-pack-summary --context-pack <id>
repolens ai proposal --kind architecture-explanation --target <path-or-symbol>
repolens ai proposal --kind patch-plan --task "..."
```

### MCP

```text
create_ai_proposal
```

Keep MCP narrow. Do not add separate MCP tools for every proposal type until the service shape has proven stable.

## Evaluation Recommendations

The current evaluation direction is good. Keep evaluation deterministic where possible.

Required checks:

```text
- default no-AI behavior is unchanged
- Context Pack IDs are unchanged when AI is disabled
- Canonical Graph Hash is unchanged by AI Proposal generation
- AI input packer is deterministic for the same graph/context input
- AI Proposal envelopes satisfy schema contracts
- Artifact Safety Audit covers AI Proposal output
```

Dogfood questions:

```text
- Did Context Pack summaries help an assistant choose better first reads?
- Did architecture explanations cite useful evidence refs?
- Did patch plans identify plausible target files and related tests?
- Did any AI output overclaim beyond available graph evidence?
- Did any AI output imply command execution, file writes, or graph mutation?
```

Dogfood findings should become:

```text
- distilled fixtures
- documented limitations
- future deterministic extractor/resolver issues
```

They should not become hosted telemetry.

## Release Gate Recommendation

Keep the existing release gate:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
uv run repolens evaluate-context --json
uv build --out-dir /tmp/repolens-dist --clear
```

Add AI-specific checks:

```text
- AI disabled-by-default smoke test
- AI provider unconfigured smoke test
- AI provider configured smoke test using a fake/local test provider
- AI provider error redaction test
- AI input packer disclosure/redaction tests
- AI input digest determinism test
- AI Proposal schema/contract tests
- Artifact Safety Audit including AI Proposal fixtures
- Context Pack Summary fixture
- Architecture Explanation fixture
- Patch Plan Proposal fixture
- Documentation updated for AI boundaries and non-goals
```

If a command cannot be run, the release note should state why and what evidence replaced it.

## Final Recommendation

Proceed with v0.8, but ship a smaller and safer AI surface first.

Recommended final scope:

```text
v0.8 = AI Proposal contract
     + provider boundary
     + metadata-only input packer
     + Context Pack Summary Proposal
     + Architecture Explanation Proposal
     + Patch Plan Proposal
     + AI Artifact Safety Audit
```

Defer until after initial dogfood:

```text
- Local PR Review Report
- Convention Inference Proposal
- Graph Fact Proposal
- Ownership Proposal
- Intent Proposal
```

The plan is directionally correct. The main risk is scope size, not product direction. The AI Proposal Layer should be introduced as a narrow, auditable, metadata-only read surface first. Once that contract proves safe, RepoLens can add richer proposal kinds without weakening its deterministic foundation.
