"""CLI operations for knowledge."""

from __future__ import annotations

from pathlib import Path

import typer

from agent_data_workbench.cli.common import emit, errors
from agent_data_workbench.workspace.project import Project

app = typer.Typer(no_args_is_help=True)


@app.command("add")
@errors
def knowledge_add(project: Path, file: Path, title: str):
    """Snapshot an explicit policy, source file, tool contract or success definition."""
    emit(
        Project(project).add_knowledge(title, file.read_text(encoding="utf-8"), str(file.resolve()))
    )


@app.command("review")
@errors
def knowledge_review(project: Path, key: str, status: str, note: str):
    """Accept, reject or return knowledge to draft; record a review note."""
    emit(Project(project).review_knowledge(key, status, note))
