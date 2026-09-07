"""FastAPI routes for traces; domain behavior lives in the SDK."""

from typing import Annotated

from fastapi import APIRouter, Query

from ...explore import ClusterQuery, SearchQuery, cluster, distribution, search
from ...store import TraceStore
from ..dependencies import ProjectDependency
from ..schemas import (
    DistributionRequest,
    TraceQuery,
)

router = APIRouter()


@router.get("/traces")
def traces(project: ProjectDependency, query: Annotated[TraceQuery, Query()]):
    return TraceStore(project).select(**query.model_dump(), limit=20)


@router.get("/trace")
def trace(project: ProjectDependency, id: Annotated[str, Query(min_length=1, max_length=1000)]):
    return TraceStore(project).get(id).model_dump()


@router.get("/aggregate")
def aggregate(
    project: ProjectDependency,
    pointer: Annotated[str, Query(max_length=300)] = "/agent_type",
    text: Annotated[str, Query(max_length=1000)] = "",
    stratum: Annotated[str, Query(max_length=200)] = "",
):
    return TraceStore(project).aggregate(pointer, text=text, stratum=stratum)


@router.post("/search")
def search_traces(project: ProjectDependency, payload: SearchQuery):
    return search(TraceStore(project), payload)


@router.post("/clusters")
def cluster_traces(project: ProjectDependency, payload: ClusterQuery):
    return cluster(TraceStore(project), payload)


@router.post("/distribution")
def trace_distribution(project: ProjectDependency, payload: DistributionRequest):
    return distribution(TraceStore(project), payload.query, payload.pointer)
