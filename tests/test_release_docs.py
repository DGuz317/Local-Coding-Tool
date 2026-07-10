from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_uses_supported_python_and_repolens_entrypoint() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM python:3.11-slim" in dockerfile
    assert 'ENTRYPOINT ["repolens"]' in dockerfile
    assert "WORKDIR /workspace" in dockerfile


def test_docker_context_excludes_local_artifacts() -> None:
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    for ignored_path in (".venv/", ".repolens/", ".git/", "__pycache__/"):
        assert ignored_path in dockerignore


def test_opencode_example_is_documentation_only_and_uses_local_image() -> None:
    active_config_names = ("opencode.json", "opencode.jsonc")

    for active_config_name in active_config_names:
        assert not (ROOT / active_config_name).exists()

    example = (ROOT / "docs" / "opencode-mcp.example.jsonc").read_text(encoding="utf-8")

    assert '"repolens:latest"' in example
    assert '"--network"' in example
    assert '"none"' in example
    assert '"--user"' in example
    assert '"mcp"' in example


def test_readme_covers_release_readiness_topics() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    required_phrases = (
        "pipx",
        "uv tool",
        "docker build -t repolens:latest .",
        '--user "$(id -u):$(id -g)"',
        "--network none",
        "OpenCode",
        "Artifact Privacy",
        "Assistant Prompt Guidance",
        "Roadmap",
        "Human Release Checkpoint",
    )
    for phrase in required_phrases:
        assert phrase in readme


def test_ci_runs_v0_3_1_graph_index_and_context_pack_gates() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "feature/repolens-v0.3.1" in workflow
    assert "Run graph-index budget regression tests" in workflow
    assert "tests/test_artifact_budget_contract.py" in workflow
    assert "tests/test_synthetic_large_repo_fixture.py" in workflow
    assert "Run Context Pack tests" in workflow
    assert "tests/test_context_pack_contract.py" in workflow
    assert "tests/test_context_pack_service.py" in workflow
    assert "tests/test_context_evaluation.py" in workflow
    assert "Run full test suite" in workflow
    assert "repolens evaluate-context" in workflow


def test_ci_runs_v0_4_release_branch_and_workspace_gates() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "feature/repolens-v0.4" in workflow
    assert "Run v0.4 package workspace tests" in workflow
    assert "tests/test_config_index.py" in workflow
    assert "tests/test_javascript_index.py" in workflow
    assert "tests/test_query_service.py" in workflow


def test_ci_indexes_fixture_before_artifact_safety_audit() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    index_command = "uv run repolens index tests/fixtures/context_pack/happy-path --json"
    audit_command = "uv run repolens audit-artifacts tests/fixtures/context_pack/happy-path --json"

    assert index_command in workflow
    assert audit_command in workflow
    assert workflow.index(index_command) < workflow.index(audit_command)


def test_release_notes_document_v0_3_1_graph_index_policy() -> None:
    release_notes = (ROOT / "docs" / "releases" / "v0.3.1.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    contract = (ROOT / "docs" / "artifact-budget-contract.md").read_text(encoding="utf-8")

    combined = "\n".join((release_notes, readme, contract))

    for required in (
        "graph-index.md",
        "bounded navigation",
        "SQLite remains the complete graph source of truth",
        "shown",
        "total",
        "reason",
        "repolens search-graph",
        "full or sharded Markdown export",
        "should not mirror full source",
    ):
        assert required in combined


def test_dogfood_reports_define_process_and_release_blocker() -> None:
    process = (ROOT / "docs" / "dogfood" / "README.md").read_text(encoding="utf-8")
    report = (ROOT / "docs" / "dogfood" / "2026-06-22-v0.2-dogfood.md").read_text(encoding="utf-8")
    readiness = (ROOT / "docs" / "release-readiness.md").read_text(encoding="utf-8")
    v0_4_report = (ROOT / "docs" / "dogfood" / "2026-06-30-v0.4-js-ts-workspace.md").read_text(
        encoding="utf-8"
    )

    for required in (
        "RepoLens on itself",
        "local Python repository",
        "local JS/TS repository",
        "mixed docs/config repository",
        "Do not commit `.repolens/`",
        "distilled fixture",
    ):
        assert required in process

    for required in (
        "False Positives",
        "False Negatives",
        "Known Limitations",
        "Actionable Regressions And Fixtures",
        "v0.2 release remains blocked on minimal CI passing",
    ):
        assert required in report

    assert "docs/dogfood/README.md" in readiness
    assert "v0.4 release remains blocked on full verification" in readiness

    for required in (
        "JS/TS Workspace Dogfooding Report",
        "Relationship Candidates",
        "Graph Quality Warnings",
        "Lockfile-only evidence does not create package ownership facts",
        "No third-party source snapshots or generated `.repolens/` artifacts are committed.",
    ):
        assert required in v0_4_report


def test_dogfood_distilled_fixtures_are_committed_sources_only() -> None:
    fixture_root = ROOT / "tests" / "fixtures" / "dogfood"

    expected_fixture_files = (
        fixture_root / "python-local-imports" / "src" / "dogpkg" / "service.py",
        fixture_root / "js-ts-workspace" / "packages" / "app" / "src" / "index.ts",
        fixture_root / "mixed-docs-config" / "AGENTS.md",
    )

    for fixture_file in expected_fixture_files:
        assert fixture_file.is_file()

    assert "@dog/lib" in (
        fixture_root / "js-ts-workspace" / "packages" / "app" / "src" / "index.ts"
    ).read_text(encoding="utf-8")
    assert "config/service.yaml" in (fixture_root / "mixed-docs-config" / "AGENTS.md").read_text(
        encoding="utf-8"
    )


def test_v0_4_release_tracker_locks_scope_and_gates() -> None:
    tracker = (ROOT / "docs" / "repolens-v0.4-release-tracker.md").read_text(encoding="utf-8")
    plan = (ROOT / "docs" / "repolens-v0.4-plan.md").read_text(encoding="utf-8")

    for required in (
        "Make RepoLens trustworthy across package/workspace repositories.",
        "#120 -> #121",
        "#121 -> #122",
        "#121 -> #123",
        "#121 -> #124",
        "#122, #123 -> #125",
        "#121, #125, #124 -> #126",
        "#122, #123, #125, #126, #124 -> #127",
        "#127 -> #128",
        "no-whole-source-disclosure coverage",
        "JS/TS workspace dogfooding evidence",
        "Context Pack evaluation",
        "hosted service",
        "telemetry",
        "embeddings or vector search",
        "runtime package registry lookups",
        "write-capable MCP tools",
        "persisted assistant sessions",
        "whole-source disclosure",
        "Maintainer approval is required before #121 is moved out of blocked state.",
    ):
        assert required in tracker

    assert "docs/repolens-v0.4-release-tracker.md" in plan


def test_package_workspace_evidence_contract_is_documented() -> None:
    contract = (ROOT / "docs" / "package-workspace-evidence-contract.md").read_text(
        encoding="utf-8"
    )

    for required in (
        "Package Identity",
        "Workspace Membership",
        "Package Ownership",
        "Package Dependency",
        "Local Resolution",
        "Relationship Candidate",
        "Graph Quality Warning",
        "Resolution Strategy",
        "Alias Resolution Scope",
        "unique explicit evidence -> graph edge or ownership fact",
        "multiple plausible matches -> relationship candidate + graph-quality warning",
        "no evidence -> unresolved",
        "must not surface source snippets",
    ):
        assert required in contract


def test_v0_4_release_readiness_docs_cover_required_topics() -> None:
    readiness = (ROOT / "docs" / "release-readiness.md").read_text(encoding="utf-8")
    limitations = (ROOT / "docs" / "known-limitations.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for required in (
        "package/workspace evidence",
        "Relationship Candidates",
        "Graph Quality Warnings",
        "docs/config orientation",
        "command risk bucket",
        "Maintainer release judgment",
        "uv run repolens evaluate-context --json",
        "uv build --out-dir /tmp/repolens-dist --clear",
    ):
        assert required in readiness

    for required in (
        "unsupported workspace declarations",
        "Complex package entrypoints",
        "Unresolved aliases",
        "Lockfile-only evidence does not create package ownership facts",
        "package/workspace overclaiming",
    ):
        assert required in limitations

    assert "RepoLens v0.6 focuses on improving JS/TS parser and resolver evidence" in readme


def test_v0_5_install_and_adoption_docs_cover_preflight_setup() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs" / "assistant-usage-guide.md").read_text(encoding="utf-8")
    readiness = (ROOT / "docs" / "release-readiness.md").read_text(encoding="utf-8")
    opencode_example = (ROOT / "docs" / "opencode-mcp.example.jsonc").read_text(encoding="utf-8")

    combined = "\n".join((readme, guide, readiness, opencode_example))

    for required in (
        "assistant_preflight before broad file reads",
        "uv run repolens preflight /absolute/path/to/repo",
        "OpenCode",
        "Claude Desktop",
        "Cursor-style MCP",
        "Docker smoke without registry publishing",
        "PyPI readiness smoke without publishing",
        "uv build --out-dir /tmp/repolens-dist --clear",
        "does not publish to PyPI",
        "candidate verification commands remain marked as found but not run",
    ):
        assert required in combined

    assert "assistant_preflight" in opencode_example


def test_v0_5_release_readiness_records_final_evidence() -> None:
    readiness = (ROOT / "docs" / "release-readiness.md").read_text(encoding="utf-8")
    limitations = (ROOT / "docs" / "known-limitations.md").read_text(encoding="utf-8")
    dogfood = (ROOT / "docs" / "dogfood" / "2026-07-02-v0.5-dogfood-evaluation-pack.md").read_text(
        encoding="utf-8"
    )

    for required in (
        "Latest local evidence for issue #149",
        "uv run repolens audit-artifacts . --json",
        "source snippet leakage",
        "absolute host paths",
        "raw secrets",
        "Local savings metrics",
        "Maintainer release judgment: approved for v0.5 release",
        "Publishing to PyPI or a Docker registry remains deferred",
    ):
        assert required in readiness

    for required in (
        "Assistant Preflight is a bounded orientation workflow",
        "Focus hints and budget controls",
        "Stale or missing graph handling is explicit",
        "No PyPI, Docker registry, or hosted publishing automation in v0.5",
    ):
        assert required in limitations

    for required in (
        "JS/TS workspace",
        "Python package",
        "Docs-heavy task",
        "Config-heavy task",
        "Ambiguous import",
        "Stale graph",
        "Package/workspace task",
    ):
        assert required in dogfood


def test_v0_6_dogfood_evaluation_pack_records_release_gate_coverage() -> None:
    readiness = (ROOT / "docs" / "release-readiness.md").read_text(encoding="utf-8")
    limitations = (ROOT / "docs" / "known-limitations.md").read_text(encoding="utf-8")
    dogfood = (ROOT / "docs" / "dogfood" / "2026-07-06-v0.6-dogfood-evaluation-pack.md").read_text(
        encoding="utf-8"
    )

    for required in (
        "Latest local evidence for issue #169",
        "JS/TS call chains",
        "re-export behavior",
        "workspace package imports",
        "route hints",
        "no-source-disclosure negatives",
        "fixture-derived estimates only",
        "bounded local fixture index timing",
    ):
        assert required in readiness

    for required in (
        "v0.6 dogfood evaluation pack",
        "Parser timing and file-count evidence are bounded local fixture evidence only",
        "not to justify parse caches, worker pools, indexing parallelism",
    ):
        assert required in limitations

    for required in (
        "JS/TS workspace aliases and package boundaries",
        "JS/TS source-free call chains",
        "JS/TS re-export behavior",
        "Next.js App Router route hint",
        "Alias ambiguity",
        "Stale graph behavior",
        "No-source-disclosure negative",
    ):
        assert required in dogfood


def test_v0_6_release_docs_record_final_readiness_contract() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs" / "assistant-usage-guide.md").read_text(encoding="utf-8")
    limitations = (ROOT / "docs" / "known-limitations.md").read_text(encoding="utf-8")
    readiness = (ROOT / "docs" / "release-readiness.md").read_text(encoding="utf-8")
    safety = (ROOT / "docs" / "security-and-artifact-privacy.md").read_text(encoding="utf-8")
    release_notes = (ROOT / "docs" / "releases" / "v0.6.0.md").read_text(encoding="utf-8")

    combined = "\n".join((readme, guide, limitations, readiness, safety, release_notes))

    for required in (
        "Tree-sitter JS/TS is the default parser backend",
        "legacy bounded scanner",
        "parser-backend warnings",
        "Call Chain Facts are structural metadata",
        "Framework Route Hints are deterministic hints",
        "not framework emulation",
        "unsupported aliases",
        "complex package entrypoints",
        "No PyPI, Docker registry, or hosted publishing automation in v0.6",
        "Artifact audit evidence",
        "Maintainer release judgment: approved for v0.6 release",
        "docs/releases/v0.6.0.md",
    ):
        assert required in combined


def test_v0_7_readme_and_assistant_guide_document_semantic_inspect_contract() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs" / "assistant-usage-guide.md").read_text(encoding="utf-8")

    for required in (
        "v0.7 Python semantic facts are experimental, source-free metadata stored "
        "separately from the stable graph.",
        "`repolens semantic-inspect` reads indexed semantic artifacts by default.",
        "When indexed semantic artifacts are missing, stale, or incompatible, "
        "`semantic-inspect` reports artifact status instead of silently parsing live source.",
        "`semantic-inspect --from-source` is an explicit, non-persistent debug mode.",
    ):
        assert required in readme

    for required in (
        "Treat semantic facts as experimental metadata, not stable graph facts.",
        "Use indexed `semantic-inspect` output before relying on Python semantic facts.",
        "If semantic artifacts are missing or stale, ask the user to run "
        "`repolens index` or `repolens update` instead of using live source implicitly.",
        "`--from-source` is for one-off debugging only and must not be treated as "
        "persisted RepoLens state.",
    ):
        assert required in guide


def test_v0_7_known_limitations_document_python_semantic_boundaries() -> None:
    limitations = (ROOT / "docs" / "known-limitations.md").read_text(encoding="utf-8")

    for required in (
        "v0.7 Python semantic analysis is limited to deterministic function-level CFG "
        "and lexical binding metadata.",
        "Unsupported or dynamic Python constructs produce warnings, unresolved statuses, "
        "or unsupported markers instead of guessed facts.",
        "Runtime dispatch, monkeypatching, metaclasses, decorators with dynamic effects, "
        "reflection, imports with runtime side effects, and framework behavior are not "
        "executed or inferred.",
        "Semantic artifacts must remain source-free and must not mirror code bodies, "
        "function signatures, raw comments, raw docstrings, raw string literals, secrets, "
        "or absolute host paths.",
    ):
        assert required in limitations


def test_v0_7_release_readiness_docs_pin_semantic_gates_and_opt_in_hints() -> None:
    readiness = (ROOT / "docs" / "release-readiness.md").read_text(encoding="utf-8")
    tracker = (ROOT / "docs" / "repolens-v0.7-release-tracker.md").read_text(encoding="utf-8")

    for required in (
        "v0.7 release readiness requires passing semantic evaluation evidence for "
        "Python CFG, lexical binding, warnings, and no-disclosure fixtures.",
        "v0.7 release readiness requires artifact audit evidence that semantic artifacts "
        "and assistant-facing output do not leak source snippets, code bodies, function "
        "signatures, raw comments, raw docstrings, raw string literals, raw secrets, raw "
        "Agent Guidance text, or absolute host paths.",
        "v0.7 release readiness requires evidence that semantic facts are excluded from "
        "Canonical Graph Hash, default Context Pack IDs, stable graph validation, default "
        "MCP output, default Assistant Preflight output, and default Context Pack output.",
        "Optional Context Pack semantic hints are included in v0.7 only behind explicit "
        "`include_experimental_semantic_hints` opt-in; they are documented, audited, release-gated",
        "uv run repolens semantic-inspect tests/fixtures/semantic_evaluation/branch_cfg.py --json",
        "uv run repolens semantic-inspect tests/fixtures/semantic_evaluation/branch_cfg.py "
        "--from-source --json",
        "uv run repolens evaluate-context --json",
        "uv run repolens audit-artifacts . --json",
    ):
        assert required in readiness

    for required in (
        "Semantic facts are experimental metadata outside the trusted stable graph contract.",
        "`semantic-inspect` reads indexed semantic artifacts by default and reports missing, "
        "stale, or incompatible artifacts explicitly",
        "`--from-source` is explicit, non-persistent, and isolated from stable graph "
        "artifacts and default assistant-facing identity",
        "artifact no-disclosure checks are documented with passing evidence",
        "Optional Context Pack semantic enrichment may defer to a later v0.7.x or v0.8 "
        "slice without blocking v0.7",
    ):
        assert required in tracker


def test_v0_8_release_docs_record_ai_proposal_gates_and_dogfood_limits() -> None:
    readiness = (ROOT / "docs" / "release-readiness.md").read_text(encoding="utf-8")
    limitations = (ROOT / "docs" / "known-limitations.md").read_text(encoding="utf-8")
    release_notes = (ROOT / "docs" / "releases" / "v0.8.0.md").read_text(encoding="utf-8")
    dogfood = (ROOT / "docs" / "dogfood" / "2026-07-10-v0.8-ai-proposal-layer.md").read_text(
        encoding="utf-8"
    )

    for required in (
        "AI is disabled by default",
        "does not change Canonical Graph Hash, Context Pack IDs or ranking",
        "schema `0.8.ai_proposal.v1`",
        "--include-ai-proposals",
        "external-provider dogfood could not run",
        "does not claim external-model quality",
    ):
        assert required in readiness

    for required in (
        "v0.8 supports only the local deterministic `test` provider",
        "Patch Plan Proposals may omit relevant files, tests, docs/config risks",
        "Active Workflow remains deferred beyond v0.8",
    ):
        assert required in limitations

    for required in (
        "disabled by default",
        "External-provider dogfood could not be run",
        "does not establish external-model quality",
        "does not apply patches, write project files, execute commands, mutate branches",
    ):
        assert required in release_notes

    for required in (
        "Context Pack Summary Proposal",
        "Architecture Explanation Proposal",
        "Patch Plan Proposal",
        "No output observed in this run claimed new graph facts",
        "External-provider dogfood could not be run",
    ):
        assert required in dogfood
