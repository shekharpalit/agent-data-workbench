---
type: guide
title: Quickstart
description: Install Agent Data Workbench, run its synthetic end-to-end example, and find the right workflow for your own agent traces and improvement experiments.
tags: [quickstart, demo, workflows, documentation]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T17:18:36.762Z
sources:
  - id: openwiki-source-868b3402493aef58bb5db066
    resource: repo://.python-version
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-457345d957e5f357847df6bd
    resource: repo://src/agent_data_workbench/commands.py
  - id: openwiki-source-1bb80de56d07cfb0dc0536b5
    resource: repo://src/agent_data_workbench/demo.py
  - id: openwiki-source-013c413ca45af5e0569b46e0
    resource: repo://src/agent_data_workbench/server.py
  - id: openwiki-source-af0e5443d83442c11181e6ce
    resource: repo://tests/test_workbench_execution.py
generated: { by: "codex", at: "2026-09-07T17:18:36.762Z" }
---

# Quickstart

Agent Data Workbench turns exported agent traces into investigated findings, reviewed tasks, executed comparisons, and curated training records. It combines a Python SDK and CLI with a local React/TypeScript workbench, served by FastAPI and backed by SQLAlchemy.

This OpenWiki is the documentation entry point. Source code and tests remain authoritative.

## Install from the repository

Use Python 3.14+ and uv. The repository pins Python 3.14.7 and locks its dependency resolution:

```sh
git clone git@github.com:shekharpalit/agent-data-workbench.git
cd agent-data-workbench
uv sync --locked
```

The GitHub repository currently requires access because it is private. The built UI is included in the Python package, so running the workbench does not require a Node build. UI development does; see [development and verification](development/contributing.md).

## Run the synthetic example

From the checkout:

```sh
uv run agent-data-workbench workbench-demo runs/workbench
uv run agent-data-workbench ui runs/workbench --open-browser
```

Use a new directory for the demo. If `runs/workbench` already contains a project, open it with the second command or choose another directory for a fresh demo.

The demo creates 18 synthetic traces and tasks, a scripted investigation, a grouped suite, and optimization/validation experiments with two repeats. It actually runs two deterministic Python target variants, performs zero provider calls, and leaves the final split unused. This demonstrates the workflow and recorded evidence; it is not evidence that an AI model improved.

The UI starts on loopback using an available port and a per-session access token. Follow the URL printed by the command. Stop the server with Ctrl-C when finished.

Explore the trace search, field distributions, lexical clusters, and lineage graph, then inspect the investigation, task audits, and experiment results. Read [local workbench operation](operations/local-workbench.md) for request contracts and limitations.

## Bring your own agent data

Create a separate project with a concrete objective, then import your export:

```sh
uv run agent-data-workbench init runs/my-agent "My agent" \
  "Improve reliable task completion"
uv run agent-data-workbench ingest runs/my-agent ./traces.jsonl
uv run agent-data-workbench query runs/my-agent --limit 20
```

Start with the smallest corpus that can answer a useful question. Preserve source groups such as conversation IDs so related tasks stay together in later splits. Add reviewed policies and tool contracts before asking an analyzer to judge behavior that depends on them.

Model-directed investigation uses an installed, authenticated Codex or Claude CLI. It is optional for ingestion and local exploration. Provider access and account limits still apply when you choose to run it.

## Choose the next workflow

| Goal | Read |
| --- | --- |
| Map exports, preserve IDs, or implement an importer | [Import and explore traces](workflows/traces.md) |
| Add project knowledge and investigate evidence | [Investigations and reviewed knowledge](workflows/investigations.md) |
| Turn findings or chat prefixes into reviewed evaluations | [Tasks and grader review](workflows/tasks-and-graders.md) |
| Execute a baseline/candidate comparison or export training records | [Experiments and training exports](workflows/experiments-and-training.md) |
| Analyze a small batch or grade output files already produced | [Batch analysis and evaluation](workflows/batch-evaluation.md) |
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
