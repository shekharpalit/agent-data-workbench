# Agent guidance

Use source code and tests as the authority. Documentation lives in `openwiki/`; start with `openwiki/quickstart.md` when you need a route to a topic. This repository uses on-demand OpenWiki generation through the coding-agent integration. There is no scheduled documentation workflow configured.

## Implementation conventions

- Use Python 3.14.7 and `uv sync --locked`. Keep stable dependencies and commit lockfile changes.
- Keep domain logic in the Python SDK. Use FastAPI and typed Pydantic contracts for HTTP routes, and SQLAlchemy mapped models, sessions, and query expressions for database access. Do not add handwritten SQL or regex route dispatch.
- Use React and TypeScript for the UI. Preserve JSON types, evidence lineage, and shared search/filter semantics.
- Write tests in Given / When / Then format. Compare complete result objects: `assert actual == expected` in Python and `expect(actual).toStrictEqual(expected)` in TypeScript. JavaScript `{} === {}` compares identity, not object contents.
- Keep tests synthetic and independent of provider credentials. Run the narrow checks relevant to each change. Backend checks: `uv run pytest -q`, `uv run ruff check src tests`, and `uv run ruff format --check src tests`. Frontend checks: `npm ci --prefix ui`, `npm --prefix ui run build`, `npm --prefix ui test`, and `npm --prefix ui run format:check`.
- Commit rebuilt `src/agent_data_workbench/web` assets when UI source changes. Verify `uv build` when packaging changes.
- Generate internal artifact IDs with UUIDs and validate them through the shared UUID type. Preserve external trace IDs verbatim.
- Preserve canonical trace data, import rollback, accepted-task audit gates, source-group separation, invalid outcomes, and final-split exposure bookkeeping.
- State what experiments actually establish. Synthetic test results do not establish model improvement; captured target files are not independent ground truth. Command runners execute trusted code with host access.
- Keep credentials, private traces, local runs, virtual environments, and dependency installations out of Git.

## Documentation

Use the installed OpenWiki skill and MCP lifecycle to generate or update the wiki. The user-authored scope is `openwiki/INSTRUCTIONS.md`. Codex and Claude integrations are installed at repository scope. Finish the current code change before starting a documentation run so source evidence remains stable. Preserve OpenWiki-managed indexes, claims, and provenance through its tools.

<!-- OPENWIKI:START -->

## OpenWiki

This repository has a generated `openwiki/` evidence index. It is optional just-in-time context, not required startup reading.

- Treat source code and tests as authoritative. A brief's unknowns and review items are verification gaps, not automatic requirements.
- Prefer the narrowest quiet validation that proves the changed behavior. Preserve complete failure output.

The scheduled OpenWiki GitHub Actions workflow refreshes the repository wiki. Do not hand-edit generated OpenWiki pages unless explicitly asked; prefer updating source code/docs and letting OpenWiki regenerate.

<!-- OPENWIKI:END -->
