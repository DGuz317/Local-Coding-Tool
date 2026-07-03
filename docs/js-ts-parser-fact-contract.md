# JS/TS Parser Fact Contract

RepoLens v0.6 promotes only source-free JS/TS parser facts into the stable graph contract.

The promoted schema version is `javascript-promoted-facts-v1`. Parser or promoted fact schema changes must update this version through `JAVASCRIPT_EXTRACTOR_VERSION`, making the change graph-affecting for freshness and artifact identity.

## Stable Fact Groups

Stable JS/TS facts are limited to these groups and fields:

| Group | Allowed fields |
| --- | --- |
| `modules` | `path`, `node_id`, `module_name`, `extension`, `parser_status` |
| `imports` | `id`, `path`, `module_node_id`, `kind`, `specifier`, `root_name`, `classification`, `resolved_path`, `resolution_status`, `line` |
| `packages` | `id`, `name`, `classification` |
| `symbols` | `id`, `path`, `module_node_id`, `kind`, `name`, `qualified_name`, `line`, `start_line`, `end_line` |
| `exports` | `id`, `path`, `module_node_id`, `kind`, `exported_name`, `local_name`, `line` |
| `commonjs_assignments` | `id`, `path`, `module_node_id`, `kind`, `exported_name`, `assigned_name`, `line` |

Line metadata is orientation evidence only. Fact IDs must remain deterministic and must not use line numbers as primary identity.

## Experimental Facts

These facts remain experimental and unpromoted:

- raw Tree-sitter AST nodes;
- source snippets;
- full source expressions;
- function signatures;
- raw comments;
- raw config values;
- full import lines;
- code bodies;
- absolute host paths;
- parser-only research facts that are not listed in the stable fact groups above.

Experimental parser-only facts must stay out of Canonical Graph Hash and default Context Pack IDs until a tracker decision promotes them, updates the promoted schema version, and adds contract tests.

## Fixture Coverage

The JS/TS parser and resolver test suite covers the minimum v0.6 matrix:

- `.js`, `.jsx`, `.mjs`, `.cjs`, `.ts`, and `.tsx` source files;
- static ESM import, side-effect import, dynamic import, and CommonJS `require`;
- `module.exports` and `exports.*` assignments;
- named export, default export, and re-export forms;
- TypeScript `baseUrl`, `paths` alias, and ambiguous alias outcomes;
- workspace package import resolution;
- package entrypoint evidence.
