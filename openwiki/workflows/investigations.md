---
type: workflow
title: Investigations and reviewed knowledge
description: Use a native Codex or Claude analyzer to investigate trace evidence through bounded local tools, review project context, and export unexecuted improvement proposals.
tags: [research, evidence, knowledge, codex, claude]
sources:
  - id: openwiki-source-1f37d6e3d3e1f41c68ed94e2
    resource: repo://src/agent_data_workbench/backends.py
  - id: openwiki-source-b5025a250cbf9f845fc9224a
    resource: repo://src/agent_data_workbench/project.py
  - id: openwiki-source-165df15cf6bb24c268cc1461
    resource: repo://src/agent_data_workbench/research.py
  - id: openwiki-source-9dba1709c16fd704c45276e9
    resource: repo://tests/test_workbench_data.py
generated: { by: "codex", at: "2026-09-07T19:39:22.177Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T19:39:22.177Z
---

# Investigations and reviewed knowledge

An investigation lets an analyzer choose which trace evidence to inspect next. Python executes the named read tools, journals the observations, and checks the final citations. The analyzer supplies hypotheses and recommendations; it does not apply changes or establish customer impact simply by writing a finding.

Import a corpus first using [trace ingestion](traces.md). The project question and reviewed knowledge define what matters for your agent.

## Supply context deliberately

Add a policy, tool contract, success definition, or source snapshot as a knowledge document:

```sh
uv run agent-data-workbench knowledge add runs/my-agent ./policy.md "Completion policy"
uv run agent-data-workbench knowledge review runs/my-agent KNOWLEDGE_ID accepted \
  "Reviewed against the current product contract"
```

Use the UUID printed by the first command. New knowledge starts as draft. Only accepted knowledge enters the research context. Reviews record a note, revision, and prior content hash; the context itself is hashed. The CLI limits each supplied file to 100,000 bytes.

Keep context specific enough to distinguish a real failure from missing information. A trace alone may not establish whether an action was authorized, a tool contract was violated, or a result was commercially useful.

## Start bounded research

Install and authenticate your chosen native CLI separately, and make its executable available on PATH. Then run:

```sh
uv run agent-data-workbench investigate runs/my-agent \
  --question "When does the agent claim completion without evidence?" \
  --backend codex --steps 6 --seed 7
```

Use `--backend claude` to select Claude Code and `--model MODEL` to select a model explicitly. Otherwise the native CLI's model selection applies. Analysis sends the supplied project context and selected trace observations through that CLI/account. Account eligibility, limits, and billing remain properties of that provider; the adapter makes no fallback API call when the native CLI fails.

The Codex adapter requests structured output in a temporary directory, with read-only sandboxing, shell tools disabled, and web search disabled. The Claude adapter requests structured JSON, disables tools, supplies an empty strict MCP configuration, and disables session persistence. These settings describe how this repository invokes the CLIs, not a guarantee that every future CLI version supports the same flags.

Each model response selects one host action:

| Action | Host behavior |
| --- | --- |
| Search | Case-insensitive substring matching with stable ID order. |
| Sample | Seeded balanced sampling across strata. |
| Inspect | Read a trace field by JSON pointer with explicit range limits. |
| Aggregate | Compute exact counts and numeric summaries over the matched eligible corpus. |
| Context | Return accepted project knowledge. |
| History | Return prior experiment summaries, excluding final experiments. |
| Finish | Validate the proposed result and evidence before completing. |

Search and sample return bounded previews, not necessarily complete traces. Inspect returns at most 16,000 characters per request. A balanced sample helps explore diversity; it is not a prevalence estimate.

Final-set source groups are excluded from subsequent model-directed research. This reservation does not retroactively make earlier research unseen.

## Resume without changing the evidence

The journal stores backend/model identity, prompt hashes, decisions, observations, visited IDs, and status after each step. Default runs allow six calls and a 120,000-character input budget; configurable limits are 1–50 steps and 5,000–500,000 input characters.

When the budget is exhausted, the investigation pauses. Provider errors or invalid returned data also preserve a paused record. Resume explicitly using the ID printed by the original command:

```sh
uv run agent-data-workbench investigate runs/my-agent \
  --resume INVESTIGATION_ID --backend codex --steps 6
```

Resume checks the trace inventory and reviewed-context hashes. Changed inputs require a new investigation. Tool argument errors are saved as observations so the analyzer can correct them in a later step. Oversized reviewed context raises an error rather than being silently discarded.

## Read evidence and proposals

Investigation, knowledge, finding, and proposal IDs are UUIDs; external trace IDs remain unchanged. The analyzer schema validates finding and proposal references with the shared UUID type.

Completion validates finding and signal citations against the visited trace snapshots. Evidence uses exact quotes and RFC 6901 pointers into `trace.data`; proposals must reference known findings. The saved result contains analysis, categorized signals, proposals, and open questions, alongside a Markdown research report.

Exact matching verifies that the cited text exists. It does not validate the interpretation, causal explanation, severity, or proposed improvement. A visited preview also does not establish full review of that trace. Review the finding and contrary examples before turning it into an accepted task.

A proposal includes a hypothesis, expected effect, and evaluation plan. Export it against a source checkout:

```sh
uv run agent-data-workbench proposal-export runs/my-agent \
  INVESTIGATION_ID PROPOSAL_ID /path/to/agent-source ./proposal-review
```

For edits, export requires one complete before/after edit per relative path and checks that the current whole-file content matches `before`. Missing paths, escaping paths, and stale source content fail validation. The export writes a reviewable patch and manifest; it does not apply the patch. Proposals without grounded source edits can still describe an improvement for manual implementation.

## Verification and next steps

`tests/test_workbench_data.py` checks pause/resume, preserved seeds, fabricated or unvisited citations, recoverable tool errors, changed inputs, provider failures, and source-checked proposal export. `tests/test_backends.py` checks the native adapter command contracts.

Next: [design tasks and audit graders](tasks-and-graders.md), then [execute an experiment](experiments-and-training.md).
