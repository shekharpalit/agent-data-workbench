import re
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from identities import uid
from test_workbench_data import Source, make_project

from agent_data_workbench import api
from agent_data_workbench.api.middleware import RESPONSE_HEADERS
from agent_data_workbench.api.routers import investigations, tasks
from agent_data_workbench.data.store import TraceStore

ORIGIN = "http://127.0.0.1:8765"
TOKEN = "synthetic-session-token"
AUTH = {"Authorization": "Bearer " + TOKEN, "Origin": ORIGIN}


@pytest.fixture
def project(tmp_path):
    return make_project(tmp_path)


@pytest.fixture
def app(project):
    return api.create_app(project, origin=ORIGIN, token=TOKEN)


@pytest.fixture
def client(app):
    with TestClient(app, base_url=ORIGIN, headers=AUTH) as client:
        yield client


def test_openapi_describes_typed_operations_and_requires_the_local_session(client):
    # Given
    requests = ["/api/search", "/api/clusters", "/api/task/edit", "/api/investigate"]
    # When
    schema = client.get("/api/openapi.json").json()
    denied = client.get("/api/openapi.json", headers={"Authorization": ""})
    contracts = {
        path: schema["paths"][path]["post"]["requestBody"]["content"]["application/json"]["schema"]
        for path in requests
    }
    # Then
    assert {
        "contracts": contracts,
        "denied": {"status": denied.status_code, "body": denied.json()},
    } == {
        "contracts": {
            "/api/search": {"$ref": "#/components/schemas/SearchQuery"},
            "/api/clusters": {"$ref": "#/components/schemas/ClusterQuery"},
            "/api/task/edit": {"$ref": "#/components/schemas/TaskEditRequest"},
            "/api/investigate": {"$ref": "#/components/schemas/InvestigationRequest"},
        },
        "denied": {
            "status": 401,
            "body": {"error": "Open the complete local URL printed by agent-data-workbench ui"},
        },
    }


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("GET", "/api/trace", None),
        ("GET", "/api/traces?offset=invalid", None),
        ("GET", "/api/artifacts?kind=unknown", None),
        ("GET", "/api/graph?limit=999", None),
        (
            "POST",
            "/api/task/review",
            {"id": uid("T1"), "status": "unknown", "note": "PRIVATE"},
        ),
        (
            "POST",
            "/api/task/edit",
            {"id": uid("T1"), "spec": {}, "note": "PRIVATE"},
        ),
        ("POST", "/api/distribution", {"query": {}, "pointer": "/bad~2key"}),
        ("POST", "/api/investigate", {"question": "PRIVATE", "steps": 1.5}),
        ("POST", "/api/investigate", {"question": ""}),
        ("POST", "/api/investigate", {"question": "PRIVATE", "backend": "other"}),
        (
            "POST",
            "/api/task/design",
            {"investigation": uid("I1"), "unexpected": "PRIVATE"},
        ),
    ],
)
def test_invalid_requests_keep_the_error_contract_and_write_nothing(
    client, project, method, path, payload
):
    # Given: invalid query parameters or an invalid structured body.
    # When
    response = client.request(method, path, json=payload)
    # Then
    assert {
        "status": response.status_code,
        "body": response.json(),
        "jobs": client.get("/api/jobs").json(),
        "artifacts": {
            kind: project.artifacts(kind) for kind in ["knowledge", "investigations", "tasks"]
        },
    } == {
        "status": 400,
        "body": {"error": "Invalid structured data; check required fields"},
        "jobs": [],
        "artifacts": {"knowledge": [], "investigations": [], "tasks": []},
    }


def test_static_assets_and_http_errors_retain_local_response_headers(client):
    # Given
    html = client.get("/").text
    assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html)
    # When
    responses = [client.get(path) for path in assets]
    missing = client.get("/assets/nonexistent.js")
    traversal = client.get("/assets/%2e%2e/api.py")
    method = client.put("/api/search")
    host = client.get("/", headers={"Host": "other.example"})
    # Then
    assert {
        "asset_types": sorted(r.headers["content-type"].split(";")[0] for r in responses),
        "asset_statuses": [r.status_code for r in responses],
        "errors": {
            "missing": missing.status_code,
            "traversal": traversal.status_code,
            "method": method.status_code,
            "host": host.status_code,
        },
        "error_bodies": [missing.json(), method.json(), host.text],
        "headers": [
            {key: r.headers[key] for key in RESPONSE_HEADERS} for r in [*responses, missing, host]
        ],
    } == {
        "asset_types": ["text/css", "text/javascript"],
        "asset_statuses": [200, 200],
        "errors": {"missing": 404, "traversal": 404, "method": 405, "host": 400},
        "error_bodies": [
            {"error": "Not Found"},
            {"error": "Method Not Allowed"},
            "Invalid host header",
        ],
        "headers": [RESPONSE_HEADERS] * 4,
    }


def test_json_media_type_and_malformed_body_fail_without_echoing_content(client):
    # Given
    cases = [("text/plain", '{"PRIVATE":1}'), ("application/json", '{"PRIVATE":')]
    # When
    actual = []
    for content_type, content in cases:
        response = client.post(
            "/api/search", content=content, headers={"Content-Type": content_type}
        )
        actual.append({"status": response.status_code, "body": response.json()})
    valid = client.post(
        "/api/search", content="{}", headers={"Content-Type": "application/json; charset=utf-8"}
    )
    # Then
    assert {
        "rejected": actual,
        "valid": {"status": valid.status_code, "eligible": valid.json()["eligible"]},
    } == {
        "rejected": [
            {"status": 400, "body": {"error": "Invalid structured data; check required fields"}},
            {"status": 400, "body": {"error": "Invalid structured data; check required fields"}},
        ],
        "valid": {"status": 200, "eligible": 9},
    }


def test_valid_json_bodies_above_two_megabytes_use_normal_fastapi_parsing(client):
    # Given: a valid request padded beyond the former transport-level body cap.
    body = " " * 2_000_001 + "{}"
    expected = client.post("/api/search", json={}).json()
    # When
    response = client.post(
        "/api/search", content=body, headers={"Content-Type": "application/json"}
    )
    # Then
    assert {"status": response.status_code, "body": response.json()} == {
        "status": 200,
        "body": expected,
    }


@pytest.mark.parametrize("port", [8765, 8766])
def test_trusted_host_validation_matches_the_hostname_independently_of_port(client, port):
    # Given: the configured hostname with either the configured port or a different one.
    # When
    response = client.get("/api/jobs", headers={"Host": f"127.0.0.1:{port}"})
    # Then
    assert {"status": response.status_code, "body": response.json()} == {
        "status": 200,
        "body": [],
    }


@pytest.mark.parametrize(
    "origin,expected",
    [
        (ORIGIN, {"status": 200, "body": "OK", "allowed_origin": ORIGIN}),
        (
            "https://other.example",
            {"status": 400, "body": "Disallowed CORS origin", "allowed_origin": None},
        ),
    ],
)
def test_cors_preflight_allows_only_the_configured_browser_origin(client, origin, expected):
    # Given: a browser checking whether it may submit authenticated JSON.
    headers = {
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Authorization, Content-Type",
    }
    # When
    response = client.options("/api/search", headers=headers)
    # Then
    assert {
        "status": response.status_code,
        "body": response.text,
        "allowed_origin": response.headers.get("access-control-allow-origin"),
    } == expected


def test_non_browser_clients_use_bearer_authentication_without_an_origin_header(app):
    # Given: an API client without the browser's Origin header.
    with TestClient(app, base_url=ORIGIN) as client:
        # When
        authorized = client.post(
            "/api/search", json={}, headers={"Authorization": AUTH["Authorization"]}
        )
        denied = client.post("/api/search", json={})
    # Then
    assert {
        "authorized": {
            "status": authorized.status_code,
            "eligible": authorized.json()["eligible"],
            "allowed_origin": authorized.headers.get("access-control-allow-origin"),
        },
        "denied": {"status": denied.status_code, "body": denied.json()},
    } == {
        "authorized": {"status": 200, "eligible": 9, "allowed_origin": None},
        "denied": {
            "status": 401,
            "body": {"error": "Open the complete local URL printed by agent-data-workbench ui"},
        },
    }


def test_cors_does_not_replace_bearer_authentication_for_direct_requests(client):
    # Given: a direct client holding the token and sending an unapproved browser origin.
    # When
    response = client.post("/api/search", json={}, headers={"Origin": "https://other.example"})
    # Then: authentication authorizes the request; CORS does not grant browser response access.
    assert {
        "status": response.status_code,
        "eligible": response.json()["eligible"],
        "allowed_origin": response.headers.get("access-control-allow-origin"),
    } == {"status": 200, "eligible": 9, "allowed_origin": None}


def test_investigation_jobs_remain_nonblocking_and_reject_concurrent_artifacts(
    client, project, monkeypatch
):
    # Given: a controlled analyzer operation that cannot make a provider call.
    entered, release = threading.Event(), threading.Event()
    calls = []
    monkeypatch.setattr(
        investigations,
        "NativeSession",
        lambda backend, model, timeout: {"backend": backend, "model": model, "timeout": timeout},
    )

    def investigate(project, key, analyzer):
        calls.append({"analyzer": analyzer})
        entered.set()
        assert release.wait(3)
        return {"status": "complete"}

    monkeypatch.setattr(investigations, "investigate", investigate)
    # When: TestClient waits for BackgroundTasks while another request inspects the job.
    with ThreadPoolExecutor(max_workers=1) as requests:
        submitted = requests.submit(
            client.post,
            "/api/investigate",
            json={
                "question": "Find outcomes",
                "backend": "claude",
                "model": "fixture",
                "mode": "complete",
            },
        )
        try:
            assert entered.wait(2)
            rejected = client.post("/api/investigate", json={"question": "Concurrent attempt"})
            overview = client.get("/api/overview")
            active = client.get("/api/jobs").json()
            # Then
            assert {
                "rejected": {"status": rejected.status_code, "body": rejected.json()},
                "responsive": overview.status_code,
                "jobs": [j["status"] for j in active],
                "investigations_created": len(project.artifacts("investigations")),
                "calls": calls,
            } == {
                "rejected": {"status": 400, "body": {"error": "An operation is already running"}},
                "responsive": 200,
                "jobs": ["running"],
                "investigations_created": 1,
                "calls": [
                    {
                        "analyzer": {"backend": "claude", "model": "fixture", "timeout": None},
                    }
                ],
            }
        finally:
            release.set()
        # When: the background operation finishes.
        started = submitted.result(timeout=2)
    final = client.get("/api/jobs").json()[0]
    # Then
    assert {
        "response": {"status": started.status_code, "body": started.json()},
        "job": final,
    } == {
        "response": {"status": 200, "body": {"job_id": final["id"]}},
        "job": {
            "id": final["id"],
            "name": "Investigate project",
            "status": "complete",
            "result": {"id": project.artifacts("investigations")[0]["id"], "status": "complete"},
            "error": None,
        },
    }


def test_failed_background_job_returns_a_recoverable_error_without_provider_text(
    client, monkeypatch
):
    # Given
    monkeypatch.setattr(tasks, "CliAnalyzer", lambda *args, **kwargs: object())

    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE provider response")

    monkeypatch.setattr(tasks, "design_tasks", fail)
    # When
    client.post("/api/task/design", json={"investigation": uid("I1")})
    jobs = client.get("/api/jobs").json()
    # Then
    assert {
        "status": jobs[0]["status"],
        "result": jobs[0]["result"],
        "error": jobs[0]["error"],
    } == {
        "status": "error",
        "result": None,
        "error": "Operation failed. Check the saved artifact and CLI; resume explicitly.",
    }


def test_native_research_api_serves_coverage_pages_and_authenticated_artifacts(client, project):
    # Given
    from agent_data_workbench.research import ResearchWorkspace, start_investigation
    from agent_data_workbench.shared.files import save

    value = start_investigation(project, "Inspect progress", mode="complete")
    workspace = ResearchWorkspace(project, value["id"])
    workspace.dataset.record("r0", output={"observed": True}, method="Read record")
    workspace.dataset.record("r1", error="Unresolved input", method="Read record")
    save(workspace.directory / "counts.json", {"completed": 1})
    artifact = workspace.attach("counts.json", "Counts", "data")
    query = {"id": workspace.id}
    # When
    detail = client.get("/api/artifact", params=query | {"kind": "investigations"}).json()
    page = client.get("/api/investigation/outcomes", params=query | {"page_size": 2}).json()
    following = client.get(
        "/api/investigation/outcomes",
        params=query | {"after": page["next_cursor"], "page_size": 1000},
    ).json()
    journal = client.get("/api/investigation/journal", params=query | {"page_size": 1}).json()
    download = client.get("/api/investigation/file", params=query | {"artifact": artifact["id"]})
    denied = client.get(
        "/api/investigation/file",
        params=query | {"artifact": artifact["id"]},
        headers={"Authorization": ""},
    )
    # Then
    assert {
        "coverage": detail["coverage"],
        "page": page,
        "following": [r["trace_id"] for r in following["records"]],
        "next": following["next_cursor"],
        "journal": {
            "count": len(journal["items"]),
            "next": journal["next_offset"],
            "total": journal["total"],
        },
        "download": {
            "status": download.status_code,
            "body": download.json(),
            "disposition": download.headers["content-disposition"],
        },
        "denied": denied.status_code,
    } == {
        "coverage": {"total": 9, "retrieved": 2, "completed": 1, "failed": 1, "pending": 7},
        "page": {
            "records": [
                {
                    "trace_id": "r0",
                    "status": "completed",
                    "output": {"observed": True},
                    "error": None,
                    "method": "Read record",
                },
                {
                    "trace_id": "r1",
                    "status": "failed",
                    "output": None,
                    "error": "Unresolved input",
                    "method": "Read record",
                },
            ],
            "next_cursor": "r1",
        },
        "following": [f"r{i}" for i in range(2, 9)],
        "next": None,
        "journal": {"count": 1, "next": 1, "total": 2},
        "download": {
            "status": 200,
            "body": {"completed": 1},
            "disposition": 'attachment; filename="counts.json"',
        },
        "denied": 401,
    }


def test_imported_event_trace_is_clustered_and_graphed_without_analysis(client, project):
    # Given
    TraceStore(project).ingest(
        Source(
            [
                {
                    "trace_id": "scan",
                    "events": [{"type": "turn.failed", "error": "invalid schema"}],
                },
            ]
        )
    )

    # When
    clusters = client.post("/api/clusters", json={"query": {"trace_ids": ["scan"]}})
    graph = client.get("/api/graph", params={"trace_id": "scan"})
    data = clusters.json()

    # Then
    assert {
        "statuses": [clusters.status_code, graph.status_code],
        "pointer": data["pointer"],
        "clustered": data["clustered"],
        "omitted_ids": data["omitted_ids"],
        "text_limit_chars": data["text_limit_chars"],
        "members": [group["trace_ids"] for group in data["clusters"]],
        "nodes": graph.json()["nodes"],
        "edges": graph.json()["edges"],
    } == {
        "statuses": [200, 200],
        "pointer": "",
        "clustered": 1,
        "omitted_ids": [],
        "text_limit_chars": None,
        "members": [["scan"]],
        "nodes": [{"id": "trace:scan", "kind": "trace", "label": "scan", "trace_id": "scan"}],
        "edges": [],
    }
