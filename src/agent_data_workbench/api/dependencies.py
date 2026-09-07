"""Typed FastAPI dependencies and local session authentication."""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..jobs import JobQueue
from ..project import Project

bearer = HTTPBearer(auto_error=False)


def require_session(
    request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
):
    if credentials is None or not secrets.compare_digest(
        credentials.credentials.encode(), request.app.state.token.encode()
    ):
        raise HTTPException(401, "Open the complete local URL printed by agent-data-workbench ui")


def current_project(request: Request) -> Project:
    return request.app.state.project


def current_jobs(request: Request) -> JobQueue:
    return request.app.state.jobs


ProjectDependency = Annotated[Project, Depends(current_project)]
JobsDependency = Annotated[JobQueue, Depends(current_jobs)]
