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


def test_dogfood_reports_define_process_and_release_blocker() -> None:
    process = (ROOT / "docs" / "dogfood" / "README.md").read_text(encoding="utf-8")
    report = (ROOT / "docs" / "dogfood" / "2026-06-22-v0.2-dogfood.md").read_text(encoding="utf-8")
    readiness = (ROOT / "docs" / "release-readiness.md").read_text(encoding="utf-8")

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
    assert "v0.2 release remains blocked on minimal CI passing" in readiness


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
