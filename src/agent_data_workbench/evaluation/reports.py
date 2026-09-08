"""Readable Markdown reports for paired experiment results."""

from __future__ import annotations


def experiment_report(record: dict) -> str:
    from agent_data_workbench.shared.markdown import md

    summary = record["summary"]
    lines = [
        "# Agent improvement experiment",
        "",
        md(record["conclusion"]),
        "",
        f"Split: {record['split']}. Repeats: {record['repeats']}.",
        "",
        "| Variant | Pass | Fail | Invalid | Recorded cost |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for key in ("baseline", "candidate"):
        s = summary[key]
        lines.append(
            f"| {key} | {s['passed']} | {s['failed']} | {s['invalid']} | {s['recorded_cost_usd']} |"
        )
    lines.extend(
        [
            "",
            "## Per-trial results",
            "",
            "| Task | Trial | Variant | Result |",
            "| --- | ---: | --- | --- |",
        ]
    )
    for r in record["trials"]:
        lines.append(f"| {r['task_id']} | {r['trial']} | {r['variant']} | {r['grade']['status']} |")
    lines.extend(
        [
            "",
            md(summary["uncertainty_note"]),
            "",
            "Command runners execute trusted local code with fresh working directories. "
            "This does not sandbox network or host access. Environment fidelity depends on "
            "the configured runner, fixtures and independent verifier evidence.",
            "",
        ]
    )
    return "\n".join(lines)
