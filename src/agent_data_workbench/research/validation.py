"""Validate citations and lineage against the investigation snapshot."""

from agent_data_workbench.analysis.contracts import Analysis
from agent_data_workbench.analysis.validation import validate_evidence
from agent_data_workbench.data.contracts import Trace
from agent_data_workbench.research.contracts import ResearchResult
from agent_data_workbench.shared.files import relative_path
from agent_data_workbench.shared.identifiers import new_id


def validate_result(result: ResearchResult, traces: list[Trace]) -> None:
    validate_evidence(result.analysis, traces)
    findings = {f.id for f in result.analysis.findings}
    for signal in result.signals:
        if signal.finding_id not in findings:
            raise ValueError("Signal references an unknown finding")
        from agent_data_workbench.analysis.contracts import Finding

        probe = Finding(
            id=new_id(),
            title="signal",
            category="opportunity",
            confidence="observation",
            explanation="signal",
            recommendation="review",
            evidence=signal.evidence,
        )
        validate_evidence(
            Analysis(summary="signal", findings=[probe], cases=[], limitations=[]), traces
        )
    ids = set()
    for proposal in result.proposals:
        if proposal.id in ids or not set(proposal.finding_ids) <= findings:
            raise ValueError("Proposal has duplicate ID or invalid finding lineage")
        ids.add(proposal.id)
        for edit in proposal.edits:
            relative_path(edit.path)
