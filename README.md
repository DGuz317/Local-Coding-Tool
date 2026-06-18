# RepoLens MCP

RepoLens MCP is a local-first repository intelligence backend for AI coding assistants. It indexes a repository into deterministic `.repolens/` graph artifacts and exposes read-only stdio MCP tools so assistants can understand repo structure before opening source files.

RepoLens v0.1 is local, deterministic, and offline-capable during normal indexing and MCP serving. It does not require AI models, embeddings, telemetry, hosted services, a browser UI, or runtime network calls.

## Quickstart

Install from a local checkout while v0.1 publishing is deferred:

```bash
uv tool install .
repolens --help
repolens index /path/to/repo
repolens status /path/to/repo
repolens report /path/to/repo
```

For an editable contributor environment:

```bash
uv sync
uv run repolens --help
uv run repolens index .
uv run repolens status .
```

The implemented CLI commands are:

- `repolens index <repo-path>`: full deterministic rebuild of known `.repolens` artifacts.
- `repolens update <repo-path>`: update artifacts using live change classification, or initialize if missing.
- `repolens status <repo-path>`: read-like freshness/status check that does not create `.repolens`.
- `repolens report <repo-path>`: print the generated Markdown graph report.
- `repolens search <repo-path> <query>`: search scanner-approved live text with capped previews.
- `repolens mcp <repo-path>`: start the read-only stdio MCP server.

## Native Install

When installing from a local checkout, prefer `uv tool`:

```bash
uv tool install /path/to/repolens
repolens --help
```

If `pipx` is your preferred tool runner:

```bash
pipx install /path/to/repolens
repolens --help
```

For package-build smoke testing before release:

```bash
uv build
uv tool install --force dist/repolens-0.1.0-py3-none-any.whl
repolens --help
```

PyPI publishing is deferred for v0.1, so install commands intentionally point at a local checkout or built wheel.

## Docker Usage

Build the local image with the required v0.1 tag:

```bash
docker build -t repolens:latest .
```

Index the current repository without runtime network access:

```bash
docker run --rm \
  --network none \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" \
  repolens:latest \
  index /workspace
```

The `--user "$(id -u):$(id -g)"` mapping avoids root-owned `.repolens` artifacts on the host. Keep it in Docker examples unless you intentionally want container-owned output.

Run a status check:

```bash
docker run --rm \
  --network none \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" \
  repolens:latest \
  status /workspace
```

Start the MCP server through Docker:

```bash
docker run --rm -i \
  --network none \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" \
  repolens:latest \
  mcp /workspace
```

The Docker image entrypoint is `repolens`, so arguments after `repolens:latest` are CLI subcommands. Runtime network access is not required for normal indexing, status checks, reports, search, or MCP serving.

## MCP Usage

Build artifacts first:

```bash
repolens index /path/to/repo
```

Then start the stdio MCP server:

```bash
repolens mcp /path/to/repo
```

The v0.1 MCP server is read-only. It does not update graphs, modify files, execute shell commands, or expose a full-source file read tool. Available tools are `repo_summary`, `graph_status`, `get_graph_report`, `search_graph`, `search_text`, `get_node`, `get_neighbors`, `shortest_path`, `impact_analysis`, `suggest_reading_order`, and `list_entrypoints`.

**Note**: `repolens mcp <repo-path>` is intended to be launched by an MCP client. It is not an interactive command. Running it manually should block silently while waiting for JSON-RPC messages on stdin.

### OpenCode Example

An OpenCode MCP example is provided at `docs/opencode-mcp.example.jsonc`. It is intentionally documentation only and is not active repo configuration.

For local contributor development from this repository, create `opencode.json` in the repository root:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "repolens": {
      "type": "local",
      "command": [
        "uv",
        "run",
        "repolens",
        "mcp",
        "/absolute/path/to/repo"
      ],
      "cwd": "/absolute/path/to/repo",
      "enabled": true,
      "timeout": 10000
    }
  }
}
```

Replace `/absolute/path/to/repo` with the absolute path to the repository being indexed.

If RepoLens is already installed as a tool, the native installed CLI form is:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "repolens": {
      "type": "local",
      "command": [
        "repolens",
        "mcp",
        "/absolute/path/to/repo"
      ],
      "cwd": "/absolute/path/to/repo",
      "enabled": true,
      "timeout": 10000
    }
  }
}
```

Docker-based example shape:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "repolens": {
      "type": "local",
      "command": [
        "docker",
        "run",
        "--rm",
        "-i",
        "--network",
        "none",
        "--user",
        "1000:1000",
        "-v",
        "/absolute/path/to/repo:/workspace",
        "repolens:latest",
        "mcp",
        "/workspace"
      ],
      "enabled": true,
      "timeout": 10000
    }
  }
}
```

Replace `1000:1000` with your host user and group IDs from `id -u` and `id -g`.

The `repolens mcp` command is a stdio MCP server, not an interactive CLI. It should be started by OpenCode or another MCP client. If you run it manually in a terminal, it should wait silently for JSON-RPC input; do not type into it.

## Security Behavior

RepoLens v0.1 is designed to be safe by default:

- The provided path is the analysis root; RepoLens does not silently expand to a broader Git root.
- Scanner and MCP behavior stay inside the provided analysis root.
- `.repolens/`, dependency folders, virtual environments, build outputs, caches, and common generated paths are skipped.
- `.gitignore` is honored for file discovery.
- Secret-looking files are skipped by path or name before parsing.
- Secret-like command and metadata values are sanitized before being written to artifacts.
- Oversized, binary, media, archive, and unsafe symlink targets are skipped.
- Candidate verification commands may be detected, but RepoLens does not execute them.
- Deploy or publish-like commands are not recommended for automatic execution.
- MCP tools are read-only and return bounded responses with freshness, warning, limit, and truncation metadata.

Content secret scanning is out of scope for v0.1. Do not intentionally place secrets in source files and assume generated artifacts are private repo metadata.

## Artifact Privacy

RepoLens writes generated artifacts under `.repolens/` in the analyzed repository. These artifacts can include repository structure, file paths, symbols, dependencies, commands, Markdown headings, tagged comments, graph relationships, and capped report/index exports.

Treat `.repolens/` as local cache output, not source. Do not commit, publish, upload, or share it unless you have reviewed the contents and are comfortable exposing repository metadata. The artifact directory includes its own ignore behavior when generated, and this repository also excludes `.repolens/` from Docker build context.

## Configuration Samples

RepoLens v0.1 does not require a project config file. The effective scan policy is the built-in local-first policy: path containment, `.gitignore`, default excludes, size caps, binary detection, generated-file hints, and secret path patterns.

Minimal command configuration is just the target path:

```bash
repolens index /path/to/repo
repolens mcp /path/to/repo
```

Assistant configuration is handled by your MCP client. Use `docs/opencode-mcp.example.jsonc` as the OpenCode sample, and keep client-specific config files outside this repository unless you intentionally want to commit them.

## Assistant Prompt Guidance

When connecting an assistant to RepoLens, ask it to use RepoLens before broad file exploration:

```text
Use RepoLens MCP for this repository. Start with graph_status. If the graph is fresh, use repo_summary and suggest_reading_order before opening files. Treat RepoLens output as static, evidence-backed context, not a substitute for reading files before editing. If graph_status reports stale or missing artifacts, ask before relying on graph facts.
```

For impact-oriented work:

```text
Before editing, call impact_analysis for the file, symbol, or package you plan to change. Use the returned related files, tests, docs, risks, and candidate verification commands as planning context. Do not execute deploy or publish commands automatically.
```

## Release Readiness

Manual dogfooding and release-prep smoke guidance lives in `docs/release-readiness.md`. The short gate is:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
```

Release prep also includes isolated native install, package build, Docker index, Docker MCP, and OpenCode dogfood checks where practical.

## Human Release Checkpoint

Before treating final release-facing docs as complete, a human maintainer must confirm:

- Project and distribution name.
- License wording and whether to add a license file.
- PyPI publishing remains deferred for v0.1.
- Docker registry publishing remains deferred for v0.1.
- Final README positioning.

Current docs use `repolens` / RepoLens MCP, mark publishing as deferred, and avoid final legal/license claims.

## Roadmap

v0.1 promises:

- Local CLI indexing, update, status, report, raw text search, and read-only stdio MCP serving.
- Deterministic `.repolens/` graph store and exports.
- Python, JavaScript, TypeScript, config, command, package, Markdown, comments, docs, and agent guidance indexing within the implemented v0.1 scope.
- Incremental staleness classification, structured graph queries, impact analysis, and reading-order queries.
- Docker support, native install guidance, assistant configuration examples, and release-readiness docs.

Deferred features:

- PyPI publishing and Docker registry publishing.
- HTTP API or HTTP MCP serving.
- Watch mode, Git hooks, or automatic background indexing.
- Browser UI, graph visualization, or hosted service.
- AI/LLM-required graph generation, embeddings, or semantic enrichment.
- Write-capable MCP tools.
- Runtime package registry lookups during indexing.
- Deep semantic call graphs, full TypeScript compiler resolution, Tree-sitter parsing, and Node-based parsers.
- Dependabot/dependency update automation and contributor pre-commit hook setup.

