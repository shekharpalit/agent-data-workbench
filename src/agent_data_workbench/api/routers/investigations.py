"""Shared human and native-agent research, coverage, journal and published files."""

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from agent_data_workbench.api.dependencies import JobsDependency, ProjectDependency
from agent_data_workbench.api.schemas import (
    ArtifactRequest,
    InvestigationChartRequest,
    InvestigationCheckpointRequest,
    InvestigationPublishRequest,
    InvestigationRecordRequest,
    InvestigationRequest,
    ManualInvestigationRequest,
)
from agent_data_workbench.research import (
    NativeSession,
    ResearchWorkspace,
    investigate,
    pause_investigation,
    start_investigation,
)
from agent_data_workbench.research.artifacts import investigation_view, load_investigation
from agent_data_workbench.research.sessions import session_lock
from agent_data_workbench.shared.identifiers import UUIDString

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


@router.post("/investigation/create")
def create_manual_investigation(
    project: ProjectDependency, payload: ManualInvestigationRequest
) -> dict:
    value = start_investigation(
        project, payload.question, mode=payload.mode, exclude_final=payload.exclude_final
    )
    return investigation_view(project, value["id"])


@router.get("/investigation/search")
def search_snapshot(
    project: ProjectDependency,
    id: UUIDString,
    text: str = "",
    stratum: str = "",
    after: str | None = None,
    pending_only: bool = False,
    page_size: Annotated[int, Query(gt=0)] = 20,
) -> dict:
    return ResearchWorkspace(project, id).search(
        text=text, stratum=stratum, after=after, pending_only=pending_only, page_size=page_size
    )


@router.get("/investigation/trace")
def read_snapshot_trace(
    project: ProjectDependency,
    id: UUIDString,
    trace_id: str,
    pointer: str = "",
    offset: Annotated[int, Query(ge=0)] = 0,
    max_chars: Annotated[int | None, Query(gt=0)] = 16000,
) -> dict:
    return ResearchWorkspace(project, id).read(
        trace_id, pointer=pointer, offset=offset, max_chars=max_chars
    )


@router.post("/investigation/checkpoint")
def checkpoint(project: ProjectDependency, payload: InvestigationCheckpointRequest) -> dict:
    workspace = ResearchWorkspace(project, payload.id)
    with session_lock(workspace.directory):
        return workspace.checkpoint(payload.note)


@router.post("/investigation/record")
def record(project: ProjectDependency, payload: InvestigationRecordRequest) -> dict:
    workspace = ResearchWorkspace(project, payload.id)
    with session_lock(workspace.directory):
        return workspace.record_outcomes(payload.outcomes)


@router.post("/investigation/publish")
def publish(project: ProjectDependency, payload: InvestigationPublishRequest) -> dict:
    workspace = ResearchWorkspace(project, payload.id)
    with session_lock(workspace.directory):
        return workspace.publish(payload.result, complete=payload.complete)


@router.post("/investigation/chart")
def chart(project: ProjectDependency, payload: InvestigationChartRequest) -> dict:
    workspace = ResearchWorkspace(project, payload.id)
    with session_lock(workspace.directory):
        return workspace.save_chart(payload.chart)
