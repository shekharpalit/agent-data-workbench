"""Validate evidence references and exact quotes against source traces."""

from __future__ import annotations

from agent_data_workbench.analysis.contracts import Analysis
from agent_data_workbench.data.contracts import Trace
from agent_data_workbench.shared.json import json_text, pointer_value


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
