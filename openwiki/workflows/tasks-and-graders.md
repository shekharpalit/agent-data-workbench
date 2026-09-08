---
type: workflow
title: Tasks and grader review
description: Convert investigated evidence or explicit specifications into draft tasks, validate grader behavior, and preserve the review history required for experiments.
tags: [tasks, graders, review, replay, evidence]
sources:
  - id: openwiki-source-52eab09bd9973949325f2e9e
    resource: repo://src/agent_data_workbench/evaluation/tasks/contracts.py
  - id: openwiki-source-b89c31d236f340bd64f3fd31
    resource: repo://src/agent_data_workbench/evaluation/tasks/design.py
  - id: openwiki-source-7873eadc6e06d9c18f47371a
    resource: repo://src/agent_data_workbench/evaluation/tasks/grading.py
  - id: openwiki-source-6574208c922e293382d49e13
    resource: repo://src/agent_data_workbench/evaluation/tasks/replay.py
  - id: openwiki-source-0c67ad46a6bd6ff73934e82d
    resource: repo://src/agent_data_workbench/evaluation/tasks/repository.py
  - id: openwiki-source-2dbe8753da4267ce652f414e
    resource: repo://src/agent_data_workbench/research/workspace.py
  - id: openwiki-source-3589dc1fc29ba0bfe0e2a50c
    resource: repo://tests/test_research.py
generated: { by: "codex", at: "2026-09-08T00:07:39.310Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-08T00:07:39.310Z
---

# Tasks and grader review

A task describes what the target sees, which behavior matters, and how its result will be judged. Task creation produces a draft. A passing verifier audit and an explicit review are separate requirements for acceptance.

The `evaluation/tasks/` package separates schema validation (`contracts.py`), persistence and review (`repository.py`), grading and verifier audits (`grading.py`), model-assisted design (`design.py`), and trace-prefix replay (`replay.py`). Shared JSON equality and pointer resolution live in `shared/json.py`. This keeps changing a grader separate from changing task storage or creation.

## Choose a creation route

| Route | Use it when | Command |
| --- | --- | --- |
| Native publication | The research agent has grounded task candidates in its snapshot. | MCP `publish_tasks` or Python `ResearchWorkspace.publish_tasks` |
| Design | A completed investigation has useful findings and reviewed context. | `task design PROJECT INVESTIGATION_ID --backend codex` |
| Import | You have authored a complete TaskSpec JSON. | `task import PROJECT ./task.json` |
| Replay | A chat trace contains the decision boundary you want to test. | `task replay PROJECT TRACE_ID CUTOFF` |

Native publication has no fixed task-count cap. It checks unique task IDs, source trace membership and any finding references, binds the captured context hash, and creates drafts. It can use any trace in the investigation snapshot and works alongside draft findings. Accepted-task checks still require current reviewed context before a task enters a suite.

Prefix commands with `uv run agent-data-workbench`. The separate one-shot Design command accepts `--backend claude` and optional `--model MODEL`. It rejects incomplete investigations or changed reviewed context, limits a response to five uniquely identified tasks, and checks that referenced findings and traces belong to the investigation. Generated tasks remain draft.

Replay copies only `messages[:cutoff]`, with an exclusive cutoff before an existing later message. It does not copy the later conversation or unrelated trace fields. The result deliberately contains missing-context reminders and an underspecified criterion; replace those before auditing and reviewing it.

## Understand the task contract

Task and criterion IDs are canonical UUID strings. Finding references use UUIDs too; trace references retain the original source IDs. Use `uv run python -m uuid` to generate an ID for a manually authored specification. The CLI prints generated IDs for design and replay.

A TaskSpec includes an ID, title, purpose, behavior, source trace IDs, optional finding lineage, fidelity, visible input, assumptions, missing context, criteria and verifier examples. Optional `world` pins an accepted UUID/digest; `environment` defines its reproducible lifecycle and observer; `conversation` defines scripted or reactive user turns.

| Fidelity | What the task claims to measure |
| --- | --- |
| `output` | The target's returned result. |
| `next_action` | A decision from a nonempty saved conversation prefix. |
| `environment` | Behavior using a command adapter and the fixtures or state it supplies. |

Fidelity is a declared contract. Choosing `environment` does not create a container, reconstruct a production system, or make target-written state independently trustworthy.

`input_json` is a string encoding a JSON object, containing only agent-visible input and fixtures. Keep answers, criteria, and hidden task details outside it. The schema checks object shape and next-action message presence; human review must still detect answer leakage.

Criteria read the output object, a named relative target JSON artifact, or independently observed state with `source: "state"`. State criteria require a configured environment and use the `artifact` name as a key into the observer map; target-written artifacts and usage cannot satisfy them. Assertion pointers address the future result or artifact, not the source trace. An example assertion criterion is:

```json
{
  "id": "a9be7944-4099-43b9-9b4a-b2cb7e78a22a",
  "description": "Preserve the actual operation status",
  "source": "output",
  "kind": "assertion",
  "assertion": {
    "pointer": "/status",
    "operator": "equals",
    "expected": "\"declined\""
  }
}
```

For `equals`, `expected` is a JSON-encoded value; a string therefore includes encoded quotes. Text containment uses literal text. `exists` requires an empty expected string. Semantic criteria supply a nonempty rubric instead of an assertion.

## Audit the grader

Provide verifier examples for all five base categories; state criteria also require a `collateral_change` example expected to fail:

| Kind | Required expected behavior |
| --- | --- |
| Valid | Pass a correct result. |
| Alternative | Pass a different valid result. |
| Mistake | Fail a realistic error. |
| Shortcut | Fail a superficial attempt that misses the objective. |
| Missing evidence | Fail or mark invalid, according to which evidence is absent. |

Run deterministic audits without a provider:

```sh
uv run agent-data-workbench task audit runs/my-agent TASK_ID
```

For semantic criteria, configure the judge explicitly:

```sh
uv run agent-data-workbench task audit runs/my-agent TASK_ID \
  --judge codex --model MODEL
```

An audit passes only when all categories are present and every observed label matches its expected label, including positive and negative examples. It records the specification hash and judge identity. These synthetic sanity fixtures are not a substitute for domain review.

## Keep invalid evidence distinct

A missing field in an existing output can fail an assertion. A missing whole required artifact or observer-state entry produces an invalid observation. Semantic criteria without a judge, failed judge calls, or unverifiable evidence also remain invalid.

For a semantic pass or fail, the judge must return exact quotes with `trace_id="result"` and JSON pointers into the judged result. The host verifies those quotes. This grounds the decision in supplied data; it does not prove the rubric or interpretation is correct. Any invalid criterion makes the overall task grade invalid.

## Review and revise

After checking the task's purpose, visible input, criteria, examples, and source evidence:

```sh
uv run agent-data-workbench task review runs/my-agent TASK_ID accepted \
  "Reviewed behavior, fixtures, alternatives, and evidence requirements"
```

Acceptance requires no unresolved `missing_context`, a passing audit of the current specification, a current context hash when bound, and an exact accepted world reference when supplied. Review notes and specification hashes are retained.

To revise a task, keep its ID and supply the new specification:

```sh
uv run agent-data-workbench task edit runs/my-agent TASK_ID ./revised-task.json \
  "Clarified the expected tool outcome"
```

Editing preserves the old specification as a revision, clears the audit, and returns review to draft. Audit and accept again. Loading an accepted task for a suite or experiment rechecks its specification, audit, and bound context rather than trusting an old acceptance flag.

## Verification and next steps

`tests/test_workbench_data.py` covers audit categories, missing context, stale acceptance, prefix replay, semantic evidence, and design lineage.

Next: [freeze a suite and execute targets](experiments-and-training.md). Return to [investigations](investigations.md) when the task exposes missing policy or unsupported assumptions.

## Review state and collaboration behavior

State verifier examples carry `state_json`, independently of `output_json` and `artifacts_json`. Include correct state, a valid alternative, a plausible wrong state, a misleading success claim, prohibited collateral changes and missing evidence. Whole-object equality at pointer `""` can check an expected record together with protected fields. The runtime independently invokes the configured observer; the example data only audits grader behavior.

A saved chat prefix remains a next-action task. To measure continued collaboration, provide a `conversation` and a persistent command target. Each task may define different follow-up turns within the same suite. [Eval engineering](eval-engineering.md) explains world versions, environment phases, NDJSON target sessions and reactive users.

After actual execution, create a calibration and compare independent human labels with the grader. False passes/fails and disputed labels help distinguish a bad task/verifier from a weak agent. Revising a task invalidates its audit and acceptance; old experiment/calibration evidence stays frozen. Existing task digests remain compatible when the new optional fields are absent.
