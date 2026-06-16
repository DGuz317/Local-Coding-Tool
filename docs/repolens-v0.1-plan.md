# RepoLens MCP v0.1 Implementation Plan

This plan tracks the approved vertical-slice issue sequence for RepoLens MCP v0.1. Each implementation issue should be independently grabbable by an AFK agent unless marked otherwise.

## Issue Tracker

- PRD: GitHub issue `#1`
- Umbrella tracker: GitHub issue `#2`
- Implementation branch: `feature/repolens-v0.1`
- AFK-ready implementation issues use the `ready-for-agent` label.

## Dependency Graph

```text
#3 -> #4 -> #5
#5 -> #6
#5 -> #7
#5 -> #8
#5 -> #9
#6,#7,#8,#9 -> #10
#5 -> #11
#10 -> #12
#12 -> #13
#11,#12,#13 -> #14
#14 -> #15
```

## Vertical Slices

1. `#3` Installable CLI Scaffold With Missing-Graph Status
   - Establish package identity, Typer CLI shell, Hatchling packaging, pytest/Ruff/mypy configuration, JSON/text CLI envelope patterns, docs, and read-like missing-graph `status`.
   - This issue intentionally excludes real scanning, graph storage, parser extraction, and MCP.

2. `#4` Safe Repository Discovery And Artifact Bootstrap
   - Add `index` traversal with path containment, `.gitignore`, built-in excludes, secret skips, binary/media and size caps, non-Git roots, repo-relative paths, `.repolens/.gitignore`, skip reasons, and sanitized logs.

3. `#5` Deterministic Graph Store And Exports
   - Create the minimum viable SQLite graph store and deterministic exports for repository, directory, file, skip-reason, and run metadata facts.
   - Keep this slice constrained so it does not become a horizontal storage project.

4. `#6` Python Structure Indexing End To End
   - Add Python AST extraction through the CLI and artifact pipeline, including symbols, imports, decorators, inheritance metadata, tagged comments, stdlib/third-party classification, local import root inference, and parse-error handling.

5. `#7` JavaScript And TypeScript Structure Indexing End To End
   - Add pure-Python JS/TS extraction through the CLI and artifact pipeline, including imports, exports, top-level symbols, interfaces, type aliases, package normalization, Node built-ins, and deterministic simple alias resolution.

6. `#8` Config, Command, Package, And Entrypoint Indexing
   - Add shallow parsing for package/config/tooling files, requirements, lockfile detection, command extraction and sanitization, package managers, dependencies, and evidence-backed entrypoints.

7. `#9` Markdown, Comments, Docs, And Agent Guidance Indexing
   - Add README metadata, Markdown headings and links, exact path mentions, code-fence metadata without code bodies, tagged comments, agent instruction classification, and skill metadata.

8. `#10` Incremental Update And Staleness Classification
   - Add `update` and richer read-like `status`, including raw/normalized/graph hashes, Git stale signals, config/extractor invalidation, and change classifications.

9. `#11` Report And Safe Raw Text Search CLI
   - Add `report` and CLI raw text `search` using the scan safety policy with capped sanitized previews and no whole-file output.

10. `#12` Structured Graph Query Service
    - Add framework-independent read-only query service methods for repo summary, graph status, graph report, structured graph search, node lookup, neighbors, shortest path, and entrypoints.

11. `#13` Impact Analysis And Reading Order Queries
    - Add deterministic impact analysis and suggested reading order with evidence, confidence, likely tests, docs, configs, risks, and candidate verification commands.

12. `#14` Read-Only Stdio MCP Server
    - Expose the v0.1 query surface over stdio MCP with read-only tools, structured envelopes, missing-graph responses, stdout discipline, caps, and MCP smoke coverage.

13. `#15` Docker, Assistant Config, And Release Readiness Docs
    - Add Docker support, host-user mapping examples, native install docs, OpenCode MCP example, README quickstart/security/config/tooling guidance, roadmap, and release-readiness checks.
    - This slice is AFK with a HITL checkpoint for release-facing decisions.

## Cross-Cutting Rules

- Each implementation issue owns tests for the behavior it introduces.
- Story 72 is cross-cutting and should not be deferred to a single late testing issue.
- Keep slices vertical and externally observable.
- Do not expand v0.1 beyond the PRD.
- Use concise area-prefixed commits that reference the issue number after issues exist.
