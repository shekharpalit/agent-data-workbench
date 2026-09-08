"""Given/When/Then checks for development and container startup."""

import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import asdict, replace
from http.client import HTTPConnection

import pytest
from fastapi.testclient import TestClient

from agent_data_workbench.api import create_app
from agent_data_workbench.workbench import runtime
from agent_data_workbench.workspace.project import ARTIFACT_KINDS


def test_initialization_is_idempotent_and_preserves_existing_project_data(tmp_path):
    # Given: the runtime creates a new private workspace without sample traces.
    settings = runtime.RuntimeSettings.from_env({"WORKBENCH_PROJECT": str(tmp_path / "project")})
    created = runtime.initialize_project(settings)
    knowledge = created.add_knowledge("Policy", "Keep reviewed context", "Human")
    config = created.config.model_dump()
    # When: startup is repeated with different creation defaults.
    reopened = runtime.initialize_project(replace(settings, name="Ignored", objective="Ignored"))
    # Then: creation defaults never overwrite the existing config or research artifacts.
    assert {
        "settings": asdict(settings),
        "config": reopened.config.model_dump(),
        "knowledge": reopened.artifacts("knowledge"),
        "other_artifacts": {
            kind: reopened.artifacts(kind) for kind in sorted(ARTIFACT_KINDS - {"knowledge"})
        },
    } == {
        "settings": {
            "project": tmp_path / "project",
            "host": "127.0.0.1",
            "port": 8765,
            "origin": "http://127.0.0.1:8765",
            "name": "Agent Data Workbench",
            "objective": "Investigate agent traces and evaluate improvements",
        },
        "config": config,
        "knowledge": [knowledge],
        "other_artifacts": {kind: [] for kind in sorted(ARTIFACT_KINDS - {"knowledge"})},
    }


def test_initialization_refuses_to_adopt_nonempty_unrelated_directory(tmp_path):
    # Given: an existing directory holds unrelated data.
    root = tmp_path / "existing"
    root.mkdir()
    (root / "retain.txt").write_text("Keep me")
    settings = runtime.RuntimeSettings.from_env({"WORKBENCH_PROJECT": str(root)})
    # When: startup attempts to initialize it.
    with pytest.raises(ValueError) as raised:
        runtime.initialize_project(settings)
    # Then: no files are overwritten or added.
    assert {
        "error": str(raised.value),
        "files": {path.name: path.read_text() for path in root.iterdir()},
    } == {
        "error": "Project directory must be new or empty",
        "files": {"retain.txt": "Keep me"},
    }


def test_initialize_only_validates_project_without_starting_server(tmp_path, monkeypatch, capsys):
    # Given: a fresh location and a startup substitute that would fail if invoked.
    monkeypatch.setenv("WORKBENCH_PROJECT", str(tmp_path / "workspace"))
    monkeypatch.setenv("WORKBENCH_NAME", "Synthetic workspace")
    monkeypatch.setenv("WORKBENCH_OBJECTIVE", "Check startup")
    calls = []
    monkeypatch.setattr(runtime.uvicorn, "run", lambda *args, **kwargs: calls.append(args))
    # When: the setup command runs twice.
    runtime.main(["--initialize-only"])
    config = (tmp_path / "workspace" / "project.json").read_bytes()
    runtime.main(["--initialize-only"])
    # Then: setup exits after validating the same workspace and never runs a server.
    assert {
        "output": capsys.readouterr().out,
        "server_calls": calls,
        "preserved_config": (tmp_path / "workspace" / "project.json").read_bytes(),
    } == {
        "output": f"Workbench project: {tmp_path / 'workspace'}\n" * 2,
        "server_calls": [],
        "preserved_config": config,
    }


@pytest.mark.parametrize(
    "origin",
    [
        "http://*",
        "http://0.0.0.0:8765",
        "http://[::]:8765",
        "http://[::1]:8765",
        "http://localhost/path",
        "http://user:secret@localhost",
        "http://localhost?query=x",
        "http://localhost#token=x",
        "ftp://localhost",
        "http://local host",
        "http://localhost:0",
        "http://localhost:65536",
        "http://localhost:bad",
    ],
)
def test_public_origin_rejects_urls_that_cannot_identify_one_browser_origin(origin):
    # Given: a URL that cannot safely serve as a precise browser origin.
    # When
    with pytest.raises(ValueError):
        # Then: invalid configuration fails before Uvicorn starts.
        runtime.RuntimeSettings.from_env({"WORKBENCH_ORIGIN": origin})


@pytest.mark.parametrize(
    "origin,canonical",
    [
        ("http://localhost:18765", "http://localhost:18765"),
        ("http://localhost/", "http://localhost"),
        ("http://localhost:", "http://localhost"),
        ("http://localhost\n", "http://localhost"),
        ("http://LOCALHOST:80", "http://localhost"),
        ("https://workbench.example:443", "https://workbench.example"),
        ("https://workbench.example:8443", "https://workbench.example:8443"),
    ],
)
def test_public_origin_matches_browser_hostname_and_default_port_normalization(origin, canonical):
    # Given: a browser origin, including a hostname or default port requiring normalization.
    # When
    actual = runtime.RuntimeSettings.from_env({"WORKBENCH_ORIGIN": origin}).origin
    # Then
    assert {"origin": actual} == {"origin": canonical}


@pytest.mark.parametrize(
    "host,origin",
    [
        ("0.0.0.0", "http://localhost:18765"),
        ("0.0.0.0", "https://workbench.example:8443"),
        ("::1", "http://localhost:8765"),
    ],
)
def test_container_binding_retains_bearer_host_and_browser_origin_requirements(
    tmp_path, host, origin
):
    # Given: the container binds every interface while publishing one browser origin.
    settings = runtime.RuntimeSettings.from_env(
        {
            "WORKBENCH_PROJECT": str(tmp_path / "workspace"),
            "WORKBENCH_HOST": host,
            "WORKBENCH_ORIGIN": origin,
        }
    )
    application = create_app(
        runtime.initialize_project(settings), origin=settings.origin, token="synthetic"
    )
    with TestClient(application, base_url=origin) as client:
        # When: clients encounter FastAPI authentication and standard Host/CORS middleware.
        unauthenticated = client.get("/api/jobs")
        client.headers.update({"Authorization": "Bearer synthetic", "Origin": origin})
        authenticated = client.get("/api/jobs")
        wrong_host = client.get("/api/jobs", headers={"Host": "other.example"})
        wrong_origin = client.options(
            "/api/search",
            headers={
                "Origin": "http://other.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            },
        )
        direct_cross_origin = client.post(
            "/api/search", json={}, headers={"Origin": "http://other.example"}
        )
        valid_write = client.post("/api/search", json={})
        # Then: the published origin and session work independently of the container bind host.
        assert {
            "binding": {"host": settings.host, "origin": settings.origin},
            "anonymous": unauthenticated.status_code,
            "authenticated": {
                "status": authenticated.status_code,
                "body": authenticated.json(),
            },
            "wrong_host": {"status": wrong_host.status_code, "body": wrong_host.text},
            "wrong_origin": {
                "status": wrong_origin.status_code,
                "allowed_origin": wrong_origin.headers.get("access-control-allow-origin"),
            },
            "direct_cross_origin": {
                "status": direct_cross_origin.status_code,
                "allowed_origin": direct_cross_origin.headers.get("access-control-allow-origin"),
            },
            "valid_write": {
                "status": valid_write.status_code,
                "allowed_origin": valid_write.headers.get("access-control-allow-origin"),
            },
        } == {
            "binding": {"host": host, "origin": origin},
            "anonymous": 401,
            "authenticated": {"status": 200, "body": []},
            "wrong_host": {"status": 400, "body": "Invalid host header"},
            "wrong_origin": {"status": 400, "allowed_origin": None},
            "direct_cross_origin": {"status": 200, "allowed_origin": None},
            "valid_write": {"status": 200, "allowed_origin": origin},
        }


def test_reload_factory_preserves_token_and_workspace_across_application_restarts(
    tmp_path, monkeypatch
):
    # Given: the development supervisor shares one token with its reload children.
    monkeypatch.setenv("WORKBENCH_PROJECT", str(tmp_path / "workspace"))
    monkeypatch.setenv("WORKBENCH_ORIGIN", "http://localhost:5173")
    monkeypatch.setenv(runtime.SESSION_TOKEN_ENV, "synthetic-stable-session")
    initial = runtime.create_application()
    entry = initial.state.project.add_knowledge("Context", "Saved before reload", "Human")
    # When: Uvicorn calls the application factory again after a source edit.
    restarted = runtime.create_application()
    with TestClient(restarted, base_url="http://localhost:5173") as client:
        response = client.get(
            "/api/jobs", headers={"Authorization": "Bearer synthetic-stable-session"}
        )
    # Then: browser credentials and stored research survive the application restart.
    assert {
        "tokens": [initial.state.token, restarted.state.token],
        "knowledge": restarted.state.project.artifacts("knowledge"),
        "response": {"status": response.status_code, "body": response.json()},
    } == {
        "tokens": ["synthetic-stable-session", "synthetic-stable-session"],
        "knowledge": [entry],
        "response": {"status": 200, "body": []},
    }


@pytest.mark.parametrize("stop_signal", [signal.SIGINT, signal.SIGTERM])
def test_runtime_serves_and_stops_cleanly_on_process_signals(tmp_path, stop_signal):
    # Given: an installed runtime starts with no pre-existing workspace.
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    log_path = tmp_path / "runtime.log"
    environment = {
        **{key: value for key, value in os.environ.items() if not key.startswith("WORKBENCH_")},
        "WORKBENCH_PROJECT": str(tmp_path / "workspace"),
        "WORKBENCH_HOST": "127.0.0.1",
        "WORKBENCH_PORT": str(port),
    }
    with log_path.open("w") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "agent_data_workbench.workbench.runtime"],
            stdout=log,
            stderr=subprocess.STDOUT,
            env=environment,
        )
        try:
            deadline = time.monotonic() + 10
            status = None
            while time.monotonic() < deadline and process.poll() is None:
                connection = HTTPConnection("127.0.0.1", port, timeout=0.2)
                try:
                    connection.request("GET", "/")
                    status = connection.getresponse().status
                    break
                except OSError:
                    time.sleep(0.05)
                finally:
                    connection.close()
            # When: the foreground server receives the signals used by Make and Docker.
            process.send_signal(stop_signal)
            process.wait(timeout=5)
            # Then: it served the UI, preserved its workspace and released the listener.
            with socket.socket() as released:
                released.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                released.bind(("127.0.0.1", port))
            assert {
                "http_status": status,
                "stopped": process.poll() is not None,
                "workspace_created": (tmp_path / "workspace" / "project.json").is_file(),
                "printed_session": f"http://127.0.0.1:{port}/#token=" in log_path.read_text(),
            } == {
                "http_status": 200,
                "stopped": True,
                "workspace_created": True,
                "printed_session": True,
            }
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
