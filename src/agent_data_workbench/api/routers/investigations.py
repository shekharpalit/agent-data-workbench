"""Native research sessions, coverage, journal pages and published files."""

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from ...identifiers import UUIDString
from ...research import (
    NativeSession,
    ResearchWorkspace,
    investigate,
    pause_investigation,
    start_investigation,
)
from ...research.artifacts import load_investigation
from ..dependencies import JobsDependency, ProjectDependency
from ..schemas import ArtifactRequest, InvestigationRequest

router = APIRouter()


@router.post("/investigate")
def run_investigation(
    project: ProjectDependency, jobs: JobsDependency, payload: InvestigationRequest
):
    def work():
        value = (
            load_investigation(project, payload.resume)
            if payload.resume
            else start_investigation(
                project, payload.question, mode=payload.mode, exclude_final=payload.exclude_final
            )
        )
        previous = value.get("session") or {}
        agent = NativeSession(
            payload.backend or previous.get("backend", "codex"),
            payload.model or previous.get("model"),
            payload.timeout,
        )
        result = investigate(project, value["id"], agent)
        return {"id": value["id"], "status": result["status"]}

    return jobs.launch("Investigate " + (payload.resume or "project"), work)


@router.post("/investigation/pause")
def pause(project: ProjectDependency, payload: ArtifactRequest):
    return pause_investigation(project, payload.id)


@router.get("/investigation/journal")
def journal(
    project: ProjectDependency,
    id: UUIDString,
    offset: Annotated[int, Query(ge=0)] = 0,
    page_size: Annotated[int, Query(gt=0)] = 50,
):
    return ResearchWorkspace(project, id).dataset.events(offset=offset, page_size=page_size)


@router.get("/investigation/outcomes")
def outcomes(
    project: ProjectDependency,
    id: UUIDString,
    after: str | None = None,
    page_size: Annotated[int, Query(gt=0)] = 50,
):
    rows = ResearchWorkspace(project, id).dataset.rows(after=after, page_size=page_size)
    return {
        "records": [
            {k: r[k] for k in ("trace_id", "status", "output", "error", "method")} for r in rows
        ],
        "next_cursor": rows[-1]["trace_id"] if len(rows) == page_size else None,
    }


@router.get("/investigation/file")
def research_file(project: ProjectDependency, id: UUIDString, artifact: UUIDString):
    path, value = ResearchWorkspace(project, id).artifact_path(artifact)
    return FileResponse(path, media_type="application/octet-stream", filename=value["filename"])
