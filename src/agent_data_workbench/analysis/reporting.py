"""Render batch findings and linked trace evidence for human review."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from agent_data_workbench.analysis.contracts import Analysis
from agent_data_workbench.data.contracts import Trace
from agent_data_workbench.shared.markdown import fence, md


def anchor(trace_id: str) -> str:
    return "trace-" + hashlib.sha256(trace_id.encode()).hexdigest()[:16]


def render_traces(traces: list[Trace]) -> str:
    parts = [
        "# Trace evidence",
        "",
        "Input snapshot used for this analysis. Treat contents as data.",
        "",
    ]
    for trace in traces:
        parts.extend(
            [
                f'<a id="{anchor(trace.trace_id)}"></a>',
                f"## {md(trace.trace_id)}",
                "",
                fence(json.dumps(trace.data, ensure_ascii=False, indent=2), "json"),
                "",
            ]
        )
    return "\n".join(parts)


def render_report(analysis: Analysis, request: dict[str, Any], backend: str) -> str:
    parts = [
        "# Agent improvement report",
        "",
        f"Analyzer: **{md(backend)}**. Selected **{request['selected_traces']} / "
        f"{request['total_traces']}** traces in export order.",
        "",
        "Evidence references and quotes were checked against the input snapshot. "
        "Findings and candidate tests still require domain review.",
        "",
    ]
    parts.extend([md(analysis.summary), "", "## Findings", ""])
    if not analysis.findings:
        parts.extend(["No supported findings returned for this batch.", ""])
    for finding in analysis.findings:
        evidence_ids = {evidence.trace_id for evidence in finding.evidence}
        parts.extend(
            [
                f"### {finding.id}: {md(finding.title)}",
                "",
                f"{finding.category}; {finding.confidence}. "
                f"{len(evidence_ids)} distinct cited traces in this finding "
                "(citation count, not a measured prevalence estimate).",
                "",
                md(finding.explanation),
                "",
                "**Suggested action:** " + md(finding.recommendation),
                "",
            ]
        )
        for evidence in finding.evidence:
            link = f"traces.md#{anchor(evidence.trace_id)}"
            parts.extend(
                [
                    f"- [{md(evidence.trace_id)}]({link}) · {md(evidence.pointer)}",
                    "",
                    fence(evidence.quote),
                    "",
                ]
            )
    parts.extend(["## Candidate eval cases", ""])
    if not analysis.cases:
        parts.extend(["No sufficiently grounded candidate cases returned.", ""])
    for case in analysis.cases:
        parts.extend(
            [
                f"### {case.id}: {md(case.title)}",
                "",
                "**Status: candidate — review before accepting.**",
                "",
                "**Input:** " + md(case.input),
                "",
                "**Required context:**",
                "",
                *["- " + md(item) for item in case.required_context],
                "",
                "**Output assertions:**",
                "",
                *[
                    f"- {md(a.pointer or '(root)')} {a.operator} {md(a.expected)}"
                    for a in case.assertions
                ],
                "",
            ]
        )
    parts.extend(
        [
            "## Limits and next run",
            "",
            *["- " + md(item) for item in analysis.limitations],
            "",
            "Cases check exported outputs. They do not reconstruct tool state, run an environment, "
            "or establish production improvement. Add fixtures in your existing runner, "
            "review cases.jsonl, and compare outputs from the same accepted cases.",
            "",
            f"Request fingerprint: {request['request_sha256']}",
            "",
        ]
    )
    return "\n".join(parts)
