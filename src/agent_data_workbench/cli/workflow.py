"""Local SDK workflow commands; JSON specifications preserve nested data types."""

from pathlib import Path

import typer

from ..calibration import (
    AttemptAdjudication,
    AttemptLabel,
    adjudicate_attempt,
    calibration_summary,
    create_calibration,
    label_attempt,
)
from ..coverage import (
    CoverageMapping,
    TaxonomySpec,
    coverage_report,
    create_taxonomy,
    map_coverage,
    review_taxonomy,
)
from ..improvements import create_improvement, decide_improvement
from ..project import Project
from ..traces import read_json
from ..worlds import WorldSpec, create_world, review_world
from .common import emit, errors, runner

app = typer.Typer(no_args_is_help=True)


@app.command("list")
@errors
def artifacts(project: Path, kind: str):
    """Read local workflow records with their evidence and review history."""
    emit(Project(project).artifacts(kind))


@app.command("world")
@errors
def world(project: Path, specification: Path, previous_id: str | None = None):
    """Create an immutable draft version of reusable world knowledge."""
    emit(
        create_world(
            Project(project), WorldSpec.model_validate(read_json(specification)), previous_id
        )
    )


@app.command("world-review")
@errors
def world_review(project: Path, key: str, status: str, note: str, reviewer: str):
    emit(review_world(Project(project), key, status, note, reviewer))


@app.command("improvement")
@errors
def improvement(
    project: Path,
    name: str,
    hypothesis: str,
    expected_behavior: str,
    baseline: Path,
    candidate: Path,
    parent_id: str | None = None,
    trace_id: list[str] | None = None,
    task_id: list[str] | None = None,
):
    """Snapshot the actual baseline/candidate sources, configurations and patch."""
    emit(
        create_improvement(
            Project(project),
            name,
            hypothesis,
            expected_behavior,
            runner(baseline),
            runner(candidate),
            parent_id=parent_id,
            trace_ids=trace_id,
            task_ids=task_id,
        )
    )


@app.command("decide")
@errors
def decide(project: Path, key: str, experiment_id: str, decision: str, reviewer: str, reason: str):
    """Record keep/reject/inconclusive against measured evidence; applies no code."""
    emit(decide_improvement(Project(project), key, experiment_id, decision, reviewer, reason))


@app.command("calibrate")
@errors
def calibrate(project: Path, experiment_id: str, name: str):
    """Freeze actual attempts for independent reviewer labels."""
    emit(create_calibration(Project(project), experiment_id, name))


@app.command("label")
@errors
def label(project: Path, key: str, specification: Path):
    emit(
        label_attempt(Project(project), key, AttemptLabel.model_validate(read_json(specification)))
    )


@app.command("adjudicate")
@errors
def adjudicate(project: Path, key: str, specification: Path):
    emit(
        adjudicate_attempt(
            Project(project), key, AttemptAdjudication.model_validate(read_json(specification))
        )
    )


@app.command("calibration")
@errors
def calibration(project: Path, key: str):
    emit(calibration_summary(Project(project), key))


@app.command("taxonomy")
@errors
def taxonomy(project: Path, specification: Path, previous_id: str | None = None):
    emit(
        create_taxonomy(
            Project(project), TaxonomySpec.model_validate(read_json(specification)), previous_id
        )
    )


@app.command("taxonomy-review")
@errors
def taxonomy_review(project: Path, key: str, status: str, note: str, reviewer: str):
    emit(review_taxonomy(Project(project), key, status, note, reviewer))


@app.command("map")
@errors
def mapping(project: Path, taxonomy_id: str, specification: Path):
    emit(
        map_coverage(
            Project(project), taxonomy_id, CoverageMapping.model_validate(read_json(specification))
        )
    )


@app.command("coverage")
@errors
def coverage(project: Path, taxonomy_id: str):
    emit(coverage_report(Project(project), taxonomy_id))


@app.command("harbor-export")
@errors
def harbor_export(project: Path, task_id: str, configuration: Path):
    """Bundle a reviewed task with developer-supplied Harbor environment/verifier code."""
    from ..harbor import HarborExportConfig, export_harbor

    emit(
        export_harbor(
            Project(project), task_id, HarborExportConfig.model_validate(read_json(configuration))
        )
    )


@app.command("harbor-run")
@errors
def harbor_run(project: Path, export_id: str, timeout: int | None = None):
    """Execute an exported bundle using the optional installed Harbor CLI."""
    from ..harbor import run_harbor_export

    emit(run_harbor_export(Project(project), export_id, timeout=timeout))
