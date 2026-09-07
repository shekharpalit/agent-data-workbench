"""FastAPI routes for investigations; domain behavior lives in the SDK."""

from fastapi import APIRouter

from ...backends import CliAnalyzer
from ...research import investigate, start_investigation
from ..dependencies import JobsDependency, ProjectDependency
from ..schemas import (
    InvestigationRequest,
)

router = APIRouter()


@router.post("/investigate")
def run_investigation(
    project: ProjectDependency, jobs: JobsDependency, payload: InvestigationRequest
):
    analyzer = CliAnalyzer(payload.backend, payload.model or None, timeout=120)

    def work():
        key = payload.resume or start_investigation(project, payload.question)["id"]
        result = investigate(project, key, analyzer, max_steps=payload.steps)
        return {"id": key, "status": result["status"]}

    # Reserve the job before creating artifacts; a rejected concurrent request writes nothing.
    return jobs.launch("Investigate " + (payload.resume or "project"), work)
