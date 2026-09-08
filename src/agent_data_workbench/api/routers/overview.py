"""FastAPI routes for overview; domain behavior lives in the SDK."""

from fastapi import APIRouter

from agent_data_workbench.api.dependencies import ProjectDependency
from agent_data_workbench.data.store import TraceStore

router = APIRouter()


@router.get("/overview")
def overview(
    project: ProjectDependency,
):
    tasks = project.artifacts("tasks")
    return {
        "project": project.config.model_dump(),
        "inventory": TraceStore(project).inventory(),
        "task_counts": {
            status: sum(t["review"]["status"] == status for t in tasks)
            for status in ("draft", "accepted", "rejected")
        },
        "investigations": [
            {
                "id": i["id"],
                "question": i["question"],
                "status": i["status"],
                "sessions": len(i.get("attempts", [])),
            }
            for i in project.artifacts("investigations")
        ],
        "experiments": [
            {k: e.get(k) for k in ("id", "created_at", "split", "status", "summary", "conclusion")}
            for e in project.artifacts("experiments")
        ],
    }
