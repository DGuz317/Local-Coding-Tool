# Package And Workspace Evidence Contract

RepoLens v0.4 keeps package/workspace facts separate so Context Packs can orient assistants without overstating certainty.

## Evidence Concepts

Package Identity is an explicit local package name declared by supported package metadata, such as `package.json` `name` or supported Python project metadata.

Workspace Membership is a package root that falls within an explicit workspace declaration and also has Package Identity evidence. Workspace globs alone are scope evidence, not membership proof.

Package Ownership is the evidence-backed nearest package root for a file. RepoLens must not infer ownership from directory names alone.

Package Dependency is a declared dependency from supported manifest metadata. It does not imply runtime reachability.

Local Resolution is a deterministic import-to-file result produced from local source/config evidence. If evidence is missing, ambiguous, or unsupported, the import remains unresolved.

Relationship Candidate is bounded metadata for a plausible or unresolved package/workspace/import relationship. Candidates are not graph edges and must include evidence labels.

Graph Quality Warning is structured warning metadata for incomplete, ambiguous, unsupported, or unresolved graph facts. Warnings are distinct from validation failures.

Resolution Strategy names how a fact was resolved, such as exact explicit package evidence, scoped alias resolution, or unresolved ambiguous import.

Resolver Evidence Labels are stable public labels for why a resolver considered a fact: `javascript_import_specifier`, `package_manifest_dependency`, `package_manifest_identity`, `package_entrypoint_metadata`, and `workspace_declaration`.

Resolver Outcome Classes are stable public classes for resolver results: `resolved_edge`, `relationship_candidate`, `unresolved`, and `unsupported`.

Alias Resolution Scope is the directory subtree controlled by the applicable `tsconfig.json` or `jsconfig.json`. Aliases outside that scope must not create definitive edges.

## Supported JS/TS Workspace Package Import Resolution

RepoLens resolves a package-style JavaScript or TypeScript import to a local workspace package entrypoint only when all evidence is unique and explicit:

- the importing file belongs to an explicit JavaScript package root;
- that package manifest declares a dependency on the imported package name;
- exactly one local JavaScript package identity matches the imported package name;
- both the importing and target package roots are within explicit workspace scope;
- the target package has exactly one scanner-approved JS/TS entrypoint path from supported simple package entrypoint metadata such as string `exports`, `main`, `module`, or `browser`.

When those checks pass, RepoLens records the import as `local_resolved` with `resolved_workspace_package` and emits an `IMPORTS` edge to the scanner-approved module path using `workspace_package_import` evidence.

RepoLens does not resolve missing entrypoints, complex entrypoint maps, ambiguous package identities, ambiguous entrypoint targets, undeclared dependencies, or package names that only resemble directory names.

When multiple explicit local package identities match a workspace package import, RepoLens records `relationship_candidates` with `relationship_candidate` outcome class and low confidence, emits a graph-quality warning, and does not emit a definitive `IMPORTS` edge for that import.

## Supported TypeScript Alias Resolution

RepoLens resolves JavaScript and TypeScript imports through `tsconfig.json` or `jsconfig.json` evidence only within the config file's directory subtree.

Supported local alias evidence includes:

- exact `paths` entries with one target;
- trailing-wildcard `paths` entries with one target;
- `baseUrl` imports when they uniquely match a scanner-approved in-repository JS/TS module path.

Unsupported alias patterns, aliases used outside the config subtree, missing alias targets, and ambiguous alias/baseUrl matches remain unresolved and are surfaced through resolution statuses, relationship candidates, or graph-quality warnings. RepoLens does not run the TypeScript compiler and does not use alias evidence as a repository-wide table.

## Default Rule

```text
unique explicit evidence -> graph edge or ownership fact
multiple plausible matches -> relationship candidate + graph-quality warning
unsupported pattern -> graph-quality warning
no evidence -> unresolved
```

## Context Pack Boundary

Context Packs may surface package/workspace evidence as structured metadata: package names, paths, evidence labels, relationship candidates, resolution statuses, line numbers, and warning codes.

Context Packs must not surface source snippets, code bodies, raw config values, raw comments, raw Agent Guidance text, paragraph excerpts, or absolute host paths.
