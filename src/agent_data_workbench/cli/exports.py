"""CLI operations for exports."""

from __future__ import annotations

from pathlib import Path

import typer

from ..exports import export_training
from ..project import Project
from ..research import export_proposal
from .common import emit, errors

app = typer.Typer(no_args_is_help=True)


@app.command("proposal-export")
@errors
def proposal_export(project: Path, investigation: str, proposal: str, source: Path, out: Path):
    """Export a proposal and checked patch; never apply changes to the source repository."""
    emit(export_proposal(Project(project), investigation, proposal, source, out))


@app.command("training-export")
@errors
def training_export(
    project: Path,
    experiment: str,
    out: Path,
    review_note: str,
    permission_note: str,
    kind: str = "sft",
):
    """Export reviewed optimization outcomes as portable SFT or preference JSONL."""
    emit(
        export_training(
            Project(project),
            experiment,
            out,
            kind=kind,
            review_note=review_note,
            permission_note=permission_note,
        )
    )
