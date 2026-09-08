"""Framework-independent trace envelope; original data stays intact."""

from __future__ import annotations

from typing import Any

from agent_data_workbench.shared.contracts import Contract


class Trace(Contract):
    trace_id: str
    data: dict[str, Any]
