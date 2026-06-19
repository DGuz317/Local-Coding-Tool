# Store edge trust fields explicitly with bounded evidence JSON

RepoLens v0.2 stores edge confidence and resolution strategy as explicit edge contract fields, with bounded normalized evidence stored as JSON. This keeps trust and provenance visible to query and MCP consumers without hiding them in generic metadata or introducing a fully normalized evidence subsystem before v0.2 needs it.
