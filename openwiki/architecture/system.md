---
type: architecture
title: System architecture
description: How the CLI, Python SDK, FastAPI service, React workbench, and local artifacts cooperate to turn traces into reviewable improvement experiments.
tags: [architecture, sdk, persistence, provenance]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-08T00:07:39.310Z
sources:
  - id: openwiki-source-8037e2358a2c4f9b2c722a11
    resource: repo://AGENTS.md
  - id: openwiki-source-e201e686a785f09b6d899f0b
    resource: repo://compose.yaml
  - id: openwiki-source-bb1ebe868e35e9e500714501
    resource: repo://Dockerfile
  - id: openwiki-source-a06d79006637fc11757f605b
    resource: repo://src/agent_data_workbench/__init__.py
  - id: openwiki-source-6015b7f3661c24935a195829
    resource: repo://src/agent_data_workbench/__main__.py
  - id: openwiki-source-fe89c78dfebbfceed4c54c0f
    resource: repo://src/agent_data_workbench/analysis/reporting.py
  - id: openwiki-source-896da76531d8a33d2c9e76b8
    resource: repo://src/agent_data_workbench/api/application.py
  - id: openwiki-source-57d1f240e9d0552b9b058bdc
    resource: repo://src/agent_data_workbench/api/dependencies.py
  - id: openwiki-source-e6d7f541d0e16503af405c8b
    resource: repo://src/agent_data_workbench/api/routers/investigations.py
  - id: openwiki-source-98bfc373ed8e75b28dcf239e
    resource: repo://src/agent_data_workbench/api/routers/tasks.py
  - id: openwiki-source-fd74f7907459785462506ae7
    resource: repo://src/agent_data_workbench/cli/tasks.py
  - id: openwiki-source-cdad3fe88d744628d97a2fa6
    resource: repo://src/agent_data_workbench/data/database.py
  - id: openwiki-source-ece138f4d793e07725c336eb
    resource: repo://src/agent_data_workbench/data/store.py
  - id: openwiki-source-fbcc81f66a8993d5ee2b7eda
    resource: repo://src/agent_data_workbench/evaluation/improvements.py
  - id: openwiki-source-7873eadc6e06d9c18f47371a
    resource: repo://src/agent_data_workbench/evaluation/tasks/grading.py
  - id: openwiki-source-0c67ad46a6bd6ff73934e82d
    resource: repo://src/agent_data_workbench/evaluation/tasks/repository.py
  - id: openwiki-source-7758acda0a6d0691a2dad9c9
    resource: repo://src/agent_data_workbench/evaluation/worlds.py
  - id: openwiki-source-c792213eed7e8f73d739e358
    resource: repo://src/agent_data_workbench/research/artifacts.py
  - id: openwiki-source-19e7dd6c7eb0091ce3762537
    resource: repo://src/agent_data_workbench/research/dataset.py
  - id: openwiki-source-1c842561c46278adab40a06d
    resource: repo://src/agent_data_workbench/research/mcp.py
  - id: openwiki-source-e5f659ea5e57c342ab8bc379
    resource: repo://src/agent_data_workbench/research/sessions.py
  - id: openwiki-source-2dbe8753da4267ce652f414e
    resource: repo://src/agent_data_workbench/research/workspace.py
  - id: openwiki-source-672190e2dfc145657515919f
    resource: repo://src/agent_data_workbench/shared/files.py
  - id: openwiki-source-b9263f82c99973ba337bc796
    resource: repo://src/agent_data_workbench/shared/identifiers.py
  - id: openwiki-source-a03e12d6f53e66e8a7ae34ba
    resource: repo://src/agent_data_workbench/shared/json.py
  - id: openwiki-source-6346ce0d406446ce0fd7a1db
    resource: repo://src/agent_data_workbench/shared/markdown.py
  - id: openwiki-source-c8c7945f688b6b620d3800cf
    resource: repo://src/agent_data_workbench/workbench/jobs.py
  - id: openwiki-source-56b68af7c871c44d9ba4d64d
    resource: repo://src/agent_data_workbench/workbench/runtime.py
  - id: openwiki-source-b9e04cc4343208a80c47ef02
    resource: repo://src/agent_data_workbench/workspace/project.py
  - id: openwiki-source-3e6ae5cbfb3aa3af0850499a
    resource: repo://tests/test_manual_research_api.py
generated: { by: "codex", at: "2026-09-08T00:07:39.310Z" }
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
  Human[Human researcher] --> UI
  SDK --> Workspace[Shared ResearchWorkspace]
  Workspace --> Snapshot
  SDK --> Session[Native Codex or Claude Code session]
  Session --> Tools[MCP and Python workspace tools]
  Tools --> Snapshot[Investigation SQLite snapshot and outcomes]
  Tools --> Artifacts
  Session --> Files[Analysis scripts and charts]
  SDK --> Runner[Configured target runner]
```

## Responsibilities

All Python paths below are relative to `src/agent_data_workbench/`. The package root contains only the public SDK exports and module CLI entrypoint.

| Package | Owns | Where to start |
| --- | --- | --- |
| `data/` | File discovery, run/record ingestion, source contracts and SQLAlchemy trace storage | `discovery.py`, `ingestion.py`, `sources.py`, `store.py` |
| `analysis/` | Batch findings, evidence validation, prompts, reports and analyzer benchmarks | `contracts.py`, `validation.py`, `batch.py` |
| `research/` | Human/native investigation snapshots, outcomes, sessions and MCP tools | `workspace.py`, `dataset.py`, `sessions.py` |
| `evaluation/` | Tasks, grading, suites, paired experiments, worlds, calibration and improvement decisions | `tasks/`, `suites.py`, `experiments.py` |
| `execution/` | Target contracts, persistent sessions, user simulators, environments and artifact capture | `contracts.py`, `sessions.py`, `environments.py`, `runners.py` |
| `exploration/` | Typed search, distributions, lexical clusters and evidence lineage | `schemas.py`, `search.py`, `clustering/`, `lineage.py` |
| `integrations/` | Native CLI analyzer adapters, Harbor and training exports | `analyzers.py`, `harbor.py`, `training.py` |
| `workspace/` | Project configuration, artifact directories, reviewed knowledge and locks | `project.py` |
| `shared/` | Domain-independent JSON/pointers/equality, UUIDs, persistence, Markdown and process helpers | `json.py`, `files.py`, `identifiers.py`, `processes.py` |
| `workbench/` | Application startup, listener/session lifecycle and background jobs | `runtime.py`, `server.py`, `jobs.py` |
| `api/`, `cli/` | Typed HTTP and command entrypoints calling domain operations | `api/application.py`, `api/routers/`, `cli/__init__.py` |

The React/TypeScript UI remains in `ui/`; the packaged browser assets remain in `web/`. Domain modules import shared infrastructure. Shared infrastructure does not import domain packages. Task contracts, persistence/review, grading, authoring and replay have separate modules inside `evaluation/tasks/`; moving a file should not mix these responsibilities again.

Public imports such as `from agent_data_workbench import Project, FilesSource, TraceStore` remain available. Code importing former internal flat modules must use the owning domain path. The CLI names, HTTP routes and persisted project format are unchanged by this reorganization.

The app factory composes domain routers. FastAPI dependencies supply the project, job queue, and bearer authentication; request middleware enforces host, origin, and body limits. `workbench/server.py` starts Uvicorn and owns the local session lifecycle.

The service layer translates requests into SDK operations. It does not contain a separate copy of task acceptance or research logic. FastAPI's interactive documentation routes are disabled; the session-protected `/api/openapi.json` describes the implemented API.

## Local state and consistency

`Project.create` requires a new or empty directory. It writes `project.json` and creates `knowledge/`, `investigations/`, `tasks/`, `suites/`, `experiments/`, `exports/`, `worlds/`, `improvements/`, `calibrations/`, `taxonomies/`, and `coverage/`. A project-local `.gitignore` excludes its contents. Use a directory under `runs/` for private working data.

`TraceStore` uses `traces.sqlite3`. SQLAlchemy maps the original six-column trace layout: ID, source group, stratum, canonical JSON, content hash, and import time. A session transaction wraps each operation; an import conflict rolls back its batch. The engine uses `NullPool`, and first-use schema creation is serialized inside the process. Worker threads obtain their own sessions.

Internal artifact IDs are canonical UUID strings validated with Python UUID/Pydantic types. Generated records use UUIDv4; content-derived identities use UUIDv5. Imported trace IDs remain unchanged. Suite names are friendly labels separate from their UUIDs. Project format 0.3 rejects older project formats before rewriting any files; create a new project and reimport the traces.

Structured artifacts are written through `shared.files.atomic_text`; Markdown escaping is shared through `shared.markdown.md`. Mutating workflows use a nonblocking POSIX project lock; a concurrent mutation returns a busy error. The HTTP job queue separately permits one background model job at a time. These mechanisms serve a local process-and-files workflow, not a distributed job system.

## Shared human and agent research workspace

Manual UI research creates a snapshot through the same SDK without invoking a native CLI or background model job. The browser can search and read that investigation snapshot, record typed outcomes, checkpoint notes, publish findings and create charts. It uses the same evidence and complete-pass rules as native research. Human creation does not introduce a different project format or a separate dataset owner.

The manual HTTP mutation routes acquire the same nonblocking session lock as native research. This prevents a stale browser tab from publishing final findings or changing outcomes underneath a running native session. The native session's own SDK and MCP tools remain available while it owns that lock. Pausing the native session returns manual write access; the UI keeps unsaved findings, note and chart forms mounted but hidden and disabled during active sessions.

`research/sessions.py` launches one native Codex or Claude Code session per invocation. The native agent owns planning, tools, code execution, context management, and session continuation. The workbench supplies `ResearchWorkspace`, exposed through Python, the CLI, and the official MCP SDK. It does not drive another model-call loop. Existing `Analyzer` integrations remain available for batch analysis, task design and semantic judging.

Each investigation captures all selected inputs into its own SQLAlchemy-backed `dataset.sqlite3`, alongside frozen context, workspace instructions, scripts and outputs. New imports or knowledge changes do not invalidate this snapshot. All imported records are included by default; excluding reserved final groups is explicit and exposure is recorded conservatively.

Research mode lets the agent explore adaptively. Complete mode requires a saved successful outcome for every record before final publication. Iterators read pages without limiting total coverage; processing checkpoints each outcome and resumes pending or failed records. Coverage records work performed through the SDK, not proof of semantic review or model quality. Native session IDs, attempt logs and journal entries preserve progress; process termination releases the separate session lock. Project locks are held for short artifact mutations, not throughout the native session.

## How evidence becomes an experiment

Import preserves source records. An [investigation](../workflows/investigations.md) researches them and cites exact evidence. [Tasks](../workflows/tasks-and-graders.md) separate target-visible input from grading criteria and require review after a grader audit. A suite freezes accepted task specifications and source-group assignments. [Experiments](../workflows/experiments-and-training.md) execute two target variants and preserve trial output, required artifacts, invalid runs, and regressions. Training export selects reviewed outcomes from optimization experiments.

These records provide provenance and detect accidental drift. They do not isolate a hostile target from host files or establish that a synthetic result generalizes to production.

## Extension seams

Implement `TraceSource.read()` to import another export format, `Analyzer.analyze(prompt, schema)` for another batch/judge backend, or `TargetRunner.identity()` and `run(visible_input, trial_dir, seed)` for another execution harness. Native research can also use the shared `ResearchWorkspace` directly from an existing coding-agent session or a custom `NativeSession` adapter. `EnvironmentRunner` supplies a setup/reset/readiness/observer/teardown lifecycle, while `ConversationRunner` owns one continuous command target session. Each reviewed task supplies its scenario; experiments record the effective runner identity. The optional Harbor adapter exports a supplied real template and invokes the installed Harbor CLI. Direct service connectors, distributed workbench execution, and training-job execution remain extension work. See [eval engineering](../workflows/eval-engineering.md).

Next: [import and explore traces](../workflows/traces.md), [run the local workbench](../operations/local-workbench.md), or [development](../development/contributing.md).

## Versioned improvement evidence

Accepted world lineage heads feed research context; a task can explicitly pin an older accepted world by UUID and digest. Independent state assertions read only observer-owned evidence, separately from target artifacts. Experiment records retain world/task snapshots, effective runner identities, chronological conversation evidence, and copied trial files.

Calibration freezes actual attempt evidence and records reviewer labels and adjudication. Behavioral coverage maps exact trace/task versions to reviewed capabilities and slices; it does not reuse research-completion counts as coverage. Improvement records capture source snapshots and a patch, require exact baseline/candidate identities when linked to experiments, and retain explicit keep/reject/inconclusive decisions with available calibration summaries. A decision does not apply or deploy code.

## Container process and storage ownership

The root Makefile drives Docker Compose. Development runs a FastAPI/Uvicorn backend and a separate TypeScript build watcher. The watcher writes a shared asset volume that FastAPI serves on the same browser origin; it does not expose a second UI server. Compose waits for the UI assets to be readable before starting the backend. The packaged app instead installs a wheel containing the production bundle and runs one Python service. See [Docker and Make workflow](../operations/containers.md).

The development image contains Python, Node and locked development dependencies. The runtime image uses the production Python environment. Both run as the workbench user. A named volume holds `/data/project` independently from source mounts and container lifetime. Python dependencies remain under `/opt/venv`; UI dependencies have their own named volume.

`workbench/runtime.py` creates an empty project once or opens the existing project, then starts Uvicorn. Development reload uses an import-string factory and inherits the same bearer token across child restarts. The externally visible origin is configured separately from the container bind address. Compose binds Python to `0.0.0.0` inside the container and publishes only the host loopback address. Native agent CLI processes still need installation and authentication in the environment hosting the backend.
