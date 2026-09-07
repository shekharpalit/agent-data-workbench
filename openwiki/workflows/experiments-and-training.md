---
type: workflow
title: Experiments and training exports
description: Execute baseline and candidate agents against reviewed tasks, preserve split boundaries and uncertainty, and export eligible optimization outcomes.
tags: [experiments, runners, splits, training, provenance]
sources:
  - id: openwiki-source-bc1c81655ba5541ecce98f99
    resource: repo://src/agent_data_workbench/cli/experiments.py
  - id: openwiki-source-f4e6f61890af760b72e18127
    resource: repo://src/agent_data_workbench/cli/exports.py
  - id: openwiki-source-fb8bc98ca92f65c4b5c08595
    resource: repo://src/agent_data_workbench/experiments.py
  - id: openwiki-source-17fefd32a0fa5ffbd20a3c46
    resource: repo://src/agent_data_workbench/exports.py
  - id: openwiki-source-b5025a250cbf9f845fc9224a
    resource: repo://src/agent_data_workbench/project.py
  - id: openwiki-source-c792213eed7e8f73d739e358
    resource: repo://src/agent_data_workbench/research/artifacts.py
  - id: openwiki-source-362b588ee7b1871bafaf5b44
    resource: repo://src/agent_data_workbench/runners.py
  - id: openwiki-source-af0e5443d83442c11181e6ce
    resource: repo://tests/test_workbench_execution.py
generated: { by: "codex", at: "2026-09-07T20:56:39.229Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T21:10:14.760Z
---

# Experiments and training exports

An experiment executes a baseline and candidate against a frozen suite. It records outputs, grader results, artifacts, latency, and available cost data. The result establishes observed behavior on those tasks. It does not establish production generalization or train a model.

Start with [accepted, audited tasks](tasks-and-graders.md). Use [batch evaluation](batch-evaluation.md) when comparing output files that have already been produced.

## Freeze a suite

Supply accepted task UUIDs from the project. The second argument is a friendly suite name:

```sh
uv run agent-data-workbench suite runs/my-agent "Accuracy / current" \
  --task-id TASK_A --task-id TASK_B --task-id TASK_C --seed 7
```

The suite groups tasks that share source groups, including transitive relationships. It requires at least three independent connected groups and allocates optimization, validation, and final roles using a seeded, behavior-stratified ordering. The repeating assignment targets a 60/20/20 distribution; small suites need not match that ratio exactly.

The manifest freezes task hashes, group membership, split roles, and source inventory. Existing group assignments cannot change in a later suite. Every manifest receives a new UUID independent of its name. Names can repeat; use the returned `id` for execution. Obtain fresh source groups when existing assignments conflict. Traces present in any native investigation snapshot are conservatively marked as previously investigated, even if no MCP read was recorded: native agents can read the snapshot directly. Legacy investigations use their recorded visited IDs. Allocating these examples to a final split does not make them unseen.

## Configure the targets

A command runner configuration is a JSON file alongside the target code:

```json
{
  "name": "baseline",
  "kind": "command",
  "command": ["python", "agent.py", "--variant", "baseline"],
  "environment_version": "my-agent-v1",
  "source_files": ["agent.py"],
  "fidelity": "output",
  "timeout": 120
}
```

Create a candidate file with its own name and command arguments. Use an executable available on PATH or an explicit interpreter path. File arguments that exist relative to the configuration directory are resolved before switching to a trial directory.

For each execution the adapter sends one JSON object on stdin:

```json
{"input": {"request": "Task-visible input"}, "seed": 7}
```

The command must return a JSON execution envelope on stdout:

```json
{"output": {"answer": "Target result"}, "status": "completed"}
```

Additional execution fields can include nonnegative `cost_usd` and a `usage` object. Unknown cost stays unknown. Write diagnostic logging to stderr so stdout remains parseable. Explicitly list files in `source_files` to hash them; this is not a recursive capture of every dependency.

The runner identity records configuration, resolved command, and listed source hashes. Changed listed sources invalidate execution. A fresh temporary directory is created per variant and trial, and required JSON artifacts are captured before cleanup. This directory provides clean working state, not host isolation: command adapters execute trusted code with host access. Supply a container or other external isolation through your adapter when needed.

Native `codex` and `claude` target runners require explicit `model` and `prompt`. They support output or next-action fidelity, cannot claim environment execution, and record that seed control is unsupported. Analysis and target execution are separate roles even when they use the same CLI.

## Run and interpret an experiment

```sh
uv run agent-data-workbench experiment runs/my-agent SUITE_UUID \
  ./baseline.json ./candidate.json --split optimization --repeats 2 --seed 7
```

Replace `SUITE_UUID` with the ID printed by `suite`. Use optimization results to iterate, then run the selected configuration on validation. Semantic criteria require an explicit judge matching the task's audited backend and model, for example `--judge codex --judge-model MODEL`.

Before execution, the workbench checks the suite hash, accepted task snapshots, target fidelity, and required judge identity. It saves each trial as it completes. Baseline/candidate ordering reverses on alternating repeats. An interruption leaves an interrupted record with the evidence collected so far.

| Outcome | Meaning |
| --- | --- |
| Pass | The recorded execution satisfied the task's criteria. |
| Fail | The execution supplied gradable evidence but failed a criterion. |
| Invalid | A runner, evidence, or judging problem prevented a capability judgment. |

Paired results count improvements and regressions by task and repeat. Invalid or missing pairs remain separate. Pass rates use valid outcomes only; read them alongside invalid counts. Cost totals include a coverage count, so partial reporting is visible.

The uncertainty estimate resamples independent source groups, preserving correlation between related tasks and repeats. It is omitted with fewer than five valid independent groups. Repeating one example does not create independent evidence. The experiment command exits unsuccessfully when it records invalid pairs or regressions.

## Preserve the final set

Run `--split final` only when the chosen configuration is ready for its final measurement. Final exposure is consumed **before the first execution**, including runs that later fail or are interrupted. Consumed final source groups cannot be reused through another suite. This prevents silently treating a retry as fresh held-out evidence; it does not erase knowledge already acquired from those examples.

Native research includes all supplied data by default. Starting an investigation after suite creation records `research_exposure` for suites containing final data. To keep reserved final groups out of a new research snapshot, pass `--exclude-final` or use the UI checkbox. Research exposure prevents a later final run from treating those groups as fresh held-out evidence, while optimization execution remains available. Exposure metadata is excluded from the suite definition hash, so recording exposure does not invalidate the suite itself.

## Export curated outcomes

After reviewing a completed optimization experiment, supply its ID and a new output directory. The review and permission notes are positional arguments:

```sh
uv run agent-data-workbench training-export runs/my-agent EXPERIMENT_ID \
  ./training-data "Reviewed selected task outcomes" \
  "Permission recorded for these selected records" --kind preference
```

Use `--kind sft` for chosen-only records. Export excludes validation and final experiments, incomplete experiments, missing pairs, and invalid pairs. SFT needs a passing outcome; preference data additionally needs a failing outcome. The passing variant can be the baseline. Identical visible inputs are deduplicated.

The output contains `data.jsonl` and `manifest.json`. Records preserve task, experiment, trace, split, variant, and verifier provenance. The manifest records hashes and the supplied review and permission notes. Those notes document the user's review; they do not verify permission automatically.

Adapt the portable `input`, `chosen`, and optional `rejected` fields to your trainer's schema. Export performs no training job or automatic redaction.

## Verification and next steps

`tests/test_workbench_execution.py` covers transitive grouping, fresh execution, invalid outcomes, interrupted final exposure, frozen configuration, grouped uncertainty, command artifacts, and training selection.

Next: [investigate trace evidence](investigations.md), [task design and grader audits](tasks-and-graders.md), or [local workbench](../operations/local-workbench.md).
