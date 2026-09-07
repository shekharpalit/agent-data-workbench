import json

import pytest
from pydantic import ValidationError

from agent_data_workbench.models import Analysis, pointer_value, validate_evidence
from agent_data_workbench.traces import load_traces, normalize
from agent_data_workbench.workflow import analyze_traces, complete_run, prepare_run


@pytest.mark.parametrize("style", ["jsonl", "array", "wrapper", "single"])
def test_load_trace_formats(tmp_path, style):
    # Given
    record = {"id": "a", "input": "hello", "output": "world"}
    path = tmp_path / ("traces.jsonl" if style == "jsonl" else "traces.json")
    value = {"array": [record], "wrapper": {"traces": [record]}, "single": record}.get(style)
    path.write_text(json.dumps(record) + "\n" if style == "jsonl" else json.dumps(value))
    # When
    result = load_traces(path)
    # Then
    assert [trace.model_dump() for trace in result] == [{"trace_id": "a", "data": record}]


def test_generated_ids_are_content_stable():
    # Given
    forward = {"input": "x", "output": "y"}
    reordered = {"output": "y", "input": "x"}
    # When
    actual = normalize([forward])[0]
    expected = normalize([reordered])[0]
    # Then
    assert actual.model_dump() == expected.model_dump()


@pytest.mark.parametrize("records", [[], [{"id": "x"}, {"id": "x"}], [None], [{"id": 1}]])
def test_invalid_records_rejected(records):
    # Given
    # When / Then
    with pytest.raises(ValueError):
        normalize(records)


def test_bad_line_reports_line_number(tmp_path):
    # Given
    path = tmp_path / "traces.jsonl"
    path.write_text('{"id":"ok"}\nnot-json\n')
    # When / Then
    with pytest.raises(ValueError, match="line 2"):
        load_traces(path)


def test_nonfinite_json_rejected(tmp_path):
    # Given
    path = tmp_path / "traces.json"
    path.write_text('{"id":"bad","value":NaN}')
    # When / Then
    with pytest.raises(ValueError):
        load_traces(path)


@pytest.mark.parametrize("pointer", ["/a/-1", "/a/00", "/a/1", "/bad~2key"])
def test_invalid_pointer_is_not_a_reference(pointer):
    # Given
    # When / Then
    with pytest.raises(ValueError):
        pointer_value({"a": [42]}, pointer)


def test_pointer_escapes_and_empty_key():
    # Given
    record = {"a/b": {"~c": {"": {"value": 7}}}}
    # When
    actual = pointer_value(record, "/a~1b/~0c/")
    # Then
    assert actual == {"value": 7}


@pytest.mark.parametrize(
    "field,value",
    [
        ("trace_id", "invented"),
        ("pointer", "/missing"),
        ("quote", "A quote that was never in the trace"),
    ],
)
def test_hallucinated_evidence_is_rejected(traces, analysis, field, value):
    # Given
    setattr(analysis.findings[0].evidence[0], field, value)
    # When / Then
    with pytest.raises(ValueError):
        validate_evidence(analysis, traces)


def test_unknown_case_lineage_rejected(traces, analysis):
    # Given
    analysis.cases[0].finding_ids = ["imaginary"]
    # When / Then
    with pytest.raises(ValueError, match="unknown finding"):
        validate_evidence(analysis, traces)


def test_duplicate_findings_rejected(traces, analysis):
    # Given
    analysis.findings.append(analysis.findings[0])
    # When / Then
    with pytest.raises(ValueError, match="Duplicate"):
        validate_evidence(analysis, traces)


def test_empty_and_malformed_assertions_rejected(analysis):
    # Given
    value = analysis.model_dump()
    value["cases"][0]["assertions"][0]["pointer"] = "/missing/bad~2key"
    # When / Then
    with pytest.raises(ValidationError):
        Analysis.model_validate(value)
    # When
    value["cases"][0]["assertions"][0] = {
        "pointer": "/message",
        "operator": "contains",
        "expected": "",
    }
    # Then
    with pytest.raises(ValidationError):
        Analysis.model_validate(value)


def test_snapshot_selection_and_evidence_report(tmp_path, traces, analysis):
    # Given
    run = tmp_path / "run"
    prepare_run(traces, run, limit=4)
    # When
    complete_run(run, analysis.model_dump(), backend="fixture")
    request = json.loads((run / "request.json").read_text())
    report = (run / "report.md").read_text()
    case = json.loads((run / "cases.jsonl").read_text().splitlines()[0])
    # Then
    assert {
        "selected": request["selected_traces"],
        "total": request["total_traces"],
        "links_evidence": "traces.md#trace-" in report,
        "includes_summary": "Synthetic demo" in report,
        "review": case["review"]["status"],
    } == {
        "selected": 4,
        "total": 4,
        "links_evidence": True,
        "includes_summary": True,
        "review": "candidate",
    }


def test_subset_cannot_cite_excluded_trace(tmp_path, traces, analysis):
    # Given
    run = prepare_run(traces, tmp_path / "subset", limit=1)
    # When / Then
    with pytest.raises(ValueError, match="Unknown evidence trace"):
        complete_run(run, analysis.model_dump())
    assert not (run / "analysis.json").exists()


def test_input_limit_fails_before_writing(tmp_path, traces):
    # Given
    run = tmp_path / "oversize"
    # When / Then
    with pytest.raises(ValueError, match="Nothing was sent"):
        prepare_run(traces, run, max_input_chars=10)
    assert not run.exists()


def test_existing_directory_is_not_overwritten(tmp_path, traces):
    # Given
    sentinel = tmp_path / "keep.txt"
    sentinel.write_text("keep")
    # When / Then
    with pytest.raises(ValueError, match="new or empty"):
        prepare_run(traces, tmp_path)
    assert sentinel.read_text() == "keep"


def test_changed_snapshot_rejected(tmp_path, traces, analysis):
    # Given
    run = prepare_run(traces, tmp_path / "run")
    request = json.loads((run / "request.json").read_text())
    request["context"] = "Changed after preparation"
    (run / "request.json").write_text(json.dumps(request))
    # When / Then
    with pytest.raises(ValueError, match="request changed"):
        complete_run(run, analysis.model_dump())


def test_sdk_analyzer_contract(traces, analysis):
    # Given
    class CustomAnalyzer:
        name = "test"

        def analyze(self, prompt, schema):
            assert {
                "question": "developer-specific question" in prompt,
                "context": "policy context" in prompt,
                "trace": "support-001" in prompt,
                "extra_properties": schema["additionalProperties"],
            } == {"question": True, "context": True, "trace": True, "extra_properties": False}
            return analysis.model_dump()

    # When
    result = analyze_traces(
        traces, CustomAnalyzer(), question="developer-specific question", context="policy context"
    )
    # Then
    assert result.model_dump() == analysis.model_dump()


def test_sdk_rejects_duplicate_trace_ids(traces, analysis):
    # Given
    class CustomAnalyzer:
        name = "test"

        def analyze(self, prompt, schema):
            raise AssertionError("Should reject before invoking the provider")

    # When / Then
    with pytest.raises(ValueError, match="Duplicate trace"):
        analyze_traces([traces[0], traces[0]], CustomAnalyzer())
