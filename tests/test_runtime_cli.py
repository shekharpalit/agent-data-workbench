"""The UI CLI configures the same FastAPI factory as the container launcher."""

import os

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from agent_data_workbench.cli import app
from agent_data_workbench.workbench import runtime
from agent_data_workbench.workspace.project import Project


def test_ui_uses_requested_project_and_port_instead_of_stale_environment(tmp_path, monkeypatch):
    # Given: an explicit project and stale settings from a different workbench.
    project = Project.create(tmp_path / "chosen", "Chosen", "Inspect chosen traces")
    monkeypatch.setenv("WORKBENCH_PROJECT", str(tmp_path / "unrelated"))
    monkeypatch.setenv("WORKBENCH_HOST", "0.0.0.0")
    monkeypatch.setenv("WORKBENCH_ORIGIN", "https://other.example")
    for name in (
        "WORKBENCH_PORT",
        "WORKBENCH_NAME",
        "WORKBENCH_OBJECTIVE",
        runtime.SESSION_TOKEN_ENV,
    ):
        monkeypatch.setenv(name, os.environ.get(name, ""))
    observed = {}

    def run_fastapi(application_import, **options):
        application = runtime.create_application()
        with TestClient(application, base_url="http://127.0.0.1:9876") as client:
            response = client.get(
                "/api/jobs",
                headers={"Authorization": "Bearer " + application.state.token},
            )
        observed.update(
            factory=application_import,
            project=application.state.project.root,
            host=options["host"],
            port=options["port"],
            factory_mode=options["factory"],
            reload=options["reload"],
            response={"status": response.status_code, "body": response.json()},
        )

    monkeypatch.setattr(runtime.uvicorn, "run", run_fastapi)
    # When: the public CLI requests that project on a specific local port.
    result = CliRunner().invoke(app, ["ui", str(project.root), "--port", "9876"])
    # Then: the serving factory uses the selected workspace and its usable private URL.
    assert {
        "exit_code": result.exit_code,
        "runtime": observed,
        "printed_url": "http://127.0.0.1:9876/#token=" in result.output,
        "unrelated_created": (tmp_path / "unrelated").exists(),
    } == {
        "exit_code": 0,
        "runtime": {
            "factory": "agent_data_workbench.workbench.runtime:create_application",
            "project": project.root,
            "host": "127.0.0.1",
            "port": 9876,
            "factory_mode": True,
            "reload": False,
            "response": {"status": 200, "body": []},
        },
        "printed_url": True,
        "unrelated_created": False,
    }
