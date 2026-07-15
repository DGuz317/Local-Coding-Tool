# Security And Artifact Privacy

RepoLens is local-first and safe by default for normal indexing and MCP serving. It creates deterministic local artifacts under `.repolens/` and exposes read-only MCP tools.

## Safety Guarantees

- The provided path is the analysis root; RepoLens does not silently expand to a broader Git root.
- Scanner, indexing, query, and MCP behavior stay inside the analysis root.
- `.repolens/`, dependency folders, virtual environments, build outputs, caches, and common generated paths are skipped.
- `.gitignore` is honored during file discovery.
- Secret-looking files are skipped by path or name before parsing.
- Secret-like metadata and command values are redacted before storage or assistant-facing output.
- Oversized, binary, media, archive, and unsafe symlink targets are skipped.
- MCP tools are read-only and return bounded responses with freshness, warning, limit, pagination, and truncation metadata where applicable.
- Candidate commands may be detected and stored, but RepoLens does not execute them.
- Deploy or publish-like commands must not be recommended for automatic execution.
- Runtime package registry lookups and telemetry are out of scope for normal indexing and MCP serving.
- The first-use Assistant Preflight lifecycle may initialize or refresh local `.repolens/` artifacts, but it does not execute repository package managers, compilers, bundlers, frameworks, tests, deploy commands, or publish commands.
- Artifact Safety Audit checks redaction, bounded output, repo-relative paths, deterministic ordering, No Whole-Source Disclosure, and Candidate Verification Commands remaining not run.
- v0.6 JS/TS parser, resolver, Call Chain Fact, and Framework Route Hint artifacts remain compact metadata. They must not contain source snippets, code bodies, function signatures, full import lines, raw comments, raw Agent Guidance text, raw config values, or absolute host paths.

## No Whole-Source Disclosure

RepoLens artifacts and MCP tools are designed not to mirror whole source files. `search_text` may read scanner-approved live text, but it returns only bounded sanitized previews. Use normal file reads outside RepoLens when the assistant needs to inspect source before editing.

## Artifact Privacy

`.repolens/` can include repository metadata such as paths, symbols, imports, package names, command strings, Markdown headings, tagged comments, relationships, graph reports, and search indexes.

Treat `.repolens/` as private local cache output:

- Do not commit it.
- Do not publish it in package or container artifacts.
- Do not upload it to hosted services unless you have reviewed the contents.
- Delete and regenerate it when switching between repositories with different privacy requirements.

## Secret Handling Limits

RepoLens skips secret-looking paths and redacts obvious secret-like values, but it is not a full secret scanner. Do not intentionally place credentials, tokens, private keys, or customer data in source files. If a secret may have been indexed, rotate the secret and delete `.repolens/` before regenerating artifacts.

## Human Review Before Release

A human maintainer must review release-facing docs and known limitations before publication. Publishing automation for PyPI, Docker registries, or hosted services remains out of scope for v0.9.
