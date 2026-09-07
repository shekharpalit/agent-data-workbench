---
type: development
title: Development and verification
description: Set up Python and TypeScript development, preserve the shared contracts, and verify changes with behavioral tests and reproducible builds.
tags: [development, testing, packaging]
sources:
  - id: openwiki-source-868b3402493aef58bb5db066
    resource: repo://.python-version
  - id: openwiki-source-8037e2358a2c4f9b2c722a11
    resource: repo://AGENTS.md
  - id: openwiki-source-012f2c78e3b1446dfc35803f
    resource: repo://Makefile
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-f0a6e7dc03522b2682f88655
    resource: repo://tests/conftest.py
  - id: openwiki-source-11519246eac934485315b3cb
    resource: repo://tests/test_api.py
  - id: openwiki-source-9ec6473d05fcc2cd40915af2
    resource: repo://tests/test_cli.py
  - id: openwiki-source-1d5897d9fc482596678731c2
    resource: repo://tests/test_conversation_exports.py
  - id: openwiki-source-9c58a0b0672b6bdbd523d5ee
    resource: repo://tests/test_identifiers.py
  - id: openwiki-source-0bb6c35cfc5dfdfa5db20794
    resource: repo://tests/test_improvement_loop.py
  - id: openwiki-source-3e6ae5cbfb3aa3af0850499a
    resource: repo://tests/test_manual_research_api.py
  - id: openwiki-source-3589dc1fc29ba0bfe0e2a50c
    resource: repo://tests/test_research.py
  - id: openwiki-source-d19087670ca2c8e59a9fb6a3
    resource: repo://tests/test_runtime.py
  - id: openwiki-source-af0e5443d83442c11181e6ce
    resource: repo://tests/test_workbench_execution.py
  - id: openwiki-source-436f4179fe22abf615d2f7d0
    resource: repo://ui/package.json
  - id: openwiki-source-434ba4f21f543ddea1569be6
    resource: repo://ui/tests/manual-editor.test.tsx
  - id: openwiki-source-85ab1a7a14e4d8d1bcfef689
    resource: repo://ui/tests/manual-research.test.tsx
  - id: openwiki-source-6c2199ef844fc5690d6362d0
    resource: repo://ui/tests/research.test.tsx
  - id: openwiki-source-a741d432f952c0dbfb4fb35d
    resource: repo://ui/vite.config.ts
generated: { by: "codex", at: "2026-09-07T23:10:49.194Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T23:10:49.194Z
---

# Development and verification

[AGENTS.md](../../AGENTS.md) is the repository's implementation brief; [CLAUDE.md](../../CLAUDE.md) points Claude Code to the same conventions. Use [system architecture](../architecture/system.md) to locate the owner of a behavior before changing it.

## Start development with Docker

Install Docker with Compose v2 and Make; on Windows use WSL2. From the repository root:

```sh
make init
make dev
```

Open the backend's printed private URL. Python source changes restart the backend with the same browser token. The UI watcher rebuilds the bundled assets; refresh the browser after a rebuild. Ctrl-C stops both services. `make test` runs Python tests, Ruff checks, UI tests, formatting and the TypeScript/production build inside containers. `make build` builds both development and packaged images. Use [Docker and Make workflow](../operations/containers.md) for imports, persistent volumes and custom ports.

## Set up and verify Python natively

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

Use Node 22.22.2+, Node 24.15+, or Node 26+ in the major versions allowed by `ui/package.json`, with npm on PATH. The declared ranges exclude Node 23 and 25. A supported Node 24 LTS installation is suitable for development.

```sh
npm ci --prefix ui
npm --prefix ui run build
npm --prefix ui test
npm --prefix ui run format:check
```

The production build runs strict TypeScript compilation, then Vite. Vite writes into `src/agent_data_workbench/web`, replacing the previous bundle. The development watcher retains existing assets while writing the next build, ignores its own output and dependencies, and uses filesystem polling for container bind mounts. Commit those assets with the source so Python installations work without Node. For iteration, run `npm --prefix ui run dev` beside the local Python workbench; it watches and rebuilds files rather than starting a separate UI development server. Refresh the browser after a rebuild.

## Tests describe behavior

Use Given / When / Then: arrange the inputs, execute the behavior, and compare a meaningful complete result. Python uses `assert actual == expected`; TypeScript uses `expect(actual).toStrictEqual(expected)`. JavaScript object identity is not deep comparison. When values include volatile IDs or timestamps, compare an explicit meaningful projection while separately testing provenance.

For example, trace-store tests check that an ID conflict rolls back the whole new batch and that a clean retry succeeds. Search-state tests check that changing filters resets pagination while retaining the rest of the query. API tests check typed schemas together with session rejection. Experiment tests check fresh target directories and preservation of regressions. These establish observable contracts rather than restating private implementation steps.

| Change | Relevant evidence and checks |
| --- | --- |
| Storage or import | `tests/test_store.py`, import cases in `tests/test_workbench_data.py` |
| Search, clustering, lineage | `tests/test_explore.py`, `ui/tests/state.test.ts`, `ui/tests/search.test.tsx` |
| HTTP behavior | `tests/test_api.py`, `tests/test_identifiers.py`, `ui/tests/api.test.ts` |
| UUIDs and project compatibility | `tests/test_identifiers.py` |
| CLI workflow integration | `tests/test_cli.py` |
| Native research, coverage and MCP | `tests/test_research.py`, `ui/tests/research.test.tsx` |
| Manual research and human/agent handoff | `tests/test_manual_research_api.py`, `ui/tests/manual-research.test.tsx`, `ui/tests/manual-editor.test.tsx` |
| Evidence, task review and batch backends | `tests/test_workbench_data.py`, `tests/test_backends.py` |
| Runner execution and exports | `tests/test_workbench_execution.py` |
| Batch analysis | `tests/test_workflow.py`, `tests/test_evaluation.py`, `tests/test_cli.py` |
| Packaging | `uv build`, install the wheel in an isolated environment, exercise bundled resources |

Runtime demo commands and canned agent data have been removed. Explicit synthetic fixtures live under `tests/fixtures/` and are loaded only by tests. The CLI integration test initializes a project, imports traces and tasks, requires audits before acceptance, creates a named suite with a UUID, executes command adapters, and exports reviewed outcomes. UUID tests verify canonicalization, unchanged external trace IDs, typed API rejection, and refusal to rewrite an older project.

Native research tests execute local subprocesses emitting Codex-shaped events and a real official MCP client/server exchange. They verify session persistence before cancellation or failure, complete-pass retries, a 257-record corpus crossing page boundaries, full large-record reads, artifact integrity, and CLI publication without a model. These tests do not exercise live provider inference or prove analysis quality.

Manual API tests create a snapshot, read exact evidence, record every outcome and publish without a provider; they also check snapshot stability after imports, typed requests, chart output, bearer authentication and final-data exposure. Session ownership tests hold the native lock, confirm manual HTTP writes are rejected without changes, and verify those writes succeed after release while native SDK access remains available. UI tests cover manual navigation, cursor and field paging, typed outcomes, citation reads from the snapshot, draft preservation across polling and active-session transitions, and retaining existing linked agent outputs.

Keep tests synthetic and independent of provider credentials. An explicitly requested live analyzer check is separate from the ordinary test suite. Record what was run and any limitation; passing fixtures do not establish production agent improvement.

## Preserve ownership and invariants

Keep native investigation orchestration separate from data processing: Codex/Claude own planning and session context; `ResearchWorkspace` owns datasets, outcomes, evidence and artifacts. Do not add a second model-call loop or default corpus/call ceilings.

Use FastAPI routes with typed Pydantic contracts. Keep domain operations in the SDK and SQLAlchemy access in the storage layer. Preserve import rollback, canonical trace content, review invalidation, source-group assignment, and invalid-versus-failed outcomes. Keep UI JSON types and lineage consistent with backend behavior.

After source changes are complete, use the [OpenWiki maintenance workflow](../operations/documentation.md). Do not regenerate against source that is still being edited. Keep local runs, credentials, virtual environments, and installed dependencies out of commits.

## Verify the complete eval workflow

`tests/test_improvement_loop.py` runs a synthetic cancellation failure through a captured human investigation, accepted world/task, verifier audit, real persistent target subprocesses, independent state observation, exact candidate change, calibration, coverage and decision. Both targets claim cancellation; only the corrected target leaves the authoritative store in the expected state. This verifies the workflow, not production model gains.

Use `test_environment_sessions.py` for reset drift, partial transcripts, cancellation, source changes, and reactive-user behavior; `test_worlds_improvements.py` for historical world references, exact candidate drift, and multiple conversation scenarios in one suite. `test_calibration_coverage.py` covers actual human/model labels, adjudication, slice gaps, stale mappings and exposure. `test_workflow_controls.py` exercises the typed UI API and CLI with provider constructors forbidden.

`test_harbor_export.py` verifies real template bundling, visible-input separation, source exposure, pinned manifests and synthetic CLI transport. It does not run a Harbor container or a provider model. `test_conversation_exports.py` uses real persistent local sessions to verify complete observed trajectories, exclusion of hidden truth and identical preferences, and legacy one-shot compatibility. `ui/tests/workflow.test.tsx` verifies human review and exact evidence identities, including hiding grader answers before a first label. See [eval engineering](../workflows/eval-engineering.md) for adapter contracts.

`tests/test_runtime.py` covers idempotent initialization, refusal to adopt unrelated directories, normalized browser origins, bearer/Host/Origin enforcement under container binding, inherited reload tokens, and real SIGINT/SIGTERM listener shutdown. `test_environment_sessions.py` also verifies that a target mutating its pinned source during shutdown becomes invalid while its already observed interaction remains saved.
