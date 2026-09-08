"""Execute a frozen Harbor bundle and retain the complete local job directory."""

from pathlib import Path

from agent_data_workbench.evaluation.tasks.contracts import TaskSpec
from agent_data_workbench.evaluation.tasks.repository import task_digest
from agent_data_workbench.shared.commands import check_sources, pinned_command
from agent_data_workbench.shared.files import save
from agent_data_workbench.shared.identifiers import new_id
from agent_data_workbench.shared.json import digest, read_json
from agent_data_workbench.shared.processes import run_process
from agent_data_workbench.shared.time import now
from agent_data_workbench.workspace.project import Project

from .commands import _command
from .contracts import HarborAgentConfig, HarborExportConfig
from .exporting import _expose_final_source, _files


def run_harbor_export(
    project: Project,
    export_id: str,
    *,
    timeout: int | None = None,
    target: HarborAgentConfig | None = None,
    single_attempt: bool = False,
) -> dict:
    """Run the exact exported bundle. Harbor remains an optional installed dependency."""
    with project.lock():
        return _run_harbor_export(
            project, export_id, timeout=timeout, target=target, single_attempt=single_attempt
        )


def _run_harbor_export(
    project: Project,
    export_id: str,
    *,
    timeout: int | None,
    target: HarborAgentConfig | None = None,
    single_attempt: bool = False,
) -> dict:
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
    if target is not None:
        config = config.model_copy(update=target.model_dump())
    if single_attempt:
        config = config.model_copy(update={"repetitions": 1})
    run_id = new_id()
    command = _command(bundle, config, run_id, manifest["conversation_continuity"])
    args, sources = pinned_command(command, [], bundle.parent)
    version = run_process([args[0], "--version"], "", bundle.parent, timeout).strip()
    result = {
        "id": run_id,
        "export_id": export_id,
        "config": config.model_dump(),
        "job_directory": str(bundle.parent / "jobs" / run_id),
        "command": args,
        "harbor_version": version,
        "source_sha256": sources,
        "logs": {
            stream: str(bundle.parent / f"{run_id}-{stream}.log") for stream in ("stdout", "stderr")
        },
        "bundle_sha256": manifest["bundle_sha256"],
        "started_at": now(),
        "status": "running",
        "error": None,
    }
    path = bundle.parent / (run_id + ".json")
    save(path, result)
    try:
        run_process(args, "", bundle.parent, timeout, log_prefix=bundle.parent / run_id)
        check_sources(sources)
        if _files(bundle) != manifest["files"]:
            raise ValueError("Harbor bundle changed during execution")
        result["status"] = "completed"
    except ValueError, RuntimeError, OSError:
        result.update(status="error", error="Harbor failed; inspect its job and configuration")
    result["finished_at"] = now()
    save(path, result)
    return result
