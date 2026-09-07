"""Validated request contracts for the local workbench API."""

from typing import Literal

from pydantic import Field, model_validator

from ..explore import SearchQuery
from ..identifiers import UUIDString
from ..models import Contract, pointer_parts
from ..tasks import TaskSpec

ArtifactKind = Literal["knowledge", "investigations", "tasks", "suites", "experiments", "exports"]


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
    content: str = Field(min_length=1, max_length=100000)
    source: str = Field(min_length=1, max_length=10000)


class AnalyzerRequest(Contract):
    backend: Literal["codex", "claude"] = "codex"
    model: str | None = Field(default=None, max_length=200)


class InvestigationRequest(AnalyzerRequest):
    question: str | None = Field(default=None, max_length=10000)
    resume: UUIDString | None = None
    steps: int = Field(default=6, ge=1, le=12, strict=True)

    @model_validator(mode="after")
    def valid(self):
        if not (self.resume and self.resume.strip()) and not (
            self.question and self.question.strip()
        ):
            raise ValueError("Supply a question or an investigation to resume")
        return self


class TaskDesignRequest(AnalyzerRequest):
    investigation: UUIDString
