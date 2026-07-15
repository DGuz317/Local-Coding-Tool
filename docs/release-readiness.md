# RepoLens MCP v0.9 Release Readiness

This checklist is for manual dogfooding and release prep. It does not publish to PyPI or a Docker registry. Use `docs/release-checklist.md` as the final release gate checklist and `docs/changelog-template.md` for release notes.

v0.9 release readiness is about one low-friction agent workflow: install the package, register the read-only stdio MCP command, and call Assistant Preflight before broad repository reads. The first call initializes missing graph state and later calls refresh stale state without project configuration, a separate indexing step, network access, or repository command execution. Focus hints, budget controls, experimental semantic hints, and AI Proposals remain optional and explicit.

v0.8 release readiness is about the optional AI Proposal Layer: disabled-by-default, metadata-only interpretations that remain outside the trusted deterministic graph while proving stable input identity, explicit provider provenance, bounded persistence, artifact safety, and read-only behavior.

v0.7 release readiness is about the Python Semantic Analysis Prototype: experimental, source-free Python CFG and lexical binding facts that remain separate from the stable graph contract while proving deterministic semantic inspection, evaluation, artifact safety, and release-gate evidence.

v0.5 release readiness is about a stable Assistant Preflight adoption path. Assistants should call preflight before broad file reads, then use the returned first-read files, likely tests, warnings, freshness, budget metadata, and candidate commands as orientation only.

v0.6 release readiness is about parser/resolver evidence that improves first-read relevance while preserving uncertainty and source-safety. JS/TS call-chain facts, re-export metadata, workspace package imports, and Next.js App Router route hints must remain compact metadata and must not become source mirrors or runtime framework/package-manager/compiler execution.

v0.4 release readiness is about trust in package/workspace repositories. The package/workspace evidence must show that RepoLens preserves uncertainty through Relationship Candidates, Graph Quality Warnings, unresolved statuses, and known limitations instead of inventing package facts.

## Human Checkpoint

Before treating release-facing docs as final, a human maintainer must confirm:

- Project and distribution name: `repolens` / RepoLens MCP.
- License wording and whether a license file should be added before release.
- PyPI publishing remains deferred for v0.9 unless a maintainer opens an explicit release issue.
- Docker registry publishing remains deferred for v0.9 unless a maintainer opens an explicit release issue.
- Assistant client config examples for OpenCode, Claude Desktop, and Cursor-style MCP are accurate for the current CLI command shape.
- Final README positioning and whether the README should target users, contributors, or both.
- Known limitations in `docs/known-limitations.md` reflect dogfooding and semantic evaluation outcomes and are acceptable for release.
- v0.4 maintainer release judgment for issue #128 remains recorded as the v0.5 prerequisite.
- Final v0.5 maintainer release judgment is recorded before v0.5 is cut.
- Final v0.6 maintainer release judgment is recorded before v0.6 is cut.
- Final v0.7 maintainer release judgment is recorded before v0.7 is cut.
- Final v0.8 maintainer release judgment is recorded before v0.8 is cut, and does not overstate local test-provider dogfood as external-model quality.
- Final v0.9 maintainer release judgment reviews `docs/dogfood/2026-07-15-v0.9-release-readiness.md`, including empty First-Read File outcomes, local timing variance, and the absence of a token-saving claim.

## Local Verification Gate

Run from the repository root:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
uv run repolens evaluate-context --json
uv run repolens evaluate-semantics --export-debug-jsonl --json
uv run repolens index . --experimental-semantic-artifact --json
uv run repolens semantic-inspect tests/fixtures/semantic_evaluation/branch_cfg.py --json
uv run repolens semantic-inspect tests/fixtures/semantic_evaluation/branch_cfg.py --from-source --json
uv run repolens audit-artifacts . --json
uv build --out-dir /tmp/repolens-dist --clear
```

The CI release gate also runs the v0.4 package/workspace regression subset: `tests/test_config_index.py`, `tests/test_javascript_index.py`, and `tests/test_query_service.py`.

## v0.4 Assistant-Facing Documentation

The v0.4 assistant-facing contract uses these domain terms:

- Package Identity: an explicit local package name from supported package metadata, not a directory-name guess.
- Workspace Membership: a Package Identity inside explicit workspace scope.
- Package Ownership: the nearest evidence-backed package root for a file.
- Local Resolution: deterministic import-to-file resolution from local source/config evidence.
- Relationship Candidate: bounded metadata for plausible, ambiguous, or unresolved package/workspace/import relationships; not a graph edge.
- Graph Quality Warning: structured warning metadata for incomplete, ambiguous, unsupported, or unresolved graph facts.
- Candidate Verification Command: a found command with `run: false`, purpose metadata, and a separate command risk bucket.

Context Packs may surface package/workspace ownership facts, relationship candidates, graph-quality warning codes, docs/config orientation, related package references, and command risk buckets as structured metadata only. They must not include source snippets, code bodies, function signatures, raw config values, raw comments, raw Agent Guidance text, paragraph excerpts, or absolute host paths.

## v0.6 Assistant-Facing Documentation

The v0.6 assistant-facing contract keeps Assistant Preflight as the first step before broad file reads and adds richer JS/TS orientation metadata:

- Tree-sitter JS/TS is the default parser backend when the parser and grammar packages are available. If not available, RepoLens falls back to the legacy bounded scanner and emits parser-backend warnings.
- Parser-backed facts include stable, source-free module, import, export, top-level symbol, provenance, and line-range metadata only.
- Call Chain Facts are structural metadata, not runtime proof, framework lifecycle analysis, or deep semantic call graphs.
- Framework Route Hints are deterministic hints from local file/config/parser evidence, not framework emulation, compiler output, bundler output, or runtime route proof.
- Resolver outcomes preserve uncertainty for unsupported aliases, ambiguous exports, incomplete workspace evidence, and complex package entrypoints through unresolved statuses, candidates, Relationship Candidates, and Graph Quality Warnings.
- Assistant-facing output must continue to omit source snippets, code bodies, function signatures, full import lines, raw comments, raw Agent Guidance text, raw config values, and absolute host paths.

## v0.9 Assistant-Facing Documentation

- Supported first use is a locally installed `repolens` command registered as `repolens mcp /absolute/path/to/repo`, followed by MCP `assistant_preflight` before broad reads.
- No RepoLens project configuration or prior `index` command is required. Explicit `index`, `update`, `status`, and `audit-artifacts` remain diagnostics and release tools.
- Focus hints and budget controls are optional deterministic narrowing inputs. Experimental semantic hints and AI Proposals remain explicit opt-ins and do not alter default graph truth.
- Assistant Preflight may return no First-Read Files when Task Matching evidence is sparse. This is bounded uncertainty, not evidence that no relevant files exist; callers may retry with a repo-relative focus hint.
- Normal indexing and MCP use remain local-first, without telemetry, hidden network access, package-manager/compiler/framework execution, or write-capable MCP tools.
- Artifact Safety Audit explicitly covers redaction, bounded output, repo-relative paths, deterministic ordering, No Whole-Source Disclosure, and Candidate Verification Commands remaining not run.

## v0.8 Assistant-Facing Documentation

The v0.8 assistant-facing contract keeps AI optional and outside deterministic graph facts:

- AI is disabled by default; every enabled request explicitly selects a provider and model, with no hidden provider call or fallback.
- Default AI input is deterministic, redacted, size-bounded RepoLens metadata rather than whole source files, raw comments, raw Agent Guidance, credentials, or raw provider errors.
- Context Pack Summary, Architecture Explanation, and Patch Plan outputs are labeled AI Proposals with provider/model provenance, evidence refs, confidence, warnings, limitations, input packer version, redaction policy version, and input digest.
- AI Proposal generation does not change Canonical Graph Hash, Context Pack IDs or ranking, Task Matching, resolver behavior, Package Ownership, or graph traversal.
- Proposals are ephemeral by default. Explicit save writes only a bounded proposal artifact and immediately runs Artifact Safety Audit; later audits include saved proposals only through explicit `--include-ai-proposals`.
- Patch Plan Proposals do not produce apply-ready diffs, write project files, apply patches, run commands, mutate branches, or post remote comments. Active Workflow remains deferred beyond v0.8.

v0.8 release readiness requires deterministic evidence that equivalent packed input has a stable digest, all three proposal kinds satisfy schema `0.8.ai_proposal.v1`, disabled behavior leaves default output unchanged, saved proposals pass Artifact Safety Audit, and dogfood records usefulness and overclaiming limits.

## v0.7 Assistant-Facing Documentation

The v0.7 assistant-facing contract keeps semantic facts out of default MCP and Context Pack output while documenting the explicit CLI inspection path:

- v0.7 Python semantic facts are experimental, source-free metadata stored separately from the stable graph.
- `semantic-inspect` reads indexed semantic artifacts by default; missing, stale, or incompatible artifacts return artifact status and freshness instead of implicit live parsing.
- `semantic-inspect --from-source` is explicit, non-persistent debug output, not indexed repository state.
- Python CFG facts and lexical binding facts are candidate metadata, not runtime reachability proof, data-flow analysis, taint analysis, type inference, raw-value recovery, or dynamic behavior proof.
- Assistant-facing output and semantic artifacts must omit source snippets, code bodies, function signatures, raw condition text, raw expression text, raw values, raw comments, raw docstrings, raw string literals, raw secrets, raw Agent Guidance text, absolute host paths, and AI prose summaries.

v0.7 release readiness requires passing semantic evaluation evidence for Python CFG, lexical binding, warnings, and no-disclosure fixtures.

v0.7 release readiness requires artifact audit evidence that semantic artifacts and assistant-facing output do not leak source snippets, code bodies, function signatures, raw comments, raw docstrings, raw string literals, raw secrets, raw Agent Guidance text, or absolute host paths.

v0.7 release readiness requires evidence that semantic facts are excluded from Canonical Graph Hash, default Context Pack IDs, stable graph validation, default MCP output, default Assistant Preflight output, and default Context Pack output.

Optional Context Pack semantic hints are included in v0.7 only behind explicit `include_experimental_semantic_hints` opt-in; they are documented, audited, release-gated, and absent from default Context Pack and Assistant Preflight output.

## Isolated Native Install Smoke

Build and install the package in an isolated environment:

```bash
uv build
uv tool install --force dist/*.whl
repolens --help
repolens status .
uv tool uninstall repolens
```

Alternative `pipx` smoke if `pipx` is available:

```bash
uv build
pipx install --force dist/*.whl
repolens --help
pipx uninstall repolens
```

## Docker Build And Index Smoke

Build the local image:

```bash
docker build -t repolens:latest .
```

Run indexing without runtime network access and with the host user mapped, so `.repolens` files are not root-owned:

```bash
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$PWD:/workspace" repolens:latest index /workspace
test "$(stat -c '%u:%g' .repolens/graph.sqlite)" = "$(id -u):$(id -g)"
```

Check that status is read-like:

```bash
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$PWD:/workspace" repolens:latest status /workspace
```

## Docker MCP Smoke

Start the stdio MCP server through Docker with no runtime network access:

```bash
docker run --rm -i --network none --user "$(id -u):$(id -g)" -v "$PWD:/workspace" repolens:latest mcp /workspace
```

Use an MCP client to list tools and call at least `graph_status`, `get_task_context`, `expand_context`, and `explain_relevance`.

## Assistant Preflight Adoption Smoke

Run setup diagnostics before connecting an assistant:

```bash
uv run repolens --help
uv run repolens index /absolute/path/to/repo
uv run repolens status /absolute/path/to/repo
uv run repolens preflight /absolute/path/to/repo "Check setup readiness" --json
```

Expected smoke result:

- `assistant_preflight_version` is present.
- Graph freshness is included.
- First-read files, likely tests, warnings, confidence, limits, truncation, and budget controls are bounded.
- Candidate verification commands, when present, are marked found and `run: false`.
- Output contains repo-relative paths and structural metadata, not source snippets.

Use an MCP client to list tools and call `assistant_preflight` before broad file reads. OpenCode, Claude Desktop, and Cursor-style config examples live in `docs/assistant-usage-guide.md` and the README.

## Docker Preflight Smoke

Build and exercise a local image without registry publishing:

```bash
docker build -t repolens:latest .
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$PWD:/workspace" repolens:latest index /workspace
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$PWD:/workspace" repolens:latest preflight /workspace "Check Docker setup" --json
```

This smoke must not push an image, publish a package, or require runtime network access.

## PyPI Readiness Smoke

Build and install a local wheel without publishing:

```bash
uv build --out-dir /tmp/repolens-dist --clear
uv tool install --force /tmp/repolens-dist/*.whl
repolens --help
repolens preflight /absolute/path/to/repo "Check wheel setup" --json
uv tool uninstall repolens
```

This checks local packaging readiness only. Publishing to PyPI remains deferred unless a maintainer opens an explicit release issue.

## Context Pack CLI Smoke

Index a local repository, then request human and JSON Context Packs:

```bash
uv run repolens index .
uv run repolens context . "Document Context Pack workflow"
uv run repolens context . "Document Context Pack workflow" --json
```

Expected smoke result:

- `ok: true` after graph artifacts exist.
- `data.context_pack_id` is present.
- `data.first_read_files` is bounded by the default budget.
- `data.expansion_handles` references returned items only.
- Output contains repo-relative paths and structural metadata, not source snippets.
- Candidate verification commands, when present, are marked not run.

## Context Pack Evaluation

Run the release-blocking fixture suite:

```bash
uv run repolens evaluate-context
uv run repolens evaluate-context --json
```

The JSON command exits non-zero when the expectation-based release gate fails. The report covers direct symbol tasks, test-focused tasks, docs/config tasks, broad tasks, ambiguity, no matches, focus hints, stale graphs, secret redaction, stale pack IDs, JS/TS call chains, alias ambiguity, re-export behavior, workspace package imports, route hints, and no-source-disclosure negatives.

Latest local evidence for issue #229 on 2026-07-15:

- Blocker status: #222, #225, #226, #227, and #228 are closed before final readiness judgment.
- Full gate: `uv run pytest` passed 249/249 tests; Ruff lint, Ruff format check, mypy, Context Pack Evaluation (28/28 cases and all 27 release-blocking cases), Semantic Evaluation (4/4 cases), and package build passed.
- Safety: representative Artifact Safety Audits passed with zero violations. The audit output now names redaction, bounded output, repo-relative path, deterministic ordering, No Whole-Source Disclosure, and not-run command checks explicitly, with regression coverage for stable ordered output.
- Package/MCP smoke: a clean virtual environment installed the built wheel; installed CLI help and packaged first-use MCP smoke passed. The first call initialized missing graph state and the second refreshed a changed graph without prior indexing, project settings, network access, or repository command execution.
- Dogfood: `docs/dogfood/2026-07-15-v0.9-release-readiness.md` covers RepoLens itself, a Python single package, a JS/TS workspace, and mixed docs/config. Generated artifacts and repository snapshots were not committed.
- First-read quality: the JS/TS workspace returned four First-Read Files. Three task wordings returned none; this is documented as sparse Task Matching evidence and a reason to use focus hints, not as proof of absent relevant files.
- Performance: local initial indexing ranged from 35.9 ms for the mixed fixture to 16.679 seconds for RepoLens. Selective Update ranged from 40.6 ms to 33.791 seconds. The 1,000-file relative benchmark measured 1.206 seconds for Selective Update and 0.803 seconds for full rebuild, so no cache, worker-pool, or parallel indexing complexity was justified or added.
- Bounded context: dogfood preflight envelopes ranged from 4,633 to 16,060 serialized characters. Context evaluation reported 34 files and 17 likely irrelevant files avoided versus its lexical path baseline, but its approximate-token field was negative; v0.9 therefore makes no exact or universal token-saving claim.
- Boundaries: no telemetry, hosted service, package publishing, container publishing, write-capable MCP tool, hidden network call, or repository command execution was added.
- Maintainer release judgment: implementation evidence passes; publication remains a human checkpoint after accepting the documented first-read and performance limitations.

Latest local evidence for issue #209 on 2026-07-10:

- Blocker status: #208 is closed before final readiness judgment.
- Default safety evidence: a disabled Context Pack Summary request returned `status: disabled`, `provider_called: false`, `network_accessed: false`, and `file_written: false`. Context Pack ID and Canonical Graph Hash remained unchanged.
- Stable identity evidence: repeated equivalent Context Pack Summary input retained Context Pack ID `cp_8b8df4e9598223f9`, Canonical Graph Hash `4be838cac6d685fab22808e25063f9a4e0e38552e4a194a1026a67bbc62228ad`, and input digest `sha256:40574b0092e6c00de3eeb58e6ee953d429d8e1e0c11c8b0c624e3771b7875049`.
- Schema evidence: Context Pack Summary, Architecture Explanation, and Patch Plan outputs were available under schema `0.8.ai_proposal.v1` with explicit local test-provider/model provenance, evidence refs, input boundary, source-disclosure status, confidence, warnings, and limitations.
- Artifact evidence: explicit save returned `saved: true` and `safety_audit_passed: true`; `uv run repolens audit-artifacts /tmp/repolens-v08-dogfood --include-ai-proposals --json` returned `ok: true` with zero violations.
- Dogfood evidence: `docs/dogfood/2026-07-10-v0.8-ai-proposal-layer.md` records that Context Pack Summary helped confirm first reads, Architecture Explanation cited 12 useful node/neighbor evidence refs, and Patch Plan found a plausible implementation file plus three related tests.
- Dogfood limitation: the docs-focused Patch Plan omitted the supplied documentation target, docs/config risk notes, and Candidate Verification Commands. This remains bounded proposal incompleteness, not a graph claim; no output implied command execution, project file writes, graph mutation, patch application, branch mutation, or remote posting.
- Commands unavailable: external-provider dogfood could not run because v0.8 supports only the local deterministic `test` provider. Replacement evidence is deterministic local-provider dogfood, repeated-input digest evidence, focused schema/safety tests, stable graph and Context Pack identity checks, and explicit saved-artifact audit.
- Full verification gate: passed in this branch. `uv run pytest` passed 254/254 tests. `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src/repolens`, `uv run repolens evaluate-context --json`, `uv run repolens audit-artifacts /tmp/repolens-v08-dogfood --include-ai-proposals --json`, and `uv build --out-dir /tmp/repolens-dist --clear` passed.
- Maintainer release judgment: approved for the narrow v0.8 AI Proposal contract after the full gate passed. This approval does not claim external-model quality and does not approve Active Workflow behavior.

Latest local evidence for issue #190 on 2026-07-09:

- Blocker status: #181, #182, #183, #184, #185, #186, #187, #188, and #189 are closed before final readiness judgment. Optional Context Pack semantic hints are included only behind explicit `include_experimental_semantic_hints` opt-in and do not change default Context Pack or Assistant Preflight output.
- Assistant-facing docs: README, `docs/assistant-usage-guide.md`, `docs/known-limitations.md`, `docs/repolens-v0.7-release-tracker.md`, and this readiness file explain that Python semantic facts are experimental, source-free, separate from the stable graph contract, and not default MCP or Context Pack output.
- Semantic inspection evidence: `uv run repolens index . --experimental-semantic-artifact --json` returned `ok: true`, wrote `.repolens/semantic.sqlite`, indexed 225 eligible files, and skipped 19 paths. `uv run repolens semantic-inspect tests/fixtures/semantic_evaluation/branch_cfg.py --json` returned `ok: true`, `inspection_mode: indexed_artifact`, present/current artifact status, `schema_version: 3`, `source_snippets: 0`, Python CFG branch/return/exit facts, and lexical binding facts. `uv run repolens semantic-inspect tests/fixtures/semantic_evaluation/branch_cfg.py --from-source --json` returned `ok: true`, `inspection_mode: from_source_debug`, `persistent: false`, `writes_artifacts: false`, and the warning `Live --from-source debug output is not indexed repository state.`
- Semantic evaluation evidence: `uv run repolens evaluate-semantics --export-debug-jsonl --json` returned `ok: true`, release gate passed, 4/4 semantic cases passed, case summary `supported: 3`, `unsupported: 1`, `ambiguous: 1`, and `uncertain: 2`. Stable contract checks confirmed Canonical Graph Hash unchanged, default Context Pack ID unchanged, default Context Pack paths unchanged, and default MCP output excludes semantic facts. Debug export evidence confirmed `.repolens/semantic.jsonl` was written, deterministic, source-free, separate from stable graph, and passed.
- Context evaluation evidence: `uv run repolens evaluate-context --json` returned `ok: true`, release gate passed, 27/27 total cases passed, 26/26 release-blocking cases passed, 5/5 Assistant Preflight dogfood cases passed, 2/2 artifact audit cases passed, 37 candidate commands marked not run, and 1 stale graph risk case.
- Artifact audit evidence: `uv run repolens audit-artifacts . --json` returned `ok: true`, audited 9 artifacts including `.repolens/semantic.sqlite`, and reported 0 violations. Audit checks passed for source snippet leakage, absolute host paths, raw secret-like values, raw Agent Guidance mirroring, oversized artifacts, candidate commands not run, JS/TS Call Chain Facts source-free columns, artifact boundary, and MCP/preflight contract preservation.
- Optional Context Pack semantic hints evidence: issue #189 is closed, and `uv run pytest` includes `test_context_pack_and_preflight_opt_in_to_indexed_semantic_hints`, which proves default Context Pack and Assistant Preflight output omit `experimental_semantic_hints`, opt-in output includes bounded source-free hints, CLI and MCP outputs agree, and raw source strings do not leak.
- No-disclosure judgment: v0.7 semantic artifacts, debug/evaluation exports, default Context Packs, default Assistant Preflight, and MCP-facing output must not include source snippets, raw condition text, function signatures, raw expression text, raw values, function bodies, code bodies, raw comments, raw docstrings, raw string literals, raw secrets, raw Agent Guidance text, absolute host paths, or AI prose summaries. The semantic secret-like symbol regression test covers redaction of function, parameter, assignment, and semantic identity names before artifact audit.
- Full verification gate: passed in this branch. `uv run pytest` passed 230/230 tests. `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy src/repolens` passed. `uv run repolens evaluate-context --json`, `uv run repolens evaluate-semantics --export-debug-jsonl --json`, `uv run repolens index . --experimental-semantic-artifact --json`, indexed and live `semantic-inspect`, `uv run repolens audit-artifacts . --json`, and `uv build --out-dir /tmp/repolens-dist --clear` passed. Build produces v0.7.0 distribution artifacts after the release version metadata update.
- Maintainer release judgment: approved for v0.7 release readiness after the full verification gate passes. Optional Context Pack semantic hints are included only behind explicit opt-in and remain experimental, bounded, source-free metadata.

Latest local evidence for issue #170 on 2026-07-06:

- Blocker status: #163, #164, #165, #166, #167, #168, and #169 are closed before final readiness judgment.
- Assistant-facing docs: README, `docs/assistant-usage-guide.md`, `docs/known-limitations.md`, `docs/security-and-artifact-privacy.md`, and `docs/releases/v0.6.0.md` explain Tree-sitter JS/TS default-when-available behavior, legacy bounded scanner fallback warnings, source-free Call Chain Facts, Framework Route Hints as hints, resolver uncertainty, and v0.6 artifact safety boundaries.
- Dogfood evidence: `docs/dogfood/2026-07-06-v0.6-dogfood-evaluation-pack.md` covers JS/TS workspace aliases and package boundaries, source-free call chains, re-export behavior, Next.js App Router route hints, alias ambiguity, stale graph behavior, and no-source-disclosure negatives.
- Local savings metrics: `uv run repolens evaluate-context --json` reports fixture-derived estimates only; they are not telemetry, exact model-token claims, or universal productivity scores.
- Parser timing evidence: `uv run repolens evaluate-context --json` records bounded local fixture index timing and eligible file counts only to document v0.6 limitations, not to add parse cache, worker pools, indexing parallelism, or runtime package-manager/compiler/framework execution.
- Artifact audit evidence: `uv run repolens audit-artifacts . --json` remains the safety gate for source snippet leakage, absolute host paths, raw secrets, raw Agent Guidance mirroring, bounded artifact size, candidate commands not run, JS/TS Call Chain Facts source-free columns, and MCP/preflight contract preservation.
- Full verification gate: passed in this branch. `uv run pytest` passed 207/207 tests. `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy src/repolens` passed. `uv run repolens evaluate-context --json` returned `ok: true`, release gate passed, 27/27 total cases passed, 26/26 release-blocking cases passed, and 5/5 Assistant Preflight dogfood cases passed. Local savings summary reported 28 files avoided vs lexical search, 16 likely irrelevant files avoided, 37 candidate commands marked not run, and 1 stale graph risk case. Bounded parser/index evidence reported 167 eligible fixture files and max fixture index time of 45 ms. `uv run repolens index . --json` prepared root artifacts for audit with 215 eligible files and 19 skipped paths. `uv run repolens audit-artifacts . --json` returned `ok: true`, audited 8 artifacts, passed `call_chain_facts_source_free`, and reported 0 violations. `uv build --out-dir /tmp/repolens-dist --clear` built `repolens-0.6.0.tar.gz` and `repolens-0.6.0-py3-none-any.whl`.
- Maintainer release judgment: approved for v0.6 release after the full verification gate passes. Publishing to PyPI or a Docker registry remains deferred unless a separate maintainer-approved release issue is opened.

Latest local evidence for issue #169 on 2026-07-06:

- Dogfood evidence: `docs/dogfood/2026-07-06-v0.6-dogfood-evaluation-pack.md` covers JS/TS workspace aliases and package boundaries, source-free call chains, re-export behavior, Next.js App Router route hints, alias ambiguity, stale graph behavior, and no-source-disclosure negatives.
- Local savings metrics: `uv run repolens evaluate-context --json` reports fixture-derived estimates only; they are not telemetry, exact model-token claims, or universal productivity scores.
- Parser timing evidence: `uv run repolens evaluate-context --json` records bounded local fixture index timing and eligible file counts only to document v0.6 limitations, not to add parse cache, worker pools, indexing parallelism, or runtime package-manager/compiler/framework execution.
- Artifact audit evidence: `uv run repolens audit-artifacts . --json` remains the safety gate for source snippet leakage, absolute host paths, raw secrets, raw Agent Guidance mirroring, bounded artifact size, candidate commands not run, and MCP/preflight contract preservation.
- Maintainer release judgment: pending HITL approval for issue #169.

Latest local evidence for issue #149 on 2026-07-02:

- Blocker status: #139, #140, #141, #142, #143, #144, #145, #146, #147, and #148 are closed before final readiness judgment.
- Assistant-facing docs: README and `docs/assistant-usage-guide.md` explain CLI `preflight`, MCP `assistant_preflight`, deterministic focus hints and budget controls, stale or missing graph handling, candidate commands found but not run, and source-disclosure limitations.
- Dogfood evidence: `docs/dogfood/2026-07-02-v0.5-dogfood-evaluation-pack.md` covers JS/TS workspace, Python package, docs-heavy, config-heavy, ambiguous import, stale graph, and package/workspace scenarios.
- Local savings metrics: `uv run repolens evaluate-context --json` reports fixture-derived estimates only; they are not telemetry, exact model-token claims, or universal productivity scores.
- Artifact audit evidence: `uv run repolens audit-artifacts . --json` checks generated `.repolens/` artifacts and representative preflight output for source snippet leakage, absolute host paths, raw secrets, raw Agent Guidance mirroring, bounded artifact size, candidate commands not run, and MCP/preflight contract preservation.
- Full verification gate: passed in this branch. `uv run pytest` passed 192/192 tests. `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy src/repolens` passed. `uv run repolens evaluate-context --json` returned `ok: true`, release gate passed, 23/23 total cases passed, 22/22 release-blocking cases passed, and 4/4 Assistant Preflight dogfood cases passed. Local savings summary reported 22 files avoided vs lexical search, 10 likely irrelevant files avoided, 31 candidate commands marked not run, and 1 stale graph risk case. `uv run repolens index . --json` prepared root artifacts for audit with 206 eligible files and 19 skipped paths. `uv run repolens audit-artifacts . --json` returned `ok: true`, audited 8 artifacts, and reported 0 violations. `uv build --out-dir /tmp/repolens-dist --clear` built `repolens-0.5.0.tar.gz` and `repolens-0.5.0-py3-none-any.whl`.
- Maintainer release judgment: approved for v0.5 release after the full verification gate passes. Publishing to PyPI or a Docker registry remains deferred unless a separate maintainer-approved release issue is opened.

Latest local evidence for issue #128 on 2026-06-30:

- `uv run repolens evaluate-context --json`: `ok: true`, release gate passed, 19/19 cases passed, including v0.4 package/workspace, unresolved alias warning, ambiguous workspace import candidate, docs/config orientation, command risk bucket, v0.3.1 regression, and no-source-disclosure cases.
- `uv run repolens index tests/fixtures/dogfood/js-ts-workspace --json`: `ok: true`, indexed 9 eligible files, skipped `.repolens/` as generated artifacts.
- `uv run repolens context tests/fixtures/dogfood/js-ts-workspace "Trace @dog/lib workspace import and package ownership" --json`: `ok: true`, confidence `medium`, surfaced evidence-backed package boundaries for `@dog/app` and `@dog/lib`, and returned candidate verification commands with `run: false`, `verification_likely`, and `quality_check_likely` risk buckets.
- Full verification gate: passed in this branch with `uv run pytest` at 170/170 tests passed, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src/repolens`, `uv run repolens evaluate-context --json`, and `uv build --out-dir /tmp/repolens-dist --clear`.
- Maintainer release judgment: pending HITL approval for issue #128.

Latest local evidence for issue #87 on 2026-06-24:

- `uv run repolens evaluate-context --json`: `ok: true`, release gate passed, 11/11 cases passed.
- Metrics reported include first-read hit rate, irrelevant file count, test inclusion, pack size, expansion count, and safety negative outcomes across Context Pack, `suggest_reading_order`, and lexical baselines.
- `uv run repolens index .`: indexed 154 eligible files and wrote ignored local `.repolens/` artifacts.
- `uv run repolens context . "Document Context Pack workflow" --json`: `ok: true`, confidence `medium`, returned `context_pack_id`, First-Read Files, likely tests, Agent Guidance metadata, expansion handles, freshness, limits, and truncation metadata with no source snippets.
- Direct follow-up smoke for MCP-backed service functions: `get_task_context_ok=True`, `expand_context_ok=True`, `explain_relevance_ok=True` for a returned First-Read File handle.

## OpenCode Dogfood

- Copy the shape from `docs/opencode-mcp.example.jsonc` into a local OpenCode config outside this repository.
- Replace `1000:1000` with your host user and group IDs from `id -u` and `id -g`.
- Replace `/absolute/path/to/repo` with the absolute path to the repository being indexed.
- Confirm OpenCode can list the RepoLens tools.
- Ask the assistant to call `graph_status` before relying on graph context.

## Dogfooding Reports

- Follow `docs/dogfood/README.md` for dogfooding reports and fixture policy.
- Commit dated reports under `docs/dogfood/`.
- Commit only distilled regression fixtures under `tests/fixtures/dogfood/`; do not commit `.repolens/` artifacts or vendored third-party repository snapshots.
- The v0.4 JS/TS workspace report is `docs/dogfood/2026-06-30-v0.4-js-ts-workspace.md`.
- v0.4 release remains blocked on full verification, Context Pack Evaluation passing, and explicit maintainer release judgment, even when dogfooding reports are complete.

## Scope Guard

Do not add these as part of v0.4 release prep unless a maintainer opens a separate issue:

- PyPI publishing.
- Docker registry publishing.
- Dependabot or dependency update automation.
- Contributor pre-commit hook setup.
- Runtime network calls during indexing or MCP serving.
- Embeddings, LLM-generated summaries, telemetry, hosted evaluation, or persisted Context Pack sessions.
- Source snippets, code bodies, function signatures, paragraph excerpts, raw comment text, or raw Agent Guidance instruction text in Context Pack output.
