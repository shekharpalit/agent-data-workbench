"""Validate citations and lineage against the investigation snapshot."""

from ..identifiers import new_id
from ..models import Analysis, Trace, validate_evidence
from ..tasks import relative_path
from .contracts import ResearchResult


def validate_result(result: ResearchResult, traces: list[Trace]) -> None:
    validate_evidence(result.analysis, traces)
    findings = {f.id for f in result.analysis.findings}
    for signal in result.signals:
        if signal.finding_id not in findings:
            raise ValueError("Signal references an unknown finding")
        from ..models import Finding

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
