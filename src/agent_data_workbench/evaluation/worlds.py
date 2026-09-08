"""Reviewed, immutable versions of reusable domain and tool knowledge."""

from __future__ import annotations

from pydantic import Field

from agent_data_workbench.shared.contracts import Contract
from agent_data_workbench.shared.files import save
from agent_data_workbench.shared.identifiers import UUIDString, new_id
from agent_data_workbench.shared.json import digest, read_json
from agent_data_workbench.shared.time import now
from agent_data_workbench.workspace.project import Project


class ToolSpec(Contract):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)


class WorldSpec(Contract):
    name: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    description: str = Field(min_length=1)
    schemas: dict[str, dict] = Field(default_factory=dict)
    tools: list[ToolSpec] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    invariants: list[str] = Field(default_factory=list)
    sources: list[str] = Field(min_length=1)
    unresolved_questions: list[str] = Field(default_factory=list)


class WorldReference(Contract):
    id: UUIDString
    sha256: str = Field(min_length=64, max_length=64)


def create_world(project: Project, spec: WorldSpec, previous_id: str | None = None) -> dict:
    if len({tool.name for tool in spec.tools}) != len(spec.tools):
        raise ValueError("World tool names must be unique")
    with project.lock():
        previous = load_world(project, previous_id) if previous_id else None
        record = {
            "id": new_id(),
            "created_at": now(),
            "spec": spec.model_dump(),
            "sha256": digest(spec.model_dump()),
            "revision": previous["revision"] + 1 if previous else 1,
            "previous_id": previous_id,
            "previous_sha256": previous["sha256"] if previous else None,
            "review": {"status": "draft", "note": ""},
            "reviews": [],
        }
        save(project.path("worlds", record["id"]), record)
        return record


def load_world(project: Project, key: str, *, accepted: bool = False) -> dict:
    record = read_json(project.path("worlds", key))
    spec = WorldSpec.model_validate(record["spec"])
    if digest(spec.model_dump()) != record["sha256"]:
        raise ValueError("World content changed; create a new version")
    if accepted and (
        record["review"]["status"] != "accepted"
        or record["review"].get("sha256") != record["sha256"]
    ):
        raise ValueError("World needs review of this exact version")
    return record


def review_world(project: Project, key: str, status: str, note: str, reviewer: str) -> dict:
    if status not in {"draft", "accepted", "rejected"} or not note.strip() or not reviewer.strip():
        raise ValueError("Supply a review status, reviewer and reason")
    with project.lock():
        record = load_world(project, key)
        if status == "accepted" and record["spec"]["unresolved_questions"]:
            raise ValueError("Resolve world questions in a new version before acceptance")
        review = {
            "status": status,
            "note": note,
            "reviewer": reviewer,
            "at": now(),
            "sha256": record["sha256"],
        }
        record["review"] = review
        record["reviews"].append(review)
        save(project.path("worlds", key), record)
        return record


def resolve_world(project: Project, reference: WorldReference) -> dict:
    record = load_world(project, reference.id, accepted=True)
    if reference.sha256 != record["sha256"]:
        raise ValueError("Task world digest does not match its reviewed version")
    return record


def active_worlds(project: Project) -> list[dict]:
    """Accepted lineage heads feed research; older versions remain explicitly addressable."""
    records = {w["id"]: load_world(project, w["id"]) for w in project.artifacts("worlds")}
    accepted = {key for key, value in records.items() if value["review"]["status"] == "accepted"}
    ancestors = set()
    for key in accepted:
        seen = {key}
        parent = records[key]["previous_id"]
        while parent:
            if parent in seen or parent not in records:
                raise ValueError("World version lineage is invalid")
            seen.add(parent)
            ancestors.add(parent)
            parent = records[parent]["previous_id"]
    return [load_world(project, key, accepted=True) for key in sorted(accepted - ancestors)]
