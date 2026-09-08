import asyncio

import pytest
from fastapi import BackgroundTasks

from agent_data_workbench.workbench.jobs import JobQueue


def test_job_executes_only_when_fastapi_runs_the_background_tasks():
    # Given: an operation whose progress is visible to the local UI.
    jobs, background_tasks, calls = JobQueue(), BackgroundTasks(), []

    def work():
        calls.append("ran")
        return {"artifact": "saved"}

    # When: the request schedules work and FastAPI later runs its response tasks.
    started = jobs.launch(background_tasks, "Investigate", work)
    pending = {"jobs": jobs.snapshot(), "calls": list(calls)}
    asyncio.run(background_tasks())

    # Then: scheduling reserves capacity without executing work during the handler.
    assert {"pending": pending, "finished": {"jobs": jobs.snapshot(), "calls": calls}} == {
        "pending": {
            "jobs": [
                {
                    "id": started["job_id"],
                    "name": "Investigate",
                    "status": "running",
                    "result": None,
                    "error": None,
                }
            ],
            "calls": [],
        },
        "finished": {
            "jobs": [
                {
                    "id": started["job_id"],
                    "name": "Investigate",
                    "status": "complete",
                    "result": {"artifact": "saved"},
                    "error": None,
                }
            ],
            "calls": ["ran"],
        },
    }


def test_reservation_rejects_a_second_operation_before_it_creates_artifacts():
    # Given: a reserved job whose response background tasks have not started yet.
    jobs, first_tasks, second_tasks = JobQueue(), BackgroundTasks(), BackgroundTasks()
    artifacts = []
    started = jobs.launch(first_tasks, "First", lambda: {"artifact": "first"})

    def create_second_artifact():
        artifacts.append("second")
        return {"artifact": "second"}

    # When: another handler tries to reserve an operation before the first finishes.
    with pytest.raises(ValueError) as rejected:
        jobs.launch(second_tasks, "Second", create_second_artifact)
    asyncio.run(second_tasks())

    # Then: the rejected request never schedules its artifact-producing operation.
    assert {
        "error": str(rejected.value),
        "artifacts": artifacts,
        "jobs": jobs.snapshot(),
    } == {
        "error": "An operation is already running",
        "artifacts": [],
        "jobs": [
            {
                "id": started["job_id"],
                "name": "First",
                "status": "running",
                "result": None,
                "error": None,
            }
        ],
    }


def test_failed_background_operation_reports_failure_and_releases_capacity():
    # Given: a native operation that fails after the response is sent.
    jobs, failed_tasks, recovery_tasks = JobQueue(), BackgroundTasks(), BackgroundTasks()

    def fail():
        raise RuntimeError("Synthetic provider failure with private details")

    # When: FastAPI executes the failing job and a later request schedules new work.
    failed = jobs.launch(failed_tasks, "Failed investigation", fail)
    asyncio.run(failed_tasks())
    recovered = jobs.launch(recovery_tasks, "Retry investigation", lambda: {"recovered": True})
    asyncio.run(recovery_tasks())

    # Then: the UI receives the existing error contract and the next job can complete.
    assert jobs.snapshot() == [
        {
            "id": failed["job_id"],
            "name": "Failed investigation",
            "status": "error",
            "result": None,
            "error": "Operation failed. Check the saved artifact and CLI; resume explicitly.",
        },
        {
            "id": recovered["job_id"],
            "name": "Retry investigation",
            "status": "complete",
            "result": {"recovered": True},
            "error": None,
        },
    ]
