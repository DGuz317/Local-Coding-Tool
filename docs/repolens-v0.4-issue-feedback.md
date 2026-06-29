# RepoLens v0.4 Issue Feedback And Publishing Recommendations

## Summary

The v0.4 issue set is structurally sound and ready to publish with one dependency correction.

The current granularity is appropriate for agent-driven implementation. The issues separate roadmap control, evidence contracts, resolver work, ambiguity handling, docs/config orientation, command classification, evaluation, and release readiness cleanly.

The main recommended update is:

```text
Issue 6 should be blocked by: 2, 5, 7
```

Reason: Issue 6 depends on command metadata, and Issue 7 defines the command risk bucket model that Issue 6 should use when rendering docs/config Context Pack orientation.

---

## Direct Answers To Publishing Questions

### 1. Does the granularity feel right?

Yes.

The issue breakdown is neither too coarse nor too fragmented. Each slice maps to a clear v0.4 implementation concern:

| Issue | Assessment |
|---|---|
| 1. v0.4 Roadmap, Release Gates, And Non-Goals | Correct as a tracker / coordination issue |
| 2. Package Evidence Contract With First Context Pack Tracer | Correct as the foundational contract slice |
| 3. Resolve JS/TS Workspace Package Imports From Explicit Evidence | Correct separate resolver slice |
| 4. Resolve Scoped TypeScript Paths And BaseUrl Aliases | Correct separate resolver slice |
| 5. Preserve Ambiguous Package And Import Relationships As Candidates | Correct cross-cutting correctness slice |
| 6. Improve Docs And Config Context Pack Orientation Without Excerpts | Slightly broad, but acceptable |
| 7. Add Command Risk Buckets To Candidate Verification Commands | Correct separate classifier slice |
| 8. Expand v0.4 Evaluation Fixtures And Expectation Gates | Correct validation and release-gate slice |
| 9. v0.4 Docs, Dogfooding Report, And Release Readiness | Correct final release-readiness slice |

Issue 6 is the only issue that may become too large. Keep it as one issue unless the implementing agent needs a smaller scope.

Optional split if needed:

```text
6a. Improve Markdown/docs Context Pack orientation without excerpts
6b. Improve config/package/command Context Pack orientation without raw values
```

Do not split Issue 2. The first Context Pack tracer is useful because it proves the evidence model end-to-end instead of leaving it as an abstract schema.

---

### 2. Are the dependency relationships correct?

Mostly yes.

Recommended dependency graph:

```text
1
└── 2
    ├── 3
    ├── 4
    ├── 7
    └── 5
        └── 6
            └── 8
                └── 9
```

More explicitly:

```text
1 -> 2
2 -> 3
2 -> 4
2 -> 7
3,4 -> 5
5,7 -> 6
3,4,5,6,7 -> 8
8 -> 9
```

Recommended update:

```text
Issue 6
Current: Blocked by: 2, 5
Recommended: Blocked by: 2, 5, 7
```

Reason:

Issue 6 includes Candidate Verification Command metadata in docs/config Context Pack orientation. That metadata should use the command risk buckets introduced by Issue 7.

---

### 3. Should any slices be merged or split further?

Do not merge Issues 3 and 4.

Workspace package import resolution and TypeScript path/baseUrl alias resolution are different enough to justify separate implementation and test fixtures.

Do not merge Issue 5 into Issues 3 or 4.

Ambiguity preservation is a product-level correctness behavior, not only a resolver detail. It should remain a separate issue because it defines how RepoLens avoids false graph facts when evidence is incomplete or conflicting.

Only consider splitting Issue 6 if it becomes too large for one AFK slice.

Recommended optional split:

```text
6a. Improve Markdown/docs Context Pack orientation without excerpts
Blocked by: 2, 5

6b. Improve config/package/command Context Pack orientation without raw values
Blocked by: 2, 5, 7
```

If implementation capacity is normal, keep Issue 6 as-is with the added dependency on Issue 7.

---

### 4. Are the tracker and release-readiness slices correctly marked HITL?

Yes.

Issue 1 should remain HITL because it controls release scope, release gates, and non-goals.

Issue 9 should remain HITL because release readiness requires maintainer judgment: docs quality, dogfooding interpretation, known limitations, and whether the release evidence is sufficient.

Recommended note for Issue 2:

```text
Type: AFK
Maintainer checkpoint: Required before downstream implementation slices are started.
```

Issue 2 can remain AFK because it is implementable, but it defines the core contract for Issues 3 through 8. It should be reviewed before downstream slices proceed.

---

### 5. Should `ready-for-agent` be used for AFK slices when publishing?

Yes, but not all at once.

Use `ready-for-agent` only when the issue is unblocked and has complete acceptance criteria.

Initial labels:

| Issue | Initial labels |
|---|---|
| 1 | `hitl`, `tracker`, `v0.4` |
| 2 | `afk`, `blocked`, `v0.4` |
| 3 | `afk`, `blocked`, `v0.4` |
| 4 | `afk`, `blocked`, `v0.4` |
| 5 | `afk`, `blocked`, `v0.4` |
| 6 | `afk`, `blocked`, `v0.4` |
| 7 | `afk`, `blocked`, `v0.4` |
| 8 | `afk`, `blocked`, `release-gate`, `v0.4` |
| 9 | `hitl`, `blocked`, `release-readiness`, `v0.4` |

Progressive `ready-for-agent` flow:

```text
After Issue 1 is approved:
- Mark Issue 2 ready-for-agent.

After Issue 2 is merged:
- Mark Issues 3, 4, and 7 ready-for-agent.

After Issues 3 and 4 are merged:
- Mark Issue 5 ready-for-agent.

After Issues 5 and 7 are merged:
- Mark Issue 6 ready-for-agent.

After Issues 3 through 7 are merged:
- Mark Issue 8 ready-for-agent.

After Issue 8 passes:
- Issue 9 becomes HITL release-readiness work.
```

This avoids agents starting on downstream slices before the evidence contract, resolver behavior, ambiguity model, or command metadata contract exists.

---

## Revised Issue List

### 1. v0.4 Roadmap, Release Gates, And Non-Goals

```text
Type: HITL
Blocked by: None
User stories covered: Release coordination, scope approval, non-goal enforcement
Notes: Tracker / coordination issue, not an implementation slice.
Recommended labels: hitl, tracker, v0.4
```

No change needed.

---

### 2. Package Evidence Contract With First Context Pack Tracer

```text
Type: AFK
Blocked by: 1
User stories covered: Package Identity, Workspace Membership, Package Ownership, Relationship Candidates, Graph Quality Warnings
Recommended labels after Issue 1 approval: afk, ready-for-agent, v0.4
```

Recommended addition:

```text
Maintainer checkpoint required before downstream implementation slices begin.
```

Reason:

This issue defines the evidence contract that Issues 3 through 8 depend on. The first Context Pack tracer is valuable because it proves the model from indexing to graph/query output to assistant-facing orientation.

---

### 3. Resolve JS/TS Workspace Package Imports From Explicit Evidence

```text
Type: AFK
Blocked by: 2
User stories covered: Workspace Package Import, Package Entrypoint Evidence, Package Dependency, Local Resolution
Recommended labels after Issue 2 is merged: afk, ready-for-agent, v0.4
```

No change needed.

Keep separate from Issue 4.

---

### 4. Resolve Scoped TypeScript Paths And BaseUrl Aliases

```text
Type: AFK
Blocked by: 2
User stories covered: Alias Resolution Scope, Local Resolution, Graph Quality Warning
Recommended labels after Issue 2 is merged: afk, ready-for-agent, v0.4
```

No change needed.

Keep separate from Issue 3.

---

### 5. Preserve Ambiguous Package And Import Relationships As Candidates

```text
Type: AFK
Blocked by: 3, 4
User stories covered: Relationship Candidate, Graph Quality Warning, Package Ownership ambiguity
Recommended labels after Issues 3 and 4 are merged: afk, ready-for-agent, v0.4
```

No change needed.

This should remain separate because ambiguity handling is a core correctness behavior, not just a resolver implementation detail.

---

### 6. Improve Docs And Config Context Pack Orientation Without Excerpts

```text
Type: AFK
Blocked by: 2, 5, 7
User stories covered: Docs/Config Orientation, Package Reference, Candidate Verification Command metadata, No Whole-Source Disclosure
Recommended labels after Issues 5 and 7 are merged: afk, ready-for-agent, v0.4
```

Recommended change:

```text
Blocked by: 2, 5, 7
```

Reason:

This issue uses command metadata in Context Pack orientation, so it should wait for the command risk bucket model from Issue 7.

Keep as one issue unless it becomes too large.

Optional split:

```text
6a. Improve Markdown/docs Context Pack orientation without excerpts
6b. Improve config/package/command Context Pack orientation without raw values
```

---

### 7. Add Command Risk Buckets To Candidate Verification Commands

```text
Type: AFK
Blocked by: 2
User stories covered: Candidate Verification Command, Command Risk Bucket
Recommended labels after Issue 2 is merged: afk, ready-for-agent, v0.4
```

No change needed.

This can proceed in parallel with Issues 3 and 4 after the evidence contract exists.

---

### 8. Expand v0.4 Evaluation Fixtures And Expectation Gates

```text
Type: AFK
Blocked by: 3, 4, 5, 6, 7
User stories covered: Context Pack Evaluation, Release Gate, regression protection
Recommended labels after Issues 3 through 7 are merged: afk, ready-for-agent, release-gate, v0.4
```

No change needed.

This should remain downstream of all implementation slices because it locks the release behavior and guards against regressions.

---

### 9. v0.4 Docs, Dogfooding Report, And Release Readiness

```text
Type: HITL
Blocked by: 8
User stories covered: Dogfooding Report, Release Gate, known limitations
Recommended labels after Issue 8 passes: hitl, release-readiness, v0.4
```

No change needed.

This should remain HITL because it requires maintainer review and final release judgment.

---

## Publishing Recommendation

Publish the issue set with this one required update:

```text
Issue 6 Blocked by: 2, 5, 7
```

Then use `ready-for-agent` progressively instead of labeling every AFK issue ready immediately.

Recommended publish order:

```text
1. Publish all issues with correct blocked-by relationships.
2. Mark only Issue 1 as active HITL.
3. After Issue 1 approval, mark Issue 2 ready-for-agent.
4. After Issue 2 is merged and reviewed, unlock Issues 3, 4, and 7.
5. Unlock Issue 5 after Issues 3 and 4.
6. Unlock Issue 6 after Issues 5 and 7.
7. Unlock Issue 8 after Issues 3 through 7.
8. Complete Issue 9 as the final HITL release-readiness review.
```

Final verdict:

```text
The v0.4 issue set is ready to publish after updating Issue 6's dependency list.
```

The most important invariant to preserve across all slices is:

```text
Only emit evidence-backed graph facts. Preserve unresolved or ambiguous relationships as candidates or warnings instead of guessing.
```
