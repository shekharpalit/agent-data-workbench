"""Task persistence, revision history, and acceptance gates."""

from __future__ import annotations

from agent_data_workbench.evaluation.tasks.contracts import TaskSpec
from agent_data_workbench.evaluation.worlds import resolve_world
from agent_data_workbench.shared.files import save
from agent_data_workbench.shared.identifiers import canonical_uuid
from agent_data_workbench.shared.json import digest, read_json
from agent_data_workbench.shared.time import now
from agent_data_workbench.workspace.project import Project


def task_digest(task: TaskSpec) -> str:
    value = task.model_dump()
    # Keep pre-workflow task digests stable when no new feature is used.
    for field in ("world", "environment", "conversation"):
        if value[field] is None:
            value.pop(field)
    for example in value["verifier_examples"]:
        if example["state_json"] == "{}":
            example.pop("state_json")
    return digest(value)


def write_task(project: Project, task: TaskSpec, *, origin: str) -> dict:
    from agent_data_workbench.data.store import TraceStore

    store = TraceStore(project)
    for key in task.trace_ids:
        store.get(key)
    payload = {
        "id": task.id,
        "spec": task.model_dump(),
        "origin": origin,
        "created_at": now(),
        "review": {"status": "draft", "note": ""},
        "reviews": [],
        "audit": None,
    }
    path = project.path("tasks", task.id)
    if path.exists():
        raise ValueError("Task ID already exists; use a new ID for a revised task")
    save(path, payload)
    return payload


def load_task(project: Project, key: str, *, accepted: bool = False) -> tuple[dict, TaskSpec]:
    value = read_json(project.path("tasks", key))
    task = TaskSpec.model_validate(value["spec"])
    if accepted:
        if task.world:
            resolve_world(project, task.world)
        review = value["review"]
        if review["status"] != "accepted" or review.get("spec_sha256") != task_digest(task):
            raise ValueError(f"Task {key} needs review of its current specification")
        if task.context_sha256 and task.context_sha256 != project.context()["sha256"]:
            raise ValueError(f"Task {key} uses stale project knowledge; revise and review it")
        audit = value.get("audit")
        if not audit or not audit["passed"] or audit["spec_sha256"] != task_digest(task):
            raise ValueError(f"Task {key} needs a passing verifier audit")
    return value, task


def review_task(project: Project, key: str, status: str, note: str):
    if status not in {"accepted", "rejected", "draft"} or not note.strip():
        raise ValueError("A task review needs a valid status and a note")
    with project.lock():
        value, task = load_task(project, key)
        if status == "accepted":
            if task.world:
                resolve_world(project, task.world)
            if task.missing_context:
                raise ValueError("Resolve missing context before accepting the task")
            audit = value.get("audit")
            if not audit or not audit["passed"] or audit["spec_sha256"] != task_digest(task):
                raise ValueError("Run and pass the verifier audit before accepting this task")
            if task.context_sha256 and task.context_sha256 != project.context()["sha256"]:
                raise ValueError("Task context is stale; update its specification and re-audit")
        decision = {"status": status, "note": note, "at": now(), "spec_sha256": task_digest(task)}
        value["review"] = decision
        value["reviews"].append(decision)
        save(project.path("tasks", key), value)
    return value


def replace_task(project: Project, key: str, task: TaskSpec, note: str) -> dict:
    from agent_data_workbench.data.store import TraceStore

    key = canonical_uuid(key)
    if task.id != key or not note.strip():
        raise ValueError("Keep the task ID and supply an edit note")
    store = TraceStore(project)
    for trace_id in task.trace_ids:
        store.get(trace_id)
    with project.lock():
        value, old = load_task(project, key)
        value.setdefault("revisions", []).append(
            {"at": now(), "note": note, "spec": old.model_dump()}
        )
        value.update(spec=task.model_dump(), audit=None, review={"status": "draft", "note": note})
        save(project.path("tasks", key), value)
    return value
