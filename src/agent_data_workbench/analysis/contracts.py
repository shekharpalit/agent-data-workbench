"""Evidence-linked findings and candidate evaluation cases."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from agent_data_workbench.evaluation.contracts import Case
from agent_data_workbench.shared.contracts import Contract
from agent_data_workbench.shared.identifiers import UUIDString


class Evidence(Contract):
    trace_id: str
    pointer: str = Field(description="RFC 6901 JSON pointer into this trace's data.")
    quote: str = Field(
        min_length=1, description="Exact nonempty substring of the referenced value."
    )


class Finding(Contract):
    id: UUIDString
    title: str = Field(min_length=1)
    category: Literal["failure", "opportunity"]
    confidence: Literal["observation", "hypothesis"]
    explanation: str = Field(min_length=1)
    recommendation: str = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1)


class Analysis(Contract):
    summary: str = Field(min_length=1)
    findings: list[Finding]
    cases: list[Case]
    limitations: list[str]
