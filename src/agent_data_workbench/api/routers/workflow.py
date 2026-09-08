"""Typed local controls for worlds, calibration, coverage and improvement decisions."""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks
from pydantic import Field

from agent_data_workbench.api.dependencies import JobsDependency, ProjectDependency
from agent_data_workbench.evaluation.calibration import (
    AttemptAdjudication,
    AttemptLabel,
    adjudicate_attempt,
    calibration_summary,
    create_calibration,
    label_attempt,
    load_calibration,
)
from agent_data_workbench.evaluation.coverage import (
    CoverageMapping,
    TaxonomySpec,
    coverage_report,
    create_taxonomy,
    map_coverage,
    review_taxonomy,
)
from agent_data_workbench.evaluation.experiments import run_experiment
from agent_data_workbench.evaluation.improvements import create_improvement, decide_improvement
from agent_data_workbench.evaluation.worlds import WorldSpec, create_world, review_world
from agent_data_workbench.execution.contracts import RunnerConfig
from agent_data_workbench.execution.runners import ConfiguredRunner
from agent_data_workbench.integrations.harbor import (
    HarborComparisonConfig,
    HarborExportConfig,
    compare_harbor,
    export_harbor,
    run_harbor_export,
)
from agent_data_workbench.shared.contracts import Contract
from agent_data_workbench.shared.identifiers import UUIDString
from agent_data_workbench.shared.json import read_json

router = APIRouter(prefix="/workflow")


def configured(path: str) -> ConfiguredRunner:
    source = Path(path).expanduser().resolve()
    return ConfiguredRunner(RunnerConfig.model_validate(read_json(source)), source.parent)


class WorldRequest(Contract):
    spec: WorldSpec
    previous_id: UUIDString | None = None


class WorkflowReview(Contract):
    id: UUIDString
    status: Literal["draft", "accepted", "rejected"]
    note: str = Field(min_length=1)
    reviewer: str = Field(min_length=1)


class ImprovementRequest(Contract):
    name: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)
    expected_behavior: str = Field(min_length=1)
    baseline_path: str = Field(min_length=1)
    candidate_path: str = Field(min_length=1)
    trace_ids: list[str] = Field(default_factory=list)
    task_ids: list[UUIDString] = Field(default_factory=list)
    parent_id: UUIDString | None = None


class DecisionRequest(Contract):
    id: UUIDString
    experiment_id: UUIDString
    decision: Literal["keep", "reject", "inconclusive"]
    reviewer: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ExperimentRequest(Contract):
    suite_id: UUIDString
    baseline_path: str = Field(min_length=1)
    candidate_path: str = Field(min_length=1)
    improvement_id: UUIDString | None = None
    split: Literal["optimization", "validation", "final"] = "validation"
    repeats: int = Field(default=1, ge=1, le=100)
    seed: int = 0
    judge: Literal["codex", "claude"] | None = None
    judge_model: str | None = None


class CalibrationRequest(Contract):
    experiment_id: UUIDString
    name: str = Field(min_length=1)


class LabelRequest(Contract):
    id: UUIDString
    label: AttemptLabel


class AdjudicationRequest(Contract):
    id: UUIDString
    decision: AttemptAdjudication


class TaxonomyRequest(Contract):
    spec: TaxonomySpec
    previous_id: UUIDString | None = None


class MappingRequest(Contract):
    taxonomy_id: UUIDString
    mapping: CoverageMapping


@router.get("")
def workflow_overview(project: ProjectDependency):
    return {
        kind: project.artifacts(kind)
        for kind in ("worlds", "improvements", "calibrations", "taxonomies", "suites")
    }


@router.post("/world")
def world_create(project: ProjectDependency, payload: WorldRequest):
    return create_world(project, payload.spec, payload.previous_id)


@router.post("/world/review")
def world_review(project: ProjectDependency, payload: WorkflowReview):
    return review_world(project, payload.id, payload.status, payload.note, payload.reviewer)


@router.post("/improvement")
def improvement_create(project: ProjectDependency, payload: ImprovementRequest):
    return create_improvement(
        project,
        payload.name,
        payload.hypothesis,
        payload.expected_behavior,
        configured(payload.baseline_path),
        configured(payload.candidate_path),
        trace_ids=payload.trace_ids,
        task_ids=payload.task_ids,
        parent_id=payload.parent_id,
    )


@router.post("/improvement/decision")
def improvement_decide(project: ProjectDependency, payload: DecisionRequest):
    return decide_improvement(
        project,
        payload.id,
        payload.experiment_id,
        payload.decision,
        payload.reviewer,
        payload.reason,
    )


@router.post("/experiment")
def experiment_run(
    project: ProjectDependency,
    jobs: JobsDependency,
    payload: ExperimentRequest,
    background_tasks: BackgroundTasks,
):
    from agent_data_workbench.integrations.analyzers import CliAnalyzer

    baseline, candidate = configured(payload.baseline_path), configured(payload.candidate_path)
    judge = CliAnalyzer(payload.judge, payload.judge_model) if payload.judge else None
    return jobs.launch(
        background_tasks,
        "Run paired experiment",
        lambda: run_experiment(
            project,
            payload.suite_id,
            baseline,
            candidate,
            split=payload.split,
            repeats=payload.repeats,
            seed=payload.seed,
            improvement_id=payload.improvement_id,
            judge=judge,
        ),
    )


@router.post("/calibration")
def calibration_create(project: ProjectDependency, payload: CalibrationRequest):
    return create_calibration(project, payload.experiment_id, payload.name)


@router.get("/calibration/{key}")
def calibration_get(project: ProjectDependency, key: UUIDString):
    return {
        "calibration": load_calibration(project, key),
        "summary": calibration_summary(project, key),
    }


@router.post("/calibration/label")
def calibration_label(project: ProjectDependency, payload: LabelRequest):
    return label_attempt(project, payload.id, payload.label)


@router.post("/calibration/adjudicate")
def calibration_adjudicate(project: ProjectDependency, payload: AdjudicationRequest):
    return adjudicate_attempt(project, payload.id, payload.decision)


@router.post("/taxonomy")
def taxonomy_create(project: ProjectDependency, payload: TaxonomyRequest):
    return create_taxonomy(project, payload.spec, payload.previous_id)


@router.post("/taxonomy/review")
def taxonomy_review(project: ProjectDependency, payload: WorkflowReview):
    return review_taxonomy(project, payload.id, payload.status, payload.note, payload.reviewer)


@router.post("/coverage/map")
def coverage_map(project: ProjectDependency, payload: MappingRequest):
    return map_coverage(project, payload.taxonomy_id, payload.mapping)


@router.get("/coverage/{key}")
def coverage_get(project: ProjectDependency, key: UUIDString):
    return coverage_report(project, key)


class HarborRequest(Contract):
    task_id: UUIDString
    config: HarborExportConfig


class HarborRunRequest(Contract):
    export_id: UUIDString
    timeout: int | None = Field(default=None, ge=1)


@router.post("/harbor/export")
def harbor_export(project: ProjectDependency, payload: HarborRequest):
    return export_harbor(project, payload.task_id, payload.config)


@router.post("/harbor/run")
def harbor_run(
    project: ProjectDependency,
    jobs: JobsDependency,
    payload: HarborRunRequest,
    background_tasks: BackgroundTasks,
):
    return jobs.launch(
        background_tasks,
        "Run exported Harbor task",
        lambda: run_harbor_export(
            project,
            payload.export_id,
            timeout=payload.timeout,
        ),
    )


class HarborComparisonRequest(Contract):
    task_id: UUIDString
    config: HarborComparisonConfig


@router.post("/harbor/compare")
def harbor_compare(
    project: ProjectDependency,
    jobs: JobsDependency,
    payload: HarborComparisonRequest,
    background_tasks: BackgroundTasks,
):
    return jobs.launch(
        background_tasks,
        "Run Harbor comparison",
        lambda: compare_harbor(project, payload.task_id, payload.config),
    )
