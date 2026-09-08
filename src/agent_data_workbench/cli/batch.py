"""Local command-line entry point."""

from __future__ import annotations

import json
import shutil
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer

from agent_data_workbench.analysis.batch import (
    DEFAULT_QUESTION,
    complete_run,
    load_request,
    prepare_run,
)
from agent_data_workbench.analysis.contracts import Analysis
from agent_data_workbench.analysis.prompt import build_prompt
from agent_data_workbench.cli.common import errors
from agent_data_workbench.data.normalization import load_traces
from agent_data_workbench.evaluation.cases import compare as compare_outputs
from agent_data_workbench.evaluation.cases import evaluate as evaluate_outputs
from agent_data_workbench.evaluation.cases import load_cases, load_outputs, review_cases
from agent_data_workbench.integrations.analyzers import CliAnalyzer
from agent_data_workbench.shared.identifiers import new_id
from agent_data_workbench.shared.json import read_json
from agent_data_workbench.shared.processes import BackendError

app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    help="Turn agent traces into evidence-linked findings and reviewable eval cases.",
)
File = Annotated[Path, typer.Argument(exists=True, file_okay=True, dir_okay=False)]


class Backend(str, Enum):
    codex = "codex"
    claude = "claude"


def output_path(out: Path | None) -> Path:
    return out if out is not None else Path("runs") / new_id()


def context_text(paths: list[Path]) -> str:
    pieces = []
    for path in paths:
        pieces.append(f"Context file: {path.name}\n" + path.read_text(encoding="utf-8"))
    return "\n\n".join(pieces)


@app.command()
@errors
def prepare(
    traces: File,
    out: Annotated[Path | None, typer.Option(help="New or empty output directory.")] = None,
    context: Annotated[
        list[Path], typer.Option(help="Explicit context text file; repeatable.")
    ] = [],
    question: str = DEFAULT_QUESTION,
    limit: Annotated[int | None, typer.Option(min=1)] = None,
    max_input_chars: Annotated[int | None, typer.Option(min=1)] = None,
):
    """Prepare a snapshot and prompt without calling a model."""
    destination = prepare_run(
        load_traces(traces),
        output_path(out),
        question=question,
        context=context_text(context),
        limit=limit,
        max_input_chars=max_input_chars,
    )
    typer.echo(f"Prepared {destination.resolve()}")
    typer.echo("Inspect prompt.txt and request.json. Use finish to import a structured analysis.")


@app.command()
@errors
def analyze(
    traces: File,
    backend: Backend = Backend.codex,
    out: Annotated[Path | None, typer.Option(help="New or empty output directory.")] = None,
    context: Annotated[
        list[Path], typer.Option(help="Explicit context text file; repeatable.")
    ] = [],
    question: str = DEFAULT_QUESTION,
    limit: Annotated[int | None, typer.Option(min=1)] = None,
    max_input_chars: Annotated[int | None, typer.Option(min=1)] = None,
    timeout: Annotated[int, typer.Option(min=1)] = 300,
    model: str | None = None,
):
    """Analyze a batch using the selected local CLI's authentication and account limits."""
    analyzer = CliAnalyzer(backend.value, model=model, timeout=timeout)
    if shutil.which(backend.value) is None:
        raise BackendError(f"{backend.value} is not installed or not on PATH")
    destination = prepare_run(
        load_traces(traces),
        output_path(out),
        question=question,
        context=context_text(context),
        limit=limit,
        max_input_chars=max_input_chars,
    )
    request, selected = load_request(destination)
    typer.echo(
        f"Analyzing {len(selected)}/{request['total_traces']} traces with {backend.value} "
        f"(timeout {timeout}s). Input is sent through that provider's CLI."
    )
    response = analyzer.analyze(
        build_prompt(selected, question, request["context"]), Analysis.model_json_schema()
    )
    result = complete_run(destination, response, backend=backend.value)
    typer.echo(f"{len(result.findings)} findings; {len(result.cases)} candidate cases")
    typer.echo(f"Report: {(destination / 'report.md').resolve()}")


@app.command()
@errors
def finish(
    run: Annotated[Path, typer.Argument(exists=True, file_okay=False, dir_okay=True)],
    response: File,
):
    """Validate a manually produced analysis JSON against a prepared trace snapshot."""
    result = complete_run(run, read_json(response), backend="manual")
    typer.echo(f"{len(result.findings)} findings; {len(result.cases)} candidate cases")
    typer.echo(f"Report: {(run / 'report.md').resolve()}")


@app.command()
@errors
def review(
    cases: File,
    accept: Annotated[list[str], typer.Option(help="Case ID to accept; repeatable.")] = [],
    reject: Annotated[list[str], typer.Option(help="Case ID to reject; repeatable.")] = [],
    note: Annotated[
        str, typer.Option(help="Why this case is meaningful, or why it is rejected.")
    ] = "",
):
    """Record a review decision after checking the case's fixtures and assertions."""
    if bool(accept) == bool(reject):
        raise ValueError("Specify either --accept ID or --reject ID (repeat for more cases)")
    status, ids = ("accepted", accept) if accept else ("rejected", reject)
    count = review_cases(cases, ids, status, note)
    typer.echo(f"{status.capitalize()} {count} case(s)")


@app.command()
@errors
def evaluate(cases: File, outputs: File):
    """Check accepted cases against exported outputs. Exit 1 if any case fails."""
    result = evaluate_outputs(load_cases(cases), load_outputs(outputs))
    typer.echo(json.dumps(result, indent=2))
    if result["failed"]:
        raise typer.Exit(1)


@app.command()
@errors
def compare(cases: File, baseline: File, candidate: File):
    """Compare the same accepted cases. Exit 1 if any case regresses."""
    result = compare_outputs(load_cases(cases), load_outputs(baseline), load_outputs(candidate))
    typer.echo(json.dumps(result, indent=2))
    if result["regressed"]:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
