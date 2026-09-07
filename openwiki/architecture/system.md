---
type: architecture
title: System architecture
description: How the CLI, Python SDK, FastAPI service, React workbench, and local artifacts cooperate to turn traces into reviewable improvement experiments.
tags: [architecture, sdk, persistence, provenance]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T19:39:22.177Z
sources:
  - id: openwiki-source-896da76531d8a33d2c9e76b8
    resource: repo://src/agent_data_workbench/api/application.py
  - id: openwiki-source-57d1f240e9d0552b9b058bdc
    resource: repo://src/agent_data_workbench/api/dependencies.py
  - id: openwiki-source-98bfc373ed8e75b28dcf239e
    resource: repo://src/agent_data_workbench/api/routers/tasks.py
  - id: openwiki-source-fd74f7907459785462506ae7
    resource: repo://src/agent_data_workbench/cli/tasks.py
  - id: openwiki-source-2dd7f78b8d8a37f91c61de42
    resource: repo://src/agent_data_workbench/database.py
  - id: openwiki-source-4c04fd9d10dcc0e748ac55cc
    resource: repo://src/agent_data_workbench/identifiers.py
  - id: openwiki-source-12d025c9e4830dcc4dd30757
    resource: repo://src/agent_data_workbench/jobs.py
  - id: openwiki-source-1188f1141809a45a7d20b02f
    resource: repo://src/agent_data_workbench/persistence.py
  - id: openwiki-source-b5025a250cbf9f845fc9224a
    resource: repo://src/agent_data_workbench/project.py
  - id: openwiki-source-df79e35713d914a8f9a3aa91
    resource: repo://src/agent_data_workbench/reports.py
  - id: openwiki-source-069858a5e395202064ced424
    resource: repo://src/agent_data_workbench/store.py
  - id: openwiki-source-c90a57f259e123cf538cdd9c
    resource: repo://src/agent_data_workbench/workflow.py
  - id: openwiki-source-09d2a8f36f3ecb7ab9487ab2
    resource: repo://tests/test_store.py
generated: { by: "codex", at: "2026-09-07T19:39:22.177Z" }
---

# System architecture

Agent Data Workbench is a local Python application with a bundled React/TypeScript interface. The CLI and HTTP API call the same SDK functions; the browser supplies interaction and visualization. A project directory holds the evidence and derived artifacts.

```mermaid
flowchart TD
  Traces[Agent trace exports] --> Store[TraceStore and SQLAlchemy]
  CLI[Python CLI] --> SDK[Python domain functions]
  UI[React and TypeScript UI] --> API[FastAPI on Uvicorn]
  API --> SDK
  SDK --> Store
  Store --> SQLite[Local SQLite traces]
  SDK --> Artifacts[Versioned JSON and reports]
  SDK --> Analyzer[Codex or Claude analyzer]
  SDK --> Runner[Configured target runner]
```

## Responsibilities

| Component | Responsibility | Main entry points |
| --- | --- | --- |
| CLI | Import, research, task review, experiments, and export commands | `cli/__init__.py`, `cli/project.py`, and domain command modules |
| SDK | Domain contracts and the improvement workflow | `__init__.py`, `research.py`, `tasks.py`, `experiments.py` |
| Storage | Canonical trace records and query primitives | `store.py`, `database.py` |
| FastAPI | Typed operations, session boundaries, static assets, background jobs | `api/application.py`, `api/routers/`, `api/schemas.py`, `api/dependencies.py`, `api/middleware.py`, `jobs.py` |
| UI | Trace search, clusters, lineage, reviews, and experiment inspection | `ui/src/App.tsx`, `ui/src/views/` |
| Extensions | Bring another trace source, analyzer, or target harness | `TraceSource`, `Analyzer`, `TargetRunner` |

The app factory composes domain routers. FastAPI dependencies supply the project, job queue, and bearer authentication; request middleware enforces host, origin, and body limits. `server.py` starts Uvicorn and owns the local session lifecycle. The former `local_http.py` was middleware, not another server.

The service layer translates requests into SDK operations. It does not contain a separate copy of task acceptance or research logic. FastAPI's interactive documentation routes are disabled; the session-protected `/api/openapi.json` describes the implemented API.

## Local state and consistency

`Project.create` requires a new or empty directory. It writes `project.json` and creates `knowledge/`, `investigations/`, `tasks/`, `suites/`, `experiments/`, and `exports/`. A project-local `.gitignore` excludes its contents. Use a directory under `runs/` for private working data.

`TraceStore` uses `traces.sqlite3`. SQLAlchemy maps the original six-column trace layout: ID, source group, stratum, canonical JSON, content hash, and import time. A session transaction wraps each operation; an import conflict rolls back its batch. The engine uses `NullPool`, and first-use schema creation is serialized inside the process. Worker threads obtain their own sessions.

Internal artifact IDs are canonical UUID strings validated with Python UUID/Pydantic types. Generated records use UUIDv4; content-derived identities use UUIDv5. Imported trace IDs remain unchanged. Suite names are friendly labels separate from their UUIDs. Project format 0.3 rejects older project formats before rewriting any files; create a new project and reimport the traces.

Structured artifacts are written through `persistence.atomic_text`; Markdown escaping is shared through `reports.md`. Mutating workflows use a nonblocking POSIX project lock; a concurrent mutation returns a busy error. The HTTP job queue separately permits one background model job at a time. These mechanisms serve a local process-and-files workflow, not a distributed job system.

## How evidence becomes an experiment

Import preserves source records. An [investigation](../workflows/investigations.md) researches them and cites exact evidence. [Tasks](../workflows/tasks-and-graders.md) separate target-visible input from grading criteria and require review after a grader audit. A suite freezes accepted task specifications and source-group assignments. [Experiments](../workflows/experiments-and-training.md) execute two target variants and preserve trial output, required artifacts, invalid runs, and regressions. Training export selects reviewed outcomes from optimization experiments.

These records provide provenance and detect accidental drift. They do not isolate a hostile target from host files or establish that a synthetic result generalizes to production.

## Extension seams

Implement `TraceSource.read()` to import another export format, `Analyzer.analyze(prompt, schema)` for another analysis backend, or `TargetRunner.identity()` and `run(visible_input, trial_dir, seed)` for another execution harness. Keep real environment reset and authoritative state capture inside the runner integration. Direct service connectors, Harbor integration, distributed execution, and training-job execution are not bundled.

Next: [import and explore traces](../workflows/traces.md), [run the local workbench](../operations/local-workbench.md), or [development](../development/contributing.md).
