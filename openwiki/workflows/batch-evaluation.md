---
type: workflow
title: Batch evaluation and analyzer checks
description: Prepare a fixed batch for analysis, review assertions against supplied outputs, and separately evaluate the analyzer's evidence localization.
tags: [batch, evaluation, benchmark, analyzer]
sources:
  - id: openwiki-source-a17b46c83fec9ddee5bdd6a4
    resource: repo://src/agent_data_workbench/benchmark.py
  - id: openwiki-source-cb831ca27b1153da653ff8dc
    resource: repo://src/agent_data_workbench/evaluation.py
  - id: openwiki-source-a25d1495b814c3304c94e096
    resource: repo://src/agent_data_workbench/models.py
  - id: openwiki-source-868dd2d0d9ddfabf6e9776f0
    resource: repo://src/agent_data_workbench/prompt.py
  - id: openwiki-source-c90a57f259e123cf538cdd9c
    resource: repo://src/agent_data_workbench/workflow.py
generated: { by: "codex", at: "2026-09-07T19:39:22.177Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T19:39:22.177Z
---

# Batch evaluation and analyzer checks

Batch mode is useful for a small exported dataset and a reviewable report. Its commands live in `cli/batch.py` and call the shared analysis and evaluation modules. Its `evaluate` and `compare` commands check supplied output files; use [experiments](experiments-and-training.md) when the workbench should actually execute target variants.

## Prepare and analyze a batch

```sh
uv run agent-data-workbench prepare traces.jsonl --out runs/batch --limit 100
```

Preparation makes no model call. It writes `request.json`, `schema.json`, `prompt.txt`, and `traces.md` into a new or empty directory. Selection takes the first N records in export order, not a representative sample. The default prompt limit is 120,000 characters. The request records fingerprints for the source, selected snapshot, and prepared configuration.

Inspect the prompt and schema. To import a separately generated structured response:

```sh
uv run agent-data-workbench finish runs/batch analysis-response.json
```

Alternatively, prepare and call a native analyzer in one operation:

```sh
uv run agent-data-workbench analyze traces.jsonl --backend codex --out runs/batch-model
```

Use `--backend claude` for Claude Code, `--model` for an explicit supported model, and repeat `--context path.md` for explicit context files. This analysis command sends selected context through the provider CLI. Completion checks the request fingerprint and evidence references, then writes `analysis.json`, `run.json`, `cases.jsonl`, and `report.md`. An already-completed run cannot be overwritten; prepare a new one.

## Review cases and compare supplied outputs

Finding and case IDs are UUIDs; trace IDs keep the source identifiers. Prepared requests use protocol 0.3, so prepare a new batch for an older request. Read the candidate cases and replace `CASE_UUID` with an actual ID from `cases.jsonl`:

```sh
uv run agent-data-workbench review runs/batch/cases.jsonl --accept CASE_UUID --note "Reviewed fixture and assertion"
uv run agent-data-workbench evaluate runs/batch/cases.jsonl outputs.jsonl
uv run agent-data-workbench compare runs/batch/cases.jsonl baseline.jsonl candidate.jsonl
```

Each output record has this shape:

```json
{"case_id":"CASE_UUID","output":{"status":"declined"}}
```

Only accepted cases are evaluated. Unknown case IDs are rejected. Missing output fails an individual evaluation; comparison requires both sides for every accepted case. Equality preserves JSON boolean/number distinctions, so `true` is not interchangeable with `1`. Text assertions require string fields. The CLI exits 1 for failed evaluation cases or comparison regressions.

## Evaluate the analyzer separately

```sh
uv run agent-data-workbench benchmark ./analyzer-gold.json runs/analyzer-check --backend codex
uv run agent-data-workbench schema --kind human-assessment
uv run agent-data-workbench benchmark-review runs/analyzer-check annotations.json "Reviewer name"
```

The benchmark invokes the configured analyzer for explicit gold cases. Gold labels specify exact `(trace_id, pointer, category)` signals with a label source. The report records matched, extra, and missed spans, analyzer errors, precision, recall, and the dataset fingerprint. Additional useful supporting spans can count as extra labels, so inspect the explanations before interpreting a score.

Human review is a separate artifact covering correctness, actionability, usefulness for task construction, review time, and coverage of returned findings. Supply your own independently reviewed gold dataset before using these scores to compare analyzers for your product. No benchmark dataset is bundled with the runtime package; synthetic fixtures belong only to the test suite.

Next: [persistent investigations](investigations.md), [task auditing](tasks-and-graders.md), or [executed comparisons](experiments-and-training.md).
