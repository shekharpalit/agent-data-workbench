"""Compose FastAPI routers, dependencies, middleware and packaged assets."""

from importlib.resources import files
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agent_data_workbench.api.dependencies import require_session
from agent_data_workbench.api.errors import register_error_handlers
from agent_data_workbench.api.middleware import register_middleware
from agent_data_workbench.api.routers import (
    artifacts,
    investigations,
    jobs,
    knowledge,
    overview,
    tasks,
    traces,
    workflow,
)
from agent_data_workbench.workbench.jobs import JobQueue
from agent_data_workbench.workspace.project import Project


def create_app(project: Project, *, origin: str, token: str) -> FastAPI:
    app = FastAPI(
        title="Agent Data Workbench Local API",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
    )
    app.state.project = project
    app.state.jobs = JobQueue()
    app.state.token = token
    register_middleware(app, origin=origin)
    register_error_handlers(app)
    api = APIRouter(prefix="/api", dependencies=[Depends(require_session)])
    for module in (overview, traces, artifacts, knowledge, tasks, investigations, jobs, workflow):
        api.include_router(module.router, tags=[module.__name__.rsplit(".", 1)[-1]])

    @api.get("/openapi.json", include_in_schema=False)
    def schema(request: Request):
        return request.app.openapi()

    app.include_router(api)
    ui = files("agent_data_workbench").joinpath("_ui")
    if not ui.is_dir():
        # Editable checkouts serve the Vite build directly from the frontend project.
        ui = Path(__file__).resolve().parents[3] / "ui" / "dist"
    app.mount("/assets", StaticFiles(directory=str(ui.joinpath("assets"))), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(str(ui.joinpath("index.html")), media_type="text/html")

    return app
