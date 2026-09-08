"""Materialize reviewed tasks into real Harbor templates and invoke Harbor's CLI.

Format and flags follow Harbor's official task/CLI sources (schema 1.4). Harbor owns
containers, tools and verifier execution; an export is not evidence that a verifier works.
"""

from __future__ import annotations

import json
import shutil
import tomllib
from pathlib import Path

from agent_data_workbench.data.store import TraceStore
from agent_data_workbench.evaluation.tasks.repository import load_task, task_digest
from agent_data_workbench.shared.commands import file_sha256
from agent_data_workbench.shared.files import relative_path, save
from agent_data_workbench.shared.identifiers import new_id
from agent_data_workbench.shared.json import digest, json_text
from agent_data_workbench.shared.time import now
from agent_data_workbench.workspace.project import Project

from .commands import _command, _environment
from .contracts import HarborExportConfig


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
            "environment": _environment(config),
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
