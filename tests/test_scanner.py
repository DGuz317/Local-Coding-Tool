from __future__ import annotations

import pytest

from repolens.scanner import ScanError, scan_repository


def test_scanner_applies_safe_policy_with_repo_relative_paths(tmp_path):
    root = tmp_path
    _write_text(root / ".gitignore", "ignored.txt\nignored-dir/\n*.local\n")
    _write_text(root / "src" / "app.py", "print('ok')\n")
    _write_text(root / "docs" / "guide.md", "# Guide\n")
    _write_text(root / ".github" / "workflows" / "ci.yml", "name: ci\n")
    _write_text(root / "ignored.txt", "ignored\n")
    _write_text(root / "ignored-dir" / "file.py", "print('ignored')\n")
    _write_text(root / "settings.local", "ignored\n")
    _write_text(root / "node_modules" / "pkg" / "index.js", "module.exports = {}\n")
    _write_text(root / "vendor" / "pkg" / "client.py", "vendored\n")
    _write_text(root / ".git" / "config", "vcs metadata\n")
    _write_text(root / ".venv" / "lib" / "installed.py", "environment\n")
    _write_text(root / "dist" / "app.js", "generated\n")
    _write_text(root / ".mypy_cache" / "cache.json", "{}\n")
    _write_text(root / "generated" / "client.py", "generated\n")
    _write_text(root / "graphify-out" / "graph.json", "{}\n")
    _write_text(root / ".repolens" / "scan.json", "{}\n")
    _write_text(root / ".env", "TOKEN=secret\n")
    _write_text(root / "secrets" / "config.yml", "password: secret\n")
    _write_text(root / "static" / "app.min.js", "minified\n")
    _write_text(root / "src" / "api.generated.ts", "generated\n")
    _write_text(root / "legacy" / "Session.java", "class Session {}\n")
    _write_bytes(root / "assets" / "logo.png", b"\x89PNG\r\n\x1a\n")
    _write_bytes(root / "binary.dat", b"abc\0def")
    _write_text(root / "large.txt", "x" * 65)

    _create_symlink(root / "src" / "app.py", root / "internal-link.py")
    _create_symlink(tmp_path.parent, root / "external-link")

    result = scan_repository(root, max_file_size_bytes=64)

    file_paths = {file.path for file in result.files}
    assert file_paths == {
        ".github/workflows/ci.yml",
        ".gitignore",
        "docs/guide.md",
        "src/app.py",
    }

    skip_reasons = {skipped.path: skipped.reason for skipped in result.skipped}
    assert skip_reasons[".env"] == "secret_path"
    assert skip_reasons[".git"] == "excluded_directory"
    assert skip_reasons[".mypy_cache"] == "excluded_directory"
    assert skip_reasons[".repolens"] == "repolens_artifact_dir"
    assert skip_reasons[".venv"] == "excluded_directory"
    assert skip_reasons["assets/logo.png"] == "binary_media_archive"
    assert skip_reasons["binary.dat"] == "binary_content"
    assert skip_reasons["dist"] == "excluded_directory"
    assert skip_reasons["external-link"] == "symlink_escapes_root"
    assert skip_reasons["generated"] == "excluded_directory"
    assert skip_reasons["graphify-out"] == "excluded_directory"
    assert skip_reasons["ignored-dir"] == "gitignore"
    assert skip_reasons["ignored.txt"] == "gitignore"
    assert skip_reasons["internal-link.py"] == "symlink"
    assert skip_reasons["large.txt"] == "oversized_file"
    assert skip_reasons["legacy/Session.java"] == "unsupported_source"
    assert skip_reasons["node_modules"] == "excluded_directory"
    assert skip_reasons["secrets"] == "secret_path"
    assert skip_reasons["settings.local"] == "gitignore"
    assert skip_reasons["src/api.generated.ts"] == "generated_file"
    assert skip_reasons["static/app.min.js"] == "generated_file"
    assert skip_reasons["vendor"] == "excluded_directory"

    all_recorded_paths = file_paths | set(skip_reasons)
    assert all(not path.startswith(str(root)) for path in all_recorded_paths)
    assert all("\\" not in path for path in all_recorded_paths)
    assert all(".." not in path.split("/") for path in all_recorded_paths)


def test_scanner_honors_nested_gitignore(tmp_path):
    _write_text(tmp_path / "pkg" / ".gitignore", "ignored.py\n")
    _write_text(tmp_path / "pkg" / "kept.py", "print('kept')\n")
    _write_text(tmp_path / "pkg" / "ignored.py", "print('ignored')\n")

    result = scan_repository(tmp_path)

    assert {file.path for file in result.files} == {"pkg/.gitignore", "pkg/kept.py"}
    assert {skipped.path: skipped.reason for skipped in result.skipped} == {
        "pkg/ignored.py": "gitignore"
    }


def test_scanner_rejects_repolens_as_analysis_root(tmp_path):
    artifact_root = tmp_path / ".repolens"
    artifact_root.mkdir()

    with pytest.raises(ScanError, match="analysis_root_is_repolens_artifact_dir"):
        scan_repository(artifact_root)


def test_scanner_skips_secret_paths_before_parsing_but_keeps_non_secret_names(tmp_path):
    _write_text(tmp_path / ".env.production", "TOKEN=secret\n")
    _write_text(tmp_path / ".aws" / "credentials", "secret\n")
    _write_text(tmp_path / "config" / "private-key.yaml", "value: secret\n")
    _write_text(tmp_path / "secrets" / "settings.toml", "token = 'secret'\n")
    _write_text(tmp_path / "src" / "secret_sauce.py", "class TokenBucket: pass\n")
    _write_text(tmp_path / "docs" / "token-rotation.md", "# useful non-secret docs\n")

    result = scan_repository(tmp_path)

    assert {file.path for file in result.files} == {
        "docs/token-rotation.md",
        "src/secret_sauce.py",
    }
    skipped = {path.path: path.reason for path in result.skipped}
    assert skipped == {
        ".aws/credentials": "secret_path",
        ".env.production": "secret_path",
        "config/private-key.yaml": "secret_path",
        "secrets": "secret_path",
    }


def test_scanner_records_containment_for_paths_that_escape_analysis_root(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    _write_text(tmp_path / "app.py", "print('ok')\n")
    _write_text(outside, "outside\n")
    _create_symlink(outside, tmp_path / "outside-link.txt")

    result = scan_repository(tmp_path)

    assert {file.path for file in result.files} == {"app.py"}
    assert {path.path: path.reason for path in result.skipped} == {
        "outside-link.txt": "symlink_escapes_root"
    }


def _write_text(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_bytes(path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _create_symlink(target, link) -> None:
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlinks are not supported: {exc}")
