"""Evaluate human-reviewed assertions against exported outputs; never execute model code."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .models import Assertion, ReviewedCase, _reject_constant, pointer_value
from .traces import MAX_FILE_BYTES, read_json


def atomic_text(path: Path, text: str) -> None:
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".agent-data-workbench-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_lines(path: Path) -> list[Any]:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("JSONL file exceeds 50 MiB")
    values = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                values.append(json.loads(line, parse_constant=_reject_constant))
            except ValueError as exc:
                raise ValueError(f"Invalid JSON on line {number}") from exc
    return values


def load_cases(path: Path) -> list[ReviewedCase]:
    cases = [ReviewedCase.model_validate(value) for value in read_lines(path)]
    if not cases:
        raise ValueError("No cases found")
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("Duplicate case IDs")
    for case in cases:
        for assertion in case.assertions:
            if assertion.operator == "equals":
                json.loads(assertion.expected, parse_constant=_reject_constant)
    return cases


def review_cases(path: Path, ids: list[str], status: str, note: str) -> int:
    if status not in {"accepted", "rejected"} or not ids:
        raise ValueError("A review needs case IDs and an accepted or rejected status")
    if not note.strip():
        raise ValueError("A review note is required")
    cases = load_cases(path)
    unknown = set(ids) - {case.id for case in cases}
    if unknown:
        raise ValueError("Unknown case IDs: " + ", ".join(sorted(unknown)))
    for case in cases:
        if case.id in ids:
            case.review.status = status
            case.review.note = note
    atomic_text(path, "".join(case.model_dump_json() + "\n" for case in cases))
    return len(set(ids))


def load_outputs(path: Path) -> dict[str, Any]:
    values = read_lines(path) if path.suffix.lower() in {".jsonl", ".ndjson"} else read_json(path)
    if not isinstance(values, list):
        raise ValueError("Outputs must be a JSON array or JSONL records")
    outputs = {}
    for value in values:
        if not isinstance(value, dict) or not isinstance(value.get("case_id"), str):
            raise ValueError("Every output needs a string case_id and an output field")
        if "output" not in value:
            raise ValueError("Every output needs an output field")
        if value["case_id"] in outputs:
            raise ValueError(f"Duplicate output case_id: {value['case_id']}")
        outputs[value["case_id"]] = value["output"]
    return outputs


def json_equal(left: Any, right: Any) -> bool:
    # Python considers True == 1; JSON booleans and numbers have distinct semantics.
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(json_equal(left[k], right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(json_equal(a, b) for a, b in zip(left, right))
    return (
        type(left) is type(right)
        and left == right
        or (type(left) in (int, float) and type(right) in (int, float) and left == right)
    )


def check_assertion(assertion: Assertion, output: Any) -> tuple[bool, str]:
    try:
        actual = pointer_value(output, assertion.pointer)
    except ValueError:
        return False, "Referenced output field is missing or pointer is invalid"
    if assertion.operator == "exists":
        return True, "Output field exists"
    if assertion.operator == "equals":
        expected = json.loads(assertion.expected, parse_constant=_reject_constant)
        passed = json_equal(actual, expected)
    else:
        if not isinstance(actual, str):
            return False, "Text assertion requires a string output field"
        contains = assertion.expected in actual
        passed = contains if assertion.operator == "contains" else not contains
    return passed, "Assertion passed" if passed else "Assertion failed"


def evaluate(cases: list[ReviewedCase], outputs: dict[str, Any]) -> dict[str, Any]:
    accepted = [case for case in cases if case.review.status == "accepted"]
    if not accepted:
        raise ValueError("No accepted cases. Review and accept cases before evaluation.")
    unknown = set(outputs) - {case.id for case in cases}
    if unknown:
        raise ValueError("Outputs reference unknown cases: " + ", ".join(sorted(unknown)))
    results = []
    for case in accepted:
        checks = []
        if case.id not in outputs:
            checks.append({"passed": False, "reason": "No output submitted for this case"})
        else:
            for assertion in case.assertions:
                passed, reason = check_assertion(assertion, outputs[case.id])
                checks.append({"passed": passed, "pointer": assertion.pointer, "reason": reason})
        results.append(
            {
                "case_id": case.id,
                "passed": all(check["passed"] for check in checks),
                "checks": checks,
            }
        )
    passed = sum(result["passed"] for result in results)
    return {
        "accepted_cases": len(accepted),
        "skipped_unreviewed_or_rejected": len(cases) - len(accepted),
        "passed": passed,
        "failed": len(accepted) - passed,
        "results": results,
        "scope": "Reviewed assertions on submitted outputs; not a claim of production improvement.",
    }


def compare(
    cases: list[ReviewedCase], baseline: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    accepted_ids = {case.id for case in cases if case.review.status == "accepted"}
    for label, outputs in (("baseline", baseline), ("candidate", candidate)):
        missing = accepted_ids - outputs.keys()
        if missing:
            raise ValueError(
                f"Missing {label} outputs for accepted cases: " + ", ".join(sorted(missing))
            )
    before, after = evaluate(cases, baseline), evaluate(cases, candidate)
    before_by_id = {result["case_id"]: result["passed"] for result in before["results"]}
    improved, regressed = [], []
    for result in after["results"]:
        old, new = before_by_id[result["case_id"]], result["passed"]
        if new and not old:
            improved.append(result["case_id"])
        if old and not new:
            regressed.append(result["case_id"])
    return {"baseline": before, "candidate": after, "improved": improved, "regressed": regressed}
