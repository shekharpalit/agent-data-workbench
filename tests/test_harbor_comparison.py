import json
from pathlib import Path

import pytest
from test_harbor_export import template_at
from test_workbench_data import accept, make_project, spec

from agent_data_workbench.data.store import TraceStore
from agent_data_workbench.integrations.harbor import (
    HarborAgentConfig,
    HarborComparisonConfig,
    compare_harbor,
    runtime,
)
from agent_data_workbench.integrations.harbor.results import verifier_grade
from agent_data_workbench.shared.json import read_json


def test_comparison_pairs_frozen_tasks_imports_full_trajectories_and_retains_invalid_outcomes(
    tmp_path, monkeypatch
):
    # Given
    project = make_project(tmp_path)
    task = accept(project, spec(project))
    template = template_at(tmp_path)
    config = HarborComparisonConfig(
        template_directory=str(template),
        baseline=HarborAgentConfig(agent="baseline"),
        candidate=HarborAgentConfig(agent="candidate"),
        repetitions=2,
    )
    original = {
        "schema_version": "ATIF-v1.6",
        "steps": [{"source": "agent", "message": "evidence α " * 10000 + "FINAL"}],
        "metadata": {"ok": False, "count": 0, "missing": None},
    }
    calls = []

    def process(args, prompt, cwd, timeout, **kwargs):
        if args[1:] == ["--version"]:
            return "harbor synthetic-test"
        agent = args[args.index("--agent") + 1]
        calls.append({"agent": agent, "bundle": args[args.index("--path") + 1]})
        directory = (
            Path(args[args.index("--jobs-dir") + 1]) / args[args.index("--job-name") + 1] / "trial"
        )
        (directory / "agent").mkdir(parents=True)
        reward = 0 if agent == "baseline" else 1
        raw = {
            "trial_name": "trial",
            "verifier_result": {"rewards": {"reward": reward}},
            "exception_info": {"exception_type": "TimedOut"} if len(calls) == 3 else None,
            "agent_result": {"cost_usd": 0},
            "agent_execution": {
                "started_at": "2026-09-08T00:00:00+00:00",
                "finished_at": "2026-09-08T00:00:02+00:00",
            },
        }
        (directory / "result.json").write_text(json.dumps(raw))
        (directory / "agent" / "trajectory.json").write_text(json.dumps(original))
        return "Complete logs"

    monkeypatch.setattr(runtime, "run_process", process)
    monkeypatch.setattr(runtime, "pinned_command", lambda command, *args: (command, {}))
    # When
    result = compare_harbor(project, task.id, config)
    # Then
    store = TraceStore(project)
    assert {
        "order": [call["agent"] for call in calls],
        "bundle_count": len({call["bundle"] for call in calls}),
        "outcomes": [
            {"repeat": t["trial"], "variant": t["variant"], "grade": t["grade"]["status"]}
            for t in result["trials"]
        ],
        "improved": result["summary"]["improved"],
        "invalid": result["summary"]["invalid_pairs"],
        "trajectories": [
            store.get(t["trace_ids"][0]).data["trajectories"][0]["data"] for t in result["trials"]
        ],
        "snapshot": result["task_snapshots"],
        "persisted": read_json(project.path("experiments", result["id"])) == result,
    } == {
        "order": ["baseline", "candidate", "candidate", "baseline"],
        "bundle_count": 1,
        "outcomes": [
            {"repeat": 0, "variant": "baseline", "grade": "fail"},
            {"repeat": 0, "variant": "candidate", "grade": "pass"},
            {"repeat": 1, "variant": "candidate", "grade": "invalid"},
            {"repeat": 1, "variant": "baseline", "grade": "fail"},
        ],
        "improved": [{"task_id": task.id, "trial": 0}],
        "invalid": [{"task_id": task.id, "trial": 1}],
        "trajectories": [original] * 4,
        "snapshot": [task.model_dump()],
        "persisted": True,
    }


@pytest.mark.parametrize(
    "reward,exception,expected",
    [
        (1, None, "pass"),
        (0, None, "fail"),
        (None, None, "invalid"),
        ("1", None, "invalid"),
        (True, None, "invalid"),
        (1, {"exception_type": "Timeout"}, "invalid"),
    ],
)
def test_harbor_verifier_never_treats_missing_rewards_or_exceptions_as_success(
    reward, exception, expected
):
    # Given
    config = HarborComparisonConfig(
        template_directory="template",
        baseline=HarborAgentConfig(agent="a"),
        candidate=HarborAgentConfig(agent="b"),
    )
    # When
    actual = verifier_grade(
        {"verifier_result": {"rewards": {"reward": reward}}, "exception_info": exception}, config
    )
    # Then
    assert actual == {
        "status": expected,
        "checks": [
            {
                "kind": "harbor_verifier",
                "reward_key": "reward",
                "reward": reward,
                "operator": "gte",
                "threshold": 1.0,
                "exception": exception,
            }
        ],
        "reason": "Recorded Harbor verifier reward"
        if expected != "invalid"
        else "Missing/invalid verifier reward or execution exception",
    }


def test_completed_harbor_traces_link_to_the_exact_recorded_experiment(tmp_path):
    # Given
    from agent_data_workbench.exploration.lineage import lineage
    from agent_data_workbench.shared.files import save
    from agent_data_workbench.shared.identifiers import new_id

    project = make_project(tmp_path)
    key = new_id()
    save(
        project.path("experiments", key),
        {
            "id": key,
            "conclusion": "Recorded trial",
            "status": "complete",
            "task_snapshots": [],
            "trials": [{"trace_ids": ["r0"]}],
        },
    )
    # When
    graph = lineage(project, trace_id="r0")
    # Then
    assert [{k: edge[k] for k in ("source", "target", "label")} for edge in graph["edges"]] == [
        {"source": "trace:r0", "target": f"experiment:{key}", "label": "recorded in"}
    ]


def test_failed_command_saves_complete_private_logs_without_echoing_them_in_errors(tmp_path):
    # Given
    import sys

    from agent_data_workbench.shared.processes import BackendError, run_process

    prefix = tmp_path / "trial"
    # When
    with pytest.raises(BackendError) as failure:
        run_process(
            [
                sys.executable,
                "-c",
                "import sys; print('output '*20000+'FINAL'); "
                "print('private diagnostic',file=sys.stderr); sys.exit(3)",
            ],
            "",
            tmp_path,
            10,
            log_prefix=prefix,
        )
    # Then
    assert {
        "stdout": (tmp_path / "trial-stdout.log").read_text(),
        "stderr": (tmp_path / "trial-stderr.log").read_text(),
        "echoed_private_log": "private diagnostic" in str(failure.value),
    } == {
        "stdout": "output " * 20000 + "FINAL\n",
        "stderr": "private diagnostic\n",
        "echoed_private_log": False,
    }


@pytest.mark.parametrize("damaged_file", ["result", "trajectory"])
def test_malformed_harbor_artifacts_are_preserved_and_do_not_abort_comparison(
    tmp_path, monkeypatch, damaged_file
):
    # Given
    project = make_project(tmp_path)
    task = accept(project, spec(project))
    config = HarborComparisonConfig(
        template_directory=str(template_at(tmp_path)),
        baseline=HarborAgentConfig(agent="nop"),
        candidate=HarborAgentConfig(agent="codex", use_host_codex_login=True),
    )
    damaged = '{"count": [REDACTED], "message": "full evidence Ω 1 true"}\n'
    calls = []

    def process(args, prompt, cwd, timeout, **kwargs):
        if args[1:] == ["--version"]:
            return "harbor synthetic-test"
        agent = args[args.index("--agent") + 1]
        calls.append(
            {
                "agent": agent,
                "login": kwargs.get("env", {}).get("CODEX_FORCE_AUTH_JSON"),
                "agent_env_option": "--ae" in args,
            }
        )
        folder = (
            Path(args[args.index("--jobs-dir") + 1]) / args[args.index("--job-name") + 1] / "trial"
        )
        (folder / "agent").mkdir(parents=True)
        (folder / "result.json").write_text(
            json.dumps({"verifier_result": {"rewards": {"reward": 1}}})
        )
        (folder / "agent/trajectory.json").write_text('{"steps": [{"message": "complete"}]}')
        if agent == "codex":
            (
                folder / ("result.json" if damaged_file == "result" else "agent/trajectory.json")
            ).write_text(damaged)
        return "Complete"

    monkeypatch.delenv("CODEX_FORCE_AUTH_JSON", raising=False)
    monkeypatch.setattr(runtime, "run_process", process)
    monkeypatch.setattr(runtime, "pinned_command", lambda command, *args: (command, {}))
    # When
    actual = compare_harbor(project, task.id, config)
    candidate = actual["trials"][1]
    trace = TraceStore(project).get(candidate["trace_ids"][0]).data
    artifact = trace["result"] if damaged_file == "result" else trace["trajectories"][0]["data"]
    # Then
    assert {
        "status": actual["status"],
        "outcomes": [trial["grade"]["status"] for trial in actual["trials"]],
        "raw_text": artifact["raw_text"],
        "resolved": trace["resolved"],
        "error_type": candidate["grade"]["checks"][0]["exception"]["exception_type"],
        "calls": calls,
        "captured_environment": candidate["runner_identity"]["environment"],
    } == {
        "status": "complete",
        "outcomes": ["pass", "invalid"],
        "raw_text": damaged,
        "resolved": None,
        "error_type": "WorkbenchHarborArtifactError",
        "calls": [
            {"agent": "nop", "login": None, "agent_env_option": False},
            {"agent": "codex", "login": "1", "agent_env_option": False},
        ],
        "captured_environment": {"CODEX_FORCE_AUTH_JSON": "1"},
    }
