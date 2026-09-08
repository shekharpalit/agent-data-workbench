"""Materialize reviewed tasks into real Harbor templates and invoke Harbor's CLI.

Format and flags follow Harbor's official task/CLI sources (schema 1.4). Harbor owns
containers, tools and verifier execution; an export is not evidence that a verifier works.
"""

from __future__ import annotations

import json
import shutil
import tomllib
from pathlib import Path

from pydantic import Field

from agent_data_workbench.data.store import TraceStore
from agent_data_workbench.evaluation.tasks.contracts import TaskSpec
from agent_data_workbench.evaluation.tasks.repository import load_task, task_digest
from agent_data_workbench.shared.commands import check_sources, file_sha256, pinned_command
from agent_data_workbench.shared.contracts import Contract
from agent_data_workbench.shared.files import relative_path, save
from agent_data_workbench.shared.identifiers import new_id
from agent_data_workbench.shared.json import digest, json_text, read_json
from agent_data_workbench.shared.processes import run_process
from agent_data_workbench.shared.time import now
from agent_data_workbench.workspace.project import Project


class HarborExportConfig(Contract):
    template_directory: str = Field(min_length=1)
    agent: str = Field(min_length=1)
    model: str = ""
    environment_type: str = Field(default="docker", min_length=1)
    repetitions: int = Field(default=1, ge=1)


def _files(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Harbor templates must materialize symlinks before export")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = file_sha256(path)
    return result


def _expose_final_source(project: Project, groups: list[str], export_id: str, action: str) -> None:
    for suite in project.artifacts("suites"):
        if any(
            task["split"] == "final" and set(task["trace_groups"]) & set(groups)
            for task in suite["tasks"]
        ):
            suite.setdefault("research_exposure", []).append(
                {
                    "harbor_export_id": export_id,
                    "at": now(),
                    "scope": f"source snapshot available through Harbor {action}",
                }
            )
            save(project.path("suites", suite["id"]), suite)


def _command(
    bundle: Path, config: HarborExportConfig, job_name: str, conversation: bool
) -> list[str]:
    command = [
        "harbor",
        "run",
        "--path",
        str(bundle),
        "--agent",
        config.agent,
        "-e",
        config.environment_type,
        "--n-attempts",
        str(config.repetitions),
        "--jobs-dir",
        str(bundle.parent / "jobs"),
        "--job-name",
        job_name,
    ]
    if config.model:
        command.extend(["--model", config.model])
    if conversation:
        command.append("--resume-trajectory")
    return command


def export_harbor(project: Project, task_id: str, config: HarborExportConfig) -> dict:
    """Bundle supplied environment/verifier code; never invent success checks from prose."""
    with project.lock():
        return _export_harbor(project, task_id, config)


def _export_harbor(project: Project, task_id: str, config: HarborExportConfig) -> dict:
    record, task = load_task(project, task_id, accepted=True)
    template = Path(config.template_directory).expanduser().resolve()
    if not template.is_dir():
        raise ValueError("Harbor template directory does not exist")
    source_files = _files(template)
    if "task.toml" not in source_files:
        raise ValueError("Harbor template needs task.toml")
    settings = tomllib.loads((template / "task.toml").read_text(encoding="utf-8"))
    if settings.get("schema_version") != "1.4":
        raise ValueError("Use a Harbor schema_version 1.4 template")
    if not (template / "environment").is_dir() and not settings.get("environment", {}).get(
        "docker_image"
    ):
        raise ValueError("Harbor template needs an environment definition or image")
    conversation = getattr(task, "conversation", None)
    steps = settings.get("steps", [])
    if conversation:
        if conversation.simulator:
            raise ValueError(
                "This Harbor exporter supports scripted turns; use a session adapter "
                "for reactive users"
            )
        if len(steps) != len(conversation.turns):
            raise ValueError("Harbor template needs one verified step per conversation turn")
        names = []
        for step in steps:
            name = step.get("name", "")
            relative_path(name)
            if len(Path(name).parts) != 1 or name in names:
                raise ValueError("Harbor step names must be unique directory names")
            names.append(name)
            if not (
                (template / "steps" / name / "tests" / "test.sh").is_file()
                or (template / "tests" / "test.sh").is_file()
            ):
                raise ValueError("Every Harbor step needs a supplied verifier test.sh")
    else:
        if steps:
            raise ValueError("Multi-step template requires a reviewed conversation specification")
        if not (template / "tests" / "test.sh").is_file():
            raise ValueError("Harbor template needs a supplied tests/test.sh verifier")
    export_id = new_id()
    folder = project.directory("exports") / export_id
    bundle = folder / "task"
    if template == bundle or folder.is_relative_to(template):
        raise ValueError("Export destination must be outside the template")
    store = TraceStore(project)
    groups = sorted({store.metadata(trace_id)["group_id"] for trace_id in task.trace_ids})
    _expose_final_source(project, groups, export_id, "export")
    folder.mkdir(mode=0o700)
    try:
        shutil.copytree(template, bundle)
        if _files(bundle) != source_files:
            raise ValueError("Harbor template changed during export")
        visible = json_text({"input": json.loads(task.input_json)})
        if conversation:
            for index, (step, turn) in enumerate(zip(steps, conversation.turns, strict=True)):
                instruction = turn.message + ("\n\nTask input:\n" + visible if index == 0 else "")
                (bundle / "steps" / step["name"] / "instruction.md").write_text(
                    instruction + "\n", encoding="utf-8"
                )
        else:
            (bundle / "instruction.md").write_text(
                "Task input:\n" + visible + "\n", encoding="utf-8"
            )
        # Full reviewed truth stays outside the directory Harbor exposes as the task.
        save(folder / "reviewed-task.json", record)
        files = _files(bundle)
        job_name = new_id()
        command = _command(bundle, config, job_name, bool(conversation))
        manifest = {
            "id": export_id,
            "kind": "harbor",
            "created_at": now(),
            "task_id": task.id,
            "trace_ids": task.trace_ids,
            "trace_groups": groups,
            "job_name": job_name,
            "task_sha256": task_digest(task),
            "config": config.model_dump(),
            "template_sha256": digest(source_files),
            "files": files,
            "bundle_sha256": digest(files),
            "bundle_directory": str(bundle),
            "command": command,
            "conversation_continuity": bool(conversation),
            "validation": "exported; execute and calibrate the supplied Harbor verifier",
            "sources": [
                "https://www.harborframework.com/docs/tasks",
                "https://www.harborframework.com/docs/tasks/multi-step",
            ],
        }
        manifest["sha256"] = digest(manifest)
        save(folder / "manifest.json", manifest)
        save(project.path("exports", export_id), manifest)
        return manifest
    except BaseException:
        shutil.rmtree(folder)
        raise


def run_harbor_export(project: Project, export_id: str, *, timeout: int | None = None) -> dict:
    """Run the exact exported bundle. Harbor remains an optional installed dependency."""
    with project.lock():
        return _run_harbor_export(project, export_id, timeout=timeout)


def _run_harbor_export(project: Project, export_id: str, *, timeout: int | None) -> dict:
    manifest = read_json(project.path("exports", export_id))
    if manifest.get("kind") != "harbor":
        raise ValueError("Expected a Harbor export")
    if manifest.get("sha256") != digest({k: v for k, v in manifest.items() if k != "sha256"}):
        raise ValueError("Harbor manifest changed after export")
    bundle = Path(manifest["bundle_directory"])
    expected_bundle = project.directory("exports") / manifest["id"] / "task"
    if (
        bundle.resolve() != expected_bundle.resolve()
        or _files(bundle) != manifest["files"]
        or digest(manifest["files"]) != manifest["bundle_sha256"]
    ):
        raise ValueError("Harbor bundle changed after export")
    if read_json(bundle.parent / "manifest.json") != manifest:
        raise ValueError("Harbor manifest differs from its frozen export snapshot")
    frozen_task = read_json(bundle.parent / "reviewed-task.json")
    if task_digest(TaskSpec.model_validate(frozen_task["spec"])) != manifest["task_sha256"]:
        raise ValueError("Harbor reviewed task changed after export")
    config = HarborExportConfig.model_validate(manifest["config"])
    expected_command = _command(
        bundle, config, manifest["job_name"], manifest["conversation_continuity"]
    )
    if manifest["command"] != expected_command:
        raise ValueError("Harbor launch command differs from its captured configuration")
    _expose_final_source(project, manifest["trace_groups"], manifest["id"], "execution")
    run_id = new_id()
    command = _command(bundle, config, run_id, manifest["conversation_continuity"])
    args, sources = pinned_command(command, [], bundle.parent)
    version = run_process([args[0], "--version"], "", bundle.parent, timeout).strip()
    result = {
        "id": run_id,
        "export_id": export_id,
        "command": args,
        "harbor_version": version,
        "source_sha256": sources,
        "bundle_sha256": manifest["bundle_sha256"],
        "started_at": now(),
        "status": "running",
        "error": None,
    }
    path = bundle.parent / (run_id + ".json")
    save(path, result)
    try:
        output = run_process(args, "", bundle.parent, timeout)
        check_sources(sources)
        if _files(bundle) != manifest["files"]:
            raise ValueError("Harbor bundle changed during execution")
        (bundle.parent / (run_id + "-stdout.log")).write_text(output, encoding="utf-8")
        result["status"] = "completed"
    except ValueError, RuntimeError, OSError:
        result.update(status="error", error="Harbor failed; inspect its job and configuration")
    result["finished_at"] = now()
    save(path, result)
    return result
