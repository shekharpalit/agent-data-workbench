"""CLI operations for benchmark."""

from __future__ import annotations

from pathlib import Path

import typer

from agent_data_workbench.analysis.benchmark import benchmark as run_benchmark
from agent_data_workbench.analysis.benchmark import review_benchmark
from agent_data_workbench.cli.common import emit, errors
from agent_data_workbench.integrations.analyzers import CliAnalyzer

app = typer.Typer(no_args_is_help=True)


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
