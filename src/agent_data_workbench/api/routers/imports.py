"""Dataset inspection and atomic import operations for the local UI."""

from fastapi import APIRouter, BackgroundTasks

from agent_data_workbench.api.dependencies import JobsDependency, ProjectDependency
from agent_data_workbench.data.imports import import_dataset
from agent_data_workbench.integrations.huggingface import DatasetImport, HuggingFaceSource

router = APIRouter(prefix="/imports")


@router.get("")
def imports(project: ProjectDependency):
    return project.artifacts("imports")


@router.post("/huggingface/inspect")
def inspect_dataset(payload: DatasetImport):
    from huggingface_hub.errors import HfHubHTTPError

    try:
        source = HuggingFaceSource(payload)
    except HfHubHTTPError as exc:
        raise ValueError(
            "Cannot access this Hugging Face source. "
            "Check the dataset, revision and local Hugging Face login."
        ) from exc
    return {"source": source.source, "config": source.config.model_dump()}


@router.post("/huggingface")
def ingest_dataset(
    project: ProjectDependency,
    jobs: JobsDependency,
    payload: DatasetImport,
    background_tasks: BackgroundTasks,
):
    return jobs.launch(
        background_tasks, "Import Hugging Face dataset", lambda: import_dataset(project, payload)
    )
