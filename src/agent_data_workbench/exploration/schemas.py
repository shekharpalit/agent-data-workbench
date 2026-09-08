"""Validated requests for the local trace explorer."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import Field, model_validator

from agent_data_workbench.shared.contracts import Contract
from agent_data_workbench.shared.json import _reject_constant, json_text, pointer_parts


class FieldFilter(Contract):
    pointer: str = Field(max_length=300)
    operator: Literal["equals", "contains", "gte", "lte", "exists", "missing"] = "equals"
    value_json: str = Field(default="null", max_length=2000)

    @model_validator(mode="after")
    def valid(self):
        pointer_parts(self.pointer)
        value = json.loads(self.value_json, parse_constant=_reject_constant)
        json_text(value)  # Reject numeric overflow, including nested nonfinite values.
        if self.operator in {"gte", "lte"} and type(value) not in {int, float}:
            raise ValueError("Numeric comparisons require a JSON number")
        if self.operator == "contains" and not isinstance(value, str):
            raise ValueError("Contains requires a JSON string")
        return self


class SearchQuery(Contract):
    text: str = Field(default="", max_length=1000)
    stratum: str = Field(default="", max_length=200)
    filters: list[FieldFilter] = Field(default_factory=list, max_length=8)
    sort: str = Field(default="trace_id", max_length=300)
    direction: Literal["asc", "desc"] = "asc"
    limit: int = Field(default=20, ge=1, le=200)
    offset: int = Field(default=0, ge=0, le=10000)
    trace_ids: list[str] | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def valid(self):
        if self.sort not in {"trace_id", "stratum"}:
            pointer_parts(self.sort)
        return self


class ClusterQuery(Contract):
    query: SearchQuery = Field(default_factory=SearchQuery)
    pointer: str = Field(default="/input", max_length=300)
    threshold: float = Field(default=0.55, ge=0.1, le=1, allow_inf_nan=False)
    limit: int = Field(default=100, ge=2, le=200)

    @model_validator(mode="after")
    def valid(self):
        pointer_parts(self.pointer)
        return self
