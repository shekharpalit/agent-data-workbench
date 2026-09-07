"""FastAPI routes for tasks; domain behavior lives in the SDK."""

from fastapi import APIRouter

from ...backends import CliAnalyzer
from ...tasks import audit_task, design_tasks, replace_task, review_task
from ..dependencies import JobsDependency, ProjectDependency
from ..schemas import (
    ArtifactRequest,
    ReviewRequest,
    TaskDesignRequest,
    TaskEditRequest,
)

router = APIRouter()


@router.post("/task/review")
def task_review(project: ProjectDependency, payload: ReviewRequest):
    return review_task(project, payload.id, payload.status, payload.note)


@router.post("/task/edit")
def task_edit(project: ProjectDependency, payload: TaskEditRequest):
    return replace_task(project, payload.id, payload.spec, payload.note)


@router.post("/task/audit")
def task_audit(project: ProjectDependency, payload: ArtifactRequest):
    return audit_task(project, payload.id)


@router.post("/task/design")
def task_design(project: ProjectDependency, jobs: JobsDependency, payload: TaskDesignRequest):
    analyzer = CliAnalyzer(payload.backend, payload.model or None)
    return jobs.launch(
        "Design tasks",
        lambda: {
            "tasks": [t.id for t in design_tasks(project, payload.investigation, analyzer).tasks]
        },
    )
