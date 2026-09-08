import json
import re
import sys

import pytest
from fastapi.testclient import TestClient
from identities import uid
from test_workbench_data import Scripted, accept, make_project, result, spec

from agent_data_workbench.analysis.benchmark import benchmark, review_benchmark
from agent_data_workbench.api import create_app
from agent_data_workbench.evaluation.experiments import run_experiment
from agent_data_workbench.evaluation.statistics import summarize
from agent_data_workbench.evaluation.suites import make_suite
from agent_data_workbench.evaluation.tasks.repository import load_task, replace_task
from agent_data_workbench.execution.artifacts import read_artifacts
from agent_data_workbench.execution.contracts import Execution, RunnerConfig
from agent_data_workbench.execution.runners import ConfiguredRunner
from agent_data_workbench.integrations.training import export_training
from agent_data_workbench.shared.files import save
from agent_data_workbench.shared.json import read_json


@pytest.fixture
def project(tmp_path):
    return make_project(tmp_path)


def suite(project, name="suite", extra=False):
    tasks = [accept(project, spec(project, key=f"T{i}", trace_ids=[f"r{i}"])) for i in range(9)]
    if extra:
        tasks.append(accept(project, spec(project, key="joined", trace_ids=["r0", "r1"])))
        tasks.append(accept(project, spec(project, key="transitive", trace_ids=["r1", "r2"])))
    return make_suite(project, name, [t.id for t in tasks], seed=7)


class FixedRunner:
    def __init__(self, value=1, status="completed"):
        self.value = value
        self.status = status
        self.directories = []
        self.inputs = []

    def identity(self):
        return {"fixture": True, "value": self.value}

    def run(self, visible_input, trial_dir, seed):
        assert not list(trial_dir.iterdir())
        assert set(visible_input) == {"request", "expected_input"}
        self.directories.append(trial_dir)
        self.inputs.append(visible_input)
        (trial_dir / "test.txt").write_text("fresh directory")
        return Execution(output={"value": self.value}, status=self.status, cost_usd=0.01)


def test_correlated_and_transitively_related_tasks_never_cross_splits(project):
    # Given: the synthetic project and tasks sharing direct and transitive source groups.
    # When
    manifest = suite(project, extra=True)
    entries = {t["id"]: t for t in manifest["tasks"]}
    # Then
    assert {
        "related_split_count": len(
            {
                entries[t]["split"]
                for t in [
                    uid("T0"),
                    uid("T1"),
                    uid("T2"),
                    uid("joined"),
                    uid("transitive"),
                ]
            }
        ),
        "related_cluster_count": len(
            {
                entries[t]["cluster_id"]
                for t in [
                    uid("T0"),
                    uid("T1"),
                    uid("T2"),
                    uid("joined"),
                    uid("transitive"),
                ]
            }
        ),
        "all_splits": {t["split"] for t in entries.values()},
    } == {
        "related_split_count": 1,
        "related_cluster_count": 1,
        "all_splits": {"optimization", "validation", "final"},
    }


def test_experiment_executes_fresh_trials_and_preserves_regressions(project):
    # Given
    manifest = suite(project)
    before, after = FixedRunner(1), FixedRunner(0)
    # When
    value = run_experiment(project, manifest["id"], before, after, repeats=2)
    directories = before.directories + after.directories
    # Then
    assert {
        "status": value["status"],
        "regressed_pairs": len(value["summary"]["regressed"]),
        "conclusion": value["conclusion"],
        "fresh_directories": len(set(directories)) == len(directories),
        "remaining_directories": [str(d) for d in directories if d.exists()],
        "report_written": (project.path("experiments", value["id"], "") / "report.md").exists(),
    } == {
        "status": "complete",
        "regressed_pairs": 4,
        "conclusion": "Regressions detected",
        "fresh_directories": True,
        "remaining_directories": [],
        "report_written": True,
    }


def test_invalid_runs_are_not_counted_as_capability_failures(project):
    # Given
    manifest = suite(project)
    # When
    value = run_experiment(
        project, manifest["id"], FixedRunner(), FixedRunner(status="runner_error")
    )
    candidate = value["summary"]["candidate"]
    # Then
    assert candidate == {
        "passed": 0,
        "failed": 0,
        "invalid": 2,
        "total": 2,
        "valid": 0,
        "pass_rate": None,
        "recorded_cost_usd": 0.02,
        "cost_coverage": 2,
        "mean_latency_seconds": 0,
    }
    assert {"conclusion": value["conclusion"]} == {
        "conclusion": "Invalid runs require investigation"
    }


def test_final_exposure_consumed_before_interruption_and_cannot_be_reused(project):
    # Given
    manifest = suite(project)
    second = make_suite(
        project, "same-tasks-new-name", [t["id"] for t in manifest["tasks"]], seed=7
    )

    def interrupt(row):
        raise KeyboardInterrupt()

    # When / Then
    with pytest.raises(KeyboardInterrupt):
        run_experiment(
            project, manifest["id"], FixedRunner(), FixedRunner(), split="final", on_trial=interrupt
        )
    # When
    saved = read_json(project.path("suites", manifest["id"]))
    # Then
    assert saved["final_exposure"]
    # When
    record = read_json(project.path("experiments", saved["final_exposure"]["experiment_id"]))
    # Then
    assert {"status": record["status"], "trial_count": len(record["trials"])} == {
        "status": "interrupted",
        "trial_count": 1,
    }
    # When
    for name in [manifest["id"], second["id"]]:
        with pytest.raises(ValueError, match="exposed"):
            run_experiment(project, name, FixedRunner(), FixedRunner(), split="final")


def test_suite_and_task_changes_prevent_running_stale_configuration(project):
    # Given
    manifest = suite(project)
    key = next(t["id"] for t in manifest["tasks"] if t["split"] == "validation")
    _, old = load_task(project, key)
    replace_task(project, key, old.model_copy(update={"purpose": "Changed"}), "Revise")
    # When / Then
    with pytest.raises(ValueError, match="review"):
        run_experiment(project, manifest["id"], FixedRunner(), FixedRunner())
    # When
    manifest["seed"] = 999
    save(project.path("suites", manifest["id"]), manifest)
    # Then
    with pytest.raises(ValueError, match="manifest changed"):
        run_experiment(project, manifest["id"], FixedRunner(), FixedRunner())


def test_bootstrap_does_not_treat_repeated_or_related_tasks_as_independent():
    # Given
    rows = []
    for task in range(10):
        for repeat in range(3):
            for variant in ["baseline", "candidate"]:
                rows.append(
                    {
                        "task_id": f"T{task}",
                        "cluster_id": "one-source-group",
                        "trial": repeat,
                        "variant": variant,
                        "grade": {"status": "pass" if variant == "candidate" else "fail"},
                        "execution": {"cost_usd": None, "latency_seconds": 1},
                    }
                )
    # When
    summary = summarize(rows)
    # Then
    assert {
        key: summary[key]
        for key in ["task_mean_delta", "independent_groups", "task_bootstrap_95_interval"]
    } == {"task_mean_delta": 1, "independent_groups": 1, "task_bootstrap_95_interval": None}
    # When
    for row in rows:
        row["cluster_id"] = row["task_id"]
    # Then
    assert summarize(rows)["task_bootstrap_95_interval"] == [1, 1]


def command_runner(tmp_path, code, *, timeout=3):
    script = tmp_path / "target.py"
    script.write_text(code)
    config = RunnerConfig(
        name="fixture",
        kind="command",
        command=[sys.executable, "target.py"],
        source_files=["target.py"],
        environment_version="test-v1",
        timeout=timeout,
    )
    return ConfiguredRunner(config, tmp_path), script


def test_real_command_uses_json_stdin_and_captures_actual_artifact(tmp_path):
    # Given
    runner, script = command_runner(
        tmp_path,
        "import json,sys\nfrom pathlib import Path\n"
        "request=json.load(sys.stdin)\n"
        'Path("state.json").write_text(json.dumps({"seen":request["input"]}))\n'
        'print(json.dumps({"output":{"seed":request["seed"]}}))\n',
    )
    trial = tmp_path / "trial"
    trial.mkdir()
    # When
    out = runner.run({"literal": "$(do not execute)"}, trial, 42)
    artifacts = read_artifacts(trial, ["state.json"])
    # Then
    assert {"status": out.status, "output": out.output, "artifacts": artifacts} == {
        "status": "completed",
        "output": {"seed": 42},
        "artifacts": {"state.json": {"seen": {"literal": "$(do not execute)"}}},
    }
    # When
    script.write_text('print("changed")')
    # Then
    assert runner.run({}, trial, 42).status == "runner_error"


def test_timeout_is_invalid_and_private_stderr_not_exposed(tmp_path):
    # Given
    runner, _ = command_runner(tmp_path, "import time\ntime.sleep(30)\n", timeout=1)
    # When
    out = runner.run({}, tmp_path, 0)
    # Then
    assert out.status == "timeout"
    # When
    runner, _ = command_runner(
        tmp_path, 'import sys\nprint("PRIVATE",file=sys.stderr)\nsys.exit(1)\n'
    )
    out = runner.run({}, tmp_path, 0)
    # Then
    assert out.status == "runner_error" and "PRIVATE" not in out.error


def test_artifact_escape_and_nonfinite_data_are_rejected(tmp_path):
    # Given
    root = tmp_path / "trial"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text('{"secret":1}')
    (root / "state.json").symlink_to(outside)
    # When
    (root / "nan.json").write_text('{"number":NaN}')
    # Then
    assert read_artifacts(root, ["state.json", "nan.json"]) == {}
    with pytest.raises(ValueError):
        read_artifacts(root, ["../outside.json"])
    with pytest.raises(ValueError):
        Execution(cost_usd=float("nan"))


def test_training_exports_use_winning_variant_and_deduplicate(project, tmp_path):
    # Given
    suite_manifest = suite(project)
    experiment = run_experiment(
        project,
        suite_manifest["id"],
        FixedRunner(1),
        FixedRunner(0),
        split="optimization",
        repeats=2,
    )
    out = tmp_path / "preferences"
    # When
    manifest = export_training(
        project,
        experiment["id"],
        out,
        kind="preference",
        review_note="Reviewed synthetic outputs",
        permission_note="Synthetic test data",
    )
    # Then
    assert manifest["records"] == 1
    # When
    record = json.loads((out / "data.jsonl").read_text())
    # Then
    assert {
        "chosen": record["chosen"],
        "rejected": record["rejected"],
        "chosen_variant": record["provenance"]["chosen_variant"],
    } == {"chosen": {"value": 1}, "rejected": {"value": 0}, "chosen_variant": "baseline"}
    # When
    held = run_experiment(
        project, suite_manifest["id"], FixedRunner(), FixedRunner(), split="validation"
    )
    # Then
    with pytest.raises(ValueError, match="optimization"):
        export_training(
            project,
            held["id"],
            tmp_path / "bad",
            kind="sft",
            review_note="Reviewed",
            permission_note="Test",
        )


def test_benchmark_scores_spans_and_keeps_human_review_separate(tmp_path):
    # Given
    dataset = tmp_path / "gold.json"
    save(
        dataset,
        {
            "name": "Synthetic gold",
            "cases": [
                {
                    "id": "G1",
                    "traces_json": '[{"trace_id":"r0","text":"actual result"}]',
                    "context": "synthetic",
                    "question": "Find result",
                    "label_source": "synthetic fixture",
                    "expected": [{"trace_id": "r0", "pointer": "/text", "category": "opportunity"}],
                }
            ],
        },
    )
    out = tmp_path / "benchmark"
    # When
    report = benchmark(Scripted(result()["analysis"]), dataset, out)
    # Then
    assert report["precision"] == report["recall"] == 1
    # When
    annotation = tmp_path / "annotations.json"
    save(
        annotation,
        [
            {
                "case_id": "G1",
                "finding_id": uid("F1"),
                "correct": True,
                "actionable": False,
                "useful_for_task": False,
                "review_seconds": 12,
                "note": "Correct localization but no useful recommendation",
            }
        ],
    )
    review = review_benchmark(out, annotation, "Synthetic reviewer fixture")
    # Then
    assert review["correct_fraction"] == 1 and review["actionable_fraction"] == 0
    assert read_json(out / "report.json") == report


@pytest.fixture
def client(project):
    application = create_app(project, origin="http://127.0.0.1:8765", token="synthetic")
    with TestClient(application, base_url="http://127.0.0.1:8765") as client:
        yield client


def request(client, path, payload=None, *, token=True, origin=None, host=None):
    headers = {}
    if token:
        headers["Authorization"] = "Bearer synthetic"
    if origin is not None:
        headers["Origin"] = origin
    if host is not None:
        headers["Host"] = host
    response = client.request(
        "POST" if payload is not None else "GET", path, json=payload, headers=headers
    )
    return response.status_code, response.text


def test_local_ui_requires_token_and_allows_only_configured_browser_origin(client):
    # Given: the UI uses a bearer session and FastAPI's standard browser-origin policy.
    payload = {"title": "Contract", "content": "Policy", "source": "Test"}
    origin = str(client.base_url).rstrip("/")
    preflight_headers = {
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Authorization, Content-Type",
    }
    # When: browser preflights, native clients and invalid credentials reach FastAPI.
    no_token = request(client, "/api/overview", token=False)
    wrong_host = request(client, "/api/overview", host="unrelated.example")
    wrong_origin = client.options(
        "/api/knowledge/add", headers={**preflight_headers, "Origin": "https://other.example"}
    )
    allowed_origin = client.options(
        "/api/knowledge/add", headers={**preflight_headers, "Origin": origin}
    )
    native_status, native_body = request(client, "/api/knowledge/add", payload)
    read_status, read_body = request(client, "/api/overview")
    write_status, write_body = request(client, "/api/knowledge/add", payload, origin=origin)
    path_escape = request(client, "/api/artifact?kind=tasks&id=../../project")
    private_file = request(client, "/project.json")
    # Then: session credentials protect the API and browser access uses standard CORS.
    assert {
        "denied": {
            "no_token": no_token[0],
            "wrong_host": wrong_host[0],
            "path_escape": path_escape[0],
            "private_file": private_file[0],
        },
        "preflight": {
            "wrong_origin": {
                "status": wrong_origin.status_code,
                "allowed_origin": wrong_origin.headers.get("access-control-allow-origin"),
            },
            "allowed_origin": {
                "status": allowed_origin.status_code,
                "allowed_origin": allowed_origin.headers.get("access-control-allow-origin"),
            },
        },
        "native_write": {"status": native_status, "review": json.loads(native_body)["status"]},
        "read": {"status": read_status, "total": json.loads(read_body)["inventory"]["total"]},
        "write": {"status": write_status, "review": json.loads(write_body)["status"]},
    } == {
        "denied": {
            "no_token": 401,
            "wrong_host": 400,
            "path_escape": 400,
            "private_file": 404,
        },
        "preflight": {
            "wrong_origin": {"status": 400, "allowed_origin": None},
            "allowed_origin": {"status": 200, "allowed_origin": origin},
        },
        "native_write": {"status": 200, "review": "draft"},
        "read": {"status": 200, "total": 9},
        "write": {"status": 200, "review": "draft"},
    }


def test_ui_static_files_and_exact_aggregate_filter(client):
    # Given: the built TypeScript entry point served without project credentials.
    index_status, html = request(client, "/", token=False)
    assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html)

    # When
    asset_statuses = [request(client, path, token=False)[0] for path in assets]
    status, data = request(client, "/api/traces?equals_pointer=%2Fvalue&equals_json=1")

    # Then
    assert {
        "index_status": index_status,
        "asset_types": sorted(path.rsplit(".", 1)[-1] for path in assets),
        "asset_statuses": asset_statuses,
        "query_status": status,
        "trace_ids": json.loads(data)["ids"],
    } == {
        "index_status": 200,
        "asset_types": ["css", "js"],
        "asset_statuses": [200, 200],
        "query_status": 200,
        "trace_ids": ["r1"],
    }


def test_ui_analytics_endpoints_share_filters_and_enforce_access_controls(client):
    # Given
    query = {"filters": [{"pointer": "/value", "operator": "gte", "value_json": "7"}]}

    # When
    def post(path, payload):
        status, body = request(client, path, payload, origin=str(client.base_url).rstrip("/"))
        return {"status": status, "body": json.loads(body)}

    found = post("/api/search", query)
    grouped = post("/api/clusters", {"query": query, "pointer": "/text"})
    counted = post("/api/distribution", {"query": query, "pointer": "/value"})
    graph_status, graph_body = request(client, "/api/graph")
    denied = {
        path: request(client, path, payload, token=False, origin=str(client.base_url).rstrip("/"))[
            0
        ]
        for path, payload in [
            ("/api/search", query),
            ("/api/clusters", {"query": query}),
            ("/api/distribution", {"query": query, "pointer": "/value"}),
        ]
    }

    # Then
    assert {
        "statuses": [found["status"], grouped["status"], counted["status"], graph_status],
        "ids": found["body"]["ids"],
        "groups": [c["trace_ids"] for c in grouped["body"]["clusters"]],
        "counts": counted["body"]["counts"],
        "graph": {k: json.loads(graph_body)[k] for k in ["nodes", "edges", "total_nodes"]},
        "denied": denied,
        "invalid_filter": post("/api/search", {"limit": 0})["status"],
    } == {
        "statuses": [200, 200, 200, 200],
        "ids": ["r7", "r8"],
        "groups": [["r7", "r8"]],
        "counts": [{"value": 7, "count": 1}, {"value": 8, "count": 1}],
        "graph": {"nodes": [], "edges": [], "total_nodes": 0},
        "denied": {"/api/search": 401, "/api/clusters": 401, "/api/distribution": 401},
        "invalid_filter": 400,
    }


def test_native_snapshot_exposure_is_recorded_without_changing_suite_definition(project):
    # Given
    from agent_data_workbench.research import start_investigation

    manifest = suite(project)
    # When
    excluded = start_investigation(project, "Optimization data", exclude_final=True)
    before = project.final_groups(consumed=True)
    included = start_investigation(project, "All supplied data")
    saved = read_json(project.path("suites", manifest["id"]))
    optimization = run_experiment(project, manifest["id"], FixedRunner(), FixedRunner())
    # Then
    assert {
        "excluded_total": excluded["source"]["total"],
        "before": before,
        "included_total": included["source"]["total"],
        "source": [e["investigation_id"] for e in saved["research_exposure"]],
        "suite_hash": saved["sha256"],
        "optimization": optimization["status"],
    } == {
        "excluded_total": 7,
        "before": set(),
        "included_total": 9,
        "source": [included["id"]],
        "suite_hash": manifest["sha256"],
        "optimization": "complete",
    }
    with pytest.raises(ValueError, match="exposed"):
        run_experiment(project, manifest["id"], FixedRunner(), FixedRunner(), split="final")
