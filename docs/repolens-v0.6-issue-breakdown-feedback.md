# RepoLens v0.6 Issue Breakdown Feedback

## Verdict

The v0.6 breakdown is strong and publishable with minor edits. The scope is coherent: it upgrades the weakest current area, JS/TS graph quality, without breaking the RepoLens safety model of deterministic, local, read-only, source-free assistant context.

## Direct Answers

### 1. Parent tracker only, or also create the 8 child issues?

Create **the parent tracker plus all 8 child issues**.

Do not make the child issues `ready-for-agent` yet unless their blockers are satisfied. Create them as blocked/proposed implementation slices so the dependency graph is visible from the start.

Recommended GitHub shape:

| Issue | Create now? | Label/state |
|---|---:|---|
| Issue 1 parent tracker | Yes | `HITL`, `v0.6`, `scope-control` |
| Issues 2-8 | Yes | `AFK`, `v0.6`, `blocked` |
| Issue 9 release readiness | Yes | `HITL`, `v0.6`, `blocked` |

This is better than creating only one parent issue because the parser, parity, resolver, call-chain, route-hint, preflight, evaluation, and release-readiness work are separable.

### 2. First Framework Route Hint fixture: Next.js or generic?

Use **Next.js as the first concrete fixture**, but keep the **Framework Route Hint contract generic**.

Recommended target: **Next.js App Router**, not Pages Router, because it gives a clean deterministic fixture:

```text
app/api/users/route.ts      -> likely API route handler
app/users/page.tsx          -> likely page route
app/layout.tsx              -> likely app shell/layout hint
```

The contract should not say “RepoLens understands Next.js runtime behavior.” It should say:

```text
RepoLens can emit deterministic route hints from local file/config/source structure.
These hints are assistant-orientation metadata, not runtime route proof.
```

That keeps the product honest while giving dogfood something real enough to test.

## Recommended Changes Before Publishing

### 1. Resolve the backend-default ambiguity

Issue 2 says the stable backend remains default unless the tracker explicitly promotes Tree-sitter. But the v0.6 theme says this release should replace shallow regex-oriented extraction with a real parser-backed path. Those can conflict.

Add this decision to Issue 1:

```markdown
Maintainer decision:
For v0.6, Tree-sitter JS/TS is the default parser backend when the dependency and grammar are available. If unavailable, RepoLens falls back to the legacy bounded scanner and emits a parser-backend warning. Stable graph facts remain limited to promoted facts only.
```

This gives v0.6 a real improvement without making missing grammar/dependency cases fatal.

### 2. Add a stable fact schema requirement to Issue 3

Issue 3 already says stable facts must be documented or encoded in contract tests. Make that more explicit:

```markdown
Acceptance criteria:
- Stable JS/TS parser fact schema is documented with allowed fields.
- Experimental parser-only facts are listed separately.
- Stable facts include only source-free structural fields.
- Parser fact schema changes are treated as graph-affecting extractor version changes.
```

This matters because parser-backed extraction can easily leak too much detail if the stable schema is vague.

### 3. Tighten the no-disclosure rule around import specifiers and route paths

The issue correctly bans source snippets, code bodies, signatures, raw comments, raw config values, and absolute host paths. JS/TS resolver work still needs import specifiers, route paths, and package names to be useful.

Add this clarification:

```markdown
Assistant-facing output may include normalized package names, repo-relative paths, normalized import targets, and route paths derived from file structure. It must not include full source expressions, full import lines, string-literal source snippets, raw config values, or code bodies.
```

For Next.js, prefer route paths derived from repo-relative file paths, not copied string literals.

### 4. Add parser-version freshness coverage

v0.6 should explicitly include Tree-sitter grammar/parser version in parser status or extractor provenance.

Add to Issue 2 or Issue 3:

```markdown
- Parser backend name, parser package version, grammar version where available, and promoted fact schema version are included in extractor provenance.
- Parser or promoted fact schema changes force reparse of affected JS/TS files.
```

### 5. Add a minimum fixture matrix

The current fixture coverage is good but slightly abstract. Add a concrete minimum matrix to Issue 3 and Issue 5:

```text
Minimum JS/TS parser/resolver fixtures:
- .js, .jsx, .mjs, .cjs, .ts, .tsx
- static ESM import
- side-effect import
- dynamic import
- CommonJS require/module.exports/exports.*
- named export
- default export
- re-export
- tsconfig baseUrl
- tsconfig paths alias
- ambiguous alias
- workspace package import
- package entrypoint evidence
```

This makes the release gate easier for agents to verify.

### 6. Add bounded performance evidence without adding optimization work

The non-goal “no parse cache or worker pool without measured parser throughput pressure” is correct. Keep parse cache, worker pools, and indexing parallelism out of v0.6 unless measured pressure justifies them.

Add this to Issue 8:

```markdown
- Dogfood report records bounded local parser timing and file-count evidence.
- Performance evidence is used only to document limitations in v0.6, not to add parse cache, worker pool, or indexing parallelism unless separately approved.
```

## Issue-by-Issue Assessment

| Issue | Assessment | Suggested change |
|---|---|---|
| 1 Roadmap / gates | Good | Add explicit Tree-sitter default/fallback decision. |
| 2 Parser backend | Good | Add parser provenance/version and fallback warning behavior. |
| 3 Parser parity | Very important | Add stable fact schema and concrete fixture matrix. |
| 4 Call Chain Facts | Good | Clarify `receiver_shape` must be normalized, not source text. |
| 5 Resolver outcomes | Strong | Add package `exports` / `main` / `types` evidence if applicable, without full Node resolution. |
| 6 Route hints | Good | Use Next.js App Router as first fixture, generic contract. |
| 7 Impact / Preflight | Good | Add before/after evaluation examples for first-read improvement. |
| 8 Dogfood / evaluation | Strong | Add bounded parser performance evidence. |
| 9 Docs / release | Good | Add migration note: legacy JS/TS scanner fallback vs Tree-sitter parser. |

## Recommended Final Publish Decision

Publish it as:

```text
Parent tracker + 8 child issues.
First Framework Route Hint fixture: Next.js App Router.
Tree-sitter JS/TS: default when available, legacy scanner fallback with warning.
No semantic/runtime claims.
No source disclosure.
No AI, Kuzu, CFG, data-flow, active workflow, or command execution in v0.6.
```

This keeps v0.6 ambitious enough to improve real JS/TS usefulness, but still bounded enough for AFK implementation slices.

## Suggested Patch Text for the v0.6 Tracker

### Maintainer Decisions To Add

```markdown
## v0.6 Maintainer Decisions

- Create one parent tracker issue plus all 8 child implementation/release issues.
- Child issues remain blocked until their listed dependencies complete.
- Use Next.js App Router as the first concrete Framework Route Hint fixture.
- Keep the Framework Route Hint contract generic and deterministic.
- Use Tree-sitter JS/TS as the default parser backend when dependency and grammar support are available.
- Fall back to the legacy bounded JS/TS scanner when Tree-sitter is unavailable, and emit a clear parser-backend warning.
- Promote only source-free structural parser facts into the stable graph contract.
- Keep experimental parser-only facts out of Canonical Graph Hash and default Context Pack IDs until explicitly promoted.
- Do not add AI graph facts, embeddings, Kuzu, CFG/data-flow, active workflows, command execution, or write-capable MCP tools in v0.6.
```

### Stable Parser Fact Contract Addition

```markdown
## Stable JS/TS Parser Fact Contract

v0.6 must define which Tree-sitter-extracted JS/TS facts are promoted into the stable graph contract.

Stable facts may include:
- repo-relative file path;
- language and extension;
- parser backend status;
- import/export fact kind;
- normalized import target or package root;
- top-level symbol kind and name;
- source-free line range metadata;
- evidence label and confidence category.

Stable facts must not include:
- source snippets;
- full source expressions;
- function signatures;
- raw comments;
- raw config values;
- full import lines;
- code bodies;
- absolute host paths.

Experimental parser-only facts must remain excluded from Canonical Graph Hash and default Context Pack IDs until explicitly promoted by a tracker decision and covered by contract tests.
```

### Framework Route Hint Contract Addition

```markdown
## Framework Route Hint Contract

Framework Route Hints are deterministic assistant-orientation metadata derived from local file, config, and parser evidence.

They are not runtime route proof, framework emulation, compiler output, bundler output, or package-manager resolution.

The first v0.6 fixture targets Next.js App Router patterns, including:
- `app/**/page.tsx` as likely page route hints;
- `app/**/layout.tsx` as likely layout/app-shell hints;
- `app/api/**/route.ts` as likely API route handler hints.

Route hints should include:
- repo-relative path;
- normalized route path derived from file structure where possible;
- evidence labels;
- confidence category;
- line range when parser-backed evidence is available;
- warning metadata for ambiguous or unsupported patterns.

Route hints must not become definitive runtime route edges unless future evidence is explicit, deterministic, and separately approved.
```
