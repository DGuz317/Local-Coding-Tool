# Artifact Budget Contract

This contract covers AI-facing generated graph artifacts, especially the default `.repolens/graph-index.md` navigation artifact.

## Source Of Truth

SQLite remains the full graph source of truth. Default Markdown artifacts are bounded navigation views, not full graph dumps.

Use `.repolens/graph.sqlite` and SQLite-backed RepoLens query surfaces for complete graph detail. The default `graph-index.md` should help an assistant orient quickly, then move to targeted queries or file reads when more detail is needed.

## Default `graph-index.md` Budget

The centralized constants live in `src/repolens/artifact_budget_contract.py`.

Default budget:

- `max_total_chars`: 200,000
- `max_section_rows`: 100
- smaller support sections: 50 rows

Section row caps:

- directories: 100
- files: 100
- Python modules, symbols, imports, packages, and calls: 100
- JavaScript modules, symbols, imports, packages, exports, and CommonJS assignments: 100
- config packages: 100
- config files, commands, entrypoints, package managers, package roots, workspaces, lockfiles, and parse errors: 50
- documentation files, headings, links, path mentions, code fences, tagged comments, and skills: 50
- skipped paths: 50

## Deterministic Ordering

Each capped section must order rows deterministically within that section. Ordering must not depend on filesystem iteration order, randomness, wall-clock time, or environment-specific state.

Stable tie-breakers should prefer repo-relative POSIX path, qualified name or label, line number, then stable node or fact ID.

## Truncation Metadata

Every truncated section must report section-level truncation metadata with:

- `shown`: number of rows emitted in the default artifact
- `total`: total rows available from the graph source
- `reason`: why rows were omitted, such as `section_row_budget`

If the total character budget is reached, the artifact-level reason should be `total_character_budget`.

This metadata is a disclosure boundary, not a relevance claim. Omitted rows are lower-priority context to inspect later, not irrelevant or safe to ignore.
