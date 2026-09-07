"""CLI operations for project."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ..project import Project
from ..runners import RunnerConfig
from ..store import JsonSource, TraceStore
from ..tasks import (
    TaskSpec,
)
from .common import emit, errors

app = typer.Typer(no_args_is_help=True)


@app.command("schema")
@errors
def schema(kind: str = "task"):
    """Print a JSON Schema for an import or extension contract."""
    from ..benchmark import GoldCase, HumanAssessment
    from ..research import ResearchResult

    contracts = {
        "task": TaskSpec,
        "runner": RunnerConfig,
        "research": ResearchResult,
        "gold-case": GoldCase,
        "human-assessment": HumanAssessment,
    }
    if kind not in contracts:
        raise ValueError("Choose task, runner, research, gold-case or human-assessment")
    emit(contracts[kind].model_json_schema())


@app.command("init")
@errors
def init_project(
    project: Path,
    name: str,
    objective: str,
    criterion: Annotated[list[str], typer.Option()] = [],
):
    """Create a private local workspace for traces and improvement experiments."""
    p = Project.create(project, name, objective, criterion)
    typer.echo(f"Created {p.root}")


@app.command("ingest")
@errors
def ingest(
    project: Path,
    traces: Path,
    group_pointer: str = "/thread_id",
    stratum_pointer: str = "/agent_type",
):
    """Index JSON/JSONL; identical IDs are idempotent, conflicting content is rejected."""
    emit(
        TraceStore(Project(project)).ingest(
            JsonSource(traces), group_pointer=group_pointer, stratum_pointer=stratum_pointer
        )
    )


@app.command("query")
@errors
def query(
    project: Path,
    text: str = "",
    stratum: str = "",
    limit: int = 20,
    offset: int = 0,
    sample: bool = False,
    seed: int = 0,
    aggregate: str = "",
):
    """Search, sample or aggregate a JSON-pointer field without calling a model."""
    store = TraceStore(Project(project))
    emit(
        store.aggregate(aggregate, text=text, stratum=stratum)
        if aggregate
        else store.select(
            text=text, stratum=stratum, limit=limit, offset=offset, sample=sample, seed=seed
        )
    )


@app.command("ui")
@errors
def ui(project: Path, port: int = 0, open_browser: bool = False):
    """Serve the local workbench on loopback with a per-session access token."""
    from ..server import serve

    serve(Project(project), port=port, open_browser=open_browser)
