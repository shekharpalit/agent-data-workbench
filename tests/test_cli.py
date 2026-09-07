import json
from pathlib import Path

from typer.testing import CliRunner

from agent_data_workbench.cli import app

runner = CliRunner()


def test_offline_demo_review_evaluate_compare(tmp_path):
    # Given
    run = tmp_path / "demo"
    cases, baseline, candidate = [
        str(run / name) for name in ("cases.jsonl", "baseline.jsonl", "candidate.jsonl")
    ]

    # When
    demo = runner.invoke(app, ["demo", "--out", str(run)])
    before_review = runner.invoke(app, ["evaluate", cases, candidate])
    review = runner.invoke(
        app,
        [
            "review",
            cases,
            "--accept",
            "C1",
            "--accept",
            "C2",
            "--note",
            "Reviewed the bundled synthetic fixture contracts",
        ],
    )
    baseline_evaluation = runner.invoke(app, ["evaluate", cases, baseline])
    candidate_evaluation = runner.invoke(app, ["evaluate", cases, candidate])
    comparison = runner.invoke(app, ["compare", cases, baseline, candidate])
    reverse = runner.invoke(app, ["compare", cases, candidate, baseline])

    # Then
    assert {
        "exit_codes": {
            "demo": demo.exit_code,
            "before_review": before_review.exit_code,
            "review": review.exit_code,
            "baseline": baseline_evaluation.exit_code,
            "candidate": candidate_evaluation.exit_code,
            "comparison": comparison.exit_code,
            "reverse": reverse.exit_code,
        },
        "synthetic_notice": "no model or real agent was run" in demo.output,
        "improved": json.loads(comparison.output)["improved"],
    } == {
        "exit_codes": {
            "demo": 0,
            "before_review": 2,
            "review": 0,
            "baseline": 1,
            "candidate": 0,
            "comparison": 0,
            "reverse": 1,
        },
        "synthetic_notice": True,
        "improved": ["C1", "C2"],
    }


def test_manual_prepare_finish(tmp_path, sample_data):
    # Given
    run = tmp_path / "manual"

    # When
    prepared = runner.invoke(
        app, ["prepare", str(sample_data.joinpath("traces.jsonl")), "--out", str(run)]
    )
    premature_analysis = (run / "analysis.json").exists()
    finished = runner.invoke(app, ["finish", str(run), str(sample_data.joinpath("analysis.json"))])
    metadata = json.loads((run / "run.json").read_text())

    # Then
    assert {
        "prepare_exit": prepared.exit_code,
        "premature_analysis": premature_analysis,
        "finish_exit": finished.exit_code,
        "backend": metadata["backend"],
    } == {
        "prepare_exit": 0,
        "premature_analysis": False,
        "finish_exit": 0,
        "backend": "manual",
    }


def test_analyze_orchestrates_backend_and_preserves_context(
    tmp_path, sample_data, analysis, monkeypatch
):
    # Given
    observed = {}

    class FakeAnalyzer:
        def __init__(self, backend, **kwargs):
            observed["backend"] = backend

        def analyze(self, prompt, schema):
            observed["policy_in_prompt"] = "Important fixture policy" in prompt
            return analysis.model_dump()

    monkeypatch.setattr("agent_data_workbench.cli.CliAnalyzer", FakeAnalyzer)
    monkeypatch.setattr("agent_data_workbench.cli.shutil.which", lambda name: "/fake/codex")
    context = tmp_path / "policy.txt"
    context.write_text("Important fixture policy")
    run = tmp_path / "analysis"

    # When
    response = runner.invoke(
        app,
        [
            "analyze",
            str(Path(str(sample_data.joinpath("traces.jsonl")))),
            "--context",
            str(context),
            "--out",
            str(run),
        ],
    )

    # Then
    assert {
        "exit_code": response.exit_code,
        "report_exists": (run / "report.md").is_file(),
        "backend_request": observed,
    } == {
        "exit_code": 0,
        "report_exists": True,
        "backend_request": {"backend": "codex", "policy_in_prompt": True},
    }


def test_invalid_review_does_not_succeed(tmp_path):
    # Given
    run = tmp_path / "demo"
    runner.invoke(app, ["demo", "--out", str(run)])

    # When
    result = runner.invoke(
        app, ["review", str(run / "cases.jsonl"), "--accept", "C1", "--reject", "C2", "--note", "x"]
    )

    # Then
    assert {"exit_code": result.exit_code} == {"exit_code": 2}
