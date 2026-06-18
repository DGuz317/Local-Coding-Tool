# Python / RepoLens Architecture Notes

Use this when applying the architecture skill to the RepoLens MCP codebase.

## Preferred module seams

For RepoLens, look for these seams first:

- CLI command handlers
- application services
- scanner/discovery policy
- parser/extractor modules
- graph store
- artifact exporters
- query service
- MCP server wrapper

CLI handlers should stay thin. They parse user input, call application services, and format output.

Application services should own behavior. They should be testable without invoking the actual shell.

The MCP server should be a wrapper over the query service, not a second implementation of graph behavior.

## Good deepening candidates

Prefer candidates where complexity can move behind one interface:

- scan policy behind one scanner interface
- graph writes behind one graph store interface
- artifact generation behind one export interface
- graph reads behind one query service interface
- MCP tools behind one query-service adapter

## Avoid shallow modules

Watch for modules that only rename or forward calls:

- `cli_status.py` calls `status_service.py` calls `status_builder.py` with no added leverage
- `graph_json_exporter.py`, `graph_lite_exporter.py`, and `graph_report_exporter.py` duplicating traversal logic
- MCP tool handlers reimplementing query behavior already present in the query service

Apply the deletion test: if deleting the module only moves the same complexity into its caller, the module is shallow.

## Testing implication

The interface is the test surface.

For RepoLens, prefer tests through:

- CLI commands for user-facing behavior
- scanner service for scan policy
- graph store/query service for graph behavior
- exporter service for artifact behavior
- MCP smoke tests only for protocol wrapping

Do not create seams only for tests. One adapter means a hypothetical seam; two adapters means a real seam.