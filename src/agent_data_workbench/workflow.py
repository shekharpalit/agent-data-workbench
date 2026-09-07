"""Prepare inspectable input, validate analysis, and produce portable local artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .backends import Analyzer
from .models import Analysis, ReviewedCase, Trace, json_text, validate_evidence
from .prompt import PROMPT_VERSION, build_prompt
from .traces import fingerprint, read_json

DEFAULT_QUESTION = "Which recurring failures and improvement opportunities should I work on next?"


def analyze_traces(
    traces: list[Trace],
    analyzer: Analyzer,
    *,
    question: str = DEFAULT_QUESTION,
    context: str = "",
    max_input_chars: int = 120_000,
) -> Analysis:
    if not traces:
        raise ValueError("At least one trace is required")
    if len({trace.trace_id for trace in traces}) != len(traces):
        raise ValueError("Duplicate trace IDs")
    prompt = build_prompt(traces, question, context)
    check_size(prompt, max_input_chars)
    result = Analysis.model_validate(analyzer.analyze(prompt, Analysis.model_json_schema()))
    validate_evidence(result, traces)
    return result


def check_size(prompt: str, limit: int) -> None:
    if len(prompt) > limit:
        raise ValueError(
            f"Prepared input has {len(prompt):,} characters, exceeding {limit:,}. "
            "Use fewer traces/context or explicitly increase --max-input-chars. Nothing was sent."
        )


def request_digest(request: dict[str, Any]) -> str:
    payload = {key: value for key, value in request.items() if key != "request_sha256"}
    return hashlib.sha256(json_text(payload).encode()).hexdigest()


def prepare_run(
    traces: list[Trace],
    out: Path,
    *,
    question: str = DEFAULT_QUESTION,
    context: str = "",
    limit: int = 100,
    max_input_chars: int = 120_000,
) -> Path:
    if not traces or limit < 1:
        raise ValueError("At least one trace and a positive limit are required")
    if len({trace.trace_id for trace in traces}) != len(traces):
        raise ValueError("Duplicate trace IDs")
    selected = traces[:limit]
    prompt = build_prompt(selected, question, context)
    check_size(prompt, max_input_chars)
    request: dict[str, Any] = {
        "protocol_version": PROMPT_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "total_traces": len(traces),
        "selected_traces": len(selected),
        "selection": "first N records in export order; no claim of representativeness",
        "source_sha256": fingerprint(traces),
        "selected_sha256": fingerprint(selected),
        "question": question,
        "context": context,
        "traces": [trace.model_dump() for trace in selected],
    }
    request["request_sha256"] = request_digest(request)
    if out.is_symlink() or out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError(f"Output directory must be new or empty: {out}")
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_json(out / "request.json", request)
    write_json(out / "schema.json", Analysis.model_json_schema())
    (out / "prompt.txt").write_text(prompt, encoding="utf-8")
    (out / "traces.md").write_text(render_traces(selected), encoding="utf-8")
    return out


def load_request(out: Path) -> tuple[dict[str, Any], list[Trace]]:
    request = read_json(out / "request.json")
    if not isinstance(request, dict) or request.get("protocol_version") != PROMPT_VERSION:
        raise ValueError("Unsupported or invalid prepared request")
    if request.get("request_sha256") != request_digest(request):
        raise ValueError("Prepared request changed; prepare a fresh run")
    traces = [Trace.model_validate(value) for value in request["traces"]]
    if fingerprint(traces) != request["selected_sha256"]:
        raise ValueError("Trace snapshot does not match its recorded fingerprint")
    return request, traces


def complete_run(out: Path, response: Any, *, backend: str = "manual") -> Analysis:
    if (out / "analysis.json").exists():
        raise ValueError("This run already has analysis; use a new run directory")
    request, traces = load_request(out)
    analysis = Analysis.model_validate(response)
    validate_evidence(analysis, traces)
    write_json(
        out / "run.json",
        {
            "backend": backend,
            "completed_at": datetime.now(UTC).isoformat(),
            "request_sha256": request["request_sha256"],
            "prompt_version": PROMPT_VERSION,
            "evidence_checks": "IDs, pointers and quotes checked; conclusions need review.",
        },
    )
    cases = [ReviewedCase(**case.model_dump()) for case in analysis.cases]
    (out / "cases.jsonl").write_text(
        "".join(case.model_dump_json() + "\n" for case in cases), encoding="utf-8"
    )
    (out / "report.md").write_text(render_report(analysis, request, backend), encoding="utf-8")
    write_json(out / "analysis.json", analysis.model_dump())
    return analysis


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def md(value: str) -> str:
    # Keep supplied text as text instead of turning trace content into HTML/links/images.
    return re.sub(r"([\\\x60*_{}\[\]()<>#!|])", r"\\\1", value).replace("\n", " ")


def anchor(trace_id: str) -> str:
    return "trace-" + hashlib.sha256(trace_id.encode()).hexdigest()[:16]


def fence(value: str, language: str = "") -> str:
    marker = chr(96) * max(
        3, max((len(m.group()) + 1 for m in re.finditer(r"`+", value)), default=3)
    )
    return marker + language + "\n" + value + "\n" + marker


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
    if backend == "fixture":
        parts.extend(["**Synthetic demo with a prewritten analysis; no model was called.**", ""])
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
