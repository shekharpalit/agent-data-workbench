---
type: workflow
title: Investigations and reviewed knowledge
description: Run persistent Codex or Claude Code research over complete local snapshots, record resumable outcomes, and publish evidence, tasks, reports and charts.
tags: [research, evidence, knowledge, codex, claude]
sources:
  - id: openwiki-source-32f4d2812881234bd0f7d75a
    resource: repo://src/agent_data_workbench/cli/knowledge.py
  - id: openwiki-source-25b71218f03a1e216debf67e
    resource: repo://src/agent_data_workbench/cli/research.py
  - id: openwiki-source-b5025a250cbf9f845fc9224a
    resource: repo://src/agent_data_workbench/project.py
  - id: openwiki-source-c792213eed7e8f73d739e358
    resource: repo://src/agent_data_workbench/research/artifacts.py
  - id: openwiki-source-219194215a29797e5e6ef5bf
    resource: repo://src/agent_data_workbench/research/contracts.py
  - id: openwiki-source-19e7dd6c7eb0091ce3762537
    resource: repo://src/agent_data_workbench/research/dataset.py
  - id: openwiki-source-1c842561c46278adab40a06d
    resource: repo://src/agent_data_workbench/research/mcp.py
  - id: openwiki-source-613a68c172b951e8d3ef8837
    resource: repo://src/agent_data_workbench/research/proposals.py
  - id: openwiki-source-e5f659ea5e57c342ab8bc379
    resource: repo://src/agent_data_workbench/research/sessions.py
  - id: openwiki-source-e583a74c09dc96bfdcc444cb
    resource: repo://src/agent_data_workbench/research/validation.py
  - id: openwiki-source-2dbe8753da4267ce652f414e
    resource: repo://src/agent_data_workbench/research/workspace.py
  - id: openwiki-source-3589dc1fc29ba0bfe0e2a50c
    resource: repo://tests/test_research.py
  - id: openwiki-source-9dba1709c16fd704c45276e9
    resource: repo://tests/test_workbench_data.py
generated: { by: "codex", at: "2026-09-07T21:14:42.725Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T21:14:42.725Z
---

# Investigations and reviewed knowledge

An investigation gives a native Codex or Claude Code session a complete local data workspace. The coding agent decides how to explore, writes and runs analysis code, manages its own context, and publishes findings and useful outputs. The workbench stores inputs, progress, evidence and outcomes. It does not implement another model-call loop.

Import a corpus using [trace ingestion](traces.md). The question and reviewed project knowledge define what matters for your agent.

## Supply context deliberately

Add a policy, tool contract, success definition, or source snapshot:

```sh
uv run agent-data-workbench knowledge add runs/my-agent ./policy.md "Completion policy"
uv run agent-data-workbench knowledge review runs/my-agent KNOWLEDGE_ID accepted \
  "Reviewed against the current product contract"
```

Use the UUID printed by the first command. New knowledge starts as draft. Only accepted knowledge enters the hashed project context. Reviews record a note, revision and prior content hash. Knowledge import and SDK revision preserve the full supplied content without a fixed size cap. The local HTTP API still has its general request-body boundary; use the CLI or SDK for larger files.

Keep context specific enough to distinguish a real failure from missing information. A trace alone may not establish whether an action was authorized, a tool contract was violated, or a result was useful.

## Choose research or complete processing

Install and authenticate your chosen native CLI separately, and make it available on PATH:

```sh
uv run agent-data-workbench investigate runs/my-agent \
  --question "When does the agent claim completion without evidence?" \
  --backend codex
```

Use `--backend claude` for Claude Code and `--model MODEL` for an explicit model. Otherwise the CLI's model selection applies. The installed CLI uses its existing authentication; the workbench makes no fallback API call. Provider eligibility, account limits, context constraints and billing still apply.

| Mode | Work and completion |
| --- | --- |
| `research` (default) | Explore adaptively, gather evidence and publish findings. State what was examined and what remains uncertain. |
| `complete` | Save a successful outcome for every snapshot record and resolve failures before final publication. |

Add `--mode complete` for a complete pass. Native research has no workbench model-call count, corpus-size cap, or default time budget. Supply `--timeout SECONDS` only when you want a time budget; reaching it pauses the run and preserves progress. Available memory, disk, the native CLI and the chosen model still constrain execution.

## What the agent receives

Starting an investigation captures every included record into `investigations/INVESTIGATION_ID/dataset.sqlite3` with its original JSON, external ID, source group, stratum and content hash. It also captures the accepted context. New imports or knowledge changes do not alter this investigation's inputs or prevent resume. The disk-backed snapshot duplicates the selected corpus, so plan for that local disk space.

All imported data is included by default. `--exclude-final` excludes reserved final source groups. If final data is available to research, the workbench records that exposure conservatively because native agents can read files directly. See [final-set bookkeeping](experiments-and-training.md#preserve-the-final-set).

The workspace contains `AGENTS.md`, `CLAUDE.md`, `context.json` and `result-schema.json`. The native session starts there and can create scripts, reports, plots and data files. Codex runs with workspace-write settings that also permit SDK mutations in the project directory. Claude retains its native tools, uses the local workbench MCP configuration and permits workspace edits and Python execution. These settings are not isolation from hostile agent code; native account settings and permissions remain relevant.

The agent can use three equivalent entry points:

- **MCP:** `workspace_info`, `search_traces`, `read_trace`, `aggregate_traces`, `read_context`, `checkpoint`, `record_outcomes`, `publish_findings`, `publish_tasks`, and `save_artifact`.
- **Python:** `ResearchWorkspace` and its `dataset` methods for streaming records, arbitrary analysis code, aggregation and export.
- **CLI:** `research info`, `records`, `record`, `publish`, `attach`, `export`, and `pause`.

MCP runs through the official Python SDK over stdio. This workbench data server is separate from the repository's OpenWiki documentation integration. Search returns previews with a continuation cursor; `read_trace` follows JSON pointers and ranges, with `max_chars: null` available for full text. Page size controls each response, not total available data. Aggregation processes every matching record or saved outcome; distinct values are paginated.

## Use an existing coding-agent session

Prepare a workspace without starting another model process:

```sh
uv run agent-data-workbench research create runs/my-agent \
  "Which outcomes need investigation?" --mode complete
```

The command prints the investigation UUID, workspace directory and MCP command. Open that directory in your existing agent and use its instructions. To connect through MCP, configure a stdio server invoking:

```sh
agent-data-workbench mcp /absolute/path/to/runs/my-agent INVESTIGATION_ID
```

Use the installed executable and absolute project path in your client's MCP configuration. The CLI and Python APIs also work without MCP.

For example, a script can record a deterministic feature for every input:

```python
from agent_data_workbench import ResearchWorkspace

w = ResearchWorkspace("/absolute/path/to/runs/my-agent", "INVESTIGATION_ID")

def describe_record(trace):
    return {"message_count": len(trace.data.get("messages", []))}

coverage = w.dataset.process(describe_record, method="Count recorded messages")
w.dataset.export(w.directory / "outcomes.jsonl")
```

This counts messages; it does not evaluate conversational quality. Replace the function with analysis appropriate to your question. `process` commits each successful output or failure, skips completed records on the next call, and retries failed or pending records. Each output must be a JSON object with a recorded method. A failure stays unfinished. An interrupt preserves earlier outcomes.

Coverage distinguishes `completed`, `failed`, `pending` and `retrieved` from the total snapshot count. Retrieval records SDK access, including pages fetched by processing; direct file reads are not counted. Neither retrieval nor a saved output proves semantic review or correctness. Complete mode verifies outcome coverage, not whether a model understood every record.

## Pause and resume the native session

The workbench saves the native session ID as soon as the CLI emits it, plus attempt prompts, native JSONL events, stderr diagnostics and structured journal notes. It does not reconstruct the conversation from a custom step history.

```sh
uv run agent-data-workbench research pause runs/my-agent INVESTIGATION_ID
uv run agent-data-workbench investigate runs/my-agent --resume INVESTIGATION_ID
```

Resume uses the original backend and saved model setting. A separate process lock prevents two native sessions from owning one investigation; short project locks protect artifact updates. If the process crashes, its lock releases and the investigation can resume even if its last saved status was running. Native provider session files must remain available for native continuation. Local checkpoints and input snapshots remain in the project independently.

Cancellation, an explicit timeout or an unfinished native response leaves paused research. Failures preserve saved progress; inspect local logs for diagnostics. Draft findings remain visible and do not prevent resume. A completed investigation requires a new investigation for further record processing. Existing project format 0.3 remains supported; old completed investigations can be viewed, but paused investigations from the earlier step protocol require a new native investigation.

## Publish evidence, tasks and files

`publish_findings` accepts the `ResearchResult` shape in `result-schema.json`: analysis, signals, proposals and open questions. Set `complete=false` to save a draft. Final publication in complete mode requires zero pending and zero failed records. Publication records coverage and a Markdown report; subsequent SDK outcome edits cannot change a completed investigation.

Citations use exact quotes and RFC 6901 pointers into original `trace.data`. Finding and signal evidence must match the snapshot, and proposal finding references must exist. Citations may reference any snapshot record, including records analyzed by native scripts outside MCP reads. Internal investigation, knowledge, finding, proposal and artifact IDs use UUIDs; source trace IDs remain unchanged.

Exact matching verifies that cited text exists. It does not establish interpretation, causal explanation, severity or impact. `publish_tasks` creates draft tasks with snapshot trace lineage and captured context; [grader audits and review](tasks-and-graders.md) remain separate.

To publish a chart, write a workspace-relative JSON file:

```json
{"title":"Outcome counts","description":"Population and analysis method","values":[{"label":"Needs review","value":12}]}
```

Register it with `save_artifact(path="counts.json", title="Outcome counts", kind="chart")` over MCP or `w.attach("counts.json", "Outcome counts", "chart")` in Python. Values must be finite and nonnegative for the inline bar renderer. Other charts, code, reports and datasets can be attached as downloadable files. Publication copies a file under an artifact UUID, records its digest, and verifies that copy when downloaded. Changing the source script or file does not change the published copy.

A proposal includes a hypothesis, expected effect and evaluation plan. Export it against a source checkout:

```sh
uv run agent-data-workbench proposal-export runs/my-agent \
  INVESTIGATION_ID PROPOSAL_ID /path/to/agent-source ./proposal-review
```

Export requires completed research. Each edit is one complete before/after pair for a relative file path, checked against the checkout's current whole-file content. Missing, escaping and stale paths fail validation. Export writes a patch and manifest without applying the patch. Proposals without source edits can still describe work for manual implementation.

## Verification and next steps

`tests/test_research.py` exercises native-shaped subprocesses, interruption and retry behavior, a complete corpus larger than one page, official MCP stdio, workspace CLI operations, tasks and artifacts. `tests/test_workbench_data.py` checks exact evidence, stable snapshots after project changes and proposal export. Tests use synthetic inputs without live provider inference.

Next: [design tasks and audit graders](tasks-and-graders.md), [inspect the local UI](../operations/local-workbench.md), then [execute an experiment](experiments-and-training.md).
