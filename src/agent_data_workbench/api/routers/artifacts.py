"""FastAPI routes for artifacts; domain behavior lives in the SDK."""

from typing import Annotated

from fastapi import APIRouter, Query

from agent_data_workbench.api.dependencies import ProjectDependency
from agent_data_workbench.api.schemas import ArtifactKind
from agent_data_workbench.exploration.lineage import lineage
from agent_data_workbench.research.artifacts import investigation_view
from agent_data_workbench.shared.identifiers import UUIDString
from agent_data_workbench.shared.json import read_json

router = APIRouter()


@router.get("/artifacts")
def artifacts(project: ProjectDependency, kind: ArtifactKind):
    return (
        [investigation_view(project, i["id"]) for i in project.artifacts(kind)]
        if kind == "investigations"
        else project.artifacts(kind)
    )


@router.get("/artifact")
def artifact(
    project: ProjectDependency,
    kind: ArtifactKind,
    id: UUIDString,
):
    return (
        investigation_view(project, id)
        if kind == "investigations"
        else read_json(project.path(kind, id))
    )


@router.get("/graph")
def graph(
    project: ProjectDependency,
    trace_id: Annotated[str, Query(max_length=1000)] = "",
    limit: Annotated[int | None, Query(ge=1)] = None,
):
    return lineage(project, trace_id=trace_id, limit=limit)
