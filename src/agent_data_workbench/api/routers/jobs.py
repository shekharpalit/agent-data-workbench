"""FastAPI routes for jobs; domain behavior lives in the SDK."""

from fastapi import APIRouter

from agent_data_workbench.api.dependencies import JobsDependency

router = APIRouter()


@router.get("/jobs")
def list_jobs(
    jobs: JobsDependency,
):
    return jobs.snapshot()
