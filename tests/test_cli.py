import json
import shutil
from pathlib import Path

from identities import uid
from typer.testing import CliRunner

from agent_data_workbench.cli import app

runner = CliRunner()


def test_review_evaluate_compare_on_explicit_test_fixtures(tmp_path, sample_data):
    # Given
    run = tmp_path / "batch"
    cases, baseline, candidate = [
        str(run / name) for name in ("cases.jsonl", "baseline.jsonl", "candidate.jsonl")
    ]

    # When
    prepared = runner.invoke(app, ["prepare", str(sample_data / "traces.jsonl"), "--out", str(run)])
    finished = runner.invoke(app, ["finish", str(run), str(sample_data / "analysis.json")])
    for name in ("baseline.jsonl", "candidate.jsonl"):
        shutil.copyfile(sample_data / name, run / name)
    before_review = runner.invoke(app, ["evaluate", cases, candidate])
    review = runner.invoke(
        app,
        [
            "review",
            cases,
            "--accept",
            uid("C1"),
            "--accept",
            uid("C2"),
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
            "prepare": prepared.exit_code,
            "finish": finished.exit_code,
            "before_review": before_review.exit_code,
            "review": review.exit_code,
            "baseline": baseline_evaluation.exit_code,
            "candidate": candidate_evaluation.exit_code,
            "comparison": comparison.exit_code,
            "reverse": reverse.exit_code,
        },
        "improved": json.loads(comparison.output)["improved"],
    } == {
        "exit_codes": {
            "prepare": 0,
            "finish": 0,
            "before_review": 2,
            "review": 0,
            "baseline": 1,
            "candidate": 0,
            "comparison": 0,
            "reverse": 1,
        },
        "improved": [
            uid("C1"),
            uid("C2"),
        ],
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

    monkeypatch.setattr("agent_data_workbench.cli.batch.CliAnalyzer", FakeAnalyzer)
    monkeypatch.setattr("agent_data_workbench.cli.batch.shutil.which", lambda name: "/fake/codex")
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


def test_invalid_review_does_not_succeed(tmp_path, sample_data):
    # Given
    run = tmp_path / "batch"
    runner.invoke(app, ["prepare", str(sample_data / "traces.jsonl"), "--out", str(run)])
    runner.invoke(app, ["finish", str(run), str(sample_data / "analysis.json")])

    # When
    result = runner.invoke(
        app,
        [
            "review",
            str(run / "cases.jsonl"),
            "--accept",
            uid("C1"),
            "--reject",
            uid("C2"),
            "--note",
            "x",
        ],
    )

    # Then
    assert {"exit_code": result.exit_code} == {"exit_code": 2}


def test_modular_project_cli_imports_reviews_executes_and_exports(tmp_path, sample_data):
    # Given: explicit test records and trusted command adapters, without a demo command.
    import sys
    from uuid import UUID

    from test_workbench_data import spec

    from agent_data_workbench.project import Project

    directory = tmp_path / "project"
    baseline, candidate = tmp_path / "baseline.json", tmp_path / "candidate.json"
    for path, value in [(baseline, 0), (candidate, 1)]:
        path.write_text(
            json.dumps(
                {
                    "name": path.stem,
                    "kind": "command",
                    "command": [
                        sys.executable,
                        "-c",
                        f"import json; print(json.dumps({{'output': {{'value': {value}}}}}))",
                    ],
                    "environment_version": "test-command-v1",
                    "fidelity": "output",
                }
            )
        )
    # When
    exits = [
        runner.invoke(app, ["init", str(directory), "Test agent", "Reliable outcomes"]).exit_code,
        runner.invoke(app, ["ingest", str(directory), str(sample_data / "traces.jsonl")]).exit_code,
    ]
    project = Project(directory)
    ids = []
    blocked = []
    for index, trace in enumerate(["support-001", "research-001", "coding-001"]):
        task = spec(project, key=uid(f"task-{index}"), trace_ids=[trace])
        task_file = tmp_path / f"task-{index}.json"
        task_file.write_text(task.model_dump_json())
        ids.append(task.id)
        exits.append(
            runner.invoke(app, ["task", "import", str(directory), str(task_file)]).exit_code
        )
        blocked.append(
            runner.invoke(
                app, ["task", "review", str(directory), task.id, "accepted", "Reviewed"]
            ).exit_code
        )
        exits.append(runner.invoke(app, ["task", "audit", str(directory), task.id]).exit_code)
        exits.append(
            runner.invoke(
                app, ["task", "review", str(directory), task.id, "accepted", "Reviewed"]
            ).exit_code
        )
    command = ["suite", str(directory), "Accuracy / current"]
    for key in ids:
        command.extend(["--task-id", key])
    created = runner.invoke(app, command)
    suite = json.loads(created.output)
    executed = runner.invoke(
        app,
        [
            "experiment",
            str(directory),
            suite["id"],
            str(baseline),
            str(candidate),
            "--split",
            "optimization",
        ],
    )
    experiment = project.artifacts("experiments")[0]
    exported = runner.invoke(
        app,
        [
            "training-export",
            str(directory),
            experiment["id"],
            str(tmp_path / "export"),
            "Reviewed test outcomes",
            "Test-owned data",
            "--kind",
            "preference",
        ],
    )
    # Then
    assert {
        "setup": exits,
        "acceptance_before_audit": blocked,
        "execution": [created.exit_code, executed.exit_code, exported.exit_code],
        "suite": {"name": suite["name"], "uuid_version": UUID(suite["id"]).version},
        "experiment": {
            "status": experiment["status"],
            "improved": len(experiment["summary"]["improved"]),
            "invalid": experiment["summary"]["invalid_pairs"],
        },
        "exported": json.loads(exported.output)["records"],
    } == {
        "setup": [0] * 11,
        "acceptance_before_audit": [2, 2, 2],
        "execution": [0, 0, 0],
        "suite": {"name": "Accuracy / current", "uuid_version": 4},
        "experiment": {"status": "complete", "improved": 1, "invalid": []},
        "exported": 1,
    }
