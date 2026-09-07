"""The public data contract. Provider output is untrusted until validated."""

from __future__ import annotations

import json
import re
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def pointer_parts(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/") or re.search(r"~(?![01])", pointer):
        raise ValueError(f"Invalid JSON pointer: {pointer}")
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Trace(Contract):
    trace_id: str
    data: dict[str, Any]


class Evidence(Contract):
    trace_id: str
    pointer: str = Field(description="RFC 6901 JSON pointer into this trace's data.")
    quote: str = Field(
        min_length=1, description="Exact nonempty substring of the referenced value."
    )


class Finding(Contract):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    title: str = Field(min_length=1)
    category: Literal["failure", "opportunity"]
    confidence: Literal["observation", "hypothesis"]
    explanation: str = Field(min_length=1)
    recommendation: str = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1)


class Assertion(Contract):
    pointer: str = Field(description="RFC 6901 JSON pointer into the agent's submitted output.")
    operator: Literal["equals", "contains", "not_contains", "exists"]
    expected: str = Field(
        description="For equals: a JSON-encoded value. For contains/not_contains: literal text. "
        "For exists: empty string."
    )

    @field_validator("pointer")
    @classmethod
    def valid_pointer(cls, value: str) -> str:
        pointer_parts(value)
        return value

    @model_validator(mode="after")
    def valid_expected(self) -> Self:
        if self.operator == "equals":
            try:
                json.loads(self.expected, parse_constant=_reject_constant)
            except ValueError as exc:
                raise ValueError("equals expected must be a JSON-encoded value") from exc
        elif self.operator in {"contains", "not_contains"} and not self.expected:
            raise ValueError("Text assertions need a nonempty expected string")
        elif self.operator == "exists" and self.expected != "":
            raise ValueError("exists expected must be empty")
        return self


class Case(Contract):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    title: str = Field(min_length=1)
    finding_ids: list[str] = Field(min_length=1)
    trace_ids: list[str] = Field(min_length=1)
    input: str = Field(min_length=1, description="The complete request for the agent under test.")
    required_context: list[str] = Field(
        description="Required policies, fixtures, tools or state. Never invent missing context."
    )
    assertions: list[Assertion] = Field(min_length=1)


class Analysis(Contract):
    summary: str = Field(min_length=1)
    findings: list[Finding]
    cases: list[Case]
    limitations: list[str]


class Review(Contract):
    status: Literal["candidate", "accepted", "rejected"] = "candidate"
    note: str = ""


class ReviewedCase(Case):
    review: Review = Field(default_factory=Review)


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def pointer_value(value: Any, pointer: str) -> Any:
    """Resolve RFC 6901, rejecting negative array indices and malformed escapes."""
    for part in pointer_parts(pointer):
        if isinstance(value, list):
            if not part.isascii() or not part.isdigit() or (len(part) > 1 and part[0] == "0"):
                raise ValueError(f"Invalid array index in pointer: {pointer}")
            try:
                value = value[int(part)]
            except IndexError as exc:
                raise ValueError(f"Missing pointer: {pointer}") from exc
        elif isinstance(value, dict) and part in value:
            value = value[part]
        else:
            raise ValueError(f"Missing pointer: {pointer}")
    return value


def validate_evidence(analysis: Analysis, traces: list[Trace]) -> None:
    """Check references and literal evidence. This does not certify a model's conclusions."""
    by_id = {trace.trace_id: trace for trace in traces}
    if len(by_id) != len(traces):
        raise ValueError("Duplicate trace IDs")
    finding_ids: set[str] = set()
    for finding in analysis.findings:
        if finding.id in finding_ids:
            raise ValueError(f"Duplicate finding ID: {finding.id}")
        finding_ids.add(finding.id)
        for evidence in finding.evidence:
            if evidence.trace_id not in by_id:
                raise ValueError(f"Unknown evidence trace ID: {evidence.trace_id}")
            source = pointer_value(by_id[evidence.trace_id].data, evidence.pointer)
            text = source if isinstance(source, str) else json_text(source)
            if evidence.quote not in text:
                raise ValueError(
                    f"Evidence quote does not match {evidence.trace_id}{evidence.pointer}"
                )
    case_ids: set[str] = set()
    for case in analysis.cases:
        if case.id in case_ids:
            raise ValueError(f"Duplicate case ID: {case.id}")
        case_ids.add(case.id)
        if not set(case.finding_ids).issubset(finding_ids):
            raise ValueError(f"Case {case.id} references an unknown finding")
        if not set(case.trace_ids).issubset(by_id):
            raise ValueError(f"Case {case.id} references an unknown trace")


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-JSON numeric constant: {value}")
