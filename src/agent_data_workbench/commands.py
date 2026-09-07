"""Workbench CLI commands. Existing single-batch commands remain supported."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from .backends import CliAnalyzer
from .benchmark import benchmark as run_benchmark
from .benchmark import review_benchmark
from .experiments import make_suite, run_experiment
from .exports import export_training
from .project import Project
from .research import export_proposal, investigate, start_investigation
from .runners import ConfiguredRunner, RunnerConfig
from .store import JsonSource, TraceStore
from .tasks import (
    TaskSpec,
    audit_task,
    design_tasks,
    replace_task,
    replay_task,
    review_task,
    write_task,
)
from .traces import read_json


def emit(value):
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2))


def runner(path: Path):
    return ConfiguredRunner(RunnerConfig.model_validate(read_json(path)), path.parent)


def register(app: typer.Typer, errors):
    knowledge = typer.Typer(no_args_is_help=True, help="Reviewed, versioned project knowledge.")
    task = typer.Typer(no_args_is_help=True, help="Design, audit and review portable tasks.")
    app.add_typer(knowledge, name="knowledge")
    app.add_typer(task, name="task")

    @app.command("schema")
    @errors
    def schema(kind: str = "task"):
        """Print a JSON Schema for an import or extension contract."""
        from .benchmark import GoldCase, HumanAssessment
        from .research import ResearchStep

        contracts = {
            "task": TaskSpec,
            "runner": RunnerConfig,
            "research": ResearchStep,
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

    @knowledge.command("add")
    @errors
    def knowledge_add(project: Path, file: Path, title: str):
        """Snapshot an explicit policy, source file, tool contract or success definition."""
        if file.stat().st_size > 100_000:
            raise ValueError("Context file exceeds 100,000 bytes")
        emit(
            Project(project).add_knowledge(
                title, file.read_text(encoding="utf-8"), str(file.resolve())
            )
        )

    @knowledge.command("review")
    @errors
    def knowledge_review(project: Path, key: str, status: str, note: str):
        """Accept, reject or return knowledge to draft; record a review note."""
        emit(Project(project).review_knowledge(key, status, note))

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

    @task.command("design")
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

    @task.command("import")
    @errors
    def task_import(project: Path, specification: Path):
        """Import a TaskSpec JSON as draft; never marks it reviewed."""
        p = Project(project)
        with p.lock():
            emit(write_task(p, TaskSpec.model_validate(read_json(specification)), origin="manual"))

    @task.command("edit")
    @errors
    def task_edit(project: Path, key: str, specification: Path, note: str):
        """Replace a task spec; invalidate prior review and audit, preserving its revision."""
        emit(
            replace_task(
                Project(project), key, TaskSpec.model_validate(read_json(specification)), note
            )
        )

    @task.command("replay")
    @errors
    def replay(project: Path, trace_id: str, cutoff: int, title: str = "Next action"):
        """Draft a next-action case with only messages before the exclusive cutoff."""
        emit(replay_task(Project(project), trace_id, cutoff, title))

    @task.command("audit")
    @errors
    def task_audit(project: Path, key: str, judge: str = "", model: str | None = None):
        """Test the grader with valid, alternative, mistake, shortcut and missing evidence."""
        value = audit_task(Project(project), key, CliAnalyzer(judge, model) if judge else None)
        emit(value)
        if not value["passed"]:
            raise typer.Exit(1)

    @task.command("review")
    @errors
    def task_review(project: Path, key: str, status: str, note: str):
        """Accept a meaningful, audited task or reject it with a reason."""
        emit(review_task(Project(project), key, status, note))

    @app.command("suite")
    @errors
    def suite(
        project: Path, name: str, task_id: Annotated[list[str], typer.Option()], seed: int = 0
    ):
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
            judge=CliAnalyzer(judge, judge_model) if judge else None,
            on_trial=lambda r: typer.echo(f"{r['task_id']} {r['variant']}: {r['grade']['status']}"),
        )
        emit({"id": value["id"], "conclusion": value["conclusion"], "summary": value["summary"]})
        if value["summary"]["invalid_pairs"] or value["summary"]["regressed"]:
            raise typer.Exit(1)

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

    @app.command("benchmark")
    @errors
    def benchmark_command(
        dataset: Path,
        out: Path,
        backend: str = "codex",
        model: str | None = None,
        timeout: int = 120,
    ):
        """Evaluate analyzer evidence localization against explicit versioned gold labels."""
        value = run_benchmark(CliAnalyzer(backend, model, timeout), dataset, out)
        emit({k: v for k, v in value.items() if k != "cases"})

    @app.command("benchmark-review")
    @errors
    def benchmark_review(out: Path, annotations: Path, reviewer: str):
        """Record human finding correctness, usefulness and review time separately."""
        emit(review_benchmark(out, annotations, reviewer))

    @app.command("ui")
    @errors
    def ui(project: Path, port: int = 0, open_browser: bool = False):
        """Serve the local workbench on loopback with a per-session access token."""
        from .server import serve

        serve(Project(project), port=port, open_browser=open_browser)

    @app.command("workbench-demo")
    @errors
    def workbench_demo(out: Path):
        """Build and execute a synthetic end-to-end workbench example without provider calls."""
        from .demo import build_demo

        emit(build_demo(out))
