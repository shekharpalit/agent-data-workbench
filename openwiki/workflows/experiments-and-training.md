---
type: workflow
title: Experiments and training exports
description: Execute baseline and candidate agents against reviewed tasks, preserve split boundaries and uncertainty, and export eligible optimization outcomes.
tags: [experiments, runners, splits, training, provenance]
sources:
  - id: openwiki-source-54fdef6566e11f973ec27cd8
    resource: repo://src/agent_data_workbench/evaluation/experiments.py
  - id: openwiki-source-b9d6b20204f1bf0dc801535c
    resource: repo://src/agent_data_workbench/evaluation/statistics.py
  - id: openwiki-source-089f8cc32a1cbbf08c3ba0df
    resource: repo://src/agent_data_workbench/evaluation/suites.py
  - id: openwiki-source-5713c60f5b9a71216ca7a47c
    resource: repo://src/agent_data_workbench/execution/artifacts.py
  - id: openwiki-source-36dca02d2c71dfa05627a7a1
    resource: repo://src/agent_data_workbench/execution/runners.py
  - id: openwiki-source-c773d92eb0c24f4c729a0408
    resource: repo://src/agent_data_workbench/integrations/harbor/comparison.py
  - id: openwiki-source-047935dc3e143c02a13e4031
    resource: repo://src/agent_data_workbench/integrations/harbor/results.py
  - id: openwiki-source-5817a5ac325238a8edd5763a
    resource: repo://src/agent_data_workbench/integrations/training.py
  - id: openwiki-source-c792213eed7e8f73d739e358
    resource: repo://src/agent_data_workbench/research/artifacts.py
  - id: openwiki-source-ff3fb6d1981d7674fe333637
    resource: repo://src/agent_data_workbench/shared/commands.py
  - id: openwiki-source-af0e5443d83442c11181e6ce
    resource: repo://tests/test_workbench_execution.py
  - id: openwiki-source-3c84d2d1ce8be46519d0db31
    resource: repo://ui/src/views/Experiments.tsx
generated: { by: "codex", at: "2026-09-08T04:50:29.215Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-08T04:50:29.215Z
---

# Experiments and training exports

A suite experiment executes a baseline and candidate against a frozen suite. The optional Harbor flow compares two targets on one frozen accepted task and records an exploratory experiment. It records outputs, grader results, artifacts, latency, and available cost data. The result establishes observed behavior on those tasks. It does not establish production generalization or train a model.

Start with [accepted, audited tasks](tasks-and-graders.md). Use [batch evaluation](batch-evaluation.md) when comparing output files that have already been produced.

Suite freezing lives in `evaluation/suites.py`; execution orchestration, grouped statistics and report rendering live in `evaluation/experiments.py`, `evaluation/statistics.py` and `evaluation/reports.py`. Target adapters live in `execution/`. Curated training export is an integration in `integrations/training.py`.

## Start with one Harbor task

For an accepted task with a real environment/verifier template, open **Run a Harbor comparison** in the task UI. Enter baseline and candidate targets, model/options, repetitions and the verifier reward settings. The workbench runs Harbor, saves paired grades and imports available complete trajectories automatically. Open each trial in Experiments and follow its generated trace to inspect the actual messages and recorded experiment link.

The equivalent command is `workflow harbor-compare PROJECT TASK_ID harbor-comparison.json`; [Harbor comparisons](../integrations/harbor.md) provides the full setup and configuration. One export freezes both targets' task and environment inputs; ordering alternates across repetitions. Missing rewards and execution exceptions remain invalid rather than becoming task failures.

These experiments use `split: exploratory`, have no suite ID and make no claim that model randomness is controlled. A workbench task audit does not calibrate Harbor's supplied external verifier. Repeats of one task are one independent group. The training exporter accepts complete optimization experiments, so this exploratory Harbor flow is not an automatic training export pipeline. Use the suite workflow below for reserved split roles and reviewed training selection.

## Freeze a suite

Supply accepted task UUIDs from the project. The second argument is a friendly suite name:

```sh
uv run agent-data-workbench suite runs/my-agent "Accuracy / current" \
  --task-id TASK_A --task-id TASK_B --task-id TASK_C --seed 7
```

The suite groups tasks that share source groups, including transitive relationships. It requires at least three independent connected groups and allocates optimization, validation, and final roles using a seeded, behavior-stratified ordering. The repeating assignment targets a 60/20/20 distribution; small suites need not match that ratio exactly.

The manifest freezes task hashes, group membership, split roles, and source inventory. Existing group assignments cannot change in a later suite. Every manifest receives a new UUID independent of its name. Names can repeat; use the returned `id` for execution. Obtain fresh source groups when existing assignments conflict. Traces present in any native investigation snapshot are conservatively marked as previously investigated, even if no MCP read was recorded: native agents can read the snapshot directly. Legacy investigations use their recorded visited IDs. Allocating these examples to a final split does not make them unseen.

## Configure the targets

Command runners parse the complete returned JSON envelope; valid outputs are not rejected because they exceed a fixed character count. Artifact capture reads each explicitly named valid JSON file in full without a file-size cutoff. Invalid JSON, missing files and paths outside the trial directory still cannot supply grading evidence. `tests/test_workbench_execution.py` verifies complete outputs and artifacts larger than 2 MB using synthetic content.


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

For one-shot execution the adapter sends one JSON object on stdin:

```json
{"input": {"request": "Task-visible input"}, "seed": 7}
```

The command must return a JSON execution envelope on stdout:

```json
{"output": {"answer": "Target result"}, "status": "completed"}
```

Additional execution fields can include nonnegative `cost_usd` and a `usage` object. Unknown cost stays unknown. Write diagnostic logging to stderr so stdout remains parseable. The executable and directly invoked script files are hashed automatically. List imported modules, lockfiles and other dependencies in `source_files`; this is not a recursive capture of every dependency.

The runner identity records configuration, resolved command and pinned source hashes. Changed sources invalidate execution. A fresh temporary directory is created per variant and trial; JSON artifacts, independent state, runtime records and a hashed copy of trial files are retained before cleanup. This directory provides clean working state, not host isolation: command adapters execute trusted code with host access. Supply a container or other external isolation through your adapter when needed.

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

Use `--kind sft` for chosen-only records. Export excludes validation and final experiments, incomplete experiments, missing pairs, and invalid pairs. SFT needs a passing outcome; preference data additionally needs a failing outcome. The passing variant can be the baseline. Deduplication includes visible input and conversation/world/environment specifications; legacy tasks without these features still deduplicate by input. Identical chosen/rejected preferences are excluded.

The output contains `data.jsonl` and `manifest.json`. Records preserve task, experiment, trace, split, variant, and verifier provenance. The manifest records hashes and the supplied review and permission notes. Those notes document the user's review; they do not verify permission automatically.

Adapt the portable `input`, `chosen`, and optional `rejected` fields to your trainer's schema. One-shot targets retain their output-object format. Conversation targets use `agent-data-workbench.trajectory.v1` with observed user turns, assistant messages/output and `reported_evidence`. Incomplete or mismatched conversation evidence is excluded; there is no fallback to a misleading final response. Hidden verifier and authoritative state stay in the source experiment and are referenced by hashes. Export performs no training job or automatic redaction.

## Verification and next steps

`tests/test_workbench_execution.py` covers transitive grouping, fresh execution, invalid outcomes, interrupted final exposure, frozen configuration, grouped uncertainty, command artifacts, and training selection.

Next: [investigate trace evidence](investigations.md), [task design and grader audits](tasks-and-graders.md), or [local workbench](../operations/local-workbench.md).

## Connect scenarios, calibration and decisions

A task can pin an accepted world, an environment lifecycle and a scripted/reactive conversation. The configured target is bound to each frozen task scenario, so a suite can exercise different user follow-ups using the same target code. Baseline/candidate scenario defaults must agree; each trial records its effective runner identity. See [eval engineering](eval-engineering.md) for the continuous NDJSON session and independent observer contracts.

Capture an improvement before running it:

```sh
agent-data-workbench workflow improvement PROJECT "Change name" "Hypothesis" \
  "Expected behavior" baseline.json candidate.json
agent-data-workbench experiment PROJECT SUITE_ID baseline.json candidate.json \
  --improvement-id IMPROVEMENT_ID --split validation
agent-data-workbench workflow calibrate PROJECT EXPERIMENT_ID "Human review"
agent-data-workbench workflow decide PROJECT IMPROVEMENT_ID EXPERIMENT_ID keep \
  "Reviewer" "Evidence and regression assessment"
```

Captured sources and identities must still match when the linked experiment begins. The decision preserves exact experiment and calibration evidence and does not modify the candidate. Optional parent improvement IDs connect iterations. Coverage mapping and Harbor export/run also record reserved final exposure; exports created before a suite are recorded as prior available evidence.
