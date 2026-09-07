import pytest
from identities import uid

from agent_data_workbench.evaluation import (
    check_assertion,
    compare,
    evaluate,
    json_equal,
    load_cases,
    load_outputs,
    review_cases,
)
from agent_data_workbench.models import Assertion, ReviewedCase
from agent_data_workbench.workflow import complete_run, prepare_run


def accepted_cases(analysis):
    cases = [ReviewedCase(**case.model_dump()) for case in analysis.cases]
    for case in cases:
        case.review.status = "accepted"
        case.review.note = "Reviewed synthetic fixtures and expected output contracts"
    return cases


def test_unreviewed_cases_are_not_scored(analysis, outputs):
    # Given
    cases = [ReviewedCase(**case.model_dump()) for case in analysis.cases]

    # When / Then
    with pytest.raises(ValueError, match="No accepted cases"):
        evaluate(cases, outputs("candidate.jsonl"))


def test_compare_and_regression_detection(analysis, outputs):
    # Given
    cases = accepted_cases(analysis)
    baseline, candidate = outputs("baseline.jsonl"), outputs("candidate.jsonl")

    # When
    result = compare(cases, baseline, candidate)
    reverse = compare(cases, candidate, baseline)

    # Then
    assert {
        "baseline_passed": result["baseline"]["passed"],
        "candidate_passed": result["candidate"]["passed"],
        "improved": result["improved"],
        "regressed": reverse["regressed"],
    } == {
        "baseline_passed": 0,
        "candidate_passed": 2,
        "improved": [
            uid("C1"),
            uid("C2"),
        ],
        "regressed": [
            uid("C1"),
            uid("C2"),
        ],
    }


@pytest.mark.parametrize("side", ["baseline", "candidate"])
def test_compare_requires_matching_complete_coverage(analysis, outputs, side):
    # Given
    baseline, candidate = outputs("baseline.jsonl"), outputs("candidate.jsonl")
    (baseline if side == "baseline" else candidate).pop(uid("C1"))

    # When / Then
    with pytest.raises(ValueError, match="Missing"):
        compare(accepted_cases(analysis), baseline, candidate)


@pytest.mark.parametrize(
    "operator,expected",
    [
        ("exists", ""),
        ("equals", '"x"'),
        ("contains", "x"),
        ("not_contains", "x"),
    ],
)
def test_missing_field_cannot_pass(operator, expected):
    # Given
    assertion = Assertion(pointer="/missing", operator=operator, expected=expected)

    # When
    passed, reason = check_assertion(assertion, {})

    # Then
    assert {"passed": passed, "reason": reason} == {
        "passed": False,
        "reason": "Referenced output field is missing or pointer is invalid",
    }


@pytest.mark.parametrize(
    "left,right",
    [
        (True, 1),
        (False, 0),
        ({"x": True}, {"x": 1}),
        ([False], [0]),
        ("1", 1),
    ],
)
def test_json_equality_does_not_confuse_types(left, right):
    # Given: values that Python might otherwise coerce during comparison.
    # When
    actual = json_equal(left, right)

    # Then
    assert {"equal": actual} == {"equal": False}


def test_json_numbers_and_order():
    # Given
    left, right = {"x": [1, 2]}, {"x": [1.0, 2.0]}

    # When
    actual = {
        "numeric_equivalence": json_equal(left, right),
        "different_array_order": json_equal([1, 2], [2, 1]),
    }

    # Then
    assert actual == {"numeric_equivalence": True, "different_array_order": False}


def test_nonstring_cannot_pass_text_assertion():
    # Given
    assertion = Assertion(pointer="/value", operator="not_contains", expected="bad")

    # When
    passed, _ = check_assertion(assertion, {"value": 12})

    # Then
    assert {"passed": passed} == {"passed": False}


def test_duplicate_output_rejected(tmp_path):
    # Given
    path = tmp_path / "outputs.jsonl"
    path.write_text(
        '{"case_id":"7707caa1-6992-5c3a-bbd0-7ac198458224","output":{}}\n{"case_id":"7707caa1-6992-5c3a-bbd0-7ac198458224","output":{}}\n'
    )

    # When / Then
    with pytest.raises(ValueError, match="Duplicate output"):
        load_outputs(path)


def test_review_roundtrip_and_invalid_review_does_not_modify(tmp_path, traces, analysis):
    # Given
    run = prepare_run(traces, tmp_path / "run")
    complete_run(run, analysis.model_dump())
    path = run / "cases.jsonl"
    before = path.read_text()

    # When
    with pytest.raises(ValueError, match="Unknown case"):
        review_cases(path, ["missing"], "accepted", "Review note")
    after_invalid = path.read_text()
    with pytest.raises(ValueError, match="review note"):
        review_cases(path, [uid("C1")], "accepted", "")
    review_cases(
        path,
        [uid("C1")],
        "accepted",
        "Fixture and status assertion reviewed",
    )
    cases = load_cases(path)

    # Then
    assert {
        "unchanged_after_invalid": after_invalid == before,
        "reviews": {case.id: case.review.model_dump() for case in cases},
    } == {
        "unchanged_after_invalid": True,
        "reviews": {
            uid("C1"): {
                "status": "accepted",
                "note": "Fixture and status assertion reviewed",
            },
            uid("C2"): {"status": "candidate", "note": ""},
        },
    }


def test_missing_output_is_a_failed_case(analysis):
    # Given
    cases = accepted_cases(analysis)

    # When
    result = evaluate(cases, {})

    # Then
    assert {key: result[key] for key in ["passed", "failed"]} == {"passed": 0, "failed": 2}


def test_unknown_output_case_rejected(analysis):
    # Given
    outputs = {"not-a-case": {}}

    # When / Then
    with pytest.raises(ValueError, match="unknown cases"):
        evaluate(accepted_cases(analysis), outputs)
