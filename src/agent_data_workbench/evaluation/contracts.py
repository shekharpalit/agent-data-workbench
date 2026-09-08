"""Reviewed batch case and output assertion contracts."""

from __future__ import annotations

import json
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from agent_data_workbench.shared.contracts import Contract, Review
from agent_data_workbench.shared.identifiers import UUIDString
from agent_data_workbench.shared.json import _reject_constant, pointer_parts


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
    id: UUIDString
    title: str = Field(min_length=1)
    finding_ids: list[UUIDString] = Field(min_length=1)
    trace_ids: list[str] = Field(min_length=1)
    input: str = Field(min_length=1, description="The complete request for the agent under test.")
    required_context: list[str] = Field(
        description="Required policies, fixtures, tools or state. Never invent missing context."
    )
    assertions: list[Assertion] = Field(min_length=1)


class ReviewedCase(Case):
    review: Review = Field(default_factory=Review)
