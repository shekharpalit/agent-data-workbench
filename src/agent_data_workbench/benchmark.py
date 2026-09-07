"""Measure analyzer evidence localization against explicit, versioned gold labels."""

from __future__ import annotations

import time
from pathlib import Path

from pydantic import Field

from .backends import Analyzer
from .models import Contract
from .project import digest, now, save
from .traces import normalize, read_json
from .workflow import analyze_traces


class ExpectedSignal(Contract):
    trace_id: str
    pointer: str
    category: str


class GoldCase(Contract):
    id: str
    traces_json: str
    context: str
    question: str
    expected: list[ExpectedSignal]
    label_source: str = Field(min_length=1)


class HumanAssessment(Contract):
    case_id: str
    finding_id: str
    correct: bool
    actionable: bool
    useful_for_task: bool
    review_seconds: float = Field(ge=0, allow_inf_nan=False)
    note: str = Field(min_length=1)


def review_benchmark(out: Path, annotations: Path, reviewer: str) -> dict:
    """Keep human usefulness judgments separate from automatic exact-span scores."""
    report = read_json(out / "report.json")
    values = [HumanAssessment.model_validate(v) for v in read_json(annotations)]
    if not reviewer.strip() or not values:
        raise ValueError("Supply a reviewer and at least one assessment")
    expected = {
        (case["id"], finding["id"])
        for case in report["cases"]
        if case["status"] == "completed"
        for finding in case["analysis"]["findings"]
    }
    actual = {(v.case_id, v.finding_id) for v in values}
    if len(actual) != len(values) or not actual <= expected:
        raise ValueError("Assessments must reference unique returned findings")
    value = {
        "at": now(),
        "reviewer": reviewer,
        "report_sha256": digest(report),
        "assessments": [v.model_dump() for v in values],
        "coverage": {"reviewed": len(values), "total_findings": len(expected)},
        "correct_fraction": sum(v.correct for v in values) / len(values),
        "actionable_fraction": sum(v.actionable for v in values) / len(values),
        "useful_for_task_fraction": sum(v.useful_for_task for v in values) / len(values),
        "total_review_seconds": sum(v.review_seconds for v in values),
        "scope": "Human judgments over reviewed findings only; record misses in gold labels.",
    }
    from uuid import uuid4

    save(out / ("human-review-" + uuid4().hex[:12] + ".json"), value)
    return value


def benchmark(analyzer: Analyzer, dataset: Path, out: Path) -> dict:
    import json

    raw = read_json(dataset)
    cases = [GoldCase.model_validate(c) for c in raw["cases"]]
    if not cases or len({c.id for c in cases}) != len(cases):
        raise ValueError("Benchmark needs unique cases")
    if out.exists():
        raise ValueError("Benchmark output already exists")
    out.mkdir(parents=True, mode=0o700)
    results, tp, fp, fn, errors = [], 0, 0, 0, 0
    for case in cases:
        started = time.monotonic()
        traces = normalize(json.loads(case.traces_json))
        expected = {(e.trace_id, e.pointer, e.category) for e in case.expected}
        for key, pointer, _ in expected:
            from .models import pointer_value

            source = next((t for t in traces if t.trace_id == key), None)
            if source is None:
                raise ValueError("Gold label references unknown trace")
            pointer_value(source.data, pointer)
        try:
            analysis = analyze_traces(
                traces, analyzer, question=case.question, context=case.context
            )
            found = {
                (e.trace_id, e.pointer, f.category) for f in analysis.findings for e in f.evidence
            }
            matched, extra, missed = found & expected, found - expected, expected - found
            tp += len(matched)
            fp += len(extra)
            fn += len(missed)
            results.append(
                {
                    "id": case.id,
                    "label_source": case.label_source,
                    "status": "completed",
                    "matched": [list(v) for v in sorted(matched)],
                    "extra": [list(v) for v in sorted(extra)],
                    "missed": [list(v) for v in sorted(missed)],
                    "analysis": analysis.model_dump(),
                    "seconds": time.monotonic() - started,
                }
            )
        except RuntimeError, ValueError, OSError:
            errors += 1
            fn += len(expected)
            results.append(
                {"id": case.id, "status": "analyzer_error", "seconds": time.monotonic() - started}
            )
        save(out / "progress.json", results)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    report = {
        "created_at": now(),
        "dataset_sha256": digest(raw),
        "dataset": raw.get("name"),
        "analyzer": analyzer.name,
        "model": getattr(analyzer, "model", None),
        "true_positive_spans": tp,
        "extra_spans": fp,
        "missed_spans": fn,
        "precision": precision,
        "recall": recall,
        "errors": errors,
        "cases": results,
        "scope": "Strict evidence-span localization, not semantic quality or production gain. "
        "Extra supporting spans count as extra labels. Review explanations and tasks separately.",
    }
    save(out / "report.json", report)
    return report
