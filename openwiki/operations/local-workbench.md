---
type: operations
title: Run the local workbench
description: Start the bundled React UI, understand its local FastAPI session, and choose the correct interface for trace exploration, reviews, and execution.
tags: [ui, fastapi, local, operations]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T17:18:36.762Z
sources:
  - id: openwiki-source-bf36d615b629a6a49d40e06d
    resource: repo://src/agent_data_workbench/api.py
  - id: openwiki-source-12d025c9e4830dcc4dd30757
    resource: repo://src/agent_data_workbench/jobs.py
  - id: openwiki-source-0ec248246e792c935c3b8719
    resource: repo://src/agent_data_workbench/local_http.py
  - id: openwiki-source-013c413ca45af5e0569b46e0
    resource: repo://src/agent_data_workbench/server.py
  - id: openwiki-source-6d94b2e299387b69a79c432d
    resource: repo://ui/src/App.tsx
generated: { by: "codex", at: "2026-09-07T17:18:36.762Z" }
---

# Run the local workbench

```sh
uv run agent-data-workbench ui runs/workbench --open-browser
```

The CLI starts Uvicorn and binds a socket on `127.0.0.1`. The default port is selected dynamically; `--port` requests a particular one. It prints the complete session URL and opens the browser only after Uvicorn reports that it can serve requests. Ctrl-C stops the service.

## Local session and API

Each server instance creates a fresh random access token. The printed URL puts it in the fragment; the frontend obtains the token and sends it as an Authorization bearer header for API requests. Use the complete printed URL again after a restart or an unauthorized response.

The middleware checks the exact Host header, requires same-origin POST requests, and authenticates `/api/` paths. POST bodies must be JSON and are bounded to 2,000,000 bytes, including received chunks when Content-Length is absent. Responses use no-store caching, no-referrer, nosniff, and a content security policy. These are local browser boundaries; the app is not a hosted multiuser service.

The Python package includes the UI entry point and hashed assets. FastAPI serves those files and typed SDK operations from the same origin. No separate Node server is needed for normal use. `/api/openapi.json` is available with the same session authorization; the default Swagger and ReDoc pages are disabled. Invalid structured requests return HTTP 400 with an `error` field and do not echo the input values.

## What each view does

| View | Use it for |
| --- | --- |
| Overview | Corpus counts, task review state, recent experiments, and synthetic-demo labeling |
| Trace explorer | Combined filters, numeric ranges, sorting, pagination, distribution, and record inspection |
| Clusters | Bounded lexical grouping of the matching traces and membership drill-down |
| Evidence graph | Recorded trace, finding, task, and experiment relationships |
| Investigations | Start or resume bounded analysis, then inspect steps and evidence |
| Project knowledge | Add and review explicit policy or tool context |
| Tasks & graders | Inspect/edit specifications, run deterministic audits, and record reviews |
| Experiments | Inspect baseline/candidate summaries, per-trial results, and artifacts |

The graph bundle loads on demand. Trace filters and cluster membership are shared through application query state; changing filters resets pagination. See [trace exploration](../workflows/traces.md) for query semantics and limits.

## Model jobs and execution

Investigation and task-design requests enter a background queue so the HTTP request can return while analysis continues. Only one job may be running at a time. The queue reserves capacity before starting an investigation, so a rejected concurrent request does not leave an orphan investigation artifact. Job status is process-local; durable domain artifacts hold completed work.

Task audits in the UI are deterministic. A semantic rubric needs an explicitly configured judge through the [task CLI](../workflows/tasks-and-graders.md). Suite creation, baseline/candidate execution, and training export use the [experiment CLI or SDK](../workflows/experiments-and-training.md); the experiments view inspects the resulting artifacts.

Import trace files with the CLI before opening the UI. There is no browser upload endpoint. Exploration and inspection are local operations; starting an analysis is an explicit provider action and sends selected context through the configured analyzer.

## Troubleshooting and development

A busy-project error means a mutating workflow holds the project lock. Wait for it to finish and retry. Failed jobs show a bounded error; inspect the saved artifact and explicitly resume or start the relevant CLI operation. Do not interpret an interrupted execution as a completed comparison.

For UI changes, [rebuild the TypeScript bundle](../development/contributing.md), then refresh the browser. OpenWiki's `visualize` command is a separate documentation reader, described in [documentation maintenance](documentation.md).
