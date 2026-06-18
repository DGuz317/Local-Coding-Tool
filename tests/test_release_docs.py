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
