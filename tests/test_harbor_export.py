import json
import os
import sys
from pathlib import Path

import pytest
from test_workbench_data import accept, make_project, spec

from agent_data_workbench.evaluation.tasks.repository import task_digest, write_task
from agent_data_workbench.execution.contracts import ConversationSpec, SimulatorConfig, UserTurn
from agent_data_workbench.integrations.harbor import (
    HarborExportConfig,
    export_harbor,
    run_harbor_export,
)
from agent_data_workbench.shared.commands import file_sha256
from agent_data_workbench.shared.json import digest


def template_at(tmp_path, *, steps=0):
    template = tmp_path / "harbor-template"
    template.mkdir()
    (template / "environment").mkdir()
    (template / "environment" / "Dockerfile").write_text("FROM scratch\n")
    content = 'schema_version = "1.4"\n'
    if steps:
        content += 'multi_step_reward_strategy = "final"\n'
        for index in range(steps):
            name = f"step-{index}"
            content += f'\n[[steps]]\nname = "{name}"\n'
            directory = template / "steps" / name / "tests"
            directory.mkdir(parents=True)
            (directory / "test.sh").write_text("# supplied synthetic verifier\nexit 1\n")
    else:
        (template / "tests").mkdir()
        (template / "tests" / "test.sh").write_text("# supplied synthetic verifier\nexit 1\n")
    (template / "task.toml").write_text(content)
    return template


def test_harbor_export_freezes_real_template_and_keeps_grader_truth_out_of_instructions(tmp_path):
    # Given
    project = make_project(tmp_path)
    task = spec(project)
    task.criteria[0].description = "SECRET-VERIFIER-TRUTH"
    accept(project, task)
    template = template_at(tmp_path)
    config = HarborExportConfig(template_directory=str(template), agent="oracle")
    source_hashes = {
        p.relative_to(template).as_posix(): file_sha256(p)
        for p in template.rglob("*")
        if p.is_file()
    }
    # When
    manifest = export_harbor(project, task.id, config)
    bundle = Path(manifest["bundle_directory"])
    # Then
    assert {
        "kind": manifest["kind"],
        "task_id": manifest["task_id"],
        "task_sha256": manifest["task_sha256"],
        "template_sha256": manifest["template_sha256"],
        "bundle_sha256": manifest["bundle_sha256"],
        "config": manifest["config"],
        "instruction": (bundle / "instruction.md").read_text(),
        "tests": (bundle / "tests" / "test.sh").read_text(),
        "truth_in_agent_instruction": "SECRET-VERIFIER-TRUTH"
        in (bundle / "instruction.md").read_text(),
        "truth_saved_outside_bundle": (bundle.parent / "reviewed-task.json").is_file(),
        "continuity": manifest["conversation_continuity"],
    } == {
        "kind": "harbor",
        "task_id": task.id,
        "task_sha256": task_digest(task),
        "template_sha256": digest(source_hashes),
        "bundle_sha256": digest(manifest["files"]),
        "config": config.model_dump(),
        "instruction": "Task input:\n"
        + json.dumps(
            {"input": json.loads(task.input_json)},
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        "tests": "# supplied synthetic verifier\nexit 1\n",
        "truth_in_agent_instruction": False,
        "truth_saved_outside_bundle": True,
        "continuity": False,
    }
    assert manifest["command"] == [
        "harbor",
        "run",
        "--path",
        str(bundle),
        "--agent",
        "oracle",
        "-e",
        "docker",
        "--n-attempts",
        "1",
        "--jobs-dir",
        str(bundle.parent / "jobs"),
        "--job-name",
        manifest["command"][-1],
    ]


def test_harbor_multiturn_export_requests_native_session_resume(tmp_path):
    # Given
    project = make_project(tmp_path)
    task = spec(project)
    task.conversation = ConversationSpec(
        turns=[UserTurn(message="Start change"), UserTurn(message="Cancel that change")]
    )
    accept(project, task)
    template = template_at(tmp_path, steps=2)
    # When
    manifest = export_harbor(
        project,
        task.id,
        HarborExportConfig(
            template_directory=str(template), agent="claude-code", model="configured-model"
        ),
    )
    bundle = Path(manifest["bundle_directory"])
    # Then
    assert {
        "continuity": manifest["conversation_continuity"],
        "command_suffix": manifest["command"][-3:],
        "first": (bundle / "steps" / "step-0" / "instruction.md").read_text().splitlines()[0],
        "second": (bundle / "steps" / "step-1" / "instruction.md").read_text(),
        "shared_world": (bundle / "environment" / "Dockerfile").read_text(),
    } == {
        "continuity": True,
        "command_suffix": ["--model", "configured-model", "--resume-trajectory"],
        "first": "Start change",
        "second": "Cancel that change\n",
        "shared_world": "FROM scratch\n",
    }


def test_harbor_export_requires_review_and_real_verifier(tmp_path):
    # Given
    project = make_project(tmp_path)
    task = spec(project)
    write_task(project, task, origin="test fixture")
    template = template_at(tmp_path)
    config = HarborExportConfig(template_directory=str(template), agent="oracle")
    # When / Then
    with pytest.raises(ValueError, match="needs review"):
        export_harbor(project, task.id, config)
    # Given
    from agent_data_workbench.evaluation.tasks.grading import audit_task
    from agent_data_workbench.evaluation.tasks.repository import review_task

    audit_task(project, task.id)
    review_task(project, task.id, "accepted", "Synthetic fixture")
    (template / "tests" / "test.sh").unlink()
    # When / Then
    with pytest.raises(ValueError, match="supplied tests/test.sh"):
        export_harbor(project, task.id, config)
    assert project.artifacts("exports") == []


def test_harbor_reactive_user_cannot_silently_turn_into_scripted_steps(tmp_path):
    # Given
    project = make_project(tmp_path)
    task = spec(project)
    task.conversation = ConversationSpec(
        turns=[UserTurn(message="Begin")], simulator=SimulatorConfig(command=["my-simulator"])
    )
    accept(project, task)
    template = template_at(tmp_path, steps=1)
    # When / Then
    with pytest.raises(ValueError, match="supports scripted turns"):
        export_harbor(
            project,
            task.id,
            HarborExportConfig(template_directory=str(template), agent="claude-code"),
        )
    assert project.artifacts("exports") == []


def test_optional_harbor_cli_records_actual_version_and_launch_then_rejects_drift(
    tmp_path, monkeypatch
):
    # Given
    project = make_project(tmp_path)
    task = accept(project, spec(project))
    template = template_at(tmp_path)
    manifest = export_harbor(
        project, task.id, HarborExportConfig(template_directory=str(template), agent="oracle")
    )
    binary = tmp_path / "harbor"
    binary.write_text(
        f"#!{sys.executable}\n"
        + """
import sys
if sys.argv[1:] == ['--version']:
    print('harbor synthetic-test')
else:
    print('synthetic transport completed')
"""
    )
    binary.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    # When
    result = run_harbor_export(project, manifest["id"])
    # Then
    assert {
        "status": result["status"],
        "version": result["harbor_version"],
        "error": result["error"],
        "bundle": result["bundle_sha256"],
        "executable": result["command"][0],
        "run_record": (
            Path(manifest["bundle_directory"]).parent / (result["id"] + ".json")
        ).is_file(),
    } == {
        "status": "completed",
        "version": "harbor synthetic-test",
        "error": None,
        "bundle": manifest["bundle_sha256"],
        "executable": str(binary),
        "run_record": True,
    }
    # When
    (Path(manifest["bundle_directory"]) / "tests" / "test.sh").write_text("changed verifier")
    # Then
    with pytest.raises(ValueError, match="changed after export"):
        run_harbor_export(project, manifest["id"])


def test_harbor_export_records_final_source_exposure_before_materialization(tmp_path):
    # Given
    from agent_data_workbench.evaluation.suites import make_suite
    from agent_data_workbench.shared.json import read_json

    project = make_project(tmp_path)
    tasks = [accept(project, spec(project, key=f"T{i}", trace_ids=[f"r{i}"])) for i in range(3)]
    suite = make_suite(project, "held out tasks", [task.id for task in tasks])
    final_id = next(task["id"] for task in suite["tasks"] if task["split"] == "final")
    template = template_at(tmp_path)
    # When
    manifest = export_harbor(
        project, final_id, HarborExportConfig(template_directory=str(template), agent="oracle")
    )
    updated = read_json(project.path("suites", suite["id"]))
    # Then
    assert {
        "exposures": [
            {"id": event["harbor_export_id"], "scope": event["scope"]}
            for event in updated["research_exposure"]
        ],
        "trace_groups": manifest["trace_groups"],
    } == {
        "exposures": [
            {"id": manifest["id"], "scope": "source snapshot available through Harbor export"}
        ],
        "trace_groups": next(
            task["trace_groups"] for task in suite["tasks"] if task["id"] == final_id
        ),
    }


def test_harbor_manifest_edits_cannot_silently_change_the_executed_command(tmp_path):
    # Given
    from agent_data_workbench.shared.files import save

    project = make_project(tmp_path)
    task = accept(project, spec(project))
    template = template_at(tmp_path)
    manifest = export_harbor(
        project, task.id, HarborExportConfig(template_directory=str(template), agent="oracle")
    )
    manifest["command"] = ["different-program"]
    save(project.path("exports", manifest["id"]), manifest)
    # When / Then
    with pytest.raises(ValueError, match="manifest changed after export"):
        run_harbor_export(project, manifest["id"])
