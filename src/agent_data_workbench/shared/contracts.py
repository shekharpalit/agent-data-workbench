"""Base validation and review contracts shared across domains."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Review(Contract):
    status: Literal["candidate", "accepted", "rejected"] = "candidate"
    note: str = ""
