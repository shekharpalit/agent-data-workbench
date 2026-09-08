"""FastAPI routes for tasks; domain behavior lives in the SDK."""

from fastapi import APIRouter

from agent_data_workbench.api.dependencies import JobsDependency, ProjectDependency
from agent_data_workbench.api.schemas import (
    ArtifactRequest,
    ReviewRequest,
    TaskDesignRequest,
    TaskEditRequest,
)
from agent_data_workbench.evaluation.tasks.design import design_tasks
from agent_data_workbench.evaluation.tasks.grading import audit_task
from agent_data_workbench.evaluation.tasks.repository import replace_task, review_task
from agent_data_workbench.integrations.analyzers import CliAnalyzer

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
