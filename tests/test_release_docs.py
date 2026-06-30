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

    assert (
        "RepoLens v0.4 focuses on making Context Packs trustworthy across package/workspace repositories."
        in readme
    )
