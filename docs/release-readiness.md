# RepoLens MCP v0.1 Release Readiness

This checklist is for manual dogfooding and release prep. It does not publish to PyPI or a Docker registry.

## Human Checkpoint

Before treating release-facing docs as final, a human maintainer must confirm:

- Project and distribution name: `repolens` / RepoLens MCP.
- License wording and whether a license file should be added before release.
- PyPI publishing remains deferred for v0.1.
- Docker registry publishing remains deferred for v0.1.
- Final README positioning and whether the README should target users, contributors, or both.

## Local Verification Gate

Run from the repository root:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
```

## Isolated Native Install Smoke

Build and install the package in an isolated environment:

```bash
uv build
uv tool install --force dist/repolens-0.1.0-py3-none-any.whl
repolens --help
repolens status .
uv tool uninstall repolens
```

Alternative `pipx` smoke if `pipx` is available:

```bash
uv build
pipx install --force dist/repolens-0.1.0-py3-none-any.whl
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

Use an MCP client to list tools and call at least `graph_status` and `repo_summary`.

## OpenCode Dogfood

- Copy the shape from `docs/opencode-mcp.example.jsonc` into a local OpenCode config outside this repository.
- Replace `1000:1000` with your host user and group IDs from `id -u` and `id -g`.
- Replace `/absolute/path/to/repo` with the absolute path to the repository being indexed.
- Confirm OpenCode can list the RepoLens tools.
- Ask the assistant to call `graph_status` before relying on graph context.

## Dogfooding Reports

- Follow `docs/dogfood/README.md` for v0.2 dogfooding reports and fixture policy.
- Commit dated reports under `docs/dogfood/`.
- Commit only distilled regression fixtures under `tests/fixtures/dogfood/`; do not commit `.repolens/` artifacts or vendored third-party repository snapshots.
- v0.2 release remains blocked on minimal CI passing before release, even when dogfooding reports are complete.

## Scope Guard

Do not add these as part of v0.1 release prep unless a maintainer opens a separate issue:

- PyPI publishing.
- Docker registry publishing.
- Dependabot or dependency update automation.
- Contributor pre-commit hook setup.
- Runtime network calls during indexing or MCP serving.
