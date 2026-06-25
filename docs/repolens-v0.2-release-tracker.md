# RepoLens MCP v0.2 Release Tracker Archive

Status: archived historical tracker.

## Theme

```text
Make RepoLens reliable on real repositories before making it deeply semantic.
```

## Tracker

- Integration branch: `feature/repolens-v0.2`
- GitHub umbrella tracker: `#35`

## Source Documents

- `docs/repolens-v0.2-plan.md`
- `docs/repolens-v0.2-planning-interview-summary.md`
- `docs/repolens-v0.2-issue-breakdown-feedback.md`
- `docs/repolens-v0.2-issue-breakdown.md`
- `CONTEXT.md`
- `docs/adr/0001-standardize-mcp-envelope.md`
- `docs/adr/0002-edge-contract-storage.md`

## Completed Release Work

Release-blocking P0 issues were `#35` through `#49` and `#52` through `#54`.

Non-blocking P1 issues were `#50` and `#51`.

## Release Criteria Summary

v0.2 required evidence for:

- deterministic `index` and `update` behavior;
- read-like `status` behavior;
- graph schema compatibility checks and validation before replacement;
- reference resolution with strategy, confidence, evidence, and candidate-only ambiguity handling;
- grouped impact analysis and bounded suggested reading order;
- standardized MCP envelopes, structured errors, stale/missing graph handling, caps, truncation, and pagination;
- No Whole-Source Disclosure through MCP tools;
- redaction and scanner safety for secrets, command strings, and path traversal inputs;
- Candidate Verification Commands marked as not run;
- Selective Update cleanup for deleted or unparseable files;
- full verification with pytest, Ruff, format check, and mypy;
- minimal CI/build/install smoke;
- dogfooding reports, regression fixtures, and known limitations.

## Dogfooding Policy

Dogfooding was release-blocking but did not vendor third-party repositories. Committed evidence was limited to reports, distilled regression fixtures, and known limitations.

Required coverage:

- RepoLens on itself;
- one representative Python repository;
- one representative JS/TS repository;
- one mixed docs/config repository.

## Known Limitation Policy

Document limitations instead of silently resolving when behavior would require runtime import emulation, full compiler/bundler/framework resolution, deep semantic analysis, AI/LLM-required graph generation, embeddings, hosted services, telemetry, browser UI, write-capable MCP tools, or publishing automation.
