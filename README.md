# Agent Data Workbench

A local CLI, SDK, and workbench for turning agent traces into reviewed tasks and improvement experiments.

Documentation lives in [OpenWiki](openwiki/index.md). Start with the [quickstart](openwiki/quickstart.md).

```sh
make init
make dev
```

Requires Docker with Compose v2 and Make (use WSL2 on Windows). Open the private URL printed by the backend. `make dev` runs FastAPI with Python reload and the TypeScript UI build watcher; refresh the browser after a UI rebuild. Project data persists in a Docker volume. Use `make down` to stop, `make up` for the packaged app in the background, and `make help` for checks and other commands. Set another port with `make dev PORT=9000`.

Import a folder of agent runs with `make ingest DIR=./traces`. Each JSONL file becomes one trace with its events preserved in order; all runs can be researched together. `FILE=./run.jsonl` imports one run. For exports with one complete trace per line, use `LAYOUT=records`. Choose **Research myself → Start manual research** to inspect data, record outcomes, save notes, and publish findings and charts. Containers include the workbench; agent investigations additionally need an installed, authenticated Codex or Claude Code CLI in the environment running the backend.

For native development and existing local agent CLI authentication, use Python 3.14+ and uv:

```sh
uv sync --locked
uv run agent-data-workbench init runs/workbench "My agent" "Improve task completion"
uv run agent-data-workbench ingest runs/workbench ./traces
uv run agent-data-workbench investigate runs/workbench --backend codex --question "What should improve?"
uv run agent-data-workbench ui runs/workbench --open-browser
```

Agent sessions use their native account limits. `--mode complete` requires an outcome for every input; `--resume <investigation UUID>` continues saved work. Local exploration and `research create` make no provider calls.

To explore the documentation locally, install OpenWiki 0.5.0 with Node.js 22+ and run `openwiki visualize openwiki`. To regenerate it, open this repository in Codex and ask: “Update this repository’s OpenWiki from the current source and tests.” See [documentation maintenance](openwiki/operations/documentation.md).

Agent guidance: [AGENTS.md](AGENTS.md) · [CLAUDE.md](CLAUDE.md). MIT licensed; see [LICENSE](LICENSE).
