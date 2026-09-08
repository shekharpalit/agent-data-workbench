"""Typed task specifications, grading criteria, and verifier examples."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from agent_data_workbench.analysis.contracts import Evidence
from agent_data_workbench.evaluation.contracts import Assertion
from agent_data_workbench.evaluation.worlds import WorldReference
from agent_data_workbench.execution.contracts import ConversationSpec, EnvironmentConfig
from agent_data_workbench.shared.contracts import Contract
from agent_data_workbench.shared.files import relative_path
from agent_data_workbench.shared.identifiers import UUIDString
from agent_data_workbench.shared.json import parse_object


class Criterion(Contract):
    id: UUIDString
    description: str = Field(min_length=1)
    source: Literal["output", "artifact", "state"]
    artifact: str = ""
    kind: Literal["assertion", "semantic"] = "assertion"
    assertion: Assertion | None = None
    rubric: str = ""

    @model_validator(mode="after")
    def valid(self):
        if self.source in {"artifact", "state"}:
            relative_path(self.artifact)
        if self.kind == "assertion" and self.assertion is None:
            raise ValueError("Assertion criterion requires an assertion")
        if self.kind == "semantic" and not self.rubric.strip():
            raise ValueError("Semantic criterion requires a rubric")
        return self


class VerifierExample(Contract):
    name: str = Field(min_length=1)
    kind: Literal[
        "valid", "alternative", "mistake", "shortcut", "missing_evidence", "collateral_change"
    ]
    output_json: str
    artifacts_json: str = "{}"
    state_json: str = "{}"
    expected: Literal["pass", "fail", "invalid"]

    @model_validator(mode="after")
    def valid(self):
        parse_object(self.output_json)
        parse_object(self.artifacts_json)
        parse_object(self.state_json)
        required = {
            "valid": "pass",
            "alternative": "pass",
            "mistake": "fail",
            "shortcut": "fail",
            "collateral_change": "fail",
        }
        if self.kind in required and self.expected != required[self.kind]:
            raise ValueError("Verifier example label contradicts its kind")
        if self.kind == "missing_evidence" and self.expected == "pass":
            raise ValueError("Missing evidence must not be labeled as a passing example")
        return self


class TaskSpec(Contract):
    id: UUIDString
    title: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    behavior: str = Field(min_length=1)
    finding_ids: list[UUIDString] = Field(default_factory=list)
    trace_ids: list[str] = Field(min_length=1)
    fidelity: Literal["output", "next_action", "environment"]
    input_json: str = Field(description="Agent-visible JSON only. Exclude answers and graders.")
    context_sha256: str = ""
    world: WorldReference | None = None
    environment: EnvironmentConfig | None = None
    conversation: ConversationSpec | None = None
    assumptions: list[str] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)
    criteria: list[Criterion] = Field(min_length=1)
    verifier_examples: list[VerifierExample] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid(self):
        value = parse_object(self.input_json)
        if self.fidelity == "next_action":
            if not isinstance(value.get("messages"), list) or not value["messages"]:
                raise ValueError("Next-action input requires a nonempty messages prefix")
        if self.environment and self.fidelity != "environment":
            raise ValueError("Environment lifecycle requires environment fidelity")
        if any(c.source == "state" for c in self.criteria) and self.environment is None:
            raise ValueError("Independent state criteria require a configured environment")
        if len({c.id for c in self.criteria}) != len(self.criteria):
            raise ValueError("Duplicate criterion IDs")
        if len({e.name for e in self.verifier_examples}) != len(self.verifier_examples):
            raise ValueError("Duplicate verifier example names")
        return self


class TaskBatch(Contract):
    tasks: list[TaskSpec]
    limitations: list[str]


class SemanticGrade(Contract):
    status: Literal["pass", "fail", "invalid"]
    explanation: str
    evidence: list[Evidence]
