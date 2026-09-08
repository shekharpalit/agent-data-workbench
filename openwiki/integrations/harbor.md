---
type: integration
title: Harbor comparisons
description: Execute two agent targets against one reviewed task in a supplied Harbor environment and return verifier results and trajectories to the workbench.
tags: [harbor, experiments, environments, traces]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-08T04:50:29.215Z
sources:
  - id: openwiki-source-012f2c78e3b1446dfc35803f
    resource: repo://Makefile
  - id: openwiki-source-732d0f8c004bbddbd6363fdf
    resource: repo://src/agent_data_workbench/api/routers/workflow.py
  - id: openwiki-source-eab73f261f2dfa06a5a90e74
    resource: repo://src/agent_data_workbench/exploration/lineage.py
  - id: openwiki-source-c773d92eb0c24f4c729a0408
    resource: repo://src/agent_data_workbench/integrations/harbor/comparison.py
  - id: openwiki-source-75e4ee5992e64ed99a4d9be3
    resource: repo://src/agent_data_workbench/integrations/harbor/exporting.py
  - id: openwiki-source-047935dc3e143c02a13e4031
    resource: repo://src/agent_data_workbench/integrations/harbor/results.py
  - id: openwiki-source-42955c511f8e1b6d5ca11004
    resource: repo://src/agent_data_workbench/integrations/harbor/runtime.py
  - id: openwiki-source-81b5f861a3da7051234ce169
    resource: repo://src/agent_data_workbench/shared/processes.py
  - id: openwiki-source-fa49503ca8957c1fd1a98b27
    resource: repo://src/agent_data_workbench/workbench/capabilities.py
  - id: openwiki-source-c7c87ce5b17b9e4bb0ee0b1b
    resource: repo://ui/src/components/RuntimeStatus.tsx
  - id: openwiki-source-3c84d2d1ce8be46519d0db31
    resource: repo://ui/src/views/Experiments.tsx
  - id: openwiki-source-494791e4bac0ec4e13edede5
    resource: repo://ui/src/views/HarborComparison.tsx
generated: { by: "codex", at: "2026-09-08T04:50:29.215Z" }
---

# Harbor comparisons

Harbor is the optional execution harness. The workbench owns trace research, reviewed tasks and comparison evidence; the installed Harbor CLI owns the supplied environment, target agent and verifier execution. Importing old traces alone does not reconstruct the agent code or its environment.

## Prepare a runnable task

1. [Investigate the traces](../workflows/investigations.md), author a task, audit its grader and [accept the task](../workflows/tasks-and-graders.md).
2. Supply an existing Harbor schema-1.4 template directory with `task.toml`, its environment definition or image, and `tests/test.sh`. The verifier must actually check this task's intended behavior.
3. Configure two Harbor agent targets. Each can be a built-in name or an importable `package:AgentClass`, with an optional model and primitive-valued agent options. Custom code must be available to the Harbor runtime.

The exporter copies and hashes the supplied template, writes only explicit target-visible input and conversation turns into instructions, and retains the full reviewed task outside the bundle. It checks the accepted task and frozen bundle again at execution. Materialize symlinks before export. Scripted conversations require a named Harbor step for each turn and request trajectory continuation; reactive conversations use the workbench's separate session protocol.

## Start from the UI

For existing host agent logins and a local Docker daemon, use native mode:

```sh
make init MODE=native
make dev MODE=native
```

This needs uv and a supported Node installation. Initialization builds the TypeScript UI, installs the locked Python package and installs Harbor as a separate uv tool. Ensure its executable directory is on PATH. Docker is needed when the chosen Harbor environment is `docker`.

Open an accepted task and find **Run a Harbor comparison**. Check runtime setup, enter the template directory, baseline and candidate agent/model/options, environment and repetitions. Select the verifier reward key and pass threshold, then click **Run baseline & candidate**. The template path is resolved by the backend. Agent options accept a JSON object whose values are strings, numbers or booleans.

The browser receives a background job and refreshes completed artifacts automatically. Open the experiment results, inspect each variant's grade and execution evidence, then follow **Inspect generated trace** to the available full trajectory. **Data & evidence → Evidence lineage** links that generated trace to its recorded experiment.

Harbor agents need their own credential configuration in their execution environment. A host researcher CLI login does not establish credentials for a sandboxed target. The stock workbench Docker image does not install Harbor or mount the host Docker socket or agent logins; [container operation](../operations/containers.md) explains that boundary.

## Equivalent CLI configuration

Save a local configuration using your actual template and targets:

```json
{
  "template_directory": "/path/to/harbor-task-template",
  "baseline": {"agent": "your_package:BaselineAgent", "model": "", "agent_kwargs": {}},
  "candidate": {"agent": "your_package:CandidateAgent", "model": "", "agent_kwargs": {}},
  "environment_type": "docker",
  "repetitions": 3,
  "reward_key": "reward",
  "pass_threshold": 1,
  "timeout": null
}
```

The package/class names are placeholders for installed implementations. Then run:

```sh
uv run agent-data-workbench workflow harbor-compare PROJECT TASK_ID harbor-comparison.json
```

`timeout` is an optional positive number of seconds per CLI invocation; omission/null adds no workbench timeout. The SDK exposes `HarborComparisonConfig` and `compare_harbor`. The typed HTTP entry point is `POST /api/workflow/harbor/compare` with a task ID and config. The lower-level `workflow harbor-export` and `workflow harbor-run` commands remain available when only an export or single configured run is needed.

## What a comparison records

One export freezes the accepted task and supplied bundle. Each repetition launches one baseline and one candidate attempt, reversing the launch order on alternate repetitions. Pairing shares the frozen task and repeat index; it does not control model randomness. The experiment is explicitly `exploratory`, with no reserved suite or held-out generalization claim.

A pass requires a finite numeric value at `verifier_result.rewards[reward_key]` meeting the threshold. A lower valid reward is a failure. A missing or malformed reward, execution exception, failed CLI invocation, or unexpected count of trial result files produces an invalid outcome. A successful CLI exit alone is never a pass.

The adapter preserves raw Harbor trial results, available `trajectory.json` objects, timing, reported cost, installed runtime identity, frozen command and job paths. Available result files become trace records grouped by task and categorized by variant. The workbench keeps full CLI stdout/stderr in local run logs, including failures. Partial trials and the experiment's error status survive an interrupted comparison.

The workbench task audit validates its own grader. It does not calibrate the external Harbor verifier. Review and test that verifier independently before treating its reward as customer value. Repeated attempts on one task are still one independent task group; use fresh representative cases for a broader improvement claim.

## Ownership and verification

`integrations/harbor/` separates contracts, CLI command construction, frozen export, runtime invocation, result interpretation and comparison orchestration. `tests/test_harbor_export.py` and `tests/test_harbor_comparison.py` exercise those contracts with synthetic processes and result files. UI tests cover configuration and evidence navigation. Real environment and provider behavior require a separate run with the supplied template and target.

Continue with [paired experiments and training](../workflows/experiments-and-training.md) or [eval engineering](../workflows/eval-engineering.md).
