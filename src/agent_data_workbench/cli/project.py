"""CLI operations for project."""

from __future__ import annotations

import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from ..ingestion import FilesSource
from ..project import Project
from ..runners import RunnerConfig
from ..store import TraceStore
from ..tasks import (
    TaskSpec,
)
from .common import emit, errors

app = typer.Typer(no_args_is_help=True)


class IngestLayout(StrEnum):
    runs = "runs"
    records = "records"


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
    traces: Annotated[
        list[str] | None,
        typer.Argument(help="Files, directories, or quoted glob patterns to import."),
    ] = None,
    layout: Annotated[
        IngestLayout,
        typer.Option(
            help="runs: each file is one ordered trace; records: each JSONL line is a trace."
        ),
    ] = IngestLayout.runs,
    group_pointer: str = "/thread_id",
    stratum_pointer: str = "/agent_type",
    source_root: Annotated[
        Path | None,
        typer.Option(
            help="Name imported files relative to this directory across separate batches."
        ),
    ] = None,
    archive_stdin: Annotated[
        bool,
        typer.Option(help="Read a tar stream of trace files from stdin (used by make ingest)."),
    ] = False,
):
    """Import multiple JSON/JSONL files together; a failed batch rolls back all its records."""
    if archive_stdin and traces:
        raise ValueError("Use trace paths or --archive-stdin, not both")
    if not archive_stdin and not traces:
        raise ValueError("Provide one or more trace paths, directories, or glob patterns")
    if archive_stdin and source_root is not None:
        raise ValueError(
            "--source-root cannot be used with --archive-stdin; archives already name files"
        )

    store = TraceStore(Project(project))

    def import_source(source: FilesSource):
        result = store.ingest(source, group_pointer=group_pointer, stratum_pointer=stratum_pointer)
        emit({"files": len(source.files), "layout": layout.value, **result})

    if archive_stdin:
        from ..ingest_transport import archive_files

        with archive_files(sys.stdin.buffer) as files:
            import_source(FilesSource(files, layout=layout.value))
    else:
        import_source(FilesSource(traces, layout=layout.value, root=source_root))


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
