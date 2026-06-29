# RepoLens v0.4 Plan Review

## Summary

The v0.4 plan is directionally strong. The release theme is clear, the P0 scope is coherent, and the out-of-scope section protects the project boundary well.

The strongest part of the plan is that v0.4 focuses on **graph-quality correctness** rather than adding surface features. That matches the stated goal of making Context Packs more trustworthy on real package/workspace repositories.

## What Looks Solid

### 1. The Release Goal Is Well Scoped

The goal is not simply “better repo understanding” in general. It is specifically about improving Context Pack accuracy for package/workspace repositories while preserving deterministic, local-first, metadata-only behavior.

That is a good release boundary.

### 2. The P0 Items Are Mutually Reinforcing

The P0 items all support the same core outcome: better graph-derived orientation.

They include:

- workspace and package boundary hardening;
- resolver quality improvements;
- docs and config impact context;
- candidate verification command classification;
- expanded evaluation corpora.

None of these items feel disconnected from the release goal.

### 3. The Safety Model Is Preserved

The plan correctly blocks risky expansion areas, including:

- embeddings;
- runtime execution;
- registry lookups;
- source disclosure;
- assistant persistence;
- write-capable MCP tools.

This matters because v0.4 could otherwise drift into being “smarter” but less trustworthy.

### 4. The Release Criteria Are Concrete

The verification gate is practical and consistent with the implementation style:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
uv run repolens evaluate-context --json
uv build --out-dir /tmp/repolens-dist --clear
```

The requirement that existing v0.3 and v0.3.1 behavior must not regress is also important.

## Main Gaps To Tighten Before Implementation

### 1. Define “Explicit Package/Config Evidence” More Formally

The plan says workspace package imports should resolve from explicit `package.json`, workspace, lockfile, or config evidence. That is correct, but implementation will need a stricter contract.

Recommended evidence hierarchy:

| Evidence Source | Use |
|---|---|
| `package.json` `name` | Primary package identity |
| Root workspace declaration | Package membership |
| Lockfile package entries | Supporting evidence, not sole ownership evidence unless clearly mapped |
| `tsconfig.json` `paths` / `baseUrl` | Alias resolution only within configured scope |
| Package-manager workspace config | Workspace package discovery |

This prevents accidental inference from directory names such as `packages/foo` unless backed by metadata.

### 2. Separate Ownership From Resolution

Resolution and ownership are related, but they are not identical.

A file may resolve an import to a target module, but package ownership should only be attached if there is evidence that the target belongs to a known package boundary.

Recommended model:

```text
resolved_target: file/module/package candidate
ownership: evidence-backed package boundary, ambiguous, or unknown
```

This avoids a common failure mode where resolution succeeds and ownership is assumed too aggressively.

### 3. Define Ambiguity Output Shape

The plan correctly says ambiguity should be preserved, but it does not specify the artifact shape.

Recommended contract:

```text
Ambiguous import/package relationship:
- do not emit a definitive graph edge;
- emit candidates with evidence labels;
- emit a graph-quality warning;
- allow Context Packs to mention ambiguity without choosing a winner.
```

That will make tests easier to write and prevent inconsistent behavior across resolvers and Context Packs.

### 4. Be Careful With Lockfiles

Lockfiles can help, but they should not become a hidden source of false confidence.

For v0.4, lockfiles should be treated as supporting evidence for dependency presence, not as primary evidence for local workspace ownership unless the lockfile format explicitly maps the dependency to a local workspace path.

Suggested wording:

```text
Lockfile evidence may strengthen dependency/package relationship confidence, but local package ownership requires explicit local package/config mapping.
```

### 5. Clarify Docs/Config “No Excerpt” Rules

The plan already says no paragraph excerpts, snippets, raw comments, or raw Agent Guidance text. For docs/config tasks, implementation should output only structured facts such as:

```text
- mentioned paths
- referenced package names
- related config files
- candidate commands
- nearby ownership/package facts
- graph-quality warnings
```

That keeps docs/config support useful without violating the assistant-facing output boundary.

### 6. Define Command Classification Risk Buckets

The plan mentions common verification commands and conservative handling for deploy, publish, and destructive commands. The classifier should output explicit categories.

Recommended buckets:

```text
verification_likely:
  npm test, pytest, make test, make verify

quality_check_likely:
  ruff check, mypy, eslint, tsc --noEmit

build_likely:
  npm run build, uv build

risky_or_external:
  deploy, publish, release, docker push, terraform apply

unknown:
  preserved as found, not recommended as safe
```

Even safe-looking commands should remain **found/not run**.

## Suggested Implementation Order

1. **Evidence model for package/workspace boundaries**  
   Define package identity, workspace membership, ownership confidence, ambiguity, and warning types first.

2. **JavaScript/TypeScript resolver hardening**  
   Add deterministic handling for package imports, relative imports, workspace imports, and `tsconfig` path aliases.

3. **Context Pack ownership rendering**  
   Only render package/workspace ownership when backed by graph evidence.

4. **Ambiguity and unsupported-case warnings**  
   Ensure unresolved aliases, duplicate package candidates, missing configs, and unsupported resolver cases are visible but not treated as facts.

5. **Docs/config impact context**  
   Add orientation from Markdown mentions, config references, package files, and command facts without excerpts.

6. **Candidate Verification Command classifier**  
   Add classification buckets and tests.

7. **Evaluation corpus expansion**  
   Add fixtures after the core graph model exists, then lock expected behavior.

## Suggested Issue Slices

The original issue slices are good. I would make them more implementation-contract focused:

1. `v0.4 roadmap, release gates, and non-goals`
2. `Define package/workspace evidence model`
3. `Resolve JS/TS workspace package imports from explicit evidence`
4. `Harden TypeScript tsconfig paths/baseUrl resolution`
5. `Represent ambiguity and graph-quality warnings`
6. `Improve docs/config task orientation without excerpts`
7. `Classify candidate verification commands without execution`
8. `Expand v0.4 evaluation fixtures and expectation gates`
9. `Update v0.4 docs, limitations, and release readiness`

I would split ambiguity and warnings into their own issue because they are cross-cutting correctness mechanisms, not just part of resolver quality.

## Verdict

This is a good v0.4 plan.

I would approve it as a roadmap, with one required refinement before implementation: define the **package evidence model and ambiguity contract** more explicitly.

That contract will prevent most downstream mistakes in resolver behavior, Context Pack rendering, and evaluation expectations.
