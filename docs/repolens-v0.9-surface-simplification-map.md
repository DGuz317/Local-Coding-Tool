# RepoLens v0.9 Surface Simplification Decision Map

## Decision status

**Approved scope:** decisions about this RepoLens repository only. Nothing in this map authorizes RepoLens to delete, rewrite, or clean files in a repository that RepoLens analyzes.

**Removal checkpoint:** no `remove` or `consolidate` row below may be implemented until a human maintainer approves this map. Approval of the map authorizes follow-up issues, not unreviewed bulk deletion. Each follow-up must preserve the surviving contract and verify the affected vertical slice.

This audit was prepared for issue #221 from `feature/repolens-v0.9` at commit `c296300`. It used the tracked Git tree, CodeGraph references and caller/test links, CLI and MCP registrations, package metadata, tests, user documentation, release gates, `CONTEXT.md`, and every ADR under `docs/adr/`. Untracked local files and generated `.repolens/`/`.codegraph/` data were excluded.

## Classification rules

Absence from one search is never enough to remove a surface.

| Classification | Evidence required |
| --- | --- |
| **Retain** | At least one current entry point, package/runtime dependency, supported public contract, release requirement, or active domain/safety decision, plus no stronger superseding decision. Tests and current user documentation strengthen the decision. |
| **Remove** | No current implementation or package entry-point dependency; no supported CLI/MCP/artifact contract; no release-gate need; no active domain or ADR requirement; and positive evidence that the surface is stale, contradictory, or replaced. Its tests and documentation must be removed or redirected in the same follow-up slice. |
| **Consolidate** | Two or more supported surfaces serve substantially the same workflow, a named surviving surface exists, and migration can preserve required behavior. Existing tests/docs are evidence of migration cost, not evidence that duplicate exposure must remain forever. |
| **Unresolved** | Evidence conflicts, a compatibility consumer is unknown, historical value may still be active, or no surviving contract has been selected. Unresolved means no deletion. |

A removal follow-up must trace all seven evidence columns: implementation, CLI, MCP, tests, user/developer docs, packaging, and contracts/release/domain decisions. Public artifact or MCP shape changes require contract tests and a migration decision.

## Protected surfaces

These are not cleanup candidates:

- `CONTEXT.md`, because it is the active product glossary and boundary document.
- `docs/adr/0001` through `0006`, including proposed ADRs, because ADR history records why contracts exist. A later decision may mark an ADR superseded but must not delete it.
- provenance and uncertainty fields: Edge Contract evidence, Resolution Strategy, Relationship Candidates, Graph Quality Warnings, parser/backend provenance, Canonical Graph Hash, and freshness metadata.
- safety contracts and their tests: MCP Response Envelope, No Whole-Source Disclosure, Redaction Policy, Artifact Safety Audit, repo-relative POSIX paths, bounded output, and Candidate Verification Commands remaining not run.
- release notes and dated dogfooding reports. They are historical release evidence, not current setup guidance.
- `.agents/skills/` and `docs/agents/`, which define the current maintainer workflow rather than the RepoLens runtime product.

## Decision map

### Retain

| Surface | Implementation and exposure | Tests and docs | Packaging, contract, and decision evidence | Decision |
| --- | --- | --- | --- | --- |
| Assistant Preflight | `context_pack.py`; CLI `preflight`; MCP `assistant_preflight` | Context Pack service/contract/evaluation, CLI preflight, and MCP tests; README and assistant guide | Primary workflow in #219 and `CONTEXT.md`; issue #220 supplies missing-graph first use | **Retain** as the primary agent entry point. |
| Context Pack and Progressive Disclosure | `context_pack.py`; CLI `context`; MCP `get_task_context`, `expand_context`, `explain_relevance` | `test_context_pack_*`, evaluation fixtures, MCP tests; context contract and tool examples | ADR 0003 requires deterministic, stateless, bounded orientation; IDs and Item Handles are public contracts | **Retain** the service and bounded expansion contract. CLI/MCP duplication is considered separately below. |
| Graph lifecycle and validation | `scanner.py`, language/config/doc indexers, `graph.py`, `graph_store.py`, `indexer.py`; CLI `index`, `update`, `status`; MCP `graph_status` | Scanner, parser, resolver, graph-store, CLI lifecycle, update, and synthetic-repository tests | Core package behavior; Graph Store Seam, Selective Update, Branch-Aware Freshness, and Graph Validation are active domain terms; release smoke requires explicit diagnostics | **Retain**. Automatic preflight does not remove explicit maintainer troubleshooting commands. |
| Structured query and targeted fallback | `query.py`, `text_search.py`; MCP graph traversal, impact, entrypoint, and bounded text-search tools; CLI `search`, `search-graph` | Query, Related Test, CLI search/report, and MCP tests; tool examples and security docs | Progressive Disclosure needs bounded follow-up; text search is the documented scanner-approved exception to metadata-only graph search | **Retain** pending usage evidence. These are specialized follow-ups, not the first-use workflow. |
| MCP server and response envelope | `mcp_server.py`, `mcp_envelope.py`; CLI `mcp`; 15 registered read-only tools | MCP/envelope/service tests; client examples and security docs | `repolens` console script is the sole package entry point; ADR 0001 and #219 preserve read-only MCP and the standard envelope | **Retain**. Tool-count simplification must happen through explicit rows below. |
| Artifact, budget, redaction, and audit contracts | `artifact_budget_contract.py`, `redaction.py`, `artifact_audit.py`; CLI `audit-artifacts` | Dedicated budget, redaction, and artifact-audit tests; privacy and budget docs | Required by #219, release checklist, and No Whole-Source Disclosure | **Retain**. Cleanup cannot weaken these gates. |
| Evaluation and performance evidence | `context_evaluation.py`, `benchmark.py`; CLI `evaluate-context`, `benchmark-update` | Context evaluation and update benchmark tests; dogfood and release docs | Context Pack Evaluation, Local Savings Metric, Update Benchmark, and Performance Escalation Gate are v0.9 decision inputs | **Retain** as developer/release commands; do not promote them as routine user workflow. |
| Python and JS/TS deterministic foundation | `python_index.py`, `javascript_index.py`, `parser_backends.py`, resolver/config/documentation modules | Language, parser, resolver, config, docs, and fixture tests | Priority ecosystems in project policy and #219; ADRs 0002, 0004, and 0005 protect evidence/uncertainty semantics | **Retain**. |
| Build and release infrastructure | `pyproject.toml`, `uv.lock`, Docker files, `.github/workflows/*`, release checklist/readiness | CI, Docker smoke, package-build and install smoke | `pyproject.toml` packages only `src/repolens`, exposes `repolens = repolens.cli:app`, and uses README as package readme | **Retain**. Version/readiness wording should be updated in release-specific work, not deleted as cleanup. |

### Remove after human approval

| Candidate | Implementation / CLI / MCP | Tests | Documentation | Packaging and supported contracts | Decision and required follow-up |
| --- | --- | --- | --- | --- | --- |
| `AGENTS-v0.1.md`, `AGENTS-v0.2.md`, `AGENTS-v0.3.md` | No runtime imports, CLI registration, or MCP exposure; CodeGraph indexes current source/tests rather than these legacy instructions | No test names or fixtures depend on these paths | No tracked file links to these paths. Their branch/version instructions conflict with current `AGENTS.md` and v0.9 work | Not included in the wheel target; not active domain docs or ADRs. Git history preserves their historical text | **Remove together** in one docs-only slice. Keep current `AGENTS.md`, `.agents/skills/`, `docs/agents/`, `CONTEXT.md`, and ADRs. Verify tracked-reference search and normal docs/source checks. |
| `docs/Client-request.md` | No runtime imports, CLI registration, or MCP exposure | No tests depend on its path | No tracked inbound path reference. It describes superseded requirements including watch mode, Git hooks, visualization, raw comment output, and assistant-first report reading that conflict with current boundaries and Assistant Preflight | Not packaged in the wheel; not an ADR. Current product source is #219 plus `CONTEXT.md`; current setup is README/assistant guide | **Remove** in a docs-only slice after confirming the maintainer does not require it as a historical artifact. Preserve issue #219, release notes, dogfood reports, and ADRs. |

No source module, test, command, artifact, workflow, release note, dogfood report, active domain document, or ADR currently meets the `remove` threshold.

### Consolidate after human approval

| Overlap | Full trace | Surviving surface | Decision and migration requirement |
| --- | --- | --- | --- |
| MCP `suggest_reading_order` versus Assistant Preflight First-Read Files | Implemented in `query.py` and registered in `mcp_server.py`; covered by query, MCP, and context-evaluation tests; documented in tool examples, assistant guidance, troubleshooting, planning history, and release evidence; no separate package entry point; First-Read File and Assistant Preflight are active contracts | `assistant_preflight` for initial orientation; `get_task_context` plus handles for bounded follow-up | **Consolidate** by deprecating `suggest_reading_order` only after parity expectations are written for ordering, reasons, confidence, and limits. Remove its implementation/exposure/tests/docs coherently in a later versioned contract slice. Until then, retain it. |
| MCP `get_graph_report` versus metadata-first orientation | Implemented through `report.py`/`query.py` and MCP registration; covered by query/MCP and CLI report tests; documented in tool examples and historical PRD; release smoke still uses CLI `report`; report is not a package entry point | Keep CLI `report` for human troubleshooting and bounded graph queries/`repo_summary` for assistants | **Consolidate** the assistant-facing report exposure. A follow-up should first prove that no client/release contract requires MCP Markdown report retrieval, then deprecate MCP `get_graph_report` while retaining CLI report generation. |
| CLI `context` versus CLI `preflight` | Both call `context_pack.py`; both are tested and documented; `context` is also the underlying contract used by AI Proposal and semantic evaluation; one package script exposes both | Keep the Context Pack service and MCP follow-up tools; make CLI `preflight` the documented routine entry point | **Consolidate documentation first**, not implementation. Stop presenting `context` as a peer first-use command. Do not remove the service or CLI until compatibility and developer/evaluation consumers have a migration path. |
| Release-facing guidance spread across README, assistant guide, tool examples, troubleshooting, release checklist, and release readiness | No runtime exposure; all are tracked docs. README is package metadata; release checklist/readiness are gates; assistant/tool/troubleshooting docs have distinct audiences but repeat setup and stale-graph instructions | README short install/registration path; assistant guide client setup; tool examples contract examples; troubleshooting failures; checklist current gate; readiness evidence ledger | **Consolidate wording and links**, not files, in a release-doc slice. Preserve dated release evidence. Replace duplicated lifecycle-first instructions with zero-configuration preflight guidance after v0.9 behavior is complete. |

### Unresolved — do not remove

| Surface | Evidence for keeping | Evidence for simplification | Missing decision/evidence |
| --- | --- | --- | --- |
| Optional AI Proposal Layer (`ai_proposal.py`; CLI/MCP `create-ai-proposal`) | v0.8 release notes, dogfood, safety docs, CLI/MCP/service tests, Artifact Safety Audit integration, and active glossary contracts | Disabled by default, only a deterministic test provider is currently supported, and it is not required for the v0.9 zero-configuration promise | Maintainer decision on whether v0.9 supports prior optional AI Proposal contracts or moves them to a separately versioned package/surface. **Unresolved; no deletion.** |
| Experimental semantic artifact/evaluation (`semantic_artifact.py`, `semantic_evaluation.py`; CLI inspection/evaluation; index flags) | v0.7 release notes/readiness, semantic tests/fixtures, artifact audit, and ADR 0006 layered direction | Separate experimental storage and multiple debug/evaluation commands increase surface area and do not affect default preflight | Promotion, continued experiment, or retirement criteria have not been chosen. Historical ADR 0006 must remain either way. **Unresolved; no deletion.** |
| `repo_summary`, `graph_status`, `search_graph`, `search_text`, node traversal, `impact_analysis`, and `list_entrypoints` as separate MCP tools | Registered public read-only tools with MCP/query tests and examples; each exposes a bounded specialized query | Fifteen tools increase discovery cost and some facts also appear in preflight | Need MCP client usage/dogfood evidence and per-tool parity analysis before choosing fewer Progressive Disclosure tools. **Unresolved; retain all now.** |
| Historical plans, issue breakdowns, reviews, release trackers, and roadmap documents other than the explicit remove rows | They record scope, rejected alternatives, and release provenance; some are linked by current release docs | Many repeat superseded version language and can influence self-dogfood orientation | No repository convention distinguishes archival provenance from obsolete guidance, and absence of path references does not prove no maintainer use. **Unresolved; do not bulk delete or move.** |
| Legacy graph exports and human report artifacts | Implemented by graph/report/index code and covered by graph, budget, CLI, and audit tests; documented for troubleshooting and portability | SQLite is authoritative and bounded Context Packs are the agent workflow; duplicate exports consume artifact surface | Need artifact-by-artifact consumer, portability, size, migration, and release-smoke evidence. **Unresolved; no artifact shape change.** |

## Approved follow-up order

After explicit maintainer approval of this map, create independent vertical issues in this order:

1. Remove the three legacy `AGENTS-v0.*.md` files and verify no active guidance or references are lost.
2. Remove `docs/Client-request.md` only after the maintainer confirms Git history is sufficient for that superseded PRD.
3. Consolidate release-facing wording around install + MCP registration + Assistant Preflight; do not delete historical release evidence.
4. Specify and test `suggest_reading_order` parity/deprecation before changing its public MCP contract.
5. Audit MCP `get_graph_report` consumers before any deprecation.
6. Resolve AI Proposal, semantic prototype, broad MCP tool-set, historical-plan, and export questions through separate human decisions.

Do not combine these into one cleanup PR. Every implementation removal must include its command/MCP exposure, tests that exist only for removed behavior, user documentation, and replacement coverage where applicable.

## Human approval record

A maintainer approving this map should record:

- approval of the classification rules;
- approval or amendment of each `remove` and `consolidate` row;
- confirmation that unresolved rows remain untouched;
- confirmation that domain docs, ADRs, provenance, release history, and safety contracts remain protected.

Approval may be recorded in issue #221 or the pull request that adds this map. Merging this document records approval of the map only; it does not itself perform or authorize changes outside the listed follow-up slices.
