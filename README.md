# Agent Data Workbench

A local CLI, SDK, and workbench for turning agent traces into reviewed tasks and improvement experiments.

Documentation lives in [OpenWiki](openwiki/index.md). Start with the [quickstart](openwiki/quickstart.md).

```sh
uv sync --locked
uv run agent-data-workbench workbench-demo runs/workbench
uv run agent-data-workbench ui runs/workbench --open-browser
```

Requires Python 3.14+ and uv. The bundled demo is synthetic and makes no provider calls.

To explore the documentation locally, install OpenWiki 0.5.0 with Node.js 22+ and run `openwiki visualize openwiki`. To regenerate it, open this repository in Codex and ask: “Update this repository’s OpenWiki from the current source and tests.” See [documentation maintenance](openwiki/operations/documentation.md).

Agent guidance: [AGENTS.md](AGENTS.md) · [CLAUDE.md](CLAUDE.md). MIT licensed; see [LICENSE](LICENSE).
