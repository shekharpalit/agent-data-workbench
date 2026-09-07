"""Human-readable research reports."""


def research_report(value: dict) -> str:
    from ..reports import md

    result = value["result"]
    analysis = result["analysis"]
    lines = [
        "# Agent investigation",
        "",
        md(value["question"]),
        "",
        md(analysis["summary"]),
        "",
        f"Dataset: {value['source']['total']} traces. Mode: {value.get('mode', 'research')}. "
        "Record processing and evidence review are reported separately in coverage.",
        "",
    ]
    if coverage := value.get("published_coverage"):
        lines.extend(
            [
                f"At publication: {coverage['completed']} completed, {coverage['failed']} failed, "
                f"{coverage['pending']} pending. {coverage['retrieved']} records fetched through "
                "the SDK; direct file reads are not measured and retrieval is not semantic review.",
                "",
            ]
        )
    for finding in analysis["findings"]:
        lines.extend(
            [
                "## " + md(finding["title"]),
                "",
                md(finding["confidence"]),
                "",
                md(finding["explanation"]),
                "",
                md(finding["recommendation"]),
                "",
            ]
        )
        for evidence in finding["evidence"]:
            lines.extend(
                [
                    f"- {md(evidence['trace_id'])} · {md(evidence['pointer'])}: "
                    + md(evidence["quote"])
                ]
            )
        lines.append("")
    for proposal in result["proposals"]:
        lines.extend(
            [
                "## Proposal: " + md(proposal["title"]),
                "",
                md(proposal["hypothesis"]),
                "",
                "Evaluate: " + md(proposal["evaluation_plan"]),
                "",
            ]
        )
    lines.extend(["## Open questions and limits", ""])
    lines.extend("- " + md(v) for v in result["open_questions"] + analysis["limitations"])
    lines.extend(
        [
            "",
            "Exact evidence matching verifies citations, not the interpretation. "
            "Proposals are unexecuted hypotheses until a recorded experiment tests them.",
            "",
        ]
    )
    return "\n".join(lines)
