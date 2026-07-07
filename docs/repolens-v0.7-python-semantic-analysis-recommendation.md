# RepoLens v0.7 Recommendation: Python Semantic Analysis Prototype

## Recommendation

v0.7 should be:

```text
RepoLens v0.7: Python Semantic Analysis Prototype
```

A narrow Python-first release that moves RepoLens from structural graph metadata toward semantic code intelligence, without making semantic facts part of the trusted default graph yet.

Status: approved direction for v0.7 scope planning.

## Approved Maintainer Decisions

- `semantic-inspect` reads indexed semantic artifacts by default.
- `--from-source` is allowed as an explicit, non-persistent live parse/debug mode.
- Semantic facts are stored outside stable `graph.sqlite`, preferably in `.repolens/semantic.sqlite`.
- `semantic.jsonl` may exist as a deterministic debug/evaluation export.
- Semantic facts do not affect Canonical Graph Hash, default Context Pack IDs, or default MCP output.
- Context Pack enrichment is conditional and opt-in, not required for the v0.7 release.
- v0.7 may ship with CLI/evaluation only if semantic schema hardening is not complete enough for assistant-facing enrichment.

## Core Theme

Build an experimental semantic layer for Python that can describe function-level control flow and local name binding as source-free metadata.

## One-Line Version Pitch

```text
v0.7 = Python Semantic Analysis Prototype: source-free function CFG and lexical binding facts in an experimental semantic layer, proving deeper code intelligence without weakening RepoLens’ deterministic graph contract.
```

## Why This Next

v0.6 upgraded JS/TS parsing, resolver evidence, route hints, and call-chain orientation. The next valuable step is not broader framework support or AI. It is deeper code understanding.

The roadmap already points here:

- v0.5 established contracts and Assistant Preflight.
- v0.6 added real parser/resolver capability.
- v0.7 should prove semantic analysis on one bounded language before reaching definitions, data-flow, taint, PR review, AI summaries, or active workflows.

This keeps RepoLens aligned with its core product goal:

- reduce repeated assistant repository exploration;
- preserve deterministic metadata-first behavior;
- keep assistant-facing context bounded;
- avoid source disclosure;
- maintain read-only MCP behavior.

## Main Recommendation

Keep the v0.7 theme, but tighten the scope.

The release should prove **CFG + lexical binding first**. Reaching definitions, full data-flow, taint, Kuzu, branch comparison, worker pools, and AI enrichment should remain follow-up work unless fixtures prove they are needed immediately.

```text
v0.7 should prove CFG + lexical binding first.
Reaching definitions, data-flow, taint, Kuzu, and branch comparisons should remain follow-up work unless fixtures prove they are needed immediately.
```

## Suggested v0.7 P0 Scope

### 1. Semantic Fact Contract First

Before implementation, define the contract for experimental semantic facts.

Recommended concepts:

```text
SemanticFact
SemanticNode
SemanticEdge
SemanticScope
SemanticBinding
SemanticWarning
SemanticProvenance
```

Required metadata fields:

```text
schema_version
semantic_backend
parser_backend
source_language
source_path
line_range
confidence
evidence_label
is_experimental = true
```

Important rule:

```text
Semantic facts must not affect:
- Canonical Graph Hash
- default Context Pack IDs
- stable graph validation
- default MCP output
```

The semantic layer should be stored separately from stable graph facts until a later release explicitly promotes selected facts into the trusted graph contract.

### 2. Python Function-Level CFG Prototype

Add a source-free control-flow graph for Python functions.

P0 CFG node kinds:

```text
entry
statement
branch
loop
return
raise
exit
unsupported
```

P0 CFG edge kinds:

```text
next
true_branch
false_branch
loop_body
loop_exit
exception_exit
```

Recommended supported constructs:

```text
if / elif / else
for
while
break
continue
return
raise
try / except / finally as limited/uncertain
with as sequential block
match as unsupported or branch-like if simple
```

Do not try to model every Python construct perfectly in v0.7. For dynamic or complex constructs, emit an `unsupported` or `uncertain` semantic warning instead of guessing.

### 3. Local Lexical Binding Facts

Track local name definitions and references inside Python modules and functions.

Recommended binding facts:

```text
defined
referenced
assigned
parameter
imported
shadowed
unresolved
global_declared
nonlocal_declared
free_variable_candidate
```

The binding layer should preserve uncertainty for dynamic Python behavior. It should not claim runtime resolution.

Good v0.7 output shape:

```json
{
  "name": "user",
  "binding_kind": "local",
  "defs": [
    {
      "line_range": [12, 12],
      "evidence": "assignment"
    }
  ],
  "refs": [
    {
      "line_range": [15, 15],
      "evidence": "name_load"
    }
  ],
  "status": "resolved_local"
}
```

Bad v0.7 output shape:

```json
{
  "user": "definitely an instance of app.models.User"
}
```

That kind of claim belongs later, after stronger type-aware and scope-aware resolution evidence exists.

### 4. Experimental CLI Surface

Add a JSON-first inspection command for semantic facts.

Recommended command:

```bash
repolens semantic-inspect path/to/file.py --json
```

Recommended function filter:

```bash
repolens semantic-inspect path/to/file.py --function process_user --json
```

This should be the primary v0.7 debugging and evaluation surface. Do not over-invest in MCP until the semantic schema proves stable.

By default, `semantic-inspect` should read indexed semantic artifacts. If semantic artifacts are missing or stale, it should report freshness and artifact status rather than silently parsing live source outside the indexed-artifact contract.

An explicit live parse/debug mode is allowed:

```bash
repolens semantic-inspect path/to/file.py --from-source --json
```

`--from-source` must be non-persistent by default and clearly labeled as live debug output, not indexed repository state.

### 5. Context Pack Opt-In Enrichment

Allow Assistant Preflight and Context Packs to include semantic hints only behind an explicit option.

This slice is conditional for v0.7. If the semantic schema needs more hardening, v0.7 may ship with the CLI inspection and evaluation surface only, deferring assistant-facing semantic enrichment to a later v0.7.x or v0.8 slice.

Recommended option:

```json
{
  "include_experimental_semantic_hints": true
}
```

Allowed semantic hints:

```text
function has multiple exits
function contains loop and branch paths
local name is shadowed
local binding is unresolved
exception path exists
branch affects return flow
```

Do not include:

```text
function signatures
source snippets
condition text
raw variable values
AI prose summaries
```

The output should remain orientation-only and source-free.

### 6. Dogfood And Evaluation Pack

Add Python fixtures for:

```text
simple branches
loops
nested functions
exception paths
imports plus local shadowing
dynamic Python cases that must stay unresolved
comprehensions
lambdas
global declarations
nonlocal declarations
multiple exits
unsupported match cases
```

Evaluation should prove that RepoLens can emit useful semantic metadata without false certainty or source disclosure.

## What To Move Out Of v0.7

Defer these unless a concrete dogfood fixture proves immediate need:

```text
branch-aware freshness
branch comparison metadata
data-flow edges
taint source/sink registry
real reaching definitions
Kuzu evaluation
worker pools
parse cache
semantic MCP as a default assistant tool
AI summaries
AI proposals
active workflows
command execution
JS/TS semantic analysis
runtime framework behavior
write-capable MCP tools
```

These are valuable later, but they would make v0.7 too wide.

## Do Not Include In v0.7

v0.7 should explicitly exclude:

- AI summaries or AI proposals.
- Taint analysis.
- Full data-flow.
- Reaching definitions beyond tiny exploratory fixtures.
- Kuzu migration.
- Parse cache or worker pools unless dogfood proves performance pressure.
- Active workflows or command execution.
- JS/TS semantic analysis.
- Runtime framework behavior.
- Write-capable MCP tools.
- Source snippets, function bodies, raw conditions, or raw prose extracted from code.

## Success Criteria

v0.7 is successful if RepoLens can answer, from metadata only:

- What is the rough control-flow shape of this Python function?
- Which local names are defined, referenced, shadowed, or unresolved?
- Where does semantic evidence improve impact/preflight orientation?
- Which semantic cases are unsupported or ambiguous?

More testable success criteria:

```text
v0.7 is successful if:
- semantic facts are stored separately from stable graph facts;
- semantic facts are excluded from canonical graph hash and default Context Pack identity;
- semantic-inspect returns deterministic JSON for committed Python fixtures;
- CFG output handles branch, loop, return, raise, and unsupported cases;
- binding output identifies local defs, refs, parameters, imports, shadowing, and unresolved names;
- Context Pack semantic hints appear only when explicitly enabled;
- artifact audit proves no source snippets or raw condition text leak;
- unsupported/dynamic Python cases produce warnings instead of false certainty.
```

v0.7 must still preserve:

- local-first operation;
- deterministic artifacts;
- no source disclosure;
- read-only MCP;
- explicit uncertainty;
- stable graph safety.

## Recommended Issue Breakdown

### Issue 1: v0.7 Roadmap, Release Gates, And Non-Goals

**Type:** HITL  
**Blocked by:** None  
**Purpose:** Tracker and scope-control issue.

Define the semantic boundary, experimental namespace, no-source-disclosure rule, promotion rules, release gates, accepted scope, and explicit non-goals.

Acceptance criteria:

- [ ] v0.7 theme and release goal are documented.
- [ ] Experimental semantic namespace is documented.
- [ ] Default graph safety rules are documented.
- [ ] Non-goals explicitly exclude data-flow, taint, Kuzu, AI, active workflows, and write-capable MCP.
- [ ] Release gates are approved before implementation starts.

### Issue 2: Semantic Fact Contract And Experimental Hash Exclusion

**Type:** AFK  
**Blocked by:** Issue 1  
**Purpose:** Define the semantic schema and prove it does not destabilize stable graph identity.

Acceptance criteria:

- [ ] Semantic fact contract is documented or encoded in a contract module.
- [ ] Semantic facts include provenance, backend metadata, schema version, evidence labels, and uncertainty fields.
- [ ] Experimental semantic facts are excluded from Canonical Graph Hash.
- [ ] Experimental semantic facts are excluded from default Context Pack IDs.
- [ ] Tests prove stable graph output is unchanged when semantic facts are enabled experimentally.

### Issue 3: Python CFG Builder Prototype

**Type:** AFK  
**Blocked by:** Issues 1 and 2  
**Purpose:** Add source-free function-level CFG facts for Python.

Acceptance criteria:

- [ ] CFG builder emits entry, branch, loop, return, raise, exit, and unsupported nodes.
- [ ] CFG builder emits next, true_branch, false_branch, loop_body, loop_exit, and exception_exit edges.
- [ ] Line ranges and evidence labels are included.
- [ ] Dynamic or unsupported constructs produce warnings instead of false precision.
- [ ] Fixtures cover branches, loops, returns, raises, and unsupported constructs.

### Issue 4: Python Local Binding Extractor

**Type:** AFK  
**Blocked by:** Issues 1 and 2  
**Purpose:** Add source-free local lexical binding facts.

Acceptance criteria:

- [ ] Extractor tracks parameters, assignments, imports, references, shadowing, unresolved names, global declarations, and nonlocal declarations.
- [ ] Nested function cases preserve local scope boundaries.
- [ ] Dynamic Python cases remain unresolved or uncertain.
- [ ] No runtime type or object-instance resolution is claimed.
- [ ] Fixtures cover imports, local shadowing, nested functions, global/nonlocal, comprehensions, and unresolved dynamic cases.

### Issue 5: Semantic Storage And Query Service

**Type:** AFK  
**Blocked by:** Issues 2, 3, and 4  
**Purpose:** Store semantic facts separately from stable graph facts and expose internal query helpers.

Acceptance criteria:

- [ ] Semantic facts are stored outside stable `graph.sqlite`, preferably in `.repolens/semantic.sqlite`.
- [ ] Optional `semantic.jsonl` export is deterministic and intended only for debug/evaluation workflows.
- [ ] Stable graph queries remain unchanged by default.
- [ ] Semantic query helpers can retrieve CFG and binding facts by file and function.
- [ ] SQLite remains the storage backend unless a measured query problem appears.
- [ ] Artifact replacement and status behavior remain deterministic.

### Issue 6: `repolens semantic-inspect` CLI

**Type:** AFK  
**Blocked by:** Issue 5  
**Purpose:** Add a JSON-first inspection surface for semantic facts.

Acceptance criteria:

- [ ] `repolens semantic-inspect path/to/file.py --json` returns indexed semantic facts for one file by default.
- [ ] Missing or stale semantic artifacts return bounded artifact/freshness status rather than silently parsing live source.
- [ ] `--from-source` enables explicit non-persistent live parse/debug output.
- [ ] Optional `--function` narrows output to one function when resolvable.
- [ ] Ambiguous function names return bounded candidates, not a guessed match.
- [ ] Output includes schema version, backend metadata, provenance, warnings, and limits.
- [ ] Output contains no source snippets, signatures, raw condition text, or function bodies.

### Issue 7: Opt-In Context Pack Semantic Hints

**Type:** AFK  
**Blocked by:** Issues 5 and 6  
**Purpose:** Conditionally add bounded semantic hints to Context Packs only behind an explicit flag.

This issue is optional for the v0.7 release. It should proceed only if the semantic schema is stable enough for assistant-facing enrichment. Otherwise, defer it without blocking v0.7 CLI/evaluation release readiness.

Acceptance criteria:

- [ ] Default Context Pack output remains unchanged.
- [ ] Semantic hints appear only when `include_experimental_semantic_hints` is enabled.
- [ ] Hints are bounded, source-free, and evidence-backed.
- [ ] Hints include examples such as multiple exits, unresolved binding, shadowed local, branch/loop shape, and exception path.
- [ ] No snippets, signatures, raw conditions, or AI prose summaries appear.

### Issue 8: Semantic Fixture And Evaluation Pack

**Type:** AFK  
**Blocked by:** Issues 3, 4, 6, and 7  
**Purpose:** Prove v0.7 behavior with expectation-based fixtures.

Acceptance criteria:

- [ ] Fixtures cover branches, loops, nested functions, exceptions, imports plus local shadowing, comprehensions, lambdas, global/nonlocal declarations, and dynamic unresolved cases.
- [ ] Evaluation reports supported, unsupported, ambiguous, and uncertain semantic cases.
- [ ] Evaluation checks no-source-disclosure behavior.
- [ ] Evaluation confirms default Context Packs are unchanged unless semantic hints are enabled.

### Issue 9: v0.7 Docs, Known Limitations, And Release Readiness

**Type:** HITL  
**Blocked by:** Issues 2 through 8  
**Purpose:** Final release documentation and signoff.

Acceptance criteria:

- [ ] Docs explain what semantic facts mean and what they do not mean.
- [ ] Docs explain how assistants should interpret uncertainty.
- [ ] Docs show `semantic-inspect` examples.
- [ ] Known limitations document unsupported Python constructs and dynamic behavior.
- [ ] Release gate includes tests, lint, typecheck, semantic evaluation, artifact audit, and build.

## Recommended Release Gates

Suggested final gate:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
uv run repolens evaluate-context --json
uv run repolens semantic-inspect tests/fixtures/semantic/simple_branch.py --json
uv run repolens audit-artifacts /repo
uv build
```

Adjust paths and fixture names to match the actual repository layout.

## Bottom Line

This v0.7 plan is directionally correct and should be approved with one key constraint:

```text
Keep v0.7 narrow.
Build Python function-level CFG and local lexical binding facts first.
Keep all semantic facts experimental, source-free, deterministic, and opt-in.
Do not promote semantic facts into the trusted default graph until later evidence proves they are stable and useful.
```

Approved v0.7 release flexibility:

```text
v0.7 may ship with semantic contract, Python CFG/binding extraction, separate semantic artifacts, semantic-inspect, evaluation, docs, and artifact safety checks.
Context Pack semantic enrichment is opt-in and conditional, not a release blocker.
```
