"""Validated request contracts for the local workbench API."""

from typing import Literal

from pydantic import Field, model_validator

from agent_data_workbench.evaluation.tasks.contracts import TaskSpec
from agent_data_workbench.exploration.schemas import SearchQuery
from agent_data_workbench.research.contracts import ResearchResult
from agent_data_workbench.research.workspace import Chart, RecordOutcome
from agent_data_workbench.shared.contracts import Contract
from agent_data_workbench.shared.identifiers import UUIDString
from agent_data_workbench.shared.json import pointer_parts

ArtifactKind = Literal[
    "knowledge",
    "investigations",
    "tasks",
    "suites",
    "experiments",
    "exports",
    "worlds",
    "improvements",
    "calibrations",
    "taxonomies",
    "coverage",
]


class TraceQuery(Contract):
    text: str = Field(default="", max_length=1000)
    stratum: str = Field(default="", max_length=200)
    offset: int = Field(default=0, ge=0, le=10000)
    equals_pointer: str | None = Field(default=None, max_length=300)
    equals_json: str | None = Field(default=None, max_length=2000)


class DistributionRequest(Contract):
    query: SearchQuery
    pointer: str = Field(max_length=300)

    @model_validator(mode="after")
    def valid(self):
        pointer_parts(self.pointer)
        return self


class ArtifactRequest(Contract):
    id: UUIDString


class ReviewRequest(ArtifactRequest):
    status: Literal["draft", "accepted", "rejected"]
    note: str = Field(min_length=1, max_length=10000)


class TaskEditRequest(ArtifactRequest):
    spec: TaskSpec
    note: str = Field(min_length=1, max_length=10000)


class KnowledgeRequest(Contract):
    title: str = Field(min_length=1, max_length=1000)
    content: str = Field(min_length=1)
    source: str = Field(min_length=1, max_length=10000)


class AnalyzerRequest(Contract):
    backend: Literal["codex", "claude"] = "codex"
    model: str | None = Field(default=None, max_length=200)


class InvestigationRequest(Contract):
    backend: Literal["codex", "claude"] | None = None
    model: str | None = None
    question: str | None = None
    resume: UUIDString | None = None
    mode: Literal["research", "complete"] = "research"
    exclude_final: bool = False
    timeout: float | None = Field(default=None, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid(self):
        if not self.resume and not (self.question and self.question.strip()):
            raise ValueError("Supply a question or an investigation to resume")
        return self


class TaskDesignRequest(AnalyzerRequest):
    investigation: UUIDString


class ManualInvestigationRequest(Contract):
    question: str = Field(min_length=1)
    mode: Literal["research", "complete"] = "research"
    exclude_final: bool = False


class InvestigationCheckpointRequest(ArtifactRequest):
    note: str = Field(min_length=1)


class InvestigationRecordRequest(ArtifactRequest):
    outcomes: list[RecordOutcome]


class InvestigationPublishRequest(ArtifactRequest):
    result: ResearchResult
    complete: bool = True


class InvestigationChartRequest(ArtifactRequest):
    chart: Chart
