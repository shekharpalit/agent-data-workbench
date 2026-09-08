---
type: guide
title: Quickstart
description: Install Agent Data Workbench, import your own traces, and use the local UI to begin an evidence-based improvement workflow.
tags: [quickstart, traces, workflows, documentation]
sources:
  - id: openwiki-source-868b3402493aef58bb5db066
    resource: repo://.python-version
  - id: openwiki-source-e201e686a785f09b6d899f0b
    resource: repo://compose.yaml
  - id: openwiki-source-bb1ebe868e35e9e500714501
    resource: repo://Dockerfile
  - id: openwiki-source-012f2c78e3b1446dfc35803f
    resource: repo://Makefile
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
  - id: openwiki-source-a06d79006637fc11757f605b
    resource: repo://src/agent_data_workbench/__init__.py
  - id: openwiki-source-896da76531d8a33d2c9e76b8
    resource: repo://src/agent_data_workbench/api/application.py
  - id: openwiki-source-e6d7f541d0e16503af405c8b
    resource: repo://src/agent_data_workbench/api/routers/investigations.py
  - id: openwiki-source-732d0f8c004bbddbd6363fdf
    resource: repo://src/agent_data_workbench/api/routers/workflow.py
  - id: openwiki-source-2ee7fba2bd1c703c70f5f285
    resource: repo://src/agent_data_workbench/cli/project.py
  - id: openwiki-source-25b71218f03a1e216debf67e
    resource: repo://src/agent_data_workbench/cli/research.py
  - id: openwiki-source-758da06aa8f472c43add8d88
    resource: repo://src/agent_data_workbench/cli/workflow.py
  - id: openwiki-source-a69866c703779e64969315b7
    resource: repo://src/agent_data_workbench/data/ingestion.py
  - id: openwiki-source-2dbe8753da4267ce652f414e
    resource: repo://src/agent_data_workbench/research/workspace.py
  - id: openwiki-source-10d0a7c9280c304f0e5afe28
    resource: repo://src/agent_data_workbench/shared/environment.py
  - id: openwiki-source-56b68af7c871c44d9ba4d64d
    resource: repo://src/agent_data_workbench/workbench/runtime.py
  - id: openwiki-source-b9e04cc4343208a80c47ef02
    resource: repo://src/agent_data_workbench/workspace/project.py
  - id: openwiki-source-7e7b3478097a461915e85751
    resource: repo://tests/test_ingestion_research.py
  - id: openwiki-source-436f4179fe22abf615d2f7d0
    resource: repo://ui/package.json
  - id: openwiki-source-2d1b137901c9e38ec418fdad
    resource: repo://ui/src/views/ManualResearchEditor.tsx
  - id: openwiki-source-a6ff0ad9c45aedc12177eaec
    resource: repo://ui/src/views/ResearchControls.tsx
  - id: openwiki-source-a741d432f952c0dbfb4fb35d
    resource: repo://ui/vite.config.ts
generated: { by: "codex", at: "2026-09-08T00:58:07.648Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-08T00:58:07.648Z
---

# Quickstart

Agent Data Workbench turns exported agent traces into investigated findings, reviewed tasks, executed comparisons, and curated training records. It combines a Python SDK and CLI with a local React/TypeScript workbench, served by FastAPI and backed by SQLAlchemy.

This OpenWiki is the documentation entry point. Source code and tests remain authoritative.

## Start with Docker and Make

From a repository checkout, install Docker with Compose v2 and Make, then run:

```sh
make init
make dev
```

Docker installs the locked Python and TypeScript dependencies and initializes an empty project in a persistent named volume. Open the complete private URL printed by the backend. Ctrl-C stops the backend and UI watcher together. Repeating `make init` preserves existing project data.

Import your own export from another terminal:

```sh
make ingest DIR=./traces
```

The directory is scanned recursively. Each JSONL file becomes one agent trace with its events preserved in order, and a new investigation can compare all imported runs together. Refresh the UI after import. For exports containing one complete trace per line, use `make ingest DIR=./exports LAYOUT=records`. `make up` runs the packaged app in the background; `make down` stops containers while keeping their data. Change the host port with `make dev PORT=9000`. On Windows, use WSL2 with Docker integration. See [Docker and Make workflow](operations/containers.md) for volumes, checks, rebuilding and configuration.

Manual research works in the stock container. Native agent investigations additionally need the selected Codex or Claude Code CLI installed and authenticated in the backend's environment. To use an existing host CLI login, follow the native setup below.

## Native setup and agent CLI authentication

Use Python 3.14+, uv and a supported Node version such as Node 24.15+. The repository pins Python 3.14.7 and locks its dependencies. Build the TypeScript UI before installing the editable checkout:

```sh
git clone git@github.com:shekharpalit/agent-data-workbench.git
cd agent-data-workbench
npm ci --prefix ui
npm --prefix ui run build
uv sync --locked
```

The GitHub repository currently requires access because it is private. Frontend source lives in `ui/`; its generated `ui/dist/` output is ignored by Git. Installed wheels include those compiled assets and need no Node runtime. Source checkouts require the build step above, while Docker performs it automatically. See [development and verification](development/contributing.md) for rebuilding and packaging.

## Bring your own agent data

Create a new project with a concrete objective, import your export, and open the UI:

```sh
uv run agent-data-workbench init runs/my-agent "My agent" \
  "Improve reliable task completion"
uv run agent-data-workbench ingest runs/my-agent ./traces
uv run agent-data-workbench query runs/my-agent --limit 20
uv run agent-data-workbench ui runs/my-agent
```

The project starts empty. You can also pass several files (`ingest runs/my-agent ./run-a.jsonl ./run-b.jsonl`) or a quoted glob. Use `--layout records` for the older record-per-line export format. Use `--source-root` when changing file selections within one collection; [trace import](workflows/traces.md) explains stable identities and `/events/N` evidence pointers. An invalid file rolls back the entire selected batch. The runtime contains no demo commands, fake agent, or canned corpus. JSON/JSONL records come from your own exports; see [trace import](workflows/traces.md) for the record format. Synthetic fixtures remain confined to tests.

The UI starts on `127.0.0.1:8765` with a per-session access token; add `--port 9000` to use another port. Open the printed URL after Uvicorn reports startup. Ctrl-C initiates graceful shutdown, which waits for active response background jobs; pause long native research first if it should resume later. Search traces and field distributions first; investigations, tasks, and experiments appear as you create them. Read [local operation](operations/local-workbench.md) for details.

Project format 0.3 uses UUIDs for internal artifacts and keeps external trace IDs unchanged. Older project formats are rejected without rewriting their files. Create a new project directory and reimport the original traces; prior derived artifacts remain in the old directory. Suite names are friendly labels, and execution uses the suite UUID returned at creation.

Import the corpus needed for your question; native research makes the full snapshot available. Preserve source groups such as conversation IDs so related tasks stay together in later splits. Add reviewed policies and tool contracts before asking an analyzer to judge behavior that depends on them.

## Research without a model

In the local UI, open **Investigations → Research myself**, enter your question, choose a mode and click **Start manual research**. This opens a captured dataset without a Codex/Claude process or a provider account.

Search records in **Research dataset**, inspect original fields, save your observations as record outcomes, and add journal notes. **Write findings** lets you connect conclusions to exact trace/pointer/quote evidence. Save a draft while working and publish final findings when ready. You can also create bar charts from label/value rows. Complete mode requires successful outcomes for every input; exploratory research can finish with partial coverage.

A saved investigation can later use **Bring in an agent** on the same snapshot, or you can continue manually. Save drafts before leaving the view or refreshing. [The research guide](workflows/investigations.md) covers evidence, coverage and handoff details.

## Run native research

Use an installed, authenticated Codex or Claude Code CLI. Ingestion and local exploration need no model. To start a persistent native investigation:

```sh
uv run agent-data-workbench investigate runs/my-agent --backend codex \
  --question "Which recurring failures should we improve?"
```

Use `--backend claude` for Claude Code. Add `--mode complete` to require an outcome for every input; the default `research` mode explores adaptively. The agent can query the snapshot, run analysis scripts and publish findings, charts, reports and draft tasks. No default model-call count or total trace limit is imposed by native research. Provider context and account limits still apply.

If interrupted, resume using the printed investigation UUID:

```sh
uv run agent-data-workbench investigate runs/my-agent --resume INVESTIGATION_ID
```

To use your current coding-agent session instead of launching another process, run `research create runs/my-agent "Your question"`. It prints a workspace and MCP command without making a provider call. [The research guide](workflows/investigations.md) explains tools, progress, complete processing and publication.

Project format 0.3 remains compatible. Native investigations use protocol 0.4; old completed investigations are readable, while paused legacy investigations need a new native investigation.

## Complete the improvement loop

Product version 0.1.0 includes reviewed world specifications, reproducible environment commands, continuous target sessions, human grader calibration, behavioral coverage and candidate decisions. The product, SDK, API and UI all report 0.1.0. Project format 0.3 and native research protocol 0.4 are independent saved-data contracts and remain unchanged.

Start with one important failure: capture its evidence, review the relevant domain rules, and author an audited task. Configure your real target and the environment observer; run a baseline/candidate pair on a reserved execution split. In the UI, use **Grader calibration** to label the actual attempts, **Behavioral coverage** to inspect missing cases, and **Improvements** to capture and decide on an exact source change. Human decisions retain evidence without applying or deploying code.

[Eval engineering](workflows/eval-engineering.md) specifies the runtime protocols and CLI commands. Optional Harbor export uses your real environment/verifier template. The full loop is verified with synthetic local processes; a production performance claim still needs your real agent and fresh cases.

## Choose the next workflow

| Goal | Read |
| --- | --- |
| Map exports, preserve IDs, or implement an importer | [Import and explore traces](workflows/traces.md) |
| Research manually or with an agent and add project knowledge | [Investigations and reviewed knowledge](workflows/investigations.md) |
| Turn findings or chat prefixes into reviewed evaluations | [Tasks and grader review](workflows/tasks-and-graders.md) |
| Define worlds, continuous conversations, independent state, human calibration, coverage or Harbor tasks | [Eval engineering](workflows/eval-engineering.md) |
| Execute a baseline/candidate comparison or export training records | [Experiments and training exports](workflows/experiments-and-training.md) |
| Analyze a small batch or grade output files already produced | [Batch analysis and evaluation](workflows/batch-evaluation.md) |
| Set up containers, import host files, or manage persistent data | [Docker and Make workflow](operations/containers.md) |
| Run or troubleshoot the local trace workbench | [Local workbench](operations/local-workbench.md) |
| Find the owning domain package, shared helpers, or SDK/server boundary | [System architecture](architecture/system.md) |
| Change code and run the relevant checks | [Development and verification](development/contributing.md) |
| Refresh this documentation through Codex or Claude | [Maintain the OpenWiki](operations/documentation.md) |

The Python implementation is grouped by responsibility, with shared infrastructure in `shared/` and a root SDK facade for public imports. Start at the [package ownership map](architecture/system.md#responsibilities) when changing ingestion, analysis, evaluation, execution or exploration.

For implementation conventions, read the root [AGENTS.md](../AGENTS.md). [CLAUDE.md](../CLAUDE.md) points to the same project guidance.

## Browse the documentation graph

With Node.js 22+ and npm available:

```sh
npm install --global openwiki@0.5.0
openwiki visualize openwiki
```

This opens the OpenWiki documentation reader and graph. It is separate from the agent trace workbench. The repository carries the Codex and Claude OpenWiki integration configuration and skills; [the maintenance page](operations/documentation.md) explains discovery, generation, and updates.
