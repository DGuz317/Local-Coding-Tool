# RepoLens v0.2 Issue Breakdown Feedback Archive

Status: archived historical review summary.

## Verdict

The v0.2 direction was approved after revision. The release correctly focused on reliability hardening rather than a rewrite, but the first issue breakdown had dependency bottlenecks and a few oversized slices.

## What Worked

- The theme was correct: make RepoLens reliable on real repositories before making it deeply semantic.
- Edge Contract storage came before resolver and MCP polish.
- Canonical Graph Hash and validation came before deeper resolution work.
- Python and JS/TS resolver work were split.
- Candidate-only ambiguity handling was explicit.
- Impact analysis and reading order were separate but connected.
- Selective update included both implementation and verification.
- Dogfooding was treated as release-confidence work.
- Tree-sitter remained non-blocking P1.

## Required Revisions

1. Move MCP envelope foundation earlier.
2. Split MCP envelope foundation from MCP tool migration.
3. Remove the P1 package/workspace blocker from P0 dogfooding, or promote package/workspace work to P0 only if dogfooding proved it necessary.
4. Split CI from docs and release readiness.
5. Split shared security policy from MCP source-disclosure proof.
6. Keep parser backend and optional Tree-sitter as non-blocking P1.

## Final Recommended Issue List

1. RepoLens MCP v0.2 roadmap and release criteria.
2. Add Edge Contract storage and duplicate edge normalization.
3. Add Canonical Graph Hash, Graph Validation, and rebuild guardrails.
4. Resolve Python local imports deterministically.
5. Resolve JS/TS relative imports and harden simple aliases.
6. Normalize Resolution Strategy and candidate-only ambiguity handling.
7. Store Related Test relationships with confidence and evidence.
8. Group Impact Analysis and enforce Target Expansion traversal boundaries.
9. Improve Suggested Reading Order ranking and command context.
10. Add shared MCP envelope foundation and contract tests.
11. Migrate MCP tools to standardized envelope, errors, pagination, and stdio discipline.
12. Add file-level Selective Update planner and graph replacement path.
13. Add Selective Update cleanup tests and generated benchmark fixture.
14. Add shared Redaction Policy and scanner/security fixtures.
15. Add MCP No Whole-Source Disclosure and raw text safety tests.
16. Improve Package Boundary, workspace, and command grouping awareness.
17. Add optional Parser Backend experiment behind default-stable behavior.
18. Add Dogfooding Reports and regression fixture process.
19. Add minimal CI and isolated install smoke.
20. Add v0.2 user docs, assistant docs, release checklist, and known limitations.

## Final Recommendation

Publish only after the revisions above. After those edits, the issue breakdown was strong enough to become the v0.2 GitHub backlog.
