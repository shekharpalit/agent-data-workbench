"""CLI operations for research."""

from __future__ import annotations

from pathlib import Path

import typer

from ..backends import CliAnalyzer
from ..project import Project
from ..research import investigate, start_investigation
from .common import errors

app = typer.Typer(no_args_is_help=True)


@app.command("investigate")
@errors
def investigate_command(
    project: Path,
    question: str = "What should we improve next?",
    backend: str = "codex",
    model: str | None = None,
    steps: int = 6,
    seed: int = 0,
    timeout: int = 120,
    max_input_chars: int = 120_000,
    resume: str = "",
):
    """Run or resume bounded model-directed research using local search and aggregate tools."""
    p = Project(project)
    key = resume or start_investigation(p, question, seed)["id"]
    typer.echo(f"Investigation: {key}. Provider input uses {backend}'s native CLI/account.")
    value = investigate(
        p,
        key,
        CliAnalyzer(backend, model, timeout),
        max_steps=steps,
        max_input_chars=max_input_chars,
        on_step=lambda action, note: typer.echo(f"{action}: {note}"),
    )
    typer.echo(f"{value['status']}: {p.path('investigations', key)}")
    if value["status"] == "paused":
        typer.echo(f"Resume explicitly with --resume {key}")
