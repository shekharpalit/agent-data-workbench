---
type: development
title: Development and verification
description: Set up Python and TypeScript development, preserve the shared contracts, and verify changes with behavioral tests and reproducible builds.
tags: [development, testing, packaging]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T17:18:36.762Z
sources:
  - id: openwiki-source-868b3402493aef58bb5db066
    resource: repo://.python-version
  - id: openwiki-source-8037e2358a2c4f9b2c722a11
    resource: repo://AGENTS.md
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-11519246eac934485315b3cb
    resource: repo://tests/test_api.py
  - id: openwiki-source-09d2a8f36f3ecb7ab9487ab2
    resource: repo://tests/test_store.py
  - id: openwiki-source-af0e5443d83442c11181e6ce
    resource: repo://tests/test_workbench_execution.py
  - id: openwiki-source-436f4179fe22abf615d2f7d0
    resource: repo://ui/package.json
  - id: openwiki-source-e77b7b0b1f74ca6b888c0fb8
    resource: repo://ui/tests/state.test.ts
  - id: openwiki-source-a741d432f952c0dbfb4fb35d
    resource: repo://ui/vite.config.ts
generated: { by: "codex", at: "2026-09-07T17:18:36.762Z" }
---

# Development and verification

[AGENTS.md](../../AGENTS.md) is the repository's implementation brief; [CLAUDE.md](../../CLAUDE.md) points Claude Code to the same conventions. Use [system architecture](../architecture/system.md) to locate the owner of a behavior before changing it.

## Set up and verify Python

The repository pins Python 3.14.7 in `.python-version`, declares Python 3.14+ support, and targets Python 3.14 in Ruff. Keep uv current enough to obtain the pinned interpreter.

```sh
uv sync --locked
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
uv build
```

The lockfile records the tested versions. `pyproject.toml` declares minimum versions and excludes prereleases during uv resolution. For a deliberate dependency update, run `uv lock --upgrade`, review its diff, sync with `--locked`, and run the relevant checks. Do not replace reproducible locks with unbounded installation on every run.

## Work on the UI

Use a current Node.js LTS release satisfying the UI dependency engine requirements, with npm on PATH. The UI manifest declares Node 22.12+; individual development dependencies can impose stricter patch requirements, so heed npm's engine checks.

```sh
npm ci --prefix ui
npm --prefix ui run build
npm --prefix ui test
npm --prefix ui run format:check
```

The build runs strict TypeScript compilation, then Vite. Vite writes into `src/agent_data_workbench/web`, replacing the previous bundle. Commit those assets with the source so Python installations work without Node. For iteration, run `npm --prefix ui run dev` beside the local Python workbench; it watches and rebuilds files rather than starting a separate UI development server. Refresh the browser after a rebuild.

## Tests describe behavior

Use Given / When / Then: arrange the inputs, execute the behavior, and compare a meaningful complete result. Python uses `assert actual == expected`; TypeScript uses `expect(actual).toStrictEqual(expected)`. JavaScript object identity is not deep comparison. When values include volatile IDs or timestamps, compare an explicit meaningful projection while separately testing provenance.

For example, trace-store tests check that an ID conflict rolls back the whole new batch and that a clean retry succeeds. Search-state tests check that changing filters resets pagination while retaining the rest of the query. API tests check typed schemas together with session rejection. Experiment tests check fresh target directories and preservation of regressions. These establish observable contracts rather than restating private implementation steps.

| Change | Relevant evidence and checks |
| --- | --- |
| Storage or import | `tests/test_store.py`, import cases in `tests/test_workbench_data.py` |
| Search, clustering, lineage | `tests/test_explore.py`, `ui/tests/state.test.ts`, `ui/tests/search.test.tsx` |
| HTTP behavior | `tests/test_api.py`, `ui/tests/api.test.ts` |
| Research and task review | `tests/test_workbench_data.py`, `tests/test_backends.py` |
| Runner execution and exports | `tests/test_workbench_execution.py` |
| Legacy batch mode | `tests/test_workflow.py`, `tests/test_evaluation.py`, `tests/test_cli.py` |
| Packaging | `uv build`, install the wheel in an isolated environment, exercise bundled resources |

Keep tests synthetic and independent of provider credentials. An explicitly requested live analyzer check is separate from the ordinary test suite. Record what was run and any limitation; passing fixtures do not establish production agent improvement.

## Preserve ownership and invariants

Use FastAPI routes with typed Pydantic contracts. Keep domain operations in the SDK and SQLAlchemy access in the storage layer. Preserve import rollback, canonical trace content, review invalidation, source-group assignment, and invalid-versus-failed outcomes. Keep UI JSON types and lineage consistent with backend behavior.

After source changes are complete, use the [OpenWiki maintenance workflow](../operations/documentation.md). Do not regenerate against source that is still being edited. Keep local runs, credentials, virtual environments, and installed dependencies out of commits.
