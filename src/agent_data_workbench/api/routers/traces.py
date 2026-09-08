"""FastAPI routes for traces; domain behavior lives in the SDK."""

from typing import Annotated

from fastapi import APIRouter, Query

from agent_data_workbench.api.dependencies import ProjectDependency
from agent_data_workbench.api.schemas import DistributionRequest, TraceQuery
from agent_data_workbench.data.store import TraceStore
from agent_data_workbench.exploration.clustering.service import cluster
from agent_data_workbench.exploration.distributions import distribution
from agent_data_workbench.exploration.schemas import ClusterQuery, SearchQuery
from agent_data_workbench.exploration.search import search

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


@router.post("/dataset-profile")
def profile(project: ProjectDependency, payload: DistributionRequest):
    from agent_data_workbench.exploration.dataset import dataset_profile

    return dataset_profile(TraceStore(project), payload.query, payload.pointer)
