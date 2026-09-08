import hashlib
import json
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from identities import uid
from test_workbench_data import Source, make_project, result

from agent_data_workbench import api
from agent_data_workbench.api.routers import investigations
from agent_data_workbench.data.store import TraceStore
from agent_data_workbench.research import ResearchWorkspace, load_investigation
from agent_data_workbench.research.sessions import session_lock
from agent_data_workbench.research.workspace import RecordOutcome
from agent_data_workbench.shared.files import save
from agent_data_workbench.shared.json import json_text

ORIGIN = "http://127.0.0.1:8765"
AUTH = {"Authorization": "Bearer synthetic-manual-session", "Origin": ORIGIN}
EMPTY_COVERAGE = {"total": 9, "retrieved": 0, "completed": 0, "failed": 0, "pending": 9}


@pytest.fixture
def project(tmp_path):
    return make_project(tmp_path)


@pytest.fixture
def client(project, monkeypatch):
    def forbidden_native_session(*args, **kwargs):
        raise AssertionError("Manual research must not invoke a native agent")

    monkeypatch.setattr(investigations, "NativeSession", forbidden_native_session)
    app = api.create_app(project, origin=ORIGIN, token="synthetic-manual-session")
    with TestClient(app, base_url=ORIGIN, headers=AUTH) as client:
        yield client


def response_value(response):
    return {"status": response.status_code, "body": response.json()}


def test_human_can_create_read_record_and_publish_a_complete_snapshot(client, project):
    # Given: synthetic traces and no available model execution path.
    inventory = TraceStore(project).inventory()
    context = project.context()
    question = "What did each tool actually return?"
    # When
    response = client.post(
        "/api/investigation/create", json={"question": question, "mode": "complete"}
    )
    created = response.json()
    key = created["id"]
    event = created["journal"]["items"][0]
    # Then: a complete workspace is returned synchronously, without a job or session.
    assert response_value(response) == {
        "status": 200,
        "body": {
            "id": str(UUID(key)),
            "created_at": created["created_at"],
            "question": question,
            "mode": "complete",
            "status": "paused",
            "source": inventory,
            "context": context,
            "seed": 0,
            "exclude_final": False,
            "session": None,
            "attempts": [],
            "result": None,
            "evidence_snapshot": [],
            "visited_ids": [],
            "attachments": [],
            "error": None,
            "protocol_version": "0.4",
            "active": False,
            "coverage": EMPTY_COVERAGE,
            "journal": {
                "items": [
                    {
                        "id": str(UUID(event["id"])),
                        "at": event["at"],
                        "kind": "created",
                        "note": "Investigation inputs captured",
                        "details": {"mode": "complete", "source": inventory},
                    }
                ],
                "total": 1,
                "next_offset": None,
            },
        },
    }
    # When: a human reads exact source evidence, records each outcome, then publishes.
    read = client.get(
        "/api/investigation/trace",
        params={"id": key, "trace_id": "r0", "pointer": "/messages/1/content"},
    )
    recorded = client.post(
        "/api/investigation/record",
        json={
            "id": key,
            "outcomes": [
                {"trace_id": f"r{i}", "output": {"tool_declined": True}, "method": "Human review"}
                for i in range(9)
            ],
        },
    )
    findings = result(quote="declined")
    findings["analysis"]["findings"][0]["evidence"][0]["pointer"] = "/messages/1/content"
    published = client.post(
        "/api/investigation/publish", json={"id": key, "result": findings, "complete": True}
    )
    frozen = client.post(
        "/api/investigation/record",
        json={"id": key, "outcomes": [{"trace_id": "r0", "output": {}, "method": "Edit"}]},
    )
    saved = load_investigation(project, key)
    coverage = {"total": 9, "retrieved": 9, "completed": 9, "failed": 0, "pending": 0}
    # Then
    assert {
        "read": response_value(read),
        "recorded": response_value(recorded),
        "published": response_value(published),
        "frozen": response_value(frozen),
        "result": saved["result"],
        "evidence": saved["evidence_snapshot"],
        "session": saved["session"],
        "jobs": client.get("/api/jobs").json(),
    } == {
        "read": {
            "status": 200,
            "body": {
                "trace_id": "r0",
                "pointer": "/messages/1/content",
                "content": "declined",
                "offset": 0,
                "total_chars": 8,
                "next_offset": None,
            },
        },
        "recorded": {"status": 200, "body": coverage},
        "published": {
            "status": 200,
            "body": {"id": key, "status": "complete", "coverage": coverage},
        },
        "frozen": {
            "status": 400,
            "body": {"error": "Published outcomes are complete; start a new investigation"},
        },
        "result": findings,
        "evidence": [TraceStore(project).get("r0").model_dump()],
        "session": None,
        "jobs": [],
    }


def test_complete_mode_retains_drafts_and_rejects_pending_failed_or_fabricated_evidence(client):
    # Given
    created = client.post(
        "/api/investigation/create", json={"question": "Check outcomes", "mode": "complete"}
    ).json()
    key = created["id"]
    # When
    recorded = client.post(
        "/api/investigation/record",
        json={
            "id": key,
            "outcomes": [{"trace_id": "r0", "error": "Needs follow-up", "method": "Human review"}],
        },
    )
    draft = client.post(
        "/api/investigation/publish", json={"id": key, "result": result(), "complete": False}
    )
    incomplete = client.post(
        "/api/investigation/publish", json={"id": key, "result": result(), "complete": True}
    )
    fabricated = client.post(
        "/api/investigation/publish",
        json={"id": key, "result": result(quote="invented evidence"), "complete": False},
    )
    coverage = {"total": 9, "retrieved": 1, "completed": 0, "failed": 1, "pending": 8}
    # Then
    assert {
        "recorded": response_value(recorded),
        "draft": response_value(draft),
        "incomplete": response_value(incomplete),
        "fabricated": response_value(fabricated),
    } == {
        "recorded": {"status": 200, "body": coverage},
        "draft": {"status": 200, "body": {"id": key, "status": "paused", "coverage": coverage}},
        "incomplete": {
            "status": 400,
            "body": {"error": "Complete-pass processing still has pending or failed records"},
        },
        "fabricated": {
            "status": 400,
            "body": {"error": "Evidence quote does not match r0/text"},
        },
    }


def test_search_and_ranged_reads_use_the_frozen_snapshot_after_new_imports(client, project):
    # Given
    created = client.post("/api/investigation/create", json={"question": "Find patterns"}).json()
    key = created["id"]
    TraceStore(project).ingest(Source([{"trace_id": "new", "text": "actual result"}]))
    original = TraceStore(project).get("r8").data
    preview = json_text(original)
    query = {"id": key, "text": "ACTUAL", "stratum": "rare", "page_size": 1}
    # When
    first = client.get("/api/investigation/search", params=query)
    following = client.get("/api/investigation/search", params=query | {"after": "r8"})
    read = client.get(
        "/api/investigation/trace",
        params={"id": key, "trace_id": "r8", "pointer": "/text", "offset": 7, "max_chars": 3},
    )
    unknown = client.get("/api/investigation/trace", params={"id": key, "trace_id": "new"})
    client.post(
        "/api/investigation/record",
        json={"id": key, "outcomes": [{"trace_id": "r8", "output": {}, "method": "Human review"}]},
    )
    pending = client.get("/api/investigation/search", params=query | {"pending_only": True})
    # Then
    assert {
        "first": response_value(first),
        "following": response_value(following),
        "read": response_value(read),
        "new_record": response_value(unknown),
        "pending": response_value(pending),
    } == {
        "first": {
            "status": 200,
            "body": {
                "records": [
                    {
                        "trace_id": "r8",
                        "stratum": "rare",
                        "group_id": "g8",
                        "preview": preview,
                        "total_chars": len(preview),
                        "truncated": False,
                        "status": "pending",
                    }
                ],
                "next_cursor": "r8",
                "coverage": EMPTY_COVERAGE,
            },
        },
        "following": {
            "status": 200,
            "body": {"records": [], "next_cursor": None, "coverage": EMPTY_COVERAGE},
        },
        "read": {
            "status": 200,
            "body": {
                "trace_id": "r8",
                "pointer": "/text",
                "content": "res",
                "offset": 7,
                "total_chars": 13,
                "next_offset": 10,
            },
        },
        "new_record": {"status": 400, "body": {"error": "Invalid request or missing artifact"}},
        "pending": {
            "status": 200,
            "body": {
                "records": [],
                "next_cursor": None,
                "coverage": {"total": 9, "retrieved": 1, "completed": 1, "failed": 0, "pending": 8},
            },
        },
    }


def test_humans_save_journal_notes_and_inline_chart_content(client, project):
    # Given
    key = client.post("/api/investigation/create", json={"question": "Compare outcomes"}).json()[
        "id"
    ]
    chart = {
        "title": "Observed tool outcomes",
        "description": "Counts from human review",
        "values": [{"label": "Declined", "value": 9.0}],
    }
    # When
    checkpoint = client.post(
        "/api/investigation/checkpoint", json={"id": key, "note": "All reviewed tools declined."}
    )
    response = client.post("/api/investigation/chart", json={"id": key, "chart": chart})
    artifact = response.json()
    download = client.get("/api/investigation/file", params={"id": key, "artifact": artifact["id"]})
    workspace = ResearchWorkspace(project, key)
    journal = client.get("/api/investigation/journal", params={"id": key}).json()
    encoded = (json.dumps(chart, ensure_ascii=False, indent=2) + "\n").encode()
    # Then
    assert {
        "checkpoint": response_value(checkpoint),
        "artifact": response_value(response),
        "download": response_value(download),
        "journal": [{k: e[k] for k in ("kind", "note", "details")} for e in journal["items"][1:]],
        "temporary_files": sorted(p.name for p in workspace.directory.glob("*.json")),
    } == {
        "checkpoint": {"status": 200, "body": EMPTY_COVERAGE},
        "artifact": {
            "status": 200,
            "body": {
                "id": str(UUID(artifact["id"])),
                "title": chart["title"],
                "kind": "chart",
                "path": "outputs/" + artifact["id"] + ".json",
                "filename": str(UUID(artifact["filename"].removesuffix(".json"))) + ".json",
                "sha256": hashlib.sha256(encoded).hexdigest(),
                "bytes": len(encoded),
                "chart": chart,
            },
        },
        "download": {"status": 200, "body": chart},
        "journal": [
            {"kind": "checkpoint", "note": "All reviewed tools declined.", "details": None},
            {
                "kind": "artifact",
                "note": chart["title"],
                "details": {"id": artifact["id"], "kind": "chart"},
            },
        ],
        "temporary_files": ["context.json"],
    }


def test_manual_creation_preserves_explicit_final_exclusion_and_exposure(client, project):
    # Given
    save(
        project.path("suites", uid("reserved")),
        {
            "id": uid("reserved"),
            "tasks": [{"split": "final", "trace_groups": ["g0"]}],
            "final_exposure": None,
        },
    )
    # When
    reserved = client.post(
        "/api/investigation/create", json={"question": "Keep final fresh", "exclude_final": True}
    ).json()
    before = project.final_groups(consumed=True)
    all_inputs = client.post(
        "/api/investigation/create", json={"question": "All supplied data"}
    ).json()
    # Then
    assert {
        "excluded": {
            "total": reserved["coverage"]["total"],
            "excluded_groups": reserved["source"]["excluded_groups"],
        },
        "before": before,
        "all": {
            "total": all_inputs["coverage"]["total"],
            "excluded_groups": all_inputs["source"]["excluded_groups"],
        },
        "after": project.final_groups(consumed=True),
    } == {
        "excluded": {"total": 8, "excluded_groups": 1},
        "before": set(),
        "all": {"total": 9, "excluded_groups": 0},
        "after": {"g0"},
    }


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("POST", "create", {"question": "Human research"}),
        ("GET", "search", None),
        ("GET", "trace", None),
        ("POST", "checkpoint", {"id": uid("I1"), "note": "Private note"}),
        ("POST", "record", {"id": uid("I1"), "outcomes": []}),
        ("POST", "publish", {"id": uid("I1"), "result": result()}),
        ("POST", "chart", {"id": uid("I1"), "chart": {"title": "Counts", "values": []}}),
    ],
)
def test_every_manual_route_requires_the_local_session(client, project, method, path, payload):
    # Given: a request without the local bearer token.
    # When
    response = client.request(
        method, "/api/investigation/" + path, json=payload, headers={"Authorization": ""}
    )
    # Then
    assert {
        "response": response_value(response),
        "artifacts": project.artifacts("investigations"),
    } == {
        "response": {
            "status": 401,
            "body": {"error": "Open the complete local URL printed by agent-data-workbench ui"},
        },
        "artifacts": [],
    }


@pytest.mark.parametrize(
    "path,payload",
    [
        ("create", {"question": "Research", "mode": "unknown"}),
        ("create", {"question": "Research", "backend": "codex"}),
        ("checkpoint", {"id": "not-a-uuid", "note": "Note"}),
        (
            "record",
            {"id": uid("I1"), "outcomes": [{"trace_id": "r0", "output": [], "method": "Read"}]},
        ),
        ("publish", {"id": uid("I1"), "result": {}}),
        (
            "chart",
            {
                "id": uid("I1"),
                "chart": {"title": "Counts", "values": [{"label": "count", "value": -1}]},
            },
        ),
        (
            "chart",
            {"id": uid("I1"), "chart": {"title": "Counts", "values": [], "path": "../escape.json"}},
        ),
    ],
)
def test_manual_requests_use_typed_contracts_before_writing(client, project, path, payload):
    # Given: malformed structured input or a caller-selected output path.
    # When
    response = client.post("/api/investigation/" + path, json=payload)
    # Then
    assert {
        "response": response_value(response),
        "artifacts": project.artifacts("investigations"),
    } == {
        "response": {
            "status": 400,
            "body": {"error": "Invalid structured data; check required fields"},
        },
        "artifacts": [],
    }


def test_manual_mutations_wait_for_native_session_ownership_to_be_released(client, project):
    # Given: the native runtime owns this workspace and can still use its shared SDK tools.
    key = client.post("/api/investigation/create", json={"question": "Review outcomes"}).json()[
        "id"
    ]
    workspace = ResearchWorkspace(project, key)
    actions = [
        ("checkpoint", {"note": "Human review started"}),
        (
            "record",
            {"outcomes": [{"trace_id": "r1", "output": {"reviewed": True}, "method": "Human"}]},
        ),
        ("chart", {"chart": {"title": "Reviewed", "values": [{"label": "Records", "value": 2}]}}),
        ("publish", {"result": result(), "complete": True}),
    ]
    # When: human HTTP mutations arrive during an active native session.
    with session_lock(workspace.directory):
        workspace.record_outcomes(
            [RecordOutcome(trace_id="r0", output={"reviewed": True}, method="Native SDK tool")]
        )
        before = workspace.info()
        denied = [
            response_value(client.post("/api/investigation/" + path, json={"id": key} | body))
            for path, body in actions
        ]
        after = workspace.info()
    # Then: no manual mutation can publish, seal, or alter work owned by the native session.
    assert {"denied": denied, "after": after} == {
        "denied": [
            {"status": 400, "body": {"error": "This investigation already has an active session"}}
        ]
        * 4,
        "after": before,
    }
    # When: ownership is released, the same human requests can proceed.
    responses = [
        client.post("/api/investigation/" + path, json={"id": key} | body) for path, body in actions
    ]
    value = load_investigation(project, key)
    coverage = {"total": 9, "retrieved": 2, "completed": 2, "failed": 0, "pending": 7}
    # Then
    assert {
        "checkpoint": response_value(responses[0]),
        "record": response_value(responses[1]),
        "chart": {"status": responses[2].status_code, "chart": responses[2].json()["chart"]},
        "publish": response_value(responses[3]),
        "saved": {"status": value["status"], "result": value["result"]},
    } == {
        "checkpoint": {
            "status": 200,
            "body": {"total": 9, "retrieved": 1, "completed": 1, "failed": 0, "pending": 8},
        },
        "record": {"status": 200, "body": coverage},
        "chart": {
            "status": 200,
            "chart": {
                "title": "Reviewed",
                "description": "",
                "values": [{"label": "Records", "value": 2.0}],
            },
        },
        "publish": {"status": 200, "body": {"id": key, "status": "complete", "coverage": coverage}},
        "saved": {"status": "complete", "result": result()},
    }


def test_default_research_http_reads_preserve_long_fields_and_search_records(client, project):
    # Given
    data = {"trace_id": "long-record", "text": "content " * 3000 + "final evidence"}
    TraceStore(project).ingest(Source([data]))
    key = client.post(
        "/api/investigation/create", json={"question": "Read complete evidence"}
    ).json()["id"]

    # When
    read = client.get(
        "/api/investigation/trace",
        params={"id": key, "trace_id": "long-record", "pointer": "/text"},
    )
    search = client.get("/api/investigation/search", params={"id": key, "text": "long-record"})
    record = search.json()["records"][0]

    # Then
    assert {
        "statuses": [read.status_code, search.status_code],
        "read": read.json(),
        "search_content": record["preview"],
        "search_truncated": record["truncated"],
    } == {
        "statuses": [200, 200],
        "read": {
            "trace_id": "long-record",
            "pointer": "/text",
            "content": data["text"],
            "offset": 0,
            "total_chars": len(data["text"]),
            "next_offset": None,
        },
        "search_content": json_text(data),
        "search_truncated": False,
    }
