# RepoLens MCP v0.1 Plan Archive

Status: archived historical plan.

v0.1 established RepoLens as a local-first repository intelligence backend for AI coding assistants.

## Tracker

- PRD: GitHub issue `#1`
- Umbrella tracker: GitHub issue `#2`
- Integration branch: `feature/repolens-v0.1`

## Release Shape

v0.1 shipped the first end-to-end RepoLens loop:

- installable `repolens` CLI;
- safe repository discovery and `.repolens` artifact bootstrap;
- deterministic SQLite graph store and deterministic exports;
- Python, JavaScript, TypeScript, config, command, docs, comments, and Agent Guidance indexing;
- incremental update and stale status classification;
- report and safe raw text search CLI;
- framework-independent graph query service;
- impact analysis and suggested reading order;
- read-only stdio MCP server;
- Docker, assistant configuration, and release-readiness docs.

## Issue Sequence

The implementation issues were published as `#3` through `#15`.

Dependency path:

```text
#3 CLI scaffold -> #4 safe discovery -> #5 graph store
#5 -> #6 Python indexing
#5 -> #7 JS/TS indexing
#5 -> #8 config/commands/packages
#5 -> #9 docs/comments/guidance
#6-#9 -> #10 update/status
#5 -> #11 report/search
#10 -> #12 query service
#12 -> #13 impact/reading order
#11-#13 -> #14 MCP
#14 -> #15 release readiness
```

## Durable Rules

- Keep MCP read-only.
- Keep indexing deterministic, local, and offline-capable.
- Keep `.repolens` local cache/output, not source.
- Never scan `.repolens`.
- Use repo-relative POSIX paths in artifacts and assistant-facing output.
- Skip secret-looking files before parsing.
- Do not copy whole source files into graph artifacts or MCP output.
