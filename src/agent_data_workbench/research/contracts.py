"""Structured research outputs shared by native agents, SDK and UI."""

from typing import Literal

from pydantic import Field

from ..identifiers import UUIDString
from ..models import Analysis, Contract, Evidence


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
