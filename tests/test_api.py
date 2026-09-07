import asyncio
import json
import re
import threading
import time
import urllib.request
import webbrowser

import pytest
from fastapi.testclient import TestClient
from test_workbench_data import make_project

from agent_data_workbench import api, server
from agent_data_workbench.local_http import MAX_BODY_BYTES, RESPONSE_HEADERS

ORIGIN = "http://127.0.0.1:8765"
TOKEN = "synthetic-session-token"
AUTH = {"Authorization": "Bearer " + TOKEN, "Origin": ORIGIN}


def test_cli_opens_the_browser_after_the_workbench_can_serve_requests(project, monkeypatch):
    # Given: a real loopback server and a browser substitute that requests its page.
    workbench = server.WorkbenchServer(project)
    monkeypatch.setattr(server, "WorkbenchServer", lambda project, port: workbench)
    observed = []

    def open_browser(url):
        try:
            with urllib.request.urlopen(url.split("#")[0], timeout=2) as response:
                observed.append(
                    {"url": url, "started": workbench.started, "status": response.status}
                )
        finally:
            workbench.shutdown()

    monkeypatch.setattr(webbrowser, "open", open_browser)
    # When
    thread = threading.Thread(target=server.serve, args=(project,), kwargs={"open_browser": True})
    thread.start()
    try:
        thread.join(5)
        # Then
        assert {"stopped": not thread.is_alive(), "opened": observed} == {
            "stopped": True,
            "opened": [
                {
                    "url": workbench.origin + "/#token=" + workbench.token,
                    "started": True,
                    "status": 200,
                }
            ],
        }
    finally:
        workbench.shutdown()
        thread.join(2)


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
        ("POST", "/api/task/review", {"id": "T1", "status": "unknown", "note": "PRIVATE"}),
        ("POST", "/api/task/edit", {"id": "T1", "spec": {}, "note": "PRIVATE"}),
        ("POST", "/api/distribution", {"query": {}, "pointer": "/bad~2key"}),
        ("POST", "/api/investigate", {"question": "PRIVATE", "steps": 1.5}),
        ("POST", "/api/investigate", {"question": ""}),
        ("POST", "/api/investigate", {"question": "PRIVATE", "backend": "other"}),
        ("POST", "/api/task/design", {"investigation": "I1", "unexpected": "PRIVATE"}),
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
        "error_bodies": [missing.json(), method.json(), host.json()],
        "headers": [
            {key: r.headers[key] for key in RESPONSE_HEADERS} for r in [*responses, missing, host]
        ],
    } == {
        "asset_types": ["text/css", "text/javascript"],
        "asset_statuses": [200, 200],
        "errors": {"missing": 404, "traversal": 404, "method": 405, "host": 403},
        "error_bodies": [
            {"error": "Not Found"},
            {"error": "Method Not Allowed"},
            {"error": "Invalid host"},
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
            {"status": 400, "body": {"error": "Supply a JSON body up to 2 MB"}},
            {"status": 400, "body": {"error": "Invalid structured data; check required fields"}},
        ],
        "valid": {"status": 200, "eligible": 9},
    }


def test_body_limit_counts_received_chunks_when_content_length_is_absent(app):
    # Given: an ASGI transport delivering bounded chunks without Content-Length.
    chunk = b" " * 100_000
    received, sent = [], []
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/search",
        "raw_path": b"/api/search",
        "root_path": "",
        "query_string": b"",
        "server": ("127.0.0.1", 8765),
        "client": ("127.0.0.1", 12345),
        "headers": [
            (b"host", b"127.0.0.1:8765"),
            (b"origin", ORIGIN.encode()),
            (b"authorization", AUTH["Authorization"].encode()),
            (b"content-type", b"application/json"),
        ],
    }

    async def receive():
        received.append(len(chunk))
        return {"type": "http.request", "body": chunk, "more_body": True}

    async def send(message):
        sent.append(message)

    # When
    asyncio.run(app(scope, receive, send))
    # Then
    assert {
        "bytes_read": sum(received),
        "status": sent[0]["status"],
        "body": json.loads(b"".join(m.get("body", b"") for m in sent[1:])),
    } == {
        "bytes_read": MAX_BODY_BYTES + len(chunk),
        "status": 400,
        "body": {"error": "Supply a JSON body up to 2 MB"},
    }


def test_declared_oversized_body_is_rejected_before_json_parsing(client):
    # Given
    headers = {"Content-Length": str(MAX_BODY_BYTES + 1)}
    # When
    response = client.post("/api/search", json={}, headers=headers)
    # Then
    assert {"status": response.status_code, "body": response.json()} == {
        "status": 400,
        "body": {"error": "Supply a JSON body up to 2 MB"},
    }


def test_investigation_jobs_remain_nonblocking_and_reject_concurrent_artifacts(
    client, project, monkeypatch
):
    # Given: a controlled analyzer operation that cannot make a provider call.
    entered, release = threading.Event(), threading.Event()
    calls = []
    monkeypatch.setattr(
        api,
        "CliAnalyzer",
        lambda backend, model, timeout: {"backend": backend, "model": model, "timeout": timeout},
    )

    def investigate(project, key, analyzer, max_steps):
        calls.append({"analyzer": analyzer, "max_steps": max_steps})
        entered.set()
        assert release.wait(3)
        return {"status": "complete"}

    monkeypatch.setattr(api, "investigate", investigate)
    # When
    started = client.post(
        "/api/investigate",
        json={"question": "Find outcomes", "backend": "claude", "model": "fixture", "steps": 2},
    )
    try:
        assert entered.wait(2)
        rejected = client.post("/api/investigate", json={"question": "Concurrent attempt"})
        overview = client.get("/api/overview")
        active = client.get("/api/jobs").json()
        # Then
        assert {
            "started": started.status_code,
            "job_keys": list(started.json()),
            "rejected": {"status": rejected.status_code, "body": rejected.json()},
            "responsive": overview.status_code,
            "jobs": [j["status"] for j in active],
            "investigations_created": len(project.artifacts("investigations")),
            "calls": calls,
        } == {
            "started": 200,
            "job_keys": ["job_id"],
            "rejected": {"status": 400, "body": {"error": "An operation is already running"}},
            "responsive": 200,
            "jobs": ["running"],
            "investigations_created": 1,
            "calls": [
                {
                    "analyzer": {"backend": "claude", "model": "fixture", "timeout": 120},
                    "max_steps": 2,
                }
            ],
        }
    finally:
        release.set()
    # When: the background operation finishes.
    deadline = time.monotonic() + 2
    while (final := client.get("/api/jobs").json())[0][
        "status"
    ] == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
    # Then
    assert {
        "status": final[0]["status"],
        "result": final[0]["result"],
        "error": final[0]["error"],
    } == {
        "status": "complete",
        "result": {"id": project.artifacts("investigations")[0]["id"], "status": "complete"},
        "error": None,
    }


def test_failed_background_job_returns_a_recoverable_error_without_provider_text(
    client, monkeypatch
):
    # Given
    monkeypatch.setattr(api, "CliAnalyzer", lambda *args, **kwargs: object())

    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE provider response")

    monkeypatch.setattr(api, "design_tasks", fail)
    # When
    client.post("/api/task/design", json={"investigation": "I1"})
    deadline = time.monotonic() + 2
    while (jobs := client.get("/api/jobs").json())[0][
        "status"
    ] == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
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
