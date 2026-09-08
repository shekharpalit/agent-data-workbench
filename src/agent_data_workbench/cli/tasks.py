"""CLI operations for tasks."""

from __future__ import annotations

from pathlib import Path

import typer

from agent_data_workbench.cli.common import emit, errors
from agent_data_workbench.evaluation.tasks.contracts import TaskSpec
from agent_data_workbench.evaluation.tasks.design import design_tasks
from agent_data_workbench.evaluation.tasks.grading import audit_task
from agent_data_workbench.evaluation.tasks.replay import replay_task
from agent_data_workbench.evaluation.tasks.repository import replace_task, review_task, write_task
from agent_data_workbench.integrations.analyzers import CliAnalyzer
from agent_data_workbench.shared.json import read_json
from agent_data_workbench.workspace.project import Project

app = typer.Typer(no_args_is_help=True)


@app.command("design")
@errors
def task_design(
    project: Path,
    investigation: str,
    backend: str = "codex",
    model: str | None = None,
    timeout: int = 180,
):
    """Generate draft tasks and verifier sanity examples from a completed investigation."""
    batch = design_tasks(Project(project), investigation, CliAnalyzer(backend, model, timeout))
    emit({"task_ids": [t.id for t in batch.tasks], "limitations": batch.limitations})


@app.command("import")
@errors
def task_import(project: Path, specification: Path):
    """Import a TaskSpec JSON as draft; never marks it reviewed."""
    p = Project(project)
    with p.lock():
        emit(write_task(p, TaskSpec.model_validate(read_json(specification)), origin="manual"))


@app.command("edit")
@errors
def task_edit(project: Path, key: str, specification: Path, note: str):
    """Replace a task spec; invalidate prior review and audit, preserving its revision."""
    emit(
        replace_task(Project(project), key, TaskSpec.model_validate(read_json(specification)), note)
    )


@app.command("replay")
@errors
def replay(project: Path, trace_id: str, cutoff: int, title: str = "Next action"):
    """Draft a next-action case with only messages before the exclusive cutoff."""
    emit(replay_task(Project(project), trace_id, cutoff, title))


@app.command("audit")
@errors
def task_audit(project: Path, key: str, judge: str = "", model: str | None = None):
    """Test the grader with valid, alternative, mistake, shortcut and missing evidence."""
    value = audit_task(Project(project), key, CliAnalyzer(judge, model) if judge else None)
    emit(value)
    if not value["passed"]:
        raise typer.Exit(1)


@app.command("review")
@errors
def task_review(project: Path, key: str, status: str, note: str):
    """Accept a meaningful, audited task or reject it with a reason."""
    emit(review_task(Project(project), key, status, note))
