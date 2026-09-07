"""FastAPI routes for local project operations. Business logic stays in the SDK."""

from importlib.resources import files
from typing import Annotated

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.exceptions import HTTPException

from .api_models import (
    ArtifactKind,
    ArtifactRequest,
    DistributionRequest,
    InvestigationRequest,
    KnowledgeRequest,
    ReviewRequest,
    TaskDesignRequest,
    TaskEditRequest,
    TraceQuery,
)
from .backends import CliAnalyzer
from .explore import ClusterQuery, SearchQuery, cluster, distribution, lineage, search
from .jobs import JobQueue
from .local_http import LocalSessionMiddleware
from .project import Project
from .research import investigate, start_investigation
from .store import TraceStore
from .tasks import audit_task, design_tasks, replace_task, review_task
from .traces import read_json


def create_app(project: Project, *, origin: str, token: str) -> FastAPI:
    app = FastAPI(
        title="Agent Data Workbench Local API",
        version="0.2.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
    )
    app.add_middleware(LocalSessionMiddleware, origin=origin, token=token)
    jobs = JobQueue()
    app.state.jobs = jobs
    api = APIRouter(prefix="/api")

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def invalid_structure(request: Request, exc: Exception):
        # Pydantic errors can contain private request values; keep the existing error envelope.
        return JSONResponse(
            {"error": "Invalid structured data; check required fields"}, status_code=400
        )

    @app.exception_handler(ValueError)
    @app.exception_handler(KeyError)
    @app.exception_handler(OSError)
    @app.exception_handler(TypeError)
    async def invalid_operation(request: Request, exc: Exception):
        message = (
            str(exc)
            if request.method == "POST" and isinstance(exc, ValueError)
            else "Invalid request or missing artifact"
        )
        return JSONResponse({"error": message}, status_code=400)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse(
            {"error": str(exc.detail)}, status_code=exc.status_code, headers=exc.headers
        )

    @api.get("/overview")
    def overview():
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
                    "steps": len(i["steps"]),
                }
                for i in project.artifacts("investigations")
            ],
            "experiments": [
                {
                    k: e.get(k)
                    for k in ("id", "created_at", "split", "status", "summary", "conclusion")
                }
                for e in project.artifacts("experiments")
            ],
            "synthetic": (project.root / "demo.json").exists(),
        }

    @api.get("/traces")
    def traces(query: Annotated[TraceQuery, Query()]):
        return TraceStore(project).select(**query.model_dump(), limit=20)

    @api.get("/trace")
    def trace(id: Annotated[str, Query(min_length=1, max_length=1000)]):
        return TraceStore(project).get(id).model_dump()

    @api.get("/aggregate")
    def aggregate(
        pointer: Annotated[str, Query(max_length=300)] = "/agent_type",
        text: Annotated[str, Query(max_length=1000)] = "",
        stratum: Annotated[str, Query(max_length=200)] = "",
    ):
        return TraceStore(project).aggregate(pointer, text=text, stratum=stratum)

    @api.get("/artifacts")
    def artifacts(kind: ArtifactKind):
        return project.artifacts(kind)

    @api.get("/artifact")
    def artifact(kind: ArtifactKind, id: Annotated[str, Query(min_length=1, max_length=80)]):
        return read_json(project.path(kind, id))

    @api.get("/jobs")
    def list_jobs():
        return jobs.snapshot()

    @api.get("/graph")
    def graph(
        trace_id: Annotated[str, Query(max_length=1000)] = "",
        limit: Annotated[int, Query(ge=10, le=300)] = 200,
    ):
        return lineage(project, trace_id=trace_id, limit=limit)

    @api.get("/openapi.json", include_in_schema=False)
    def schema():
        return app.openapi()

    @api.post("/search")
    def search_traces(payload: SearchQuery):
        return search(TraceStore(project), payload)

    @api.post("/clusters")
    def cluster_traces(payload: ClusterQuery):
        return cluster(TraceStore(project), payload)

    @api.post("/distribution")
    def trace_distribution(payload: DistributionRequest):
        return distribution(TraceStore(project), payload.query, payload.pointer)

    @api.post("/task/review")
    def task_review(payload: ReviewRequest):
        return review_task(project, payload.id, payload.status, payload.note)

    @api.post("/task/edit")
    def task_edit(payload: TaskEditRequest):
        return replace_task(project, payload.id, payload.spec, payload.note)

    @api.post("/task/audit")
    def task_audit(payload: ArtifactRequest):
        return audit_task(project, payload.id)

    @api.post("/knowledge/add")
    def knowledge_add(payload: KnowledgeRequest):
        return project.add_knowledge(payload.title, payload.content, payload.source)

    @api.post("/knowledge/review")
    def knowledge_review(payload: ReviewRequest):
        return project.review_knowledge(payload.id, payload.status, payload.note)

    @api.post("/investigate")
    def run_investigation(payload: InvestigationRequest):
        analyzer = CliAnalyzer(payload.backend, payload.model or None, timeout=120)

        def work():
            key = payload.resume or start_investigation(project, payload.question)["id"]
            result = investigate(project, key, analyzer, max_steps=payload.steps)
            return {"id": key, "status": result["status"]}

        # Reserve the job before creating artifacts; a rejected concurrent request writes nothing.
        return jobs.launch("Investigate " + (payload.resume or "project"), work)

    @api.post("/task/design")
    def task_design(payload: TaskDesignRequest):
        analyzer = CliAnalyzer(payload.backend, payload.model or None)
        return jobs.launch(
            "Design tasks",
            lambda: {
                "tasks": [
                    t.id for t in design_tasks(project, payload.investigation, analyzer).tasks
                ]
            },
        )

    app.include_router(api)
    web = files("agent_data_workbench").joinpath("web")
    app.mount("/assets", StaticFiles(directory=str(web.joinpath("assets"))), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(str(web.joinpath("index.html")), media_type="text/html")

    return app
