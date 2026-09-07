---
type: workflow
title: Batch evaluation and analyzer checks
description: Prepare a fixed batch for analysis, review assertions against supplied outputs, and separately evaluate the analyzer's evidence localization.
tags: [batch, evaluation, benchmark, analyzer]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T17:18:36.762Z
sources:
  - id: openwiki-source-a17b46c83fec9ddee5bdd6a4
    resource: repo://src/agent_data_workbench/benchmark.py
  - id: openwiki-source-cb831ca27b1153da653ff8dc
    resource: repo://src/agent_data_workbench/evaluation.py
  - id: openwiki-source-c90a57f259e123cf538cdd9c
    resource: repo://src/agent_data_workbench/workflow.py
generated: { by: "codex", at: "2026-09-07T17:18:36.762Z" }
---

# Batch evaluation and analyzer checks

Batch mode is useful for a small exported dataset and a reviewable report. It predates the persistent workbench workflow and remains supported. Its `evaluate` and `compare` commands check supplied output files; use [experiments](experiments-and-training.md) when the workbench should actually execute target variants.

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

Read the candidate cases and replace `C_ID` with an actual ID from `cases.jsonl`:

```sh
uv run agent-data-workbench review runs/batch/cases.jsonl --accept C_ID --note "Reviewed fixture and assertion"
uv run agent-data-workbench evaluate runs/batch/cases.jsonl outputs.jsonl
uv run agent-data-workbench compare runs/batch/cases.jsonl baseline.jsonl candidate.jsonl
```

Each output record has this shape:

```json
{"case_id":"C_ID","output":{"status":"declined"}}
```

Only accepted cases are evaluated. Unknown case IDs are rejected. Missing output fails an individual evaluation; comparison requires both sides for every accepted case. Equality preserves JSON boolean/number distinctions, so `true` is not interchangeable with `1`. Text assertions require string fields. The CLI exits 1 for failed evaluation cases or comparison regressions.

`demo --out runs/batch-demo` produces a prewritten synthetic batch, analysis, and outputs without running a model or target. This differs from `workbench-demo`, which executes deterministic target programs. Neither establishes real-world model improvement.

## Evaluate the analyzer separately

```sh
uv run agent-data-workbench benchmark src/agent_data_workbench/data/analyzer-gold.json runs/analyzer-check --backend codex
uv run agent-data-workbench schema --kind human-assessment
uv run agent-data-workbench benchmark-review runs/analyzer-check annotations.json "Reviewer name"
```

The benchmark invokes the configured analyzer for explicit gold cases. Gold labels specify exact `(trace_id, pointer, category)` signals with a label source. The report records matched, extra, and missed spans, analyzer errors, precision, recall, and the dataset fingerprint. Additional useful supporting spans can count as extra labels, so inspect the explanations before interpreting a score.

Human review is a separate artifact covering correctness, actionability, usefulness for task construction, review time, and coverage of returned findings. The bundled gold data is synthetic smoke coverage. Build independently reviewed domain data before using these scores to compare analyzers for your product.

Next: [persistent investigations](investigations.md), [task auditing](tasks-and-graders.md), or [executed comparisons](experiments-and-training.md).
