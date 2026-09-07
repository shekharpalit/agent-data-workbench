---
type: operations
title: Maintain the OpenWiki
description: Generate and update repository documentation through the installed Codex or Claude OpenWiki integration, then browse the result locally.
tags: [openwiki, codex, claude, documentation]
sources:
  - id: openwiki-source-0f2091252a9c3383cef44ad0
    resource: repo://.agents/skills/openwiki/SKILL.md
  - id: openwiki-source-ab585d88aca3958f2aa6a541
    resource: repo://.codex/config.toml
  - id: openwiki-source-f5a489e5822d87c0b8fc66ef
    resource: repo://.mcp.json
  - id: openwiki-source-e119253b3c3737247dc63f2a
    resource: repo://.openwikiignore
  - id: openwiki-source-8037e2358a2c4f9b2c722a11
    resource: repo://AGENTS.md
  - id: openwiki-source-a2371d6362e5db4bc834ad03
    resource: repo://CLAUDE.md
generated: { by: "codex", at: "2026-09-07T17:18:36.762Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T19:39:22.177Z
---

# Maintain the OpenWiki

The canonical documentation is `openwiki/`. The root README is an entry point. `AGENTS.md` holds implementation and testing conventions, and `CLAUDE.md` points to the same guidance. The wiki brief is `openwiki/INSTRUCTIONS.md`.

This repository uses on-demand generation through a coding agent. No scheduled documentation workflow is configured. OpenWiki's upstream managed AGENTS block mentions scheduled GitHub Actions; the project-specific instructions above that block describe this repository's actual setup.

## Install and discover the integration

Install the documented OpenWiki version with Node.js 22+ and npm on PATH:

```sh
npm install --global openwiki@0.5.0
openwiki integrations install codex --project .
openwiki integrations install claude --project .
openwiki integrations list --project .
```

The project already carries the integration configuration and skill bundles. The install commands are useful when setting up or repairing a checkout. They operate on the Git repository root rather than a nested source directory. OpenWiki itself remains a developer tool; it is not a Python runtime dependency.

| Host | MCP configuration | Skill |
| --- | --- | --- |
| Codex | `.codex/config.toml` runs `openwiki mcp --host codex` | `.agents/skills/openwiki/SKILL.md` |
| Claude Code | `.mcp.json` runs `openwiki mcp --host claude` | `.claude/skills/openwiki/SKILL.md` |

Restart the coding agent in this repository after installing a new MCP integration. Confirm that the `openwiki` server is available. If startup reports a missing executable, make both `node` and `openwiki` available on that agent's PATH; a configuration file alone does not load a tool into an already-running session.

## Generate through Codex

Ask Codex:

> Update this repository's OpenWiki from the current source and tests.

For a repository with no wiki, ask it to initialize the OpenWiki instead. The [official integration](https://github.com/langchain-ai/openwiki#coding-agent-integrations) uses the coding agent's authenticated model and repository tools; a separate OpenWiki model provider is unnecessary for this workflow.

The installed skill defines the lifecycle:

1. Resolve the absolute Git top-level and call `openwiki_begin`.
2. Inspect the source and submit a page plan when planning is required.
3. Consume `openwiki_next_page`, author only the assigned page, and submit its material claims with repository evidence.
4. Repeat until the queue is complete, then call `openwiki_finish`.

Completion means `openwiki_finish` returned `complete`, not merely that Markdown files appeared. OpenWiki manages indexes, source versions, claim sidecars, provenance, and durable run state. The coding agent supplies the research and prose. Interrupted work resumes from the saved run; source drift can require a replacement plan.

Do not edit `.claims/`, `.run.json`, indexes, logs, or generated provenance by hand. Use the lifecycle for updates and keep source changes finished before generation. Commit completed wiki artifacts and agent setup files; `.gitignore` excludes transient `.run.json`.

## Scope and review

`.openwikiignore` excludes local runs, credentials, databases, installed dependencies, caches, generated frontend bundles, and the removed legacy documentation paths. Root-anchored rules for legacy files avoid accidentally excluding wiki pages with the same basename.

Review claims against source and tests. Versioned evidence establishes where a claim came from and whether its source changed; it does not prove the prose's interpretation automatically. Keep gaps and unsupported future integrations explicit. Update `openwiki/INSTRUCTIONS.md` when documentation scope changes.

## Browse locally

```sh
openwiki visualize openwiki
```

OpenWiki provides the documentation graph and reader. This is separate from `uv run agent-data-workbench ui runs/workbench`, which displays agent trace data. The Markdown also renders directly in GitHub. This setup does not publish the private wiki to a public site.

Next: [quickstart](../quickstart.md) or [development and verification](../development/contributing.md).
