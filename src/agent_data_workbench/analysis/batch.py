"""Prepare inspectable analysis batches and validate completed responses."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_data_workbench.analysis.contracts import Analysis
from agent_data_workbench.analysis.prompt import PROMPT_VERSION, build_prompt
from agent_data_workbench.analysis.reporting import render_report, render_traces
from agent_data_workbench.analysis.validation import validate_evidence
from agent_data_workbench.data.contracts import Trace
from agent_data_workbench.data.normalization import fingerprint
from agent_data_workbench.evaluation.contracts import ReviewedCase
from agent_data_workbench.integrations.analyzers import Analyzer
from agent_data_workbench.shared.json import json_text, read_json

DEFAULT_QUESTION = "Which recurring failures and improvement opportunities should I work on next?"


def analyze_traces(
    traces: list[Trace],
    analyzer: Analyzer,
    *,
    question: str = DEFAULT_QUESTION,
    context: str = "",
    max_input_chars: int | None = None,
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


def check_size(prompt: str, limit: int | None) -> None:
    if limit is not None and len(prompt) > limit:
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
    limit: int | None = None,
    max_input_chars: int | None = None,
) -> Path:
    if not traces or limit is not None and limit < 1:
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
        "selection": (
            "all supplied records"
            if len(selected) == len(traces)
            else "first N records in export order; no claim of representativeness"
        ),
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
