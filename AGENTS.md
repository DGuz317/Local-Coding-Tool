# AGENTS.md

## Skills
- Shared Agent Skills live in `.agents/skills`; do not copy their full content here.
- OpenCode: load the relevant skill. Codex or other agents: read `.agents/skills/<skill>/SKILL.md` and referenced files.
- Use `tdd` for red-green-refactor, `diagnose` for bugs/failing tests/perf regressions, `zoom-out` for unfamiliar code, `improve-codebase-architecture` for deeper refactors, `prototype` for throwaway UI/state exploration, and `to-prd`/`to-issues`/`triage` for product or issue workflows.

## Repo Shape
- This is currently a single-file Python project: `main.py` is the runtime entrypoint.
- Runtime is Python 3.13: `pyproject.toml` has `requires-python = ">=3.13"` and `.python-version` is `3.13`.
- There are no declared dependencies, lockfile, tests, CI workflows, lint/typecheck config, or non-empty README yet.

## Commands
- Select Python 3.13 before running project commands; do not assume bare `python` is new enough.
- Install/setup: none required while `dependencies = []` and no lockfile exists.
- Run app: `python main.py`.
- Focused syntax check: `python -m py_compile main.py`.
- Build/lint/typecheck/test: not configured. Do not claim `pytest`, `ruff`, `mypy`, or packaging build checks unless their config is added first.

## Workflow Gotchas
- Prefer the smallest relevant verification; for the current repo that is usually the run or syntax check above.
- If `CONTEXT.md` or `docs/adr/` are added later, read them before architecture-level changes.
