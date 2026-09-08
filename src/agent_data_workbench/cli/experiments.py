"""CLI operations for experiments."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from agent_data_workbench.cli.common import emit, errors, runner
from agent_data_workbench.evaluation.experiments import run_experiment
from agent_data_workbench.evaluation.suites import make_suite
from agent_data_workbench.integrations.analyzers import CliAnalyzer
from agent_data_workbench.workspace.project import Project

app = typer.Typer(no_args_is_help=True)


@app.command("suite")
@errors
def suite(project: Path, name: str, task_id: Annotated[list[str], typer.Option()], seed: int = 0):
    """Freeze reviewed tasks into grouped optimization, validation and final-test splits."""
    emit(make_suite(Project(project), name, task_id, seed))


@app.command("experiment")
@errors
def experiment(
    project: Path,
    suite: str,
    baseline: Path,
    candidate: Path,
    split: str = "validation",
    repeats: int = 1,
    seed: int = 0,
    proposal: str = "",
    improvement_id: str | None = None,
    judge: str = "",
    judge_model: str | None = None,
):
    """Execute configured targets. Command adapters run trusted code without a host sandbox."""
    value = run_experiment(
        Project(project),
        suite,
        runner(baseline),
        runner(candidate),
        split=split,
        repeats=repeats,
        seed=seed,
        proposal=proposal,
        improvement_id=improvement_id,
        judge=CliAnalyzer(judge, judge_model) if judge else None,
        on_trial=lambda r: typer.echo(f"{r['task_id']} {r['variant']}: {r['grade']['status']}"),
    )
    emit({"id": value["id"], "conclusion": value["conclusion"], "summary": value["summary"]})
    if value["summary"]["invalid_pairs"] or value["summary"]["regressed"]:
        raise typer.Exit(1)
