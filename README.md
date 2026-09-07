# Agent Data Workbench

A local CLI, SDK, and workbench for turning agent traces into reviewed tasks and improvement experiments.

Documentation lives in [OpenWiki](openwiki/index.md). Start with the [quickstart](openwiki/quickstart.md).

```sh
uv sync --locked
uv run agent-data-workbench init runs/workbench "My agent" "Improve task completion"
uv run agent-data-workbench ingest runs/workbench ./traces.jsonl
uv run agent-data-workbench investigate runs/workbench --backend codex --question "What should improve?"
uv run agent-data-workbench ui runs/workbench --open-browser
```

Requires Python 3.14+ and uv. Import your own trace export. Investigations use an installed, authenticated Codex or Claude Code CLI with its native session and account limits. Use `--mode complete` to require an outcome for every input; `--resume <investigation UUID>` continues saved work. Local exploration and `research create` make no provider calls.

To explore the documentation locally, install OpenWiki 0.5.0 with Node.js 22+ and run `openwiki visualize openwiki`. To regenerate it, open this repository in Codex and ask: “Update this repository’s OpenWiki from the current source and tests.” See [documentation maintenance](openwiki/operations/documentation.md).

Agent guidance: [AGENTS.md](AGENTS.md) · [CLAUDE.md](CLAUDE.md). MIT licensed; see [LICENSE](LICENSE).
