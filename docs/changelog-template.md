# RepoLens MCP Changelog Template

Use this template for release notes. Keep entries factual and avoid publishing claims until a human maintainer confirms the release channel.

## RepoLens MCP vX.Y.Z - YYYY-MM-DD

### Summary

- One or two sentences describing the release theme and user-facing value.

### Added

- New user-visible capabilities.

### Changed

- Behavior changes, compatibility notes, and response contract changes.

### Fixed

- Bugs fixed since the previous release.

### Security And Privacy

- Scanner, redaction, artifact privacy, and no-whole-source-disclosure changes.

### MCP Contract

- Tool additions, removals, argument changes, envelope changes, freshness metadata, pagination, truncation, and error behavior.

### Known Limitations

- Link to `docs/known-limitations.md` and call out any release-relevant limitations.

### Verification

- `uv run pytest`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src/repolens`
- Build/install smoke result.
- Docker smoke result.
- MCP client smoke result.
- Dogfooding report links.

### Human Checkpoint

- Maintainer name/date:
- README reviewed:
- Assistant docs reviewed:
- Security/privacy docs reviewed:
- Known limitations reviewed:
- Publishing automation confirmed out of scope:
