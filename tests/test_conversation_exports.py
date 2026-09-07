"""Portable conversation exports retain observed behavior, not grader answers."""

import copy
import json
import sys

import pytest
from identities import uid
from test_workbench_data import accept, make_project, spec

from agent_data_workbench.conversations import ConversationSpec, UserTurn
from agent_data_workbench.experiments import make_suite, run_experiment
from agent_data_workbench.exports import export_training
from agent_data_workbench.project import digest, save
from agent_data_workbench.runners import ConfiguredRunner, RunnerConfig
from agent_data_workbench.worlds import WorldReference, WorldSpec, create_world, review_world


@pytest.fixture
def project(tmp_path):
    return make_project(tmp_path)


def export(project, run, out, kind="preference"):
    manifest = export_training(
        project,
        run["id"],
        out,
        kind=kind,
        review_note="Reviewed synthetic trajectories",
        permission_note="Synthetic test records",
    )
    return manifest, [json.loads(line) for line in (out / "data.jsonl").read_text().splitlines()]


def trajectory(turns, reported_value):
    return {
        "format": "agent-data-workbench.trajectory.v1",
        "turns": [
            {
                "index": index,
                "user": {"message": message},
                "assistant": {
                    "message": "Processed",
                    "output": {"value": 1},
                    "reported_evidence": [{"type": "reported_write", "value": reported_value}],
                },
            }
            for index, message in enumerate(turns)
        ],
    }


def actual_run(project, tmp_path):
    world = create_world(
        project,
        WorldSpec(
            name="Support",
            domain="Support",
            description="SECRET_WORLD_TRUTH",
            sources=["Synthetic policy"],
        ),
    )
    review_world(project, world["id"], "accepted", "Reviewed", "Expert")
    conversation = ConversationSpec(turns=[UserTurn(message="Start"), UserTurn(message="Cancel")])
    tasks = [
        accept(
            project,
            spec(project, key=uid(f"task-{i}"), trace_ids=[f"r{i}"], artifact=True).model_copy(
                update={
                    "conversation": conversation,
                    "world": WorldReference(id=world["id"], sha256=world["sha256"]),
                }
            ),
        )
        for i in range(3)
    ]
    manifest = make_suite(project, "Conversation export", [task.id for task in tasks])
    runners = []
    for name, outcome in (("baseline", 0), ("candidate", 1)):
        path = tmp_path / f"{name}.py"
        path.write_text(
            """import json,sys
from pathlib import Path
for line in sys.stdin:
 request=json.loads(line)
 Path("state.json").write_text(json.dumps({"value": OUTCOME}))
 print(json.dumps({"message":"Processed","output":{"value":1},
  "evidence":[{"type":"reported_write","value":OUTCOME}],"cost_usd":0.01}),flush=True)
""".replace("OUTCOME", str(outcome))
        )
        runners.append(
            ConfiguredRunner(
                RunnerConfig(
                    name=name,
                    kind="command",
                    command=[sys.executable, str(path)],
                    environment_version="synthetic-target-artifact",
                    fidelity="environment",
                ),
                tmp_path,
            )
        )
    return run_experiment(project, manifest["id"], *runners, split="optimization", repeats=2)


def test_real_continuous_sessions_export_both_observed_turns_when_final_outputs_match(
    project, tmp_path
):
    # Given: actual persistent commands report identical final output, but different tool evidence.
    run = actual_run(project, tmp_path)
    selected = next(t for t in run["task_snapshots"] if t["id"] == run["trials"][0]["task_id"])
    # When: a reviewed preference export is produced from optimization attempts.
    manifest, records = export(project, run, tmp_path / "preferences")
    record = records[0]
    # Then: observed conversations differ; hidden world/verifier data stays out of targets.
    assert {
        "count": manifest["records"],
        "input": record["input"],
        "chosen": record["chosen"],
        "rejected": record["rejected"],
        "world": record["provenance"]["world"],
        "scenario_digest": record["provenance"]["scenario_sha256"],
    } == {
        "count": 1,
        "input": {"request": "do work", "expected_input": 1},
        "chosen": trajectory(["Start", "Cancel"], 1),
        "rejected": trajectory(["Start", "Cancel"], 0),
        "world": selected["world"],
        "scenario_digest": digest(
            {
                "input": {"request": "do work", "expected_input": 1},
                "conversation": selected["conversation"],
                "world": selected["world"],
            }
        ),
    }
    assert {
        "same_final_output": run["trials"][0]["execution"]["output"]
        == run["trials"][1]["execution"]["output"],
        "secret_in_export": "SECRET_WORLD_TRUTH" in json.dumps(records),
        "reported_evidence_source": record["chosen"]["turns"][0]["assistant"]["reported_evidence"],
        "chosen_trial_digest": record["provenance"]["chosen_runtime"]["trial_sha256"],
    } == {
        "same_final_output": True,
        "secret_in_export": False,
        "reported_evidence_source": [{"type": "reported_write", "value": 1}],
        "chosen_trial_digest": digest(
            next(r for r in run["trials"] if r["variant"] == "candidate" and r["trial"] == 0)
        ),
    }


def captured_run(project):
    """Explicit recorded-attempt fixtures for malformed/partial evidence export cases."""
    task = spec(project, key=uid("captured-task")).model_copy(
        update={
            "conversation": ConversationSpec(
                turns=[UserTurn(message="Start"), UserTurn(message="Cancel")]
            )
        }
    )
    value = {
        "id": uid("captured-run"),
        "status": "complete",
        "split": "optimization",
        "baseline": {"name": "synthetic-before"},
        "candidate": {"name": "synthetic-after"},
        "task_snapshots": [task.model_dump()],
        "trials": [],
    }
    for variant, status, output in (("baseline", "fail", 0), ("candidate", "pass", 1)):
        observed = trajectory(["Start", "Cancel"], output)
        turns = [
            {
                "index": turn["index"],
                "user": turn["user"],
                "status": "completed",
                "error": None,
                "reply": {
                    "message": turn["assistant"]["message"],
                    "output": turn["assistant"]["output"],
                    "evidence": turn["assistant"]["reported_evidence"],
                    "cost_usd": 0.01,
                    "usage": {},
                },
            }
            for turn in observed["turns"]
        ]
        value["trials"].append(
            {
                "task_id": task.id,
                "trial": 0,
                "variant": variant,
                "execution": {"status": "completed", "output": {"value": 1}},
                "grade": {"status": status, "checks": [{"hidden": "SECRET_VERIFIER_TRUTH"}]},
                "state": {"private": "SECRET_AUTHORITATIVE_STATE"},
                "runtime_evidence": {
                    "conversation": {
                        "status": "completed",
                        "spec_sha256": digest(task.conversation.model_dump()),
                        "turns": turns,
                        "session_id": uid(variant),
                        "stop_reason": "script_finished",
                    }
                },
            }
        )
    save(project.path("experiments", value["id"]), value)
    return value


def test_sft_trajectory_keeps_reported_events_and_hashes_authoritative_state_only(
    project, tmp_path
):
    # Given: explicitly captured replies alongside hidden verifier and authoritative state evidence.
    run = captured_run(project)
    # When
    manifest, records = export(project, run, tmp_path / "sft", "sft")
    # Then: supervision contains observed turns; provenance references hidden truth only by hashes.
    assert {
        "count": manifest["records"],
        "chosen": records[0]["chosen"],
        "state_hash": records[0]["provenance"]["chosen_runtime"]["authoritative_state_sha256"],
        "secret_in_json": "SECRET_" in json.dumps(records),
        "has_rejected": "rejected" in records[0],
    } == {
        "count": 1,
        "chosen": trajectory(["Start", "Cancel"], 1),
        "state_hash": digest({"private": "SECRET_AUTHORITATIVE_STATE"}),
        "secret_in_json": False,
        "has_rejected": False,
    }


def test_identical_trajectories_do_not_become_self_contradicting_preferences(project, tmp_path):
    # Given: opposite grader labels whose observed conversations are identical.
    run = captured_run(project)
    run["trials"][0]["runtime_evidence"]["conversation"]["turns"] = copy.deepcopy(
        run["trials"][1]["runtime_evidence"]["conversation"]["turns"]
    )
    # Timing/session differences do not create a behavioral preference.
    run["trials"][0]["runtime_evidence"]["conversation"]["turns"][0]["reply"]["cost_usd"] = 999
    save(project.path("experiments", run["id"]), run)
    # When / Then
    with pytest.raises(ValueError, match="No eligible"):
        export(project, run, tmp_path / "identical")
    assert {"output_created": (tmp_path / "identical").exists()} == {"output_created": False}


@pytest.mark.parametrize(
    "damage", ["missing", "partial", "spec_changed", "script_truncated", "invalid"]
)
def test_unverifiable_or_invalid_conversations_never_fall_back_to_final_output(
    project, tmp_path, damage
):
    # Given: a passing chosen attempt with incomplete or untrustworthy conversation capture.
    run = captured_run(project)
    chosen = run["trials"][1]
    observed = chosen["runtime_evidence"]["conversation"]
    if damage == "missing":
        chosen["runtime_evidence"] = {}
    elif damage == "partial":
        observed["turns"][-1]["reply"] = None
    elif damage == "spec_changed":
        observed["spec_sha256"] = "changed"
    elif damage == "script_truncated":
        observed["turns"].pop()
    else:
        chosen["grade"]["status"] = "invalid"
    save(project.path("experiments", run["id"]), run)
    # When / Then: identical last outputs cannot hide missing trajectory evidence.
    with pytest.raises(ValueError, match="No eligible"):
        export(project, run, tmp_path / "ineligible")
    assert {"output_created": (tmp_path / "ineligible").exists()} == {"output_created": False}


@pytest.mark.parametrize("scenario", ["conversation", "world", "environment"])
def test_same_input_in_distinct_scenarios_is_not_deduplicated(project, tmp_path, scenario):
    # Given: recorded attempts share visible input but have distinct scenario semantics.
    run = captured_run(project)
    second = copy.deepcopy(run["task_snapshots"][0])
    second["id"] = uid("second-task")
    if scenario == "conversation":
        second["conversation"]["turns"][-1]["message"] = "Change my booking"
    elif scenario == "world":
        second["world"] = {"id": uid("second-world"), "sha256": "a" * 64}
    else:
        second["fidelity"] = "environment"
        second["environment"] = {
            "name": "Other service",
            "version": "v2",
            "authority": "Synthetic API",
            "setup": ["setup"],
            "reset": ["reset"],
            "ready": ["ready"],
            "inspect": ["inspect"],
        }
    run["task_snapshots"].append(second)
    for row in copy.deepcopy(run["trials"]):
        row["task_id"] = second["id"]
        if scenario == "conversation":
            observed = row["runtime_evidence"]["conversation"]
            observed["turns"][-1]["user"]["message"] = "Change my booking"
            observed["spec_sha256"] = digest(second["conversation"])
        run["trials"].append(row)
    save(project.path("experiments", run["id"]), run)
    # When
    manifest, records = export(project, run, tmp_path / scenario)
    # Then: task source identities and both independently classified scenarios are retained.
    assert {
        "records": manifest["records"],
        "tasks": sorted(r["provenance"]["task_id"] for r in records),
        "unique_scenarios": len({r["provenance"]["scenario_sha256"] for r in records}),
    } == {
        "records": 2,
        "tasks": sorted([run["task_snapshots"][0]["id"], second["id"]]),
        "unique_scenarios": 2,
    }


def test_legacy_one_shot_shape_and_optimization_gate_are_preserved(project, tmp_path):
    # Given: pre-conversation one-shot attempt records with a distinct winning output.
    run = captured_run(project)
    task = run["task_snapshots"][0]
    task["conversation"] = None
    for row in run["trials"]:
        row["runtime_evidence"] = {}
        row["execution"]["output"] = {"value": int(row["variant"] == "candidate")}
    save(project.path("experiments", run["id"]), run)
    # When
    _, records = export(project, run, tmp_path / "legacy")
    # Then: no new training wrapper is introduced for legacy one-shot consumers.
    assert records == [
        {
            "input": {"request": "do work", "expected_input": 1},
            "chosen": {"value": 1},
            "rejected": {"value": 0},
            "provenance": {
                "experiment_id": run["id"],
                "task_id": task["id"],
                "trace_ids": ["r0"],
                "trial": 0,
                "split": "optimization",
                "label_source": "reviewed_task_verifier",
                "verifier_sha256": digest(task["criteria"]),
                "chosen_variant": "candidate",
            },
        }
    ]
    # When / Then: moving the source to a held-out role still excludes training export.
    run["split"] = "final"
    save(project.path("experiments", run["id"]), run)
    with pytest.raises(ValueError, match="optimization"):
        export(project, run, tmp_path / "final")
