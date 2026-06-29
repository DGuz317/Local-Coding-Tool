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

Alias Resolution Scope is the directory subtree controlled by the applicable `tsconfig.json` or `jsconfig.json`. Aliases outside that scope must not create definitive edges.

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
