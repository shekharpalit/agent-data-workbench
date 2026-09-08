"""Human workflow controls preserve SDK contracts across HTTP and CLI boundaries."""

import json
import sys
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from identities import uid
from test_calibration_coverage import experiment, label, mapping
from test_workbench_data import make_project
from test_workbench_execution import suite
from typer.testing import CliRunner

from agent_data_workbench import api
from agent_data_workbench.cli import app as cli_app
from agent_data_workbench.data.store import TraceStore
from agent_data_workbench.evaluation.calibration import calibration_summary, load_calibration
from agent_data_workbench.evaluation.coverage import coverage_report, load_taxonomy
from agent_data_workbench.evaluation.experiments import run_experiment
from agent_data_workbench.evaluation.improvements import load_improvement
from agent_data_workbench.evaluation.worlds import WorldSpec, load_world
from agent_data_workbench.execution.contracts import RunnerConfig
from agent_data_workbench.execution.runners import ConfiguredRunner
from agent_data_workbench.shared.files import save
from agent_data_workbench.shared.json import digest, read_json

ORIGIN = "http://127.0.0.1:8765"
TOKEN = "synthetic-workflow-session"
STAMP = "2026-09-07T12:00:00+00:00"
WORLD = {
    "name": "Support service",
    "domain": "Customer support",
    "description": "Versioned tool rules",
    "tools": [
        {
            "name": "refund",
            "description": "Refund an authorized order",
            "input_schema": {
                "type": "object",
                "properties": {
                    "amount": {"type": "integer", "minimum": 0},
                    "confirmed": {"const": True},
                },
            },
            "output_schema": {"type": "object", "properties": {"error": {"const": None}}},
        }
    ],
    "sources": ["Reviewed synthetic policy"],
}
TAXONOMY = {
    "name": "Support behavior",
    "description": "Behaviors users depend on",
    "capabilities": [
        {
            "id": uid("cancel"),
            "name": "Cancellation",
            "description": "Respect user cancellation",
            "required_slices": ["cancel", "clarify"],
        }
    ],
}


@pytest.fixture
def project(tmp_path, monkeypatch):
    def forbidden_provider(*args, **kwargs):
        raise AssertionError("Human workflow controls must not invoke a model or native session")

    monkeypatch.setattr(
        "agent_data_workbench.integrations.analyzers.CliAnalyzer.__init__", forbidden_provider
    )
    monkeypatch.setattr(
        "agent_data_workbench.research.sessions.NativeSession.__init__", forbidden_provider
    )
    for module in ("worlds", "calibration", "coverage", "improvements"):
        monkeypatch.setattr(f"agent_data_workbench.evaluation.{module}.now", lambda: STAMP)
    return make_project(tmp_path)


@pytest.fixture
def client(project):
    application = api.create_app(project, origin=ORIGIN, token=TOKEN)
    with TestClient(
        application, base_url=ORIGIN, headers={"Authorization": f"Bearer {TOKEN}", "Origin": ORIGIN}
    ) as client:
        yield client


def response_value(response):
    return {"status": response.status_code, "body": response.json()}


def world_record(value):
    spec = WorldSpec.model_validate(WORLD).model_dump()
    return {
        "id": str(UUID(value["id"])),
        "created_at": STAMP,
        "spec": spec,
        "sha256": digest(spec),
        "revision": 1,
        "previous_id": None,
        "previous_sha256": None,
        "review": {"status": "draft", "note": ""},
        "reviews": [],
    }


def test_http_world_creation_review_and_taxonomy_mapping_preserve_typed_source_data(
    client, project
):
    # Given: a nested tool schema with booleans, integers and nulls, plus explicit behavior slices.
    # When: humans review world knowledge, then classify a trace under a reviewed taxonomy.
    created = client.post("/api/workflow/world", json={"spec": WORLD})
    world = created.json()
    reviewed = client.post(
        "/api/workflow/world/review",
        json={
            "id": world["id"],
            "status": "accepted",
            "note": "Checked domain rules",
            "reviewer": "Expert",
        },
    )
    tax_response = client.post("/api/workflow/taxonomy", json={"spec": TAXONOMY})
    tax = tax_response.json()
    taxonomy_review = client.post(
        "/api/workflow/taxonomy/review",
        json={
            "id": tax["id"],
            "status": "accepted",
            "note": "Checked behavioral slices",
            "reviewer": "Expert",
        },
    )
    mapped = client.post(
        "/api/workflow/coverage/map",
        json={"taxonomy_id": tax["id"], "mapping": mapping("trace", "r0").model_dump()},
    )
    report = client.get(f"/api/workflow/coverage/{tax['id']}")
    review = {
        "status": "accepted",
        "note": "Checked domain rules",
        "reviewer": "Expert",
        "at": STAMP,
        "sha256": world["sha256"],
    }
    expected_world = {**world_record(world), "review": review, "reviews": [review]}
    # Then: complete responses match persisted SDK artifacts without launching jobs or models.
    assert {
        "created": response_value(created),
        "reviewed": response_value(reviewed),
        "world": load_world(project, world["id"], accepted=True),
        "taxonomy": response_value(taxonomy_review),
        "map": response_value(mapped),
        "coverage": response_value(report),
        "jobs": client.get("/api/jobs").json(),
    } == {
        "created": {"status": 200, "body": world_record(world)},
        "reviewed": {"status": 200, "body": expected_world},
        "world": expected_world,
        "taxonomy": {"status": 200, "body": load_taxonomy(project, tax["id"], accepted=True)},
        "map": {"status": 200, "body": read_json(project.path("coverage", mapped.json()["id"]))},
        "coverage": {"status": 200, "body": coverage_report(project, tax["id"])},
        "jobs": [],
    }
    assert {
        "taxonomy_spec": tax["spec"],
        "source_trace": mapped.json()["entity"]["trace"],
        "source_hash": mapped.json()["entity_sha256"],
        "observed_traces": report.json()["capabilities"][0]["traces"],
        "gaps": report.json()["capabilities"][0]["missing_accepted_slices"],
    } == {
        "taxonomy_spec": TAXONOMY,
        "source_trace": TraceStore(project).get("r0").model_dump(),
        "source_hash": TraceStore(project).metadata("r0")["sha256"],
        "observed_traces": 1,
        "gaps": ["cancel", "clarify"],
    }


def test_http_human_labels_and_adjudication_reference_frozen_attempt_evidence(client, project):
    # Given: actual synthetic attempts, independent of provider credentials.
    run = experiment(project)
    created = client.post(
        "/api/workflow/calibration", json={"experiment_id": run["id"], "name": "Expert review"}
    )
    value = created.json()
    attempt = value["attempts"][0]
    # When: two people disagree and a third adjudicates the exact current set of labels.
    first = client.post(
        "/api/workflow/calibration/label",
        json={"id": value["id"], "label": label(attempt, "Alice", "pass").model_dump()},
    )
    first_saved = load_calibration(project, value["id"])
    second = client.post(
        "/api/workflow/calibration/label",
        json={"id": value["id"], "label": label(attempt, "Bob", "fail").model_dump()},
    )
    before = client.get(f"/api/workflow/calibration/{value['id']}").json()
    decision = {
        **label(attempt, "Arbiter", "fail").model_dump(),
        "labels_sha256": before["summary"]["attempts"][0]["labels_sha256"],
        "failure_cause": "grader_false_pass",
    }
    reviewed = client.post(
        "/api/workflow/calibration/adjudicate", json={"id": value["id"], "decision": decision}
    )
    current = client.get(f"/api/workflow/calibration/{value['id']}")
    # Then: the API preserves full evidence/revision records and exposes a resolved false pass.
    assert {
        "create": response_value(created),
        "first_label": response_value(first),
        "second_label": response_value(second),
        "adjudication": response_value(reviewed),
        "get": response_value(current),
        "jobs": client.get("/api/jobs").json(),
    } == {
        "create": {
            "status": 200,
            "body": read_json(project.path("calibrations", value["id"], "") / "revision-1.json"),
        },
        "first_label": {"status": 200, "body": first_saved},
        "second_label": {"status": 200, "body": before["calibration"]},
        "adjudication": {"status": 200, "body": load_calibration(project, value["id"])},
        "get": {
            "status": 200,
            "body": {
                "calibration": load_calibration(project, value["id"]),
                "summary": calibration_summary(project, value["id"]),
            },
        },
        "jobs": [],
    }
    summary = current.json()["summary"]
    assert {
        "disagreement_before": before["summary"]["disagreements"],
        "disagreement_after": summary["disagreements"],
        "adjudicated": summary["adjudicated"],
        "false_pass": summary["false_pass"],
        "cause": summary["failure_causes"],
        "frozen_trial": current.json()["calibration"]["attempts"][0]["evidence"]["trial"],
    } == {
        "disagreement_before": 1,
        "disagreement_after": 0,
        "adjudicated": 1,
        "false_pass": {"count": 1, "denominator": 1, "rate": 1.0},
        "cause": {"grader_false_pass": 1},
        "frozen_trial": run["trials"][0],
    }
    # When / Then: stale evidence cannot silently label another attempt.
    stale = client.post(
        "/api/workflow/calibration/label",
        json={
            "id": value["id"],
            "label": {**label(attempt).model_dump(), "evidence_sha256": "wrong"},
        },
    )
    assert response_value(stale) == {
        "status": 400,
        "body": {"error": "Review must refer to the exact displayed attempt evidence"},
    }


@pytest.mark.parametrize(
    "endpoint,payload",
    [
        ("world", {"spec": {**WORLD, "unexpected": True}}),
        (
            "world/review",
            {"id": "not-a-uuid", "status": "accepted", "note": "Review", "reviewer": "Expert"},
        ),
        ("taxonomy", {"spec": {**TAXONOMY, "capabilities": []}}),
        (
            "coverage/map",
            {
                "taxonomy_id": uid("tax"),
                "mapping": {**mapping("trace", "r0").model_dump(), "kind": "inferred"},
            },
        ),
        (
            "calibration/label",
            {
                "id": uid("cal"),
                "label": {
                    "task_id": uid("task"),
                    "trial": -1,
                    "variant": "candidate",
                    "evidence_sha256": "hash",
                    "reviewer": "Expert",
                    "status": "pass",
                    "reason": "Reviewed",
                },
            },
        ),
        (
            "calibration/adjudicate",
            {
                "id": uid("cal"),
                "decision": {
                    "task_id": uid("task"),
                    "trial": 0,
                    "variant": "candidate",
                    "evidence_sha256": "hash",
                    "reviewer": "Expert",
                    "status": "uncertain",
                    "reason": "Reviewed",
                    "labels_sha256": "hash",
                },
            },
        ),
    ],
)
def test_workflow_typed_requests_reject_invalid_values_before_mutation(
    client, project, endpoint, payload
):
    # Given: malformed workflow fields and no existing workflow artifacts.
    # When
    response = client.post("/api/workflow/" + endpoint, json=payload)
    # Then
    assert {
        "response": response_value(response),
        "artifacts": {
            kind: project.artifacts(kind)
            for kind in ("worlds", "taxonomies", "coverage", "calibrations")
        },
        "jobs": client.get("/api/jobs").json(),
    } == {
        "response": {
            "status": 400,
            "body": {"error": "Invalid structured data; check required fields"},
        },
        "artifacts": {"worlds": [], "taxonomies": [], "coverage": [], "calibrations": []},
        "jobs": [],
    }


def test_workflow_controls_require_the_local_session(client, project):
    # Given: a valid world specification but no session credential.
    # When
    response = client.post(
        "/api/workflow/world", json={"spec": WORLD}, headers={"Authorization": ""}
    )
    # Then
    assert {"response": response_value(response), "worlds": project.artifacts("worlds")} == {
        "response": {
            "status": 401,
            "body": {"error": "Open the complete local URL printed by agent-data-workbench ui"},
        },
        "worlds": [],
    }


def test_http_improvement_capture_and_human_decision_match_the_executed_candidate(
    client, project, tmp_path
):
    # Given: two explicit synthetic target command versions and a frozen eval suite.
    manifest = suite(project)
    paths, runners = {}, {}
    for name, outcome in (("baseline", 0), ("candidate", 1)):
        script = tmp_path / f"{name}.py"
        script.write_text(f'import json\nprint(json.dumps({{"output": {{"value": {outcome}}}}}))\n')
        config = RunnerConfig(
            name=name,
            kind="command",
            command=[sys.executable, str(script)],
            environment_version="synthetic-v1",
        )
        path = tmp_path / f"{name}.json"
        save(path, config.model_dump())
        paths[name] = str(path)
        runners[name] = ConfiguredRunner(config, tmp_path)
    # When: humans capture the change, run its exact variants, and record a decision.
    created = client.post(
        "/api/workflow/improvement",
        json={
            "name": "Respect outcome",
            "hypothesis": "Returning correct outcome satisfies task",
            "expected_behavior": "Return value 1",
            "baseline_path": paths["baseline"],
            "candidate_path": paths["candidate"],
            "trace_ids": ["r0"],
            "task_ids": [manifest["tasks"][0]["id"]],
        },
    )
    improvement = created.json()
    frozen = load_improvement(project, improvement["id"])
    run = run_experiment(
        project,
        manifest["id"],
        runners["baseline"],
        runners["candidate"],
        improvement_id=improvement["id"],
    )
    response = client.post(
        "/api/workflow/improvement/decision",
        json={
            "id": improvement["id"],
            "experiment_id": run["id"],
            "decision": "keep",
            "reviewer": "Expert",
            "reason": "Observed gains on synthetic cases; no production claim",
        },
    )
    saved = load_improvement(project, improvement["id"])
    # Then: capture and decision preserve exact source/evaluation hashes without deploying code.
    assert {
        "capture": response_value(created),
        "decision": response_value(response),
        "trial_binding": run["improvement"],
        "recorded_candidate": run["candidate"],
        "decision_evidence": {
            k: saved["decisions"][0][k]
            for k in ("experiment_id", "experiment_sha256", "decision", "reviewer", "summary")
        },
        "jobs": client.get("/api/jobs").json(),
    } == {
        "capture": {"status": 200, "body": frozen},
        "decision": {"status": 200, "body": saved},
        "trial_binding": {"id": improvement["id"], "sha256": improvement["sha256"]},
        "recorded_candidate": improvement["candidate"]["identity"],
        "decision_evidence": {
            "experiment_id": run["id"],
            "experiment_sha256": digest(run),
            "decision": "keep",
            "reviewer": "Expert",
            "summary": run["summary"],
        },
        "jobs": [],
    }


def test_cli_json_workflow_commands_create_review_classify_and_report_without_models(
    project, tmp_path
):
    # Given: filesystem JSON contracts with nested typed schemas and an imported source trace.
    runner = CliRunner()
    world_path, taxonomy_path, mapping_path = (
        tmp_path / name for name in ("world.json", "taxonomy.json", "mapping.json")
    )
    save(world_path, WORLD)
    save(taxonomy_path, TAXONOMY)
    save(mapping_path, mapping("trace", "r0").model_dump())
    root = str(project.root)
    # When: the CLI invokes the same human workflow operations as the local UI.
    world_create = runner.invoke(cli_app, ["workflow", "world", root, str(world_path)])
    world = json.loads(world_create.output)
    world_review = runner.invoke(
        cli_app,
        ["workflow", "world-review", root, world["id"], "accepted", "Reviewed tools", "Expert"],
    )
    taxonomy_create = runner.invoke(cli_app, ["workflow", "taxonomy", root, str(taxonomy_path)])
    tax = json.loads(taxonomy_create.output)
    taxonomy_review = runner.invoke(
        cli_app,
        ["workflow", "taxonomy-review", root, tax["id"], "accepted", "Reviewed slices", "Expert"],
    )
    mapped = runner.invoke(cli_app, ["workflow", "map", root, tax["id"], str(mapping_path)])
    report = runner.invoke(cli_app, ["workflow", "coverage", root, tax["id"]])
    # Then: every command returns complete machine-readable JSON matching SDK data.
    assert {
        "exit_codes": [
            r.exit_code
            for r in (world_create, world_review, taxonomy_create, taxonomy_review, mapped, report)
        ],
        "world_created": json.loads(world_create.output),
        "world_reviewed": json.loads(world_review.output),
        "taxonomy_reviewed": json.loads(taxonomy_review.output),
        "mapping": json.loads(mapped.output),
        "coverage": json.loads(report.output),
    } == {
        "exit_codes": [0, 0, 0, 0, 0, 0],
        "world_created": world_record(world),
        "world_reviewed": load_world(project, world["id"], accepted=True),
        "taxonomy_reviewed": load_taxonomy(project, tax["id"], accepted=True),
        "mapping": read_json(project.path("coverage", json.loads(mapped.output)["id"])),
        "coverage": coverage_report(project, tax["id"]),
    }
