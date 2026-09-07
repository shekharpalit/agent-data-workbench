"""FastAPI routes for artifacts; domain behavior lives in the SDK."""

from typing import Annotated

from fastapi import APIRouter, Query

from ...explore import lineage
from ...identifiers import UUIDString
from ...research.artifacts import investigation_view
from ...traces import read_json
from ..dependencies import ProjectDependency
from ..schemas import (
    ArtifactKind,
)

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
    limit: Annotated[int, Query(ge=10, le=300)] = 200,
):
    return lineage(project, trace_id=trace_id, limit=limit)
