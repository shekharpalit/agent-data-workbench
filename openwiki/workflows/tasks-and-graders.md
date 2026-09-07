---
type: workflow
title: Tasks and grader review
description: Convert investigated evidence or explicit specifications into draft tasks, validate grader behavior, and preserve the review history required for experiments.
tags: [tasks, graders, review, replay, evidence]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T17:18:36.762Z
sources:
  - id: openwiki-source-b486bbac4ad50f2085fcbadb
    resource: repo://src/agent_data_workbench/tasks.py
  - id: openwiki-source-9dba1709c16fd704c45276e9
    resource: repo://tests/test_workbench_data.py
generated: { by: "codex", at: "2026-09-07T17:18:36.762Z" }
---

# Tasks and grader review

A task describes what the target sees, which behavior matters, and how its result will be judged. Task creation produces a draft. A passing verifier audit and an explicit review are separate requirements for acceptance.

## Choose a creation route

| Route | Use it when | Command |
| --- | --- | --- |
| Design | A completed investigation has useful findings and reviewed context. | `task design PROJECT INVESTIGATION_ID --backend codex` |
| Import | You have authored a complete TaskSpec JSON. | `task import PROJECT ./task.json` |
| Replay | A chat trace contains the decision boundary you want to test. | `task replay PROJECT TRACE_ID CUTOFF` |

Prefix commands with `uv run agent-data-workbench`. Design accepts `--backend claude` and optional `--model MODEL`. It rejects incomplete investigations or changed reviewed context, limits a response to five uniquely identified tasks, and checks that referenced findings and traces belong to the investigation. Generated tasks remain draft.

Replay copies only `messages[:cutoff]`, with an exclusive cutoff before an existing later message. It does not copy the later conversation or unrelated trace fields. The result deliberately contains missing-context reminders and an underspecified criterion; replace those before auditing and reviewing it.

## Understand the task contract

A TaskSpec includes an ID, title, purpose, behavior, source trace IDs, optional finding lineage, fidelity, visible input, assumptions, missing context, criteria, and verifier examples.

| Fidelity | What the task claims to measure |
| --- | --- |
| `output` | The target's returned result. |
| `next_action` | A decision from a nonempty saved conversation prefix. |
| `environment` | Behavior using a command adapter and the fixtures or state it supplies. |

Fidelity is a declared contract. Choosing `environment` does not create a container, reconstruct a production system, or make target-written state independently trustworthy.

`input_json` is a string encoding a JSON object, containing only agent-visible input and fixtures. Keep answers, criteria, and hidden task details outside it. The schema checks object shape and next-action message presence; human review must still detect answer leakage.

Criteria read either the output object or a named relative JSON artifact. Assertion pointers address the future result or artifact, not the source trace. An example assertion criterion is:

```json
{
  "id": "C1",
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

Provide verifier examples for all five required categories:

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

A missing field in an existing output can fail an assertion. A missing whole required artifact produces an invalid observation. Semantic criteria without a judge, failed judge calls, or unverifiable evidence also remain invalid.

For a semantic pass or fail, the judge must return exact quotes with `trace_id="result"` and JSON pointers into the judged result. The host verifies those quotes. This grounds the decision in supplied data; it does not prove the rubric or interpretation is correct. Any invalid criterion makes the overall task grade invalid.

## Review and revise

After checking the task's purpose, visible input, criteria, examples, and source evidence:

```sh
uv run agent-data-workbench task review runs/my-agent TASK_ID accepted \
  "Reviewed behavior, fixtures, alternatives, and evidence requirements"
```

Acceptance requires no unresolved `missing_context`, a passing audit of the current specification, and a current context hash when the task binds one. Review notes and specification hashes are retained.

To revise a task, keep its ID and supply the new specification:

```sh
uv run agent-data-workbench task edit runs/my-agent TASK_ID ./revised-task.json \
  "Clarified the expected tool outcome"
```

Editing preserves the old specification as a revision, clears the audit, and returns review to draft. Audit and accept again. Loading an accepted task for a suite or experiment rechecks its specification, audit, and bound context rather than trusting an old acceptance flag.

## Verification and next steps

`tests/test_workbench_data.py` covers audit categories, missing context, stale acceptance, prefix replay, semantic evidence, and design lineage.

Next: [freeze a suite and execute targets](experiments-and-training.md). Return to [investigations](investigations.md) when the task exposes missing policy or unsupported assumptions.
