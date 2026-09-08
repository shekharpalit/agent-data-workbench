---
type: operations
title: Docker and Make workflow
description: Set up, develop, import data and run the packaged workbench with Docker while preserving local project data.
tags: [docker, make, development, operations, persistence]
sources:
  - id: openwiki-source-715dace563ef484b6e8bd1e2
    resource: repo://.dockerignore
  - id: openwiki-source-e201e686a785f09b6d899f0b
    resource: repo://compose.yaml
  - id: openwiki-source-bb1ebe868e35e9e500714501
    resource: repo://Dockerfile
  - id: openwiki-source-012f2c78e3b1446dfc35803f
    resource: repo://Makefile
  - id: openwiki-source-57d1f240e9d0552b9b058bdc
    resource: repo://src/agent_data_workbench/api/dependencies.py
  - id: openwiki-source-1848987f753961721cee2571
    resource: repo://src/agent_data_workbench/api/middleware.py
  - id: openwiki-source-2ee7fba2bd1c703c70f5f285
    resource: repo://src/agent_data_workbench/cli/project.py
  - id: openwiki-source-6e38bbd0a3d0f2e36a07885b
    resource: repo://src/agent_data_workbench/data/discovery.py
  - id: openwiki-source-a69866c703779e64969315b7
    resource: repo://src/agent_data_workbench/data/ingestion.py
  - id: openwiki-source-839952c20325a7e79d15333e
    resource: repo://src/agent_data_workbench/data/transport.py
  - id: openwiki-source-56b68af7c871c44d9ba4d64d
    resource: repo://src/agent_data_workbench/workbench/runtime.py
  - id: openwiki-source-a741d432f952c0dbfb4fb35d
    resource: repo://ui/vite.config.ts
generated: { by: "codex", at: "2026-09-08T00:07:39.310Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-08T00:07:39.310Z
---

# Docker and Make workflow

Install Docker with Compose v2 and Make. On Windows, run the repository commands in WSL2 with Docker integration enabled. Docker supplies Linux, Python and Node; host Python and Node installations are optional. Initial builds need network access to image and package registries.

## Set up and run

From the repository root:

```sh
make init
make dev
```

`make init` builds the development image from the locked dependencies, then creates `/data/project` in a named volume. Repeating it opens the same project and preserves traces and artifacts. An incompatible or unrelated nonempty project directory is rejected rather than overwritten. The workspace starts empty.

`make dev` builds and starts the UI watcher and FastAPI backend together. It stops the packaged app first so they do not compete for the published port. Open the private URL printed by the backend. Python source changes restart Uvicorn while retaining the current browser token. UI changes rebuild the assets; refresh the browser to see them. Ctrl-C stops both services.

The UI healthcheck verifies its index and referenced script/style files before Compose starts the backend. Development retains previous assets during rebuilds and polls source changes while excluding generated output and dependencies. FastAPI serves the resulting files and API on one origin.

## Import your traces

In another terminal:

```sh
make ingest DIR=./traces
```

`DIR` recursively selects JSON, JSONL and NDJSON files. Each file becomes one run by default, with original events preserved in order under `/events`. All imported runs can enter the same investigation. Use `FILE=./run.jsonl` for one file, and quote paths containing spaces. Existing exports containing one complete trace per line use `LAYOUT=records`:

```sh
make ingest DIR=./exports LAYOUT=records
```

The whole selection is one database transaction: an invalid event or conflicting trace ID rolls back every file in that batch. The result reports file count, layout, added/unchanged traces and the total stored population. See [trace import](../workflows/traces.md) for native multiple-path/glob commands, event evidence pointers and ID rules.

Logical source paths are relative to the supplied directory or a single file's parent. To reimport a subset using the same root as an earlier directory import:

```sh
make ingest FILE="./traces/nested/run 1.jsonl" SOURCE_ROOT=./traces
```

The native equivalent is `--source-root ./traces`. Keep this root and filenames stable across imports: they are recorded in run provenance and participate in generated identities. Changing a source name can create a different generated run or conflict with an existing native run ID.

Make stages a complete tar archive on the host, then streams it to the container. The importer materializes its regular files before starting the database transaction, preserving relative names and deduplicating internal hardlink aliases. Temporary host and container files are removed on completion or failure. Plan for temporary disk space for the archive and extracted inputs in addition to project storage; a run file's parsed events are held in memory one file at a time. There is no fixed file-count or event-count cap, and no browser upload endpoint is needed.

## Lifecycle commands

| Command | Result |
| --- | --- |
| `make up` | Stop development services, build the packaged image, start it in the background, wait for health, and print recent logs |
| `make down` | Remove this Compose project's containers and network while keeping its volumes |
| `make logs` | Follow logs, including the current private browser URL |
| `make test` | Build dependencies, run Python tests/Ruff, then UI tests, formatting and a TypeScript/production build |
| `make build` | Build development and packaged images |
| `make shell` | Open a development container with the project volume mounted |
| `make help` | Show supported commands |

Use `make dev PORT=9000` or `make up PORT=9000` to change the host port. The internal backend still listens on 8765. A full process restart creates a new private URL; use the newest one from logs. The default Compose project name is `agent-data-workbench`. Set `COMPOSE_PROJECT_NAME` consistently to maintain separate workspaces for separate checkouts.

## Data and dependencies

Both development and packaged services use the same `project-data` volume at `/data`, with the project under `/data/project`. Removing containers does not delete this volume. Preserve it when moving or backing up a workspace; it contains the SQLite trace store and derived artifacts. Deleting Docker volumes deletes the corresponding local data.

Development binds Python source and tests read-only, mounts UI source for editing, and keeps `node_modules` in `ui-dependencies`. Compiled assets live in `web-assets`. Python dependencies remain inside the image at `/opt/venv`. Run `make init` or restart `make dev` after changing Python dependencies; the UI service runs `npm ci` on startup to refresh its locked dependencies.

The Dockerfile pins Python 3.14.7, Node 24.20.0 and uv 0.12.10. It builds production assets in a Node stage and installs them in the runtime wheel. The development image includes test and UI tooling; the packaged runtime uses production Python dependencies. Both run as the non-root workbench user. The build context excludes private runs, Git metadata, provider login files and host dependency installations through an explicit allowlist.

## Runtime configuration and agent integrations

The Python entrypoint is `python -m agent_data_workbench.workbench.runtime`. It accepts `--initialize-only` and `--reload`. `WORKBENCH_PROJECT`, `WORKBENCH_HOST`, `WORKBENCH_PORT` and `WORKBENCH_ORIGIN` configure storage and serving. `WORKBENCH_NAME` and `WORKBENCH_OBJECTIVE` set metadata only when creating a new project. Custom runtime environment variables can be passed through a Compose override or a direct container invocation; the standard Compose file sets its own storage and network values.

The standard configuration binds the backend to `0.0.0.0` inside Docker and publishes only `127.0.0.1` on the host. The browser origin is independent of the bind address; healthchecks use its normalized host, and the existing bearer, Host and Origin checks apply. This configuration does not add TLS or a remote multiuser login system.

Agent investigations need an installed, authenticated Codex or Claude Code CLI in the same execution environment as the backend. The stock images do not install those CLIs or mount host credentials or the Docker socket. Manual research and deterministic local workflows work without them. To use an existing host CLI login, follow the native commands in the [quickstart](../quickstart.md). A Docker image for the workbench is separate from the optional Harbor environment and target-agent execution described in [eval engineering](../workflows/eval-engineering.md).
