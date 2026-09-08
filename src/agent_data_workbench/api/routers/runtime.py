"""Read-only runtime setup checks."""

from fastapi import APIRouter

from agent_data_workbench.workbench.capabilities import capabilities

router = APIRouter()


@router.get("/runtime")
def runtime():
    return capabilities()
