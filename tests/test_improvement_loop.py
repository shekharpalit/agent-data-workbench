"""Credential-free integration of the full reviewed, measured improvement workflow."""

import json
import sys

from fastapi.testclient import TestClient
from test_workbench_data import Source

from agent_data_workbench.analysis.contracts import Analysis, Evidence, Finding
from agent_data_workbench.api import create_app
from agent_data_workbench.data.store import TraceStore
from agent_data_workbench.evaluation.calibration import (
    AttemptLabel,
    calibration_summary,
    create_calibration,
    label_attempt,
)
from agent_data_workbench.evaluation.contracts import Assertion
from agent_data_workbench.evaluation.coverage import (
    Capability,
    CoverageMapping,
    TaxonomySpec,
    coverage_report,
    create_taxonomy,
    map_coverage,
    review_taxonomy,
)
from agent_data_workbench.evaluation.experiments import run_experiment
from agent_data_workbench.evaluation.improvements import create_improvement, decide_improvement
from agent_data_workbench.evaluation.suites import make_suite
from agent_data_workbench.evaluation.tasks.contracts import Criterion, TaskSpec, VerifierExample
from agent_data_workbench.evaluation.tasks.grading import audit_task, grade
from agent_data_workbench.evaluation.tasks.repository import review_task, write_task
from agent_data_workbench.evaluation.worlds import (
    WorldReference,
    WorldSpec,
    create_world,
    review_world,
)
from agent_data_workbench.execution.contracts import (
    ConversationSpec,
    EnvironmentConfig,
    RunnerConfig,
    UserTurn,
)
from agent_data_workbench.execution.runners import ConfiguredRunner
from agent_data_workbench.research import ResearchWorkspace
from agent_data_workbench.research.artifacts import start_investigation
from agent_data_workbench.research.contracts import ResearchResult
from agent_data_workbench.research.workspace import RecordOutcome
from agent_data_workbench.shared.identifiers import new_id
from agent_data_workbench.shared.json import digest
from agent_data_workbench.workspace.project import Project


def test_cancellation_failure_becomes_reviewed_multiturn_eval_and_measured_candidate(tmp_path):
    # Given a synthetic observed cancellation failure and independent fresh source groups.
    project = Project.create(tmp_path / "project", "Booking", "Honor cancellation")
    TraceStore(project).ingest(
        Source(
            [
                {
                    "trace_id": f"case-{i}",
                    "thread_id": f"thread-{i}",
                    "messages": [{"role": "user", "content": "Cancel my booking"}],
                    "observed_state": {"seats": 2, "price": 42},
                }
                for i in range(3)
            ]
        )
    )
    world = create_world(
        project,
        WorldSpec(
            name="Booking",
            domain="ticketing",
            description="Reviewed synthetic booking contract",
            sources=["Synthetic service contract in this test"],
            invariants=["Cancellation leaves zero seats; price is unchanged"],
        ),
    )
    review_world(project, world["id"], "accepted", "Checked service contract", "Domain reviewer")
    investigation = start_investigation(
        project, "Why was the booking not cancelled?", exclude_final=True
    )
    workspace = ResearchWorkspace(project, investigation["id"])
    workspace.read("case-0", pointer="/observed_state")
    workspace.record_outcomes(
        [
            RecordOutcome(
                trace_id="case-0",
                output={"failure": "cancellation ignored"},
                method="Human state review",
            )
        ]
    )
    finding = Finding(
        id=new_id(),
        title="Cancellation ignored",
        category="failure",
        confidence="observation",
        explanation="Seats remain after the cancellation request",
        recommendation="Handle followups",
        evidence=[Evidence(trace_id="case-0", pointer="/observed_state/seats", quote="2")],
    )
    workspace.publish(
        ResearchResult(
            analysis=Analysis(
                summary="Ignored cancellation",
                findings=[finding],
                cases=[],
                limitations=["Synthetic evidence"],
            ),
            signals=[],
            proposals=[],
            open_questions=[],
        )
    )
    # Trusted lifecycle commands own the state that an independently invoked observer reads.
    service = tmp_path / "service.py"
    service.write_text("""import json,sys
from pathlib import Path
r=json.load(sys.stdin); state=Path(r["state_dir"])/"store.json"
if r["phase"]=="setup": out={"target_context":{"store":str(state)}}
elif r["phase"]=="reset":
 state.write_text(json.dumps({"seats":0,"price":42})); out={"reset":True}
elif r["phase"]=="ready": out={"ready":state.exists()}
elif r["phase"]=="inspect": out={"artifacts":{"booking.json":json.loads(state.read_text())}}
else: out={}
print(json.dumps(out))
""")
    argv = [sys.executable, str(service)]
    environment = EnvironmentConfig(
        name="Booking service",
        version="synthetic-v1",
        authority="Synthetic booking state store",
        setup=argv,
        reset=argv,
        ready=argv,
        inspect=argv,
        teardown=argv,
        initial_state_sha256=digest({"booking.json": {"seats": 0, "price": 42}}),
    )
    conversation = ConversationSpec(
        turns=[UserTurn(message="Book two seats"), UserTurn(message="Cancel my booking")]
    )
    expected = {"booking.json": {"seats": 0, "price": 42}}
    examples = [
        VerifierExample(
            name=kind,
            kind=kind,
            output_json='{"claimed":"cancelled"}',
            state_json=json.dumps(state),
            expected=outcome,
        )
        for kind, state, outcome in [
            ("valid", expected, "pass"),
            ("alternative", expected, "pass"),
            ("mistake", {"booking.json": {"seats": 2, "price": 42}}, "fail"),
            ("shortcut", {"booking.json": {"seats": 2, "price": 42}}, "fail"),
            ("collateral_change", {"booking.json": {"seats": 0, "price": 0}}, "fail"),
            ("missing_evidence", {}, "invalid"),
        ]
    ]
    tasks = []
    for i in range(3):
        task = TaskSpec(
            id=new_id(),
            title="Cancel a booking",
            purpose="Honor user corrections",
            behavior="cancellation",
            trace_ids=[f"case-{i}"],
            finding_ids=[finding.id] if i == 0 else [],
            fidelity="environment",
            input_json='{"event":"synthetic"}',
            world=WorldReference(id=world["id"], sha256=world["sha256"]),
            environment=environment,
            conversation=conversation,
            criteria=[
                Criterion(
                    id=new_id(),
                    description="Booking is cancelled without changing price",
                    source="state",
                    artifact="booking.json",
                    assertion=Assertion(
                        pointer="",
                        operator="equals",
                        expected='{"seats":0,"price":42}',
                    ),
                )
            ],
            verifier_examples=examples,
        )
        write_task(project, task, origin=investigation["id"] if i == 0 else "fresh synthetic case")
        audit_task(project, task.id)
        review_task(
            project, task.id, "accepted", "Checked trace, state contract and counterexamples"
        )
        tasks.append(task)
    suite = make_suite(project, "Independent cancellation cases", [t.id for t in tasks])
    runners = []
    for name, handles_cancel in (("baseline", False), ("candidate", True)):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "agent.py").write_text(
            """import json,sys
from pathlib import Path
state=None
for line in sys.stdin:
 r=json.loads(line)
 if r["turn_index"]==0:
  state=Path(r["input"]["environment_context"]["store"])
 value=json.loads(state.read_text())
 value["seats"]=0 if HANDLE_CANCEL and r["turn_index"]>0 else 2
 state.write_text(json.dumps(value))
 print(json.dumps({"message":"Processed", "output":{"claimed":"cancelled"},
  "evidence":[{"type":"store_write","seats":value["seats"]}]}),flush=True)
""".replace("HANDLE_CANCEL", str(handles_cancel))
        )
        runners.append(
            ConfiguredRunner(
                RunnerConfig(
                    name=name,
                    kind="command",
                    command=[sys.executable, "agent.py"],
                    environment_version="synthetic-v1",
                    fidelity="environment",
                    environment=environment,
                    conversation=conversation,
                ),
                folder,
            )
        )
    change = create_improvement(
        project,
        "Honor cancellation",
        "Handle the second turn in the same session",
        "Remove reserved seats while preserving price",
        *runners,
        trace_ids=["case-0"],
        task_ids=[tasks[0].id],
    )
    # When a candidate runs on a reserved execution split and humans calibrate every attempt.
    experiment = run_experiment(project, suite["id"], *runners, improvement_id=change["id"])
    calibration = create_calibration(project, experiment["id"], "Independent state review")
    for attempt in calibration["attempts"]:
        row = attempt["evidence"]["trial"]
        label_attempt(
            project,
            calibration["id"],
            AttemptLabel(
                task_id=attempt["task_id"],
                trial=attempt["trial"],
                variant=attempt["variant"],
                evidence_sha256=attempt["evidence_sha256"],
                reviewer="Domain reviewer",
                status="pass" if row["state"] == expected else "fail",
                reason="Compared actual store state",
            ),
        )
    decision = decide_improvement(
        project,
        change["id"],
        experiment["id"],
        "keep",
        "Developer",
        "Synthetic cancellation repaired; real deployment still unmeasured",
    )
    capability = Capability(
        id=new_id(),
        name="User corrections",
        description="Honor cancellation",
        required_slices=["cancel", "clarify"],
    )
    taxonomy = create_taxonomy(
        project, TaxonomySpec(name="Booking skills", capabilities=[capability])
    )
    review_taxonomy(project, taxonomy["id"], "accepted", "Reviewed scope", "Domain reviewer")
    for task in tasks:
        # Only map validation/optimization cases: do not expose the reserved final case.
        if next(t["split"] for t in suite["tasks"] if t["id"] == task.id) == "final":
            continue
        map_coverage(
            project,
            taxonomy["id"],
            CoverageMapping(
                kind="task",
                entity_id=task.id,
                capability_id=capability.id,
                slice="cancel",
                rationale="Tests cancellation after a reservation",
                source="Reviewed task",
                reviewer="Domain reviewer",
            ),
        )
    coverage = coverage_report(project, taxonomy["id"])
    # Then independent state, continuous turns, exact patch and human judgment stay connected.
    assert {
        "status": experiment["status"],
        "grades": [(r["variant"], r["grade"]["status"]) for r in experiment["trials"]],
        "claimed_outputs": [r["execution"]["output"] for r in experiment["trials"]],
        "observer_states": [r["state"] for r in experiment["trials"]],
        "candidate_change": experiment["improvement"],
        "world_ids": list(experiment["world_snapshots"]),
        "decision": decision["decisions"][-1]["decision"],
        "captured_conversations": [
            bool(r["runtime_evidence"]["conversation"]) for r in experiment["trials"]
        ],
        "missing_state": grade(tasks[0], {"claimed": "cancelled"}, expected)["status"],
    } == {
        "status": "complete",
        "grades": [("baseline", "fail"), ("candidate", "pass")],
        "claimed_outputs": [{"claimed": "cancelled"}, {"claimed": "cancelled"}],
        "observer_states": [{"booking.json": {"seats": 2, "price": 42}}, expected],
        "candidate_change": {"id": change["id"], "sha256": change["sha256"]},
        "world_ids": [world["id"]],
        "decision": "keep",
        "captured_conversations": [True, True],
        "missing_state": "invalid",
    }
    # The same records and typed writes are accessible through the human UI API.
    origin = "http://127.0.0.1:8765"
    with TestClient(
        create_app(project, origin=origin, token="test"),
        base_url=origin,
        headers={"Authorization": "Bearer test", "Origin": origin},
    ) as client:
        assert client.get(f"/api/workflow/calibration/{calibration['id']}").json() == {
            "calibration": project.artifacts("calibrations")[0],
            "summary": calibration_summary(project, calibration["id"]),
        }
        actual_coverage = client.get(f"/api/workflow/coverage/{taxonomy['id']}").json()
        assert actual_coverage == {**coverage, "generated_at": actual_coverage["generated_at"]}
        assert {"suite_ids": [s["id"] for s in client.get("/api/workflow").json()["suites"]]} == {
            "suite_ids": [suite["id"]]
        }
