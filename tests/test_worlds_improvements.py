"""Reviewed specifications and exact candidate changes remain connected to evidence."""

import sys

import pytest
from test_workbench_data import accept, make_project, spec

from agent_data_workbench.evaluation.experiments import run_experiment
from agent_data_workbench.evaluation.improvements import (
    create_improvement,
    decide_improvement,
    verify_candidate,
)
from agent_data_workbench.evaluation.suites import make_suite
from agent_data_workbench.evaluation.tasks.repository import load_task, task_digest
from agent_data_workbench.evaluation.worlds import (
    WorldReference,
    WorldSpec,
    create_world,
    resolve_world,
    review_world,
)
from agent_data_workbench.execution.contracts import RunnerConfig
from agent_data_workbench.execution.runners import ConfiguredRunner
from agent_data_workbench.shared.files import save
from agent_data_workbench.shared.json import digest


def test_world_versions_pin_reviewed_domain_truth_and_reject_unresolved_context(tmp_path):
    # Given a sourced domain specification with unresolved permissions.
    project = make_project(tmp_path)
    first = create_world(
        project,
        WorldSpec(
            name="Support",
            domain="support",
            description="Ticket workflows",
            sources=["Reviewed service contract"],
            unresolved_questions=["Who may close a ticket?"],
        ),
    )
    # When acceptance is attempted before the knowledge is resolved.
    with pytest.raises(ValueError, match="Resolve world questions"):
        review_world(project, first["id"], "accepted", "Ready", "Domain owner")
    second = create_world(
        project,
        WorldSpec(
            name="Support",
            domain="support",
            description="Ticket workflows",
            sources=["Reviewed service contract"],
            permissions=["Only assigned users may close"],
        ),
        first["id"],
    )
    accepted = review_world(project, second["id"], "accepted", "Checked contract", "Domain owner")
    actual = resolve_world(project, WorldReference(id=second["id"], sha256=second["sha256"]))
    # Then the old draft and the new accepted version have independent identities.
    assert {
        "resolved": actual,
        "revision": actual["revision"],
        "parent": actual["previous_id"],
        "context_world_ids": [w["id"] for w in project.context()["worlds"]],
    } == {
        "resolved": accepted,
        "revision": 2,
        "parent": first["id"],
        "context_world_ids": [second["id"]],
    }
    with pytest.raises(ValueError, match="digest"):
        resolve_world(project, WorldReference(id=second["id"], sha256="0" * 64))


def test_task_digest_preserves_existing_accepted_specifications(tmp_path):
    # Given a task created before world and state support.
    project = make_project(tmp_path)
    task = spec(project)
    legacy = task.model_dump()
    for key in ("world", "environment", "conversation"):
        legacy.pop(key)
    for example in legacy["verifier_examples"]:
        example.pop("state_json")
    accepted = accept(project, task)
    # When its current digest and accepted representation are read.
    loaded = load_task(project, accepted.id, accepted=True)[1]
    # Then adding optional workflow fields has not silently invalidated its original hash.
    assert {"sha256": task_digest(loaded), "legacy_sha256": digest(legacy)} == {
        "sha256": digest(legacy),
        "legacy_sha256": digest(legacy),
    }


def targets(tmp_path):
    runners = []
    for name, value in (("baseline", 0), ("candidate", 1)):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "agent.py").write_text(
            "import json,sys\njson.load(sys.stdin)\n"
            f'print(json.dumps({{"output":{{"value":{value}}}}}))\n'
        )
        config = RunnerConfig(
            name=name,
            kind="command",
            command=[sys.executable, "agent.py"],
            environment_version="synthetic-v1",
        )
        save(folder / "runner.json", config.model_dump())
        runners.append(ConfiguredRunner(config, folder))
    return runners


def test_exact_candidate_patch_is_evaluated_then_human_records_a_decision(tmp_path):
    # Given three independent source groups and a real local command change.
    project = make_project(tmp_path)
    tasks = [
        accept(project, spec(project, key=f"change-{i}", trace_ids=[f"r{i}"])) for i in range(3)
    ]
    suite = make_suite(project, "Fresh grouped cases", [task.id for task in tasks])
    baseline, candidate = targets(tmp_path)
    change = create_improvement(
        project,
        "Correct result",
        "Return the actual result",
        "value becomes one",
        baseline,
        candidate,
        trace_ids=["r0"],
        task_ids=[tasks[0].id],
    )
    # When the exact snapshot runs on validation and receives an explicit local decision.
    experiment = run_experiment(
        project, suite["id"], baseline, candidate, improvement_id=change["id"]
    )
    decided = decide_improvement(
        project,
        change["id"],
        experiment["id"],
        "keep",
        "Developer",
        "Synthetic expected change observed",
    )
    # Then evidence and patch stay linked; no deployment is implied.
    assert {
        "linked": experiment["improvement"],
        "outcomes": [(r["variant"], r["grade"]["status"]) for r in experiment["trials"]],
        "source_names": sorted(
            name for name in change["candidate"]["sources"] if name == "agent.py"
        ),
        "patch_has_source": "candidate/agent.py" in change["patch"],
        "decision": decided["decisions"][-1]["decision"],
        "decision_evidence": decided["decisions"][-1]["experiment_sha256"],
    } == {
        "linked": {"id": change["id"], "sha256": change["sha256"]},
        "outcomes": [("baseline", "fail"), ("candidate", "pass")],
        "source_names": ["agent.py"],
        "patch_has_source": True,
        "decision": "keep",
        "decision_evidence": digest(experiment),
    }
    # When source code changes after capture, the frozen candidate cannot be reused.
    (candidate.base_dir / "agent.py").write_text('print("changed")\n')
    with pytest.raises(ValueError, match="source changed"):
        verify_candidate(project, change["id"], baseline, candidate)


def test_research_uses_accepted_world_heads_without_rewriting_historical_references(tmp_path):
    # Given two accepted revisions of the same domain knowledge.
    project = make_project(tmp_path)
    old = create_world(
        project, WorldSpec(name="World", domain="domain", description="Old rule", sources=["Spec"])
    )
    review_world(project, old["id"], "accepted", "Reviewed", "Owner")
    new = create_world(
        project,
        WorldSpec(name="World", domain="domain", description="New rule", sources=["Spec"]),
        old["id"],
    )
    review_world(project, new["id"], "accepted", "Reviewed revision", "Owner")
    # When researchers read current context while an old task resolves its pinned world.
    heads = project.context()["worlds"]
    historical = resolve_world(project, WorldReference(id=old["id"], sha256=old["sha256"]))
    # Then only the successor is injected; the predecessor stays reproducible by reference.
    assert {"head_ids": [w["id"] for w in heads], "historical_spec": historical["spec"]} == {
        "head_ids": [new["id"]],
        "historical_spec": old["spec"],
    }


def test_one_suite_runs_distinct_reviewed_conversations_with_same_target_version(tmp_path):
    from agent_data_workbench.execution.contracts import ConversationSpec, UserTurn

    # Given one target harness and nine separately reviewed conversation scenarios.
    project = make_project(tmp_path)
    source = tmp_path / "session.py"
    source.write_text(
        "import json,sys\nfor line in sys.stdin:\n r=json.loads(line)\n"
        ' print(json.dumps({"message":r["message"],"output":{"value":1}}),flush=True)\n'
    )
    tasks = []
    for i in range(9):
        task = spec(project, key=f"session-{i}", trace_ids=[f"r{i}"])
        task.conversation = ConversationSpec(
            turns=[UserTurn(message=f"Step {n}") for n in range(i + 1)]
        )
        tasks.append(accept(project, task))
    manifest = make_suite(project, "Varied conversations", [t.id for t in tasks])
    runners = [
        ConfiguredRunner(
            RunnerConfig(
                name=name,
                kind="command",
                command=[sys.executable, str(source)],
                environment_version="v1",
            ),
            tmp_path,
        )
        for name in ("baseline", "candidate")
    ]
    # When the suite binds each frozen scenario to the same unmodified command harness.
    experiment = run_experiment(project, manifest["id"], *runners)
    by_id = {task.id: task for task in tasks}
    observed = [
        {
            "task_id": row["task_id"],
            "variant": row["variant"],
            "grade": row["grade"]["status"],
            "turns": len(row["runtime_evidence"]["conversation"]["turns"]),
            "scenario": row["runner_identity"]["config"]["conversation"],
        }
        for row in experiment["trials"]
    ]
    expected = [
        {
            "task_id": row["task_id"],
            "variant": row["variant"],
            "grade": "pass",
            "turns": len(by_id[row["task_id"]].conversation.turns),
            "scenario": by_id[row["task_id"]].conversation.model_dump(),
        }
        for row in experiment["trials"]
    ]
    # Then every run records the effective reviewed scenario and full conversation.
    assert {"trials": observed, "base_scenarios": [r.config.conversation for r in runners]} == {
        "trials": expected,
        "base_scenarios": [None, None],
    }
