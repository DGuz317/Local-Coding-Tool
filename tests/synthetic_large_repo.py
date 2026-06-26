from __future__ import annotations

from pathlib import Path


def generate_synthetic_large_repo(
    root: Path,
    *,
    python_module_count: int = 115,
    javascript_module_count: int = 115,
) -> Path:
    """Generate a deterministic mixed-language repository for graph budget tests."""
    if python_module_count < 1 or javascript_module_count < 1:
        raise ValueError("module counts must be positive")

    root.mkdir(parents=True, exist_ok=True)
    _write(
        root / "pyproject.toml",
        "\n".join(
            [
                "[project]",
                'name = "synthetic-large-repo"',
                'version = "0.0.0"',
                "",
                "[project.scripts]",
                'large-fixture = "largepkg.module_0000:func_0000"',
                "",
            ]
        ),
    )
    _write(
        root / "package.json",
        "\n".join(
            [
                "{",
                '  "name": "synthetic-large-repo",',
                '  "version": "0.0.0",',
                '  "scripts": {',
                '    "test": "vitest run",',
                '    "typecheck": "tsc --noEmit"',
                "  },",
                '  "dependencies": {',
                '    "@example/runtime": "1.0.0"',
                "  }",
                "}",
                "",
            ]
        ),
    )
    _write(
        root / "README.md",
        "\n".join(
            [
                "# Synthetic Large Repo",
                "",
                "This fixture is generated during tests to exercise RepoLens budgets.",
                "",
                "See `src/largepkg/module_0000.py` and `packages/app/src/module_0000.ts`.",
                "",
            ]
        ),
    )
    _write(root / "src" / "largepkg" / "__init__.py", "")

    for index in range(python_module_count):
        previous_import = (
            "from largepkg.module_0000 import func_0000\n" if index else "import json\n"
        )
        _write(
            root / "src" / "largepkg" / f"module_{index:04d}.py",
            "\n".join(
                [
                    previous_import.rstrip(),
                    "",
                    f"class Service{index:04d}:",
                    "    def value(self) -> int:",
                    f"        return {index}",
                    "",
                    f"def func_{index:04d}() -> int:",
                    f"    return {index}",
                    "",
                ]
            ),
        )
        _write(
            root / "tests" / "python" / f"test_module_{index:04d}.py",
            "\n".join(
                [
                    f"from largepkg.module_{index:04d} import func_{index:04d}",
                    "",
                    f"def test_func_{index:04d}():",
                    f"    assert func_{index:04d}() == {index}",
                    "",
                ]
            ),
        )

    for index in range(javascript_module_count):
        import_line = (
            "import { value0000 } from './module_0000';"
            if index
            else "import runtime from '@example/runtime';"
        )
        _write(
            root / "packages" / "app" / "src" / f"module_{index:04d}.ts",
            "\n".join(
                [
                    import_line,
                    "",
                    f"export class Widget{index:04d} {{",
                    f"  value(): number {{ return {index}; }}",
                    "}",
                    "",
                    f"export function value{index:04d}(): number {{",
                    f"  return {index};",
                    "}",
                    "",
                ]
            ),
        )
        _write(
            root / "packages" / "app" / "tests" / f"module_{index:04d}.test.ts",
            "\n".join(
                [
                    f"import {{ value{index:04d} }} from '../src/module_{index:04d}';",
                    "",
                    f"test('value{index:04d}', () => {{",
                    f"  expect(value{index:04d}()).toBe({index});",
                    "});",
                    "",
                ]
            ),
        )

    return root


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
