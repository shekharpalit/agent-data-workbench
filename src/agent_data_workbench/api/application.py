"""Compose FastAPI routers, dependencies, middleware and packaged assets."""

from importlib.resources import files

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..jobs import JobQueue
from ..project import Project
from .dependencies import require_session
from .errors import register_error_handlers
from .middleware import RequestBoundaryMiddleware
from .routers import artifacts, investigations, jobs, knowledge, overview, tasks, traces


def create_app(project: Project, *, origin: str, token: str) -> FastAPI:
    app = FastAPI(
        title="Agent Data Workbench Local API",
        version="0.4.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
    )
    app.state.project = project
    app.state.jobs = JobQueue()
    app.state.token = token
    app.add_middleware(RequestBoundaryMiddleware, origin=origin)
    register_error_handlers(app)
    api = APIRouter(prefix="/api", dependencies=[Depends(require_session)])
    for module in (overview, traces, artifacts, knowledge, tasks, investigations, jobs):
        api.include_router(module.router, tags=[module.__name__.rsplit(".", 1)[-1]])

    @api.get("/openapi.json", include_in_schema=False)
    def schema(request: Request):
        return request.app.openapi()

    app.include_router(api)
    web = files("agent_data_workbench").joinpath("web")
    app.mount("/assets", StaticFiles(directory=str(web.joinpath("assets"))), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(str(web.joinpath("index.html")), media_type="text/html")

    return app
