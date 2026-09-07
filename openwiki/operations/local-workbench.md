---
type: operations
title: Run the local workbench
description: Start the bundled React UI, understand its local FastAPI session, and choose the correct interface for trace exploration, reviews, and execution.
tags: [ui, fastapi, local, operations]
sources:
  - id: openwiki-source-896da76531d8a33d2c9e76b8
    resource: repo://src/agent_data_workbench/api/application.py
  - id: openwiki-source-57d1f240e9d0552b9b058bdc
    resource: repo://src/agent_data_workbench/api/dependencies.py
  - id: openwiki-source-d4898276f02a9fa6cae75c52
    resource: repo://src/agent_data_workbench/api/errors.py
  - id: openwiki-source-1848987f753961721cee2571
    resource: repo://src/agent_data_workbench/api/middleware.py
  - id: openwiki-source-e6d7f541d0e16503af405c8b
    resource: repo://src/agent_data_workbench/api/routers/investigations.py
  - id: openwiki-source-98bfc373ed8e75b28dcf239e
    resource: repo://src/agent_data_workbench/api/routers/tasks.py
  - id: openwiki-source-732d0f8c004bbddbd6363fdf
    resource: repo://src/agent_data_workbench/api/routers/workflow.py
  - id: openwiki-source-4105c547b3781d406b01e383
    resource: repo://src/agent_data_workbench/api/schemas.py
  - id: openwiki-source-12d025c9e4830dcc4dd30757
    resource: repo://src/agent_data_workbench/jobs.py
  - id: openwiki-source-013c413ca45af5e0569b46e0
    resource: repo://src/agent_data_workbench/server.py
  - id: openwiki-source-9c58a0b0672b6bdbd523d5ee
    resource: repo://tests/test_identifiers.py
  - id: openwiki-source-6d94b2e299387b69a79c432d
    resource: repo://ui/src/App.tsx
  - id: openwiki-source-5bdf087920ed404535bafa26
    resource: repo://ui/src/views/Calibration.tsx
  - id: openwiki-source-2d1b137901c9e38ec418fdad
    resource: repo://ui/src/views/ManualResearchEditor.tsx
  - id: openwiki-source-a6ff0ad9c45aedc12177eaec
    resource: repo://ui/src/views/ResearchControls.tsx
  - id: openwiki-source-e1d27805221c9fa6fa8b7e3a
    resource: repo://ui/src/views/ResearchOutputs.tsx
  - id: openwiki-source-14a72935f36008706a0aa989
    resource: repo://ui/src/views/ResearchSnapshot.tsx
  - id: openwiki-source-826d1e88c728d7cfae868e97
    resource: repo://ui/tests/workflow.test.tsx
generated: { by: "codex", at: "2026-09-07T22:32:10.726Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T22:32:10.726Z
---

# Run the local workbench

```sh
uv run agent-data-workbench ui runs/workbench --open-browser
```

The CLI starts Uvicorn and binds a socket on `127.0.0.1`. The default port is selected dynamically; `--port` requests a particular one. It prints the complete session URL and opens the browser only after Uvicorn reports that it can serve requests. Ctrl-C stops the service.

## Local session and API

Each server instance creates a fresh random access token. The printed URL puts it in the fragment; the frontend obtains the token and sends it as an Authorization bearer header for API requests. Use the complete printed URL again after a restart or an unauthorized response.

`api/middleware.py` checks the exact Host header and requires same-origin POST requests. API operations authenticate through FastAPI’s `HTTPBearer` dependency in `api/dependencies.py`. POST bodies must be JSON and are bounded to 2,000,000 bytes, including received chunks when Content-Length is absent. Responses use no-store caching, no-referrer, nosniff, and a content security policy. These are local browser boundaries; the app is not a hosted multiuser service.

The Python package includes the UI entry point and hashed assets. FastAPI serves those files and typed SDK operations from the same origin. No separate Node server is needed for normal use. `/api/openapi.json` is available with the same session authorization; the default Swagger and ReDoc pages are disabled. Invalid structured requests return HTTP 400 with an `error` field and do not echo the input values. Internal artifact request IDs use the `uuid` format in OpenAPI; imported trace identifiers remain opaque strings. Domain routers under `api/routers/` keep trace, knowledge, task, investigation, and job operations separate.

## What each view does

| View | Use it for |
| --- | --- |
| Overview | Corpus counts, task review state, recent experiments, and project objectives |
| Trace explorer | Combined filters, numeric ranges, sorting, pagination, distribution, and record inspection |
| Clusters | Bounded lexical grouping of the matching traces and membership drill-down |
| Evidence graph | Recorded trace, finding, task, and experiment relationships |
| Investigations | Research manually or with an agent, inspect snapshot evidence, record outcomes, publish findings/charts, and pause/resume native sessions |
| Project knowledge | Add and review explicit policy or tool context |
| Tasks & graders | Inspect/edit specifications, run deterministic audits, and record reviews |
| Experiments | Inspect paired results, continuous transcripts, lifecycle phases and independent state |
| World specifications | Create/review reusable world versions and inspect pinned contracts |
| Grader calibration | Label actual attempts, classify causes, compare judgments and adjudicate |
| Behavioral coverage | Review capability versions, map traces/tasks, and inspect gaps/duplicates |
| Improvements | Capture exact candidates, launch paired runs, and record decisions |

The graph bundle loads on demand. Trace filters and cluster membership are shared through application query state; changing filters resets pagination. See [trace exploration](../workflows/traces.md) for query semantics and limits.

## Research manually

Open Investigations, leave **Research myself** selected, enter a question, choose research or complete mode, and click **Start manual research**. The request captures the dataset and opens its workspace without starting a native CLI or a model job. No provider account is required. Final evaluation inputs are included unless you select their explicit exclusion.

Use **Research dataset** to search the frozen snapshot by text or stratum, optionally narrowing to unfinished records. Select a record to inspect its original JSON, read a field by JSON pointer, and page through long content. Record a human observation or structured JSON object with a method; select failed when missing context prevents review. Notes go into the journal. **Write findings** opens summary, finding and exact citation fields; **Save findings draft** preserves unfinished research and **Publish final findings** completes it. **Create a chart** accepts labels and numeric values for a local bar chart. Citation links reopen the original snapshot field.

Draft editing retains existing cases, signals, proposals, limitations and open questions. Edits survive polling. Saved drafts survive reopening the investigation; unsaved form values remain local to the mounted view, so save before navigating away or refreshing the browser.

**Bring in an agent** explicitly starts native research on this same investigation; a saved session offers **Continue with an agent**. While a native session is active, human mutation controls are hidden/disabled and their current form values remain mounted for return after pause. The manual write endpoints also acquire the native session lock so a stale browser request cannot publish underneath the agent. Completed investigations expose their results without manual editing controls.

## Model jobs and execution

Native investigation and task-design requests enter a background queue so the HTTP request can return while analysis continues. Only one job may be running at a time. The queue reserves capacity before starting an investigation, so a rejected concurrent request does not leave an orphan investigation artifact. Job status is process-local; durable domain artifacts hold completed work.

Selecting **Use an agent** exposes a native backend and either adaptive `research` or per-record `complete` mode. Final evaluation inputs are included unless the developer selects their explicit exclusion. There is no maximum-call input. A saved session resumes with its original backend and model settings; partial findings remain visible while work is unfinished. A live session exposes Pause, and a released session lock allows recovery after a process crash.

Both research paths share the detail view, which shows successful, failed and pending record counts separately from SDK retrieval. It polls active progress, paginates record outcomes and journal entries, and displays each recorded analysis method. Registered chart JSON renders as bars; other files are downloads authenticated with the local bearer token and checked against their recorded digest. Generated HTML is downloaded as a file rather than embedded in the workbench.

Task audits in the UI are deterministic. A semantic rubric needs an explicitly configured judge through the [task CLI](../workflows/tasks-and-graders.md). Suite creation and training export use the [experiment CLI or SDK](../workflows/experiments-and-training.md). The Improvements view can launch paired comparisons from an existing suite and local runner configuration paths; it offers an explicit semantic judge when needed.

Import trace files with the CLI before opening the UI. There is no browser upload endpoint. Exploration and inspection are local operations; starting native research is an explicit provider action that gives the chosen coding agent access to the investigation snapshot and context. Native account and model constraints still apply.

## Troubleshooting and development

A busy-project error means a mutating workflow holds the project lock. Retry after that short mutation finishes; a native investigation does not hold the project lock for its whole session. Failed jobs show a bounded error; inspect the saved artifact and explicitly resume or start the relevant CLI operation. Do not interpret an interrupted execution as a completed comparison.

For UI changes, [rebuild the TypeScript bundle](../development/contributing.md), then refresh the browser. OpenWiki's `visualize` command is a separate documentation reader, described in [documentation maintenance](documentation.md).

## Human eval engineering

Start with **World specifications** to capture sourced domain rules, schemas, tool contracts and permissions. Save a draft, resolve outstanding questions in a new immutable version, and record reviewer and reason for acceptance. Task specification JSON can pin that world and define environment commands, state criteria and conversation turns. Accepted task detail offers **Harbor export** with an existing local template directory and target configuration.

In **Grader calibration**, choose a recorded experiment and create a calibration. Review the frozen requirements, chronological turns and observed state. Grader verdicts are hidden before a first assessment until explicitly revealed. Save pass/fail/invalid, a reason and optional cause; adjudication is bound to the exact displayed human label set. Reviewer identity is locally declared, not account authentication.

In **Behavioral coverage**, create and accept a capability taxonomy, then map trace IDs or exact task versions with source and rationale. Inspect missing accepted slices, unexecuted versions, duplicates and stale mappings. Research completion and production prevalence are separate measures.

In **Improvements**, supply baseline and candidate RunnerConfig file paths, the hypothesis and expected behavior. Inspect the captured patch, run the linked suite, review results/calibration, and record keep/reject/inconclusive. The decision records evidence and does not apply or deploy source changes. `/api/workflow` and its typed domain endpoints expose the same SDK operations. [Eval engineering](../workflows/eval-engineering.md) contains the runtime and file contracts.
