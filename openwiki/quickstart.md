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
  - id: openwiki-source-73ad8573b871e625469a2194
    resource: repo://src/agent_data_workbench/ingestion.py
  - id: openwiki-source-b5025a250cbf9f845fc9224a
    resource: repo://src/agent_data_workbench/project.py
  - id: openwiki-source-2dbe8753da4267ce652f414e
    resource: repo://src/agent_data_workbench/research/workspace.py
  - id: openwiki-source-cda43c2246a0f3e6a5e89dce
    resource: repo://src/agent_data_workbench/runtime.py
  - id: openwiki-source-013c413ca45af5e0569b46e0
    resource: repo://src/agent_data_workbench/server.py
  - id: openwiki-source-9c58a0b0672b6bdbd523d5ee
    resource: repo://tests/test_identifiers.py
  - id: openwiki-source-7e7b3478097a461915e85751
    resource: repo://tests/test_ingestion_research.py
  - id: openwiki-source-2d1b137901c9e38ec418fdad
    resource: repo://ui/src/views/ManualResearchEditor.tsx
  - id: openwiki-source-a6ff0ad9c45aedc12177eaec
    resource: repo://ui/src/views/ResearchControls.tsx
generated: { by: "codex", at: "2026-09-07T23:37:40.020Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T23:37:40.020Z
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

Use Python 3.14+ and uv. The repository pins Python 3.14.7 and locks its dependency resolution:

```sh
git clone git@github.com:shekharpalit/agent-data-workbench.git
cd agent-data-workbench
uv sync --locked
```

The GitHub repository currently requires access because it is private. The built UI is included in the Python package, so running the workbench does not require a Node build. UI development does; see [development and verification](development/contributing.md).

## Bring your own agent data

Create a new project with a concrete objective, import your export, and open the UI:

```sh
uv run agent-data-workbench init runs/my-agent "My agent" \
  "Improve reliable task completion"
uv run agent-data-workbench ingest runs/my-agent ./traces
uv run agent-data-workbench query runs/my-agent --limit 20
uv run agent-data-workbench ui runs/my-agent --open-browser
```

The project starts empty. You can also pass several files (`ingest runs/my-agent ./run-a.jsonl ./run-b.jsonl`) or a quoted glob. Use `--layout records` for the older record-per-line export format. Use `--source-root` when changing file selections within one collection; [trace import](workflows/traces.md) explains stable identities and `/events/N` evidence pointers. An invalid file rolls back the entire selected batch. The runtime contains no demo commands, fake agent, or canned corpus. JSON/JSONL records come from your own exports; see [trace import](workflows/traces.md) for the record format. Synthetic fixtures remain confined to tests.

The UI starts on loopback using an available port and a per-session access token. Follow the printed URL and stop the server with Ctrl-C when finished. Search traces and field distributions first; investigations, tasks, and experiments appear as you create them. Read [local operation](operations/local-workbench.md) for details.

Version 0.3 uses UUIDs for internal artifacts and keeps external trace IDs unchanged. Older project formats are rejected without rewriting their files. Create a new project directory and reimport the original traces; prior derived artifacts remain in the old directory. Suite names are friendly labels, and execution uses the suite UUID returned at creation.

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

Version 0.3 projects remain compatible. Native investigations use protocol 0.4; old completed investigations are readable, while paused legacy investigations need a new native investigation.

## Complete the improvement loop

Version 0.5 adds reviewed world specifications, reproducible environment commands, continuous target sessions, human grader calibration, behavioral coverage and candidate decisions. Project format 0.3 and native research protocol 0.4 remain compatible.

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
| Understand the SDK, storage, CLI, and server boundaries | [System architecture](architecture/system.md) |
| Change code and run the relevant checks | [Development and verification](development/contributing.md) |
| Refresh this documentation through Codex or Claude | [Maintain the OpenWiki](operations/documentation.md) |

For implementation conventions, read the root [AGENTS.md](../AGENTS.md). [CLAUDE.md](../CLAUDE.md) points to the same project guidance.

## Browse the documentation graph

With Node.js 22+ and npm available:

```sh
npm install --global openwiki@0.5.0
openwiki visualize openwiki
```

This opens the OpenWiki documentation reader and graph. It is separate from the agent trace workbench. The repository carries the Codex and Claude OpenWiki integration configuration and skills; [the maintenance page](operations/documentation.md) explains discovery, generation, and updates.
