# RepoLens MCP v0.3.1 Issue Plan

Release theme:

```text
Make RepoLens outputs usable on real repositories.
```

## Why v0.3.1 Exists

v0.3 delivered Context Packs and assistant-facing context compression. During dogfooding, `graph-index.md` became large enough that it could not be opened or loaded comfortably.

This is a product bug, not only a documentation/export bug.

RepoLens should reduce assistant orientation cost. If an assistant-facing artifact becomes too large to inspect, it works against the product goal. v0.3.1 should patch artifact usability before new graph-intelligence work continues.

## Release Goal

v0.3.1 should make generated assistant-facing artifacts bounded, deterministic, and usable on large repositories while preserving the full graph in SQLite.

Success means:

- `graph-index.md` is small enough to open quickly.
- `graph-index.md` acts as a navigation landing page, not a database dump.
- Large sections are capped with clear truncation metadata.
- Full graph detail remains queryable from `.repolens/graph.sqlite`.
- Existing v0.3 Context Pack behavior remains unchanged.
- No source disclosure boundary is weakened.

## Scope

### In Scope

- Size budgets for `graph-index.md`.
- Section-level caps and truncation metadata.
- Deterministic top-N selection for large index sections.
- Optional full index export behind an explicit flag or separate command.
- Optional sharded index exports if simple.
- CLI/query guidance for retrieving full details from SQLite-backed graph tools.
- Regression tests using synthetic large repositories.
- CI checks proving default artifacts stay bounded.

### Out of Scope

- Tree-sitter rewrite.
- Deep semantic call graph.
- CFG or data-flow analysis.
- Taint analysis.
- Embeddings.
- LLM-generated summaries.
- Browser UI.
- Hosted sync.
- Write-capable MCP tools.
- Runtime framework emulation.
- Changing Context Pack semantics except where artifact metadata helps them.

## Proposed Branch

```bash
feature/repolens-v0.3.1
```

## Suggested Labels

- `v0.3.1`
- `P0`
- `P1`
- `area:exports`
- `area:cli`
- `area:testing`
- `area:docs`
- `area:performance`
- `area:security`

---

# P0 Issues

## Issue 1 — Define AI-Facing Artifact Budget Contract

Suggested title:

```text
Define artifact budget contract for graph-index usability
```

Suggested labels:

```text
v0.3.1, P0, area:exports, area:docs
```

### Problem

`graph-index.md` can grow too large to open or load on real repositories. There is no explicit artifact size budget or section-level cap contract.

### What to build

Add a documented budget contract for AI-facing generated artifacts, especially `graph-index.md`.

The contract should define:

- default maximum rows per section;
- default maximum approximate bytes or characters for `graph-index.md`;
- section-level truncation metadata;
- deterministic item ordering;
- full-graph availability through SQLite;
- default-vs-full export behavior.

### Suggested default budget

```yaml
graph_index:
  max_total_bytes: 200000
  max_files: 100
  max_python_symbols: 100
  max_javascript_symbols: 100
  max_imports: 100
  max_packages: 100
  max_commands: 50
  max_entrypoints: 50
  max_docs: 50
  max_tests: 50
  max_risk_or_comment_signals: 50
```

Exact numbers may be adjusted after implementation, but they must be explicit and tested.

### Acceptance criteria

- [ ] Artifact budget constants are centralized.
- [ ] `graph-index.md` has an explicit default size/row budget.
- [ ] Each large section has a deterministic per-section cap.
- [ ] Truncated sections report `shown`, `total`, and `reason`.
- [ ] The contract states that SQLite remains the full source of truth.
- [ ] The contract states that default Markdown artifacts are navigation views, not full graph dumps.
- [ ] Budget behavior is documented in release notes or docs.

### Test cases

Create or update tests to verify:

```python
def test_graph_index_budget_contract_has_default_caps():
    ...

def test_graph_index_budget_contract_documents_sqlite_as_full_source_of_truth():
    ...
```

Assertions:

- budget constants exist;
- values are positive;
- per-section caps are lower than unbounded fixture totals;
- docs mention truncation and SQLite full graph source.

---

## Issue 2 — Convert `graph-index.md` Into A Bounded Landing Page

Suggested title:

```text
Bound graph-index.md and convert it into a compact landing page
```

Suggested labels:

```text
v0.3.1, P0, area:exports, area:performance
```

### Problem

`graph-index.md` currently behaves like a large dump. On large repositories, it can become too large to open.

### What to build

Change default `graph-index.md` export behavior so it presents capped, deterministic summaries and navigation guidance.

It should include:

- repository and graph freshness summary;
- total counts per major fact type;
- capped top-N tables;
- truncation notices per section;
- query guidance for retrieving more results;
- no source snippets;
- no raw full graph dump.

### Example section format

````markdown
## JavaScript Symbols

Showing 100 of 4,218 JavaScript symbols.

Use:

```bash
repolens search-graph . --kind symbol --query <name> --limit 50
```

| Kind | Name | Path | Line |
|---|---|---|---|
| function | loginFlow | src/auth/login.ts | 12 |
````

### Acceptance criteria

- [ ] Default `graph-index.md` never emits unbounded sections.
- [ ] Every capped section shows total count and shown count.
- [ ] Every capped section includes a query hint or next step.
- [ ] Item ordering is deterministic.
- [ ] The generated file remains deterministic across repeated runs except allowed volatile timestamp fields.
- [ ] The generated file does not include source snippets, code bodies, raw comments, or raw Agent Guidance text.
- [ ] Existing graph exports and SQLite data remain complete.

### Test cases

Add tests similar to:

```python
def test_graph_index_is_bounded_for_large_repository(tmp_path):
    _write_large_fixture_repo(tmp_path, file_count=300, symbol_count=3000)
    result = runner.invoke(app, ["index", str(tmp_path)])
    assert result.exit_code == 0

    graph_index = tmp_path / ".repolens" / "graph-index.md"
    text = graph_index.read_text(encoding="utf-8")

    assert graph_index.stat().st_size <= MAX_GRAPH_INDEX_BYTES
    assert "Showing " in text
    assert "Use:" in text
    assert "repolens search-graph" in text
```

```python
def test_graph_index_reports_section_truncation_counts(tmp_path):
    _write_large_javascript_fixture(tmp_path, module_count=120, symbol_count=1200)
    index_repository(tmp_path)

    text = (tmp_path / ".repolens" / "graph-index.md").read_text(encoding="utf-8")

    assert "JavaScript Symbols" in text
    assert "Showing 100 of 1200" in text
```

```python
def test_graph_index_keeps_full_graph_in_sqlite_when_markdown_is_capped(tmp_path):
    _write_large_javascript_fixture(tmp_path, symbol_count=1200)
    index_repository(tmp_path)

    text = (tmp_path / ".repolens" / "graph-index.md").read_text(encoding="utf-8")

    with sqlite3.connect(tmp_path / ".repolens" / "graph.sqlite") as connection:
        count = connection.execute("SELECT COUNT(*) FROM javascript_symbols").fetchone()[0]

    assert count == 1200
    assert text.count("| function |") < count
```

```python
def test_graph_index_does_not_expose_source_when_capped(tmp_path):
    secret_body = "THIS_SOURCE_BODY_MUST_NOT_APPEAR_IN_GRAPH_INDEX"
    _write_text(tmp_path / "src" / "app.py", f"def app():\n    return {secret_body!r}\n")
    index_repository(tmp_path)

    text = (tmp_path / ".repolens" / "graph-index.md").read_text(encoding="utf-8")

    assert secret_body not in text
```

---

## Issue 3 — Add Truncation Metadata To Graph Status And Exports

Suggested title:

```text
Expose graph-index truncation metadata in status artifacts
```

Suggested labels:

```text
v0.3.1, P0, area:exports, area:cli
```

### Problem

If `graph-index.md` is capped, users and assistants need to know what was omitted and how to retrieve more.

### What to build

Add truncation metadata to `graph-status.json` or an export metadata section.

Suggested shape:

```json
{
  "exports": {
    "graph_index": {
      "path": ".repolens/graph-index.md",
      "truncated": true,
      "max_total_bytes": 200000,
      "sections": [
        {
          "name": "javascript_symbols",
          "shown": 100,
          "total": 4218,
          "reason": "section_row_cap"
        }
      ]
    }
  }
}
```

### Acceptance criteria

- [ ] `graph-status.json` reports whether `graph-index.md` was truncated.
- [ ] Section-level truncation metadata includes section name, shown count, total count, and reason.
- [ ] Metadata is deterministic.
- [ ] Metadata does not include raw source text.
- [ ] CLI or docs explain how to query omitted data.
- [ ] Existing status consumers do not break unexpectedly.

### Test cases

```python
def test_graph_status_reports_graph_index_truncation(tmp_path):
    _write_large_fixture_repo(tmp_path)
    index_repository(tmp_path)

    status = json.loads((tmp_path / ".repolens" / "graph-status.json").read_text())

    graph_index = status["exports"]["graph_index"]
    assert graph_index["truncated"] is True
    assert graph_index["sections"]
    assert graph_index["sections"][0].keys() >= {"name", "shown", "total", "reason"}
```

```python
def test_graph_status_reports_not_truncated_for_small_repo(tmp_path):
    _write_text(tmp_path / "app.py", "def app():\n    return 1\n")
    index_repository(tmp_path)

    status = json.loads((tmp_path / ".repolens" / "graph-status.json").read_text())

    assert status["exports"]["graph_index"]["truncated"] is False
```

---

## Issue 4 — Add Query Guidance Or CLI Surface For Full Graph Lookup

Suggested title:

```text
Add bounded graph index lookup command for omitted graph-index rows
```

Suggested labels:

```text
v0.3.1, P0, area:cli, area:exports
```

### Problem

If `graph-index.md` is capped, users need a supported way to retrieve omitted facts without opening huge Markdown.

### What to build

Add or reuse a bounded CLI graph lookup command.

Preferred simple surface:

```bash
repolens search-graph <repo> --kind symbol --query auth --limit 50
repolens search-graph <repo> --kind file --query login --limit 50
repolens search-graph <repo> --kind command --query test --limit 20
```

If `search-graph` already exists, update `graph-index.md` to point users to it. If only MCP structured search exists, add a thin CLI wrapper.

### Acceptance criteria

- [ ] Users can query graph metadata without opening `graph-index.md`.
- [ ] Query output is bounded by `--limit`.
- [ ] Query supports JSON output.
- [ ] Query does not read or return whole source files.
- [ ] Query respects existing graph availability and stale-warning behavior.
- [ ] `graph-index.md` includes examples for retrieving omitted data.
- [ ] The command returns structured no-result output instead of failing for no matches.

### Test cases

```python
def test_search_graph_cli_returns_bounded_symbol_results(tmp_path):
    _write_large_fixture_repo(tmp_path)
    index_repository(tmp_path)

    result = runner.invoke(
        app,
        ["search-graph", str(tmp_path), "--kind", "symbol", "--query", "login", "--limit", "10", "--json"],
    )

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    assert envelope["ok"] is True
    assert len(envelope["data"]["results"]) <= 10
```

```python
def test_search_graph_cli_does_not_return_source_bodies(tmp_path):
    secret_body = "SOURCE_BODY_MUST_NOT_RETURN"
    _write_text(tmp_path / "src" / "app.py", f"def login():\n    return {secret_body!r}\n")
    index_repository(tmp_path)

    result = runner.invoke(
        app,
        ["search-graph", str(tmp_path), "--kind", "symbol", "--query", "login", "--json"],
    )

    assert result.exit_code == 0
    assert secret_body not in result.output
```

```python
def test_search_graph_cli_no_match_returns_ok_with_empty_results(tmp_path):
    _write_text(tmp_path / "app.py", "def app():\n    return 1\n")
    index_repository(tmp_path)

    result = runner.invoke(
        app,
        ["search-graph", str(tmp_path), "--kind", "symbol", "--query", "missing", "--json"],
    )

    assert result.exit_code == 0
    envelope = json.loads(result.output)
    assert envelope["ok"] is True
    assert envelope["data"]["results"] == []
```

---

## Issue 5 — Add Optional Full Or Sharded Index Export

Suggested title:

```text
Add explicit full or sharded graph index export for large repositories
```

Suggested labels:

```text
v0.3.1, P1, area:exports, area:cli
```

### Problem

Some users may still want a complete Markdown export for offline browsing or debugging. The default should stay small, but full export can exist behind an explicit action.

### What to build

Add one of the following:

Option A:

```bash
repolens export-index <repo> --full --output .repolens/graph-index-full.md
```

Option B:

```bash
repolens index <repo> --full-index
```

Option C:

```bash
repolens export-index <repo> --sharded
```

Suggested sharded output:

```text
.repolens/index/README.md
.repolens/index/files.md
.repolens/index/python-symbols.md
.repolens/index/javascript-symbols.md
.repolens/index/imports.md
.repolens/index/configs.md
.repolens/index/docs.md
.repolens/index/tests.md
```

### Recommendation

Prefer **Option A** or **Option C**.

Avoid making `repolens index` generate huge files by default.

### Acceptance criteria

- [ ] Default `repolens index` remains bounded.
- [ ] Full export requires an explicit command or flag.
- [ ] Full export output is clearly named as full/unbounded.
- [ ] Sharded export, if implemented, creates multiple smaller files and a table of contents.
- [ ] Full/sharded exports preserve no-source-disclosure rules.
- [ ] Docs warn that full export may be large.

### Test cases

```python
def test_default_index_does_not_create_full_graph_index(tmp_path):
    _write_large_fixture_repo(tmp_path)
    index_repository(tmp_path)

    assert not (tmp_path / ".repolens" / "graph-index-full.md").exists()
```

```python
def test_full_graph_index_export_requires_explicit_command(tmp_path):
    _write_large_fixture_repo(tmp_path)
    index_repository(tmp_path)

    result = runner.invoke(app, ["export-index", str(tmp_path), "--full"])

    assert result.exit_code == 0
    assert (tmp_path / ".repolens" / "graph-index-full.md").exists()
```

```python
def test_sharded_graph_index_export_creates_table_of_contents(tmp_path):
    _write_large_fixture_repo(tmp_path)
    index_repository(tmp_path)

    result = runner.invoke(app, ["export-index", str(tmp_path), "--sharded"])

    assert result.exit_code == 0
    assert (tmp_path / ".repolens" / "index" / "README.md").exists()
    assert (tmp_path / ".repolens" / "index" / "javascript-symbols.md").exists()
```

---

## Issue 6 — Add Large-Repo Regression Fixtures

Suggested title:

```text
Add large-repo regression fixtures for graph-index artifact usability
```

Suggested labels:

```text
v0.3.1, P0, area:testing, area:performance
```

### Problem

The oversized `graph-index.md` issue needs a regression test so it does not return.

### What to build

Add synthetic large-repo fixture helpers. Do not vendor a large real repository.

The fixture generator should create:

- many source files;
- many symbols;
- many imports;
- many tests;
- many docs/configs where useful;
- stable deterministic file contents.

Suggested fixture sizes:

```text
small: 10 files, 50 symbols
medium: 100 files, 1,000 symbols
large: 500 files, 5,000 symbols
```

Use smaller fixture size in normal CI if runtime becomes too high.

### Acceptance criteria

- [ ] Large fixture generation is deterministic.
- [ ] Large fixture is generated in temp directories during tests.
- [ ] Tests do not vendor third-party repository snapshots.
- [ ] The large fixture can trigger graph-index truncation.
- [ ] Test runtime remains acceptable for CI.
- [ ] The fixture includes enough JS/TS and Python facts to exercise major sections.

### Test cases

```python
def test_large_fixture_generator_is_deterministic(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"

    _write_large_fixture_repo(first, file_count=50, symbols_per_file=10)
    _write_large_fixture_repo(second, file_count=50, symbols_per_file=10)

    assert _relative_file_contents(first) == _relative_file_contents(second)
```

```python
def test_large_fixture_triggers_graph_index_truncation(tmp_path):
    _write_large_fixture_repo(tmp_path, file_count=150, symbols_per_file=20)
    index_repository(tmp_path)

    status = json.loads((tmp_path / ".repolens" / "graph-status.json").read_text())

    assert status["exports"]["graph_index"]["truncated"] is True
```

```python
def test_large_fixture_index_runtime_smoke(tmp_path):
    _write_large_fixture_repo(tmp_path, file_count=100, symbols_per_file=10)

    result = runner.invoke(app, ["index", str(tmp_path)])

    assert result.exit_code == 0
    assert (tmp_path / ".repolens" / "graph.sqlite").exists()
```

---

## Issue 7 — Add CI Smoke For Bounded Graph Index

Suggested title:

```text
Add CI smoke coverage for bounded graph-index.md
```

Suggested labels:

```text
v0.3.1, P0, area:testing, area:performance
```

### Problem

The release gate should explicitly prove that default `graph-index.md` remains bounded.

### What to build

Add CI coverage that runs a bounded large-fixture smoke test.

The normal pytest suite can include a medium synthetic fixture. A heavier large fixture may run behind a marker.

Suggested markers:

```python
@pytest.mark.large_repo
def test_graph_index_large_repo_budget_smoke(...):
    ...
```

CI can run:

```bash
uv run pytest
uv run pytest -m large_repo
```

Or keep large-repo smoke in the default suite if it is fast enough.

### Acceptance criteria

- [ ] CI runs graph-index budget regression tests.
- [ ] CI fails if default `graph-index.md` exceeds the budget.
- [ ] CI fails if graph-index truncation metadata is missing.
- [ ] CI continues to run v0.3 Context Pack tests.
- [ ] CI branch trigger includes `feature/repolens-v0.3.1`.

### Test cases

CI should prove:

```text
- default index succeeds on synthetic medium/large repo;
- graph-index.md size stays below budget;
- graph-status.json reports graph-index truncation;
- full graph data still exists in SQLite;
- no source body appears in graph-index.md.
```

Suggested CI addition:

```yaml
- name: Run graph-index budget regression tests
  run: uv run pytest tests/test_graph_index_budget.py
```

Optional marker:

```yaml
- name: Run large repository artifact smoke
  run: uv run pytest -m large_repo
```

---

## Issue 8 — Update Docs And Release Notes For v0.3.1

Suggested title:

```text
Document bounded graph-index behavior and v0.3.1 artifact policy
```

Suggested labels:

```text
v0.3.1, P0, area:docs
```

### Problem

Users need to understand why `graph-index.md` is capped and how to retrieve omitted details.

### What to build

Update docs and release notes.

Docs should explain:

- `graph-index.md` is a compact navigation artifact;
- full graph facts live in SQLite;
- capped sections show `shown` and `total`;
- use graph search or MCP tools for more detail;
- optional full/sharded export behavior, if implemented;
- large Markdown export can be expensive;
- no source-disclosure rules still apply.

### Acceptance criteria

- [ ] README or docs mention bounded `graph-index.md`.
- [ ] v0.3.1 release notes describe the bug and fix.
- [ ] Docs explain how to retrieve omitted graph facts.
- [ ] Docs explain that SQLite remains complete.
- [ ] Docs mention optional full/sharded export if available.
- [ ] Docs include safety note: generated Markdown should not mirror full source.

### Test cases

Docs can be checked lightly:

```python
def test_docs_mention_bounded_graph_index():
    text = Path("README.md").read_text(encoding="utf-8")
    assert "graph-index.md" in text
    assert "bounded" in text or "capped" in text
```

If docs live elsewhere:

```python
def test_release_notes_mention_v031_graph_index_policy():
    text = Path("docs/releases/v0.3.1.md").read_text(encoding="utf-8")
    assert "graph-index.md" in text
    assert "SQLite" in text
    assert "truncated" in text
```

---

# Suggested Test File Layout

Recommended new test files:

```text
tests/test_graph_index_budget.py
tests/test_graph_index_search_cli.py
tests/test_graph_index_large_fixture.py
```

Optional:

```text
tests/test_export_index_cli.py
```

## `tests/test_graph_index_budget.py`

Should cover:

- default graph-index byte budget;
- per-section row caps;
- truncation metadata;
- full SQLite data remains complete;
- no source body disclosure;
- deterministic output under repeated runs.

## `tests/test_graph_index_search_cli.py`

Should cover:

- bounded graph metadata search;
- JSON output;
- no-match behavior;
- missing graph behavior;
- stale graph warning behavior if supported;
- no source body disclosure.

## `tests/test_graph_index_large_fixture.py`

Should cover:

- deterministic synthetic fixture generation;
- medium/large fixture smoke;
- truncation is triggered;
- runtime remains acceptable.

## `tests/test_export_index_cli.py`

Should cover only if optional export command is implemented:

- default full export absent;
- explicit full export creates clearly named file;
- sharded export creates table of contents;
- exported content follows no-source-disclosure rules.

---

# Release Gate

Do not cut v0.3.1 until the following pass:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
uv build
```

Additional v0.3.1 smoke:

```bash
uv run repolens index <large-fixture-or-dogfood-repo>
test $(wc -c < <large-fixture-or-dogfood-repo>/.repolens/graph-index.md) -le 200000
uv run repolens search-graph <large-fixture-or-dogfood-repo> --kind symbol --query auth --limit 20 --json
```

If `export-index` is implemented:

```bash
uv run repolens export-index <large-fixture-or-dogfood-repo> --full
uv run repolens export-index <large-fixture-or-dogfood-repo> --sharded
```

Existing v0.3 smoke should still pass:

```bash
uv run repolens context <fixture-or-repo-path> "Fix login validation" --json
uv run repolens evaluate-context <fixture-or-repo-path> --json
```

---

# Recommended Implementation Order

1. Issue 1 — Define artifact budget contract.
2. Issue 6 — Add large-repo fixture generator.
3. Issue 2 — Bound `graph-index.md`.
4. Issue 3 — Add truncation metadata to status.
5. Issue 4 — Add or wire graph search CLI guidance.
6. Issue 7 — Add CI smoke coverage.
7. Issue 8 — Update docs and release notes.
8. Issue 5 — Optional full/sharded export, if still needed.

If time is limited, Issue 5 can move to v0.4 because the critical patch is making default output usable.

---

# Suggested Umbrella Tracker

Suggested title:

```text
RepoLens MCP v0.3.1 artifact usability patch
```

Suggested body:

```markdown
## Theme

Make RepoLens outputs usable on real repositories.

## Problem

`graph-index.md` can become too large to open or load on large repositories. This breaks the assistant-facing artifact contract and works against RepoLens' goal of reducing orientation cost.

## Scope

v0.3.1 focuses on bounded `graph-index.md`, artifact budget contracts, truncation metadata, graph lookup guidance, large-repo regression tests, CI smoke, and docs.

## Release-blocking P0 work

- [ ] Define AI-facing artifact budget contract.
- [ ] Convert `graph-index.md` into a bounded landing page.
- [ ] Add graph-index truncation metadata to status/export metadata.
- [ ] Add or wire bounded graph lookup CLI guidance.
- [ ] Add deterministic large-repo regression fixtures.
- [ ] Add CI smoke coverage for bounded graph-index behavior.
- [ ] Update docs and release notes.

## Optional P1 work

- [ ] Add explicit full or sharded graph index export.

## Release criteria

- [ ] Default `graph-index.md` stays under the configured budget on large fixtures.
- [ ] Large sections show `shown`, `total`, and truncation reason.
- [ ] Full graph facts remain available through SQLite.
- [ ] Users can query omitted graph facts without opening huge Markdown.
- [ ] No source snippets, code bodies, raw comments, or raw Agent Guidance text are exposed.
- [ ] Existing v0.3 Context Pack tests still pass.
- [ ] Full verification passes.
```

---

# Notes For Implementation Agents

- Do not solve this by deleting useful graph facts from SQLite.
- Do not solve this by silently skipping whole categories without counts.
- Do not add embeddings or AI summaries.
- Do not expose source snippets to make the index more useful.
- Do not make full Markdown export the default.
- Prefer deterministic caps, clear truncation metadata, and query paths for deeper inspection.