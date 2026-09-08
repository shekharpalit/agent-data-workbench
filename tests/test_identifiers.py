import json
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from identities import uid
from pydantic import TypeAdapter
from test_workbench_data import make_project

from agent_data_workbench.api import create_app
from agent_data_workbench.data.normalization import normalize
from agent_data_workbench.evaluation.tasks.replay import replay_task
from agent_data_workbench.research import start_investigation
from agent_data_workbench.shared.identifiers import UUIDString, canonical_uuid
from agent_data_workbench.workspace.project import Project


def test_uuid_artifacts_roundtrip_through_json_and_canonical_paths(tmp_path):
    # Given
    project = make_project(tmp_path)
    # When
    knowledge = project.add_knowledge("Policy", "Preserve outcomes", "test fixture")
    investigation = start_investigation(project, "Which outcomes need review?")
    task = replay_task(project, "r0", 2, "Next decision")
    ids = [knowledge["id"], investigation["id"], task["id"]]
    path = project.path("knowledge", UUID(knowledge["id"]).hex.upper())
    # Then
    assert {
        "versions": [UUID(key).version for key in ids],
        "distinct": len(set(ids)),
        "filename": path.name,
        "saved": json.loads(path.read_text()),
        "task_id": task["spec"]["id"],
    } == {
        "versions": [4, 4, 4],
        "distinct": 3,
        "filename": knowledge["id"] + ".json",
        "saved": knowledge,
        "task_id": task["id"],
    }


@pytest.mark.parametrize("value", ["T1", "../outside", "", 1, None])
def test_invalid_internal_ids_fail_standard_uuid_validation(value):
    # Given
    adapter = TypeAdapter(UUIDString)
    # When / Then
    with pytest.raises(ValueError):
        adapter.validate_python(value)


def test_fallback_trace_uuid_is_stable_and_external_ids_are_preserved():
    # Given
    first = {"input": "request", "output": "result"}
    reordered = {"output": "result", "input": "request"}
    external = {"trace_id": "provider/session:123", "input": "request"}
    # When
    generated = normalize([first])[0]
    # Then
    assert {
        "version": UUID(generated.trace_id).version,
        "reordered": normalize([reordered])[0].trace_id,
        "external": normalize([external])[0].model_dump(),
    } == {
        "version": 5,
        "reordered": generated.trace_id,
        "external": {"trace_id": "provider/session:123", "data": external},
    }


def test_api_uuid_schema_and_invalid_id_leave_artifacts_unchanged(tmp_path):
    # Given
    project = make_project(tmp_path)
    origin = "http://127.0.0.1:8765"
    app = create_app(project, origin=origin, token="test-token")
    with TestClient(
        app, base_url=origin, headers={"Origin": origin, "Authorization": "Bearer test-token"}
    ) as client:
        # When
        schema = client.get("/api/openapi.json").json()
        response = client.post("/api/task/audit", json={"id": "T1"})
        # Then
        assert {
            "id_schema": schema["components"]["schemas"]["ArtifactRequest"]["properties"]["id"],
            "security": schema["components"]["securitySchemes"],
            "response": {"status": response.status_code, "body": response.json()},
            "tasks": project.artifacts("tasks"),
        } == {
            "id_schema": {"type": "string", "format": "uuid", "title": "Id"},
            "security": {"HTTPBearer": {"type": "http", "scheme": "bearer"}},
            "response": {
                "status": 400,
                "body": {"error": "Invalid structured data; check required fields"},
            },
            "tasks": [],
        }


def test_old_project_format_is_rejected_without_changing_existing_files(tmp_path):
    # Given
    project = Project.create(tmp_path / "project", "Existing", "Preserve data")
    path = project.root / "project.json"
    config = json.loads(path.read_text())
    config["version"] = "0.2"
    path.write_text(json.dumps(config))
    before = path.read_bytes()
    # When / Then
    with pytest.raises(ValueError, match="older artifact format"):
        Project(project.root)
    assert {"config": path.read_bytes(), "files": list((project.root / "tasks").iterdir())} == {
        "config": before,
        "files": [],
    }


def test_uuid_schema_canonicalizes_uppercase_hex():
    # Given
    value = UUID(uid("artifact"))
    # When
    actual = TypeAdapter(UUIDString).validate_python(value.hex.upper())
    # Then
    assert {"value": actual, "schema": TypeAdapter(UUIDString).json_schema()} == {
        "value": canonical_uuid(value),
        "schema": {"type": "string", "format": "uuid"},
    }
