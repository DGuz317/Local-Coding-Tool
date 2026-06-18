from __future__ import annotations

from textwrap import dedent

from repolens.documentation_index import extract_documentation_index
from repolens.scanner import scan_repository


def test_documentation_index_extracts_markdown_facts_without_code_bodies(tmp_path):
    _write_text(tmp_path / "src" / "app.py", "def app():\n    return 1\n")
    _write_text(tmp_path / "docs" / "guide.md", "# Guide\n")
    _write_text(
        tmp_path / "README.md",
        dedent(
            """
            # RepoLens

            RepoLens maps local repositories. Extra README prose is not needed here.

            ## Setup
            See [the guide](docs/guide.md) and `src/app.py` before editing.

            ```python title="demo"
            SECRET_CODE_FENCE_BODY = "must not be stored"
            ```

            ## Setup
            """
        ).lstrip(),
    )

    scan = scan_repository(tmp_path)
    documentation_index = extract_documentation_index(tmp_path, scan.files)

    markdown_files = {fact.path: fact for fact in documentation_index.markdown_files}
    assert markdown_files["README.md"].doc_kind == "readme"
    assert markdown_files["README.md"].importance == "important"
    assert markdown_files["README.md"].title == "RepoLens"
    assert markdown_files["README.md"].intro == "RepoLens maps local repositories."

    headings = {
        (heading.path, heading.heading_id): heading for heading in documentation_index.headings
    }
    assert headings[("README.md", "repolens")].level == 1
    assert headings[("README.md", "setup")].line == 5
    assert headings[("README.md", "setup-1")].line == 12

    links = {(link.path, link.target_path, link.label) for link in documentation_index.links}
    assert ("README.md", "docs/guide.md", "the guide") in links

    path_mentions = {
        (mention.path, mention.mentioned_path, mention.target_path)
        for mention in documentation_index.path_mentions
    }
    assert ("README.md", "src/app.py", "src/app.py") in path_mentions

    code_fences = {
        (fence.path, fence.language, fence.info_string) for fence in documentation_index.code_fences
    }
    assert ("README.md", "python", 'python title="demo"') in code_fences
    assert all(
        "SECRET_CODE_FENCE_BODY" not in fence.info_string
        for fence in documentation_index.code_fences
    )


def test_documentation_index_extracts_tagged_comments_agent_guidance_and_skills(tmp_path):
    _write_text(
        tmp_path / "src" / "app.ts",
        dedent(
            """
            // ordinary comment is not a fact
            // TODO: handle browser fallback
            export const app = () => true;
            /*
             * RISK: block comment risk survives extraction
             */
            """
        ).lstrip(),
    )
    _write_text(tmp_path / "AGENTS.md", "# AGENTS.md\n\nRepo-specific instructions.\n")
    _write_text(
        tmp_path / ".agents" / "skills" / "review" / "SKILL.md",
        dedent(
            """
            ---
            name: review
            description: Review repository changes for regressions.
            ---

            # Review
            """
        ).lstrip(),
    )

    scan = scan_repository(tmp_path)
    documentation_index = extract_documentation_index(tmp_path, scan.files)

    comments = {
        (comment.tag, comment.text, comment.language)
        for comment in documentation_index.tagged_comments
    }
    assert ("TODO", "handle browser fallback", "javascript") in comments
    assert ("RISK", "block comment risk survives extraction", "javascript") in comments
    assert all(
        "ordinary comment" not in comment.text for comment in documentation_index.tagged_comments
    )

    markdown_files = {fact.path: fact for fact in documentation_index.markdown_files}
    assert markdown_files["AGENTS.md"].doc_kind == "agent_instructions"
    assert markdown_files["AGENTS.md"].importance == "important"
    assert markdown_files[".agents/skills/review/SKILL.md"].doc_kind == "skill_manifest"

    skills = {(skill.name, skill.description, skill.path) for skill in documentation_index.skills}
    assert (
        "review",
        "Review repository changes for regressions.",
        ".agents/skills/review/SKILL.md",
    ) in skills


def _write_text(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
