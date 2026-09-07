"""CLI operations for knowledge."""

from __future__ import annotations

from pathlib import Path

import typer

from ..project import Project
from .common import emit, errors

app = typer.Typer(no_args_is_help=True)


@app.command("add")
@errors
def knowledge_add(project: Path, file: Path, title: str):
    """Snapshot an explicit policy, source file, tool contract or success definition."""
    if file.stat().st_size > 100_000:
        raise ValueError("Context file exceeds 100,000 bytes")
    emit(
        Project(project).add_knowledge(title, file.read_text(encoding="utf-8"), str(file.resolve()))
    )


@app.command("review")
@errors
def knowledge_review(project: Path, key: str, status: str, note: str):
    """Accept, reject or return knowledge to draft; record a review note."""
    emit(Project(project).review_knowledge(key, status, note))
