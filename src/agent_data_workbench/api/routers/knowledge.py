"""FastAPI routes for knowledge; domain behavior lives in the SDK."""

from fastapi import APIRouter

from ..dependencies import ProjectDependency
from ..schemas import (
    KnowledgeRequest,
    ReviewRequest,
)

router = APIRouter()


@router.post("/knowledge/add")
def knowledge_add(project: ProjectDependency, payload: KnowledgeRequest):
    return project.add_knowledge(payload.title, payload.content, payload.source)


@router.post("/knowledge/review")
def knowledge_review(project: ProjectDependency, payload: ReviewRequest):
    return project.review_knowledge(payload.id, payload.status, payload.note)
