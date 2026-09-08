"""Structured research outputs shared by native agents, SDK and UI."""

from typing import Literal

from pydantic import Field

from agent_data_workbench.analysis.contracts import Analysis, Evidence
from agent_data_workbench.shared.contracts import Contract
from agent_data_workbench.shared.identifiers import UUIDString

ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"]


class Signal(Contract):
    finding_id: UUIDString
    kind: Literal[
        "error",
        "user_correction",
        "friction",
        "recovery",
        "demonstration",
        "cost",
        "latency",
        "behavior_change",
    ]
    impact: Literal["unknown", "low", "medium", "high"]
    impact_reason: str
    evidence: list[Evidence] = Field(min_length=1)


class Edit(Contract):
    path: str
    before: str
    after: str


class Proposal(Contract):
    id: UUIDString
    title: str
    finding_ids: list[UUIDString] = Field(min_length=1)
    kind: Literal["prompt", "tool", "context", "harness", "training_data"]
    hypothesis: str
    expected_effect: str
    evaluation_plan: str
    edits: list[Edit]


class ResearchResult(Contract):
    analysis: Analysis
    signals: list[Signal]
    proposals: list[Proposal]
    open_questions: list[str]
