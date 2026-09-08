"""Reviewed behavioral taxonomies and explicit, provenance-backed coverage mappings."""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from pydantic import Field, model_validator

from agent_data_workbench.data.store import TraceStore
from agent_data_workbench.evaluation.tasks.contracts import TaskSpec
from agent_data_workbench.evaluation.tasks.repository import load_task, task_digest
from agent_data_workbench.shared.contracts import Contract
from agent_data_workbench.shared.files import save
from agent_data_workbench.shared.identifiers import UUIDString, canonical_uuid, new_id
from agent_data_workbench.shared.json import digest, parse_object, read_json
from agent_data_workbench.shared.time import now
from agent_data_workbench.workspace.project import Project


class Capability(Contract):
    id: UUIDString
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    required_slices: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid(self):
        if not self.name.strip() or not self.description.strip():
            raise ValueError("Capabilities need a name and description")
        if len(set(self.required_slices)) != len(self.required_slices) or any(
            not s.strip() for s in self.required_slices
        ):
            raise ValueError("Required slices must be unique nonempty names")
        return self


class TaxonomySpec(Contract):
    name: str = Field(min_length=1)
    description: str = ""
    capabilities: list[Capability] = Field(min_length=1)

    @model_validator(mode="after")
    def valid(self):
        if not self.name.strip() or len({c.id for c in self.capabilities}) != len(
            self.capabilities
        ):
            raise ValueError("Taxonomy needs a name and unique capability IDs")
        return self


class CoverageMapping(Contract):
    kind: Literal["trace", "task"]
    entity_id: str = Field(min_length=1)
    capability_id: UUIDString
    slice: str = ""
    rationale: str = Field(min_length=1)
    source: str = Field(min_length=1)
    reviewer: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid(self):
        if self.kind == "task":
            self.entity_id = canonical_uuid(self.entity_id)
        if any(not v.strip() for v in (self.rationale, self.source, self.reviewer)):
            raise ValueError("Mapping needs a rationale, source and reviewer")
        return self


def load_taxonomy(project: Project, key: str, *, accepted: bool = False) -> dict:
    value = read_json(project.path("taxonomies", key))
    TaxonomySpec.model_validate(value["spec"])
    if value["sha256"] != digest({k: value[k] for k in ("spec", "revision", "previous")}):
        raise ValueError("Taxonomy specification changed; create a new version")
    if accepted and (
        value["review"]["status"] != "accepted" or value["review"]["spec_sha256"] != value["sha256"]
    ):
        raise ValueError("Review the taxonomy before mapping coverage")
    return value


def create_taxonomy(project: Project, spec: TaxonomySpec, previous_id: str | None = None) -> dict:
    with project.lock():
        previous = load_taxonomy(project, previous_id) if previous_id else None
        value = {
            "id": new_id(),
            "created_at": now(),
            "spec": spec.model_dump(),
            "revision": previous["revision"] + 1 if previous else 1,
            "previous": {"id": previous["id"], "sha256": previous["sha256"]} if previous else None,
            "review": {"status": "draft", "note": "", "reviewer": "", "spec_sha256": ""},
            "reviews": [],
        }
        value["sha256"] = digest({k: value[k] for k in ("spec", "revision", "previous")})
        save(project.path("taxonomies", value["id"]), value)
        return value


def review_taxonomy(project: Project, key: str, status: str, note: str, reviewer: str) -> dict:
    if status not in {"accepted", "rejected", "draft"} or not note.strip() or not reviewer.strip():
        raise ValueError("Taxonomy review needs a status, reviewer and note")
    with project.lock():
        value = load_taxonomy(project, key)
        review = {
            "status": status,
            "note": note,
            "reviewer": reviewer,
            "at": now(),
            "spec_sha256": value["sha256"],
        }
        value["review"] = review
        value["reviews"].append(review)
        save(project.path("taxonomies", key), value)
        return value


def _task_signature(spec: dict) -> str:
    # Ignore authoring/provenance labels, retaining execution/verification semantics.
    ignored = {
        "id",
        "title",
        "purpose",
        "behavior",
        "finding_ids",
        "trace_ids",
        "assumptions",
        "missing_context",
        "verifier_examples",
    }
    value = {k: v for k, v in spec.items() if k not in ignored}
    value["input_json"] = parse_object(value["input_json"])
    value["criteria"] = [{k: v for k, v in c.items() if k != "id"} for c in spec["criteria"]]
    return digest(value)


def map_coverage(project: Project, taxonomy_id: str, mapping: CoverageMapping) -> dict:
    with project.lock():
        taxonomy = load_taxonomy(project, taxonomy_id, accepted=True)
        capability = next(
            (c for c in taxonomy["spec"]["capabilities"] if c["id"] == mapping.capability_id), None
        )
        if (
            capability is None
            or mapping.slice
            and mapping.slice not in capability["required_slices"]
        ):
            raise ValueError("Mapping needs a capability and slice from this taxonomy")
        store = TraceStore(project)
        if mapping.kind == "trace":
            trace = store.get(mapping.entity_id)
            entity = {"trace": trace.model_dump(), "metadata": store.metadata(mapping.entity_id)}
            entity_sha256 = entity["metadata"]["sha256"]
            signature = digest(trace.data)
            groups = [entity["metadata"]["group_id"]]
        else:
            entity, task = load_task(project, mapping.entity_id)
            entity_sha256 = task_digest(task)
            signature = _task_signature(task.model_dump())
            groups = sorted({store.metadata(t)["group_id"] for t in task.trace_ids})
        for old in project.artifacts("coverage"):
            if (
                old["taxonomy_id"],
                old["mapping"]["kind"],
                old["mapping"]["entity_id"],
                old["entity_sha256"],
                old["mapping"]["capability_id"],
                old["mapping"]["slice"],
            ) == (
                taxonomy["id"],
                mapping.kind,
                mapping.entity_id,
                entity_sha256,
                mapping.capability_id,
                mapping.slice,
            ):
                raise ValueError(
                    "This exact entity version is already mapped to that capability slice"
                )
        value = {
            "id": new_id(),
            "created_at": now(),
            "taxonomy_id": taxonomy["id"],
            "taxonomy_sha256": taxonomy["sha256"],
            "mapping": mapping.model_dump(),
            "entity": entity,
            "entity_sha256": entity_sha256,
            "signature": signature,
            "trace_groups": groups,
        }
        value["sha256"] = digest(value)
        # Mapping copies readable source content. Preserve conservative final-set bookkeeping.
        for suite in project.artifacts("suites"):
            if any(
                t["split"] == "final" and set(t["trace_groups"]) & set(groups)
                for t in suite["tasks"]
            ):
                suite.setdefault("research_exposure", []).append(
                    {
                        "coverage_mapping_id": value["id"],
                        "at": now(),
                        "scope": "source snapshot available in behavioral coverage",
                    }
                )
                save(project.path("suites", suite["id"]), suite)
        save(project.path("coverage", value["id"]), value)
        return value


def coverage_report(project: Project, taxonomy_id: str) -> dict:
    taxonomy = load_taxonomy(project, taxonomy_id)
    mappings = [m for m in project.artifacts("coverage") if m["taxonomy_id"] == taxonomy["id"]]
    for mapping in mappings:
        if (
            mapping["sha256"] != digest({k: v for k, v in mapping.items() if k != "sha256"})
            or mapping["taxonomy_sha256"] != taxonomy["sha256"]
        ):
            raise ValueError("Coverage mapping snapshot changed")
    experiments = project.artifacts("experiments")
    current_tasks, stale = {}, []
    for mapping in mappings:
        if mapping["mapping"]["kind"] != "task":
            continue
        key = mapping["mapping"]["entity_id"]
        if key not in current_tasks:
            _, task = load_task(project, key)
            try:
                load_task(project, key, accepted=True)
                accepted = True
            except ValueError:
                accepted = False
            current_tasks[key] = {"sha256": task_digest(task), "accepted": accepted}
        if current_tasks[key]["sha256"] != mapping["entity_sha256"]:
            stale.append(mapping["id"])
    trial_index = defaultdict(list)
    for experiment in experiments:
        snapshots = {
            t["id"]: task_digest(TaskSpec.model_validate(t)) for t in experiment["task_snapshots"]
        }
        for trial in experiment["trials"]:
            sha = snapshots.get(trial["task_id"])
            trial_index[(trial["task_id"], sha)].append(trial)

    def metrics(selected: list[dict]) -> dict:
        traces = {m["mapping"]["entity_id"] for m in selected if m["mapping"]["kind"] == "trace"}
        task_versions = {
            (m["mapping"]["entity_id"], m["entity_sha256"])
            for m in selected
            if m["mapping"]["kind"] == "task"
        }
        accepted = {
            key
            for key, sha in task_versions
            if current_tasks[key] == {"sha256": sha, "accepted": True}
        }
        trials = [trial for ref in task_versions for trial in trial_index[ref]]
        counts = {
            status: sum(t["grade"]["status"] == status for t in trials)
            for status in ("pass", "fail", "invalid")
        }
        tested = sum(bool(trial_index[ref]) for ref in task_versions)
        return {
            "traces": len(traces),
            "task_versions": len(task_versions),
            "accepted_tasks": len(accepted),
            "tested_task_versions": tested,
            "unexecuted_task_versions": len(task_versions) - tested,
            "trial_results": counts,
            "all_observed_valid_attempts_passed": bool(counts["pass"]) and counts["fail"] == 0,
            "independent_trace_groups": len({g for m in selected for g in m["trace_groups"]}),
        }

    capabilities = []
    for capability in taxonomy["spec"]["capabilities"]:
        selected = [m for m in mappings if m["mapping"]["capability_id"] == capability["id"]]
        slices = [
            {"name": name, **metrics([m for m in selected if m["mapping"]["slice"] == name])}
            for name in capability["required_slices"]
        ]
        capabilities.append(
            {
                "id": capability["id"],
                "name": capability["name"],
                **metrics(selected),
                "required_slices": slices,
                "missing_accepted_slices": [s["name"] for s in slices if not s["accepted_tasks"]],
                "unexecuted_slices": [s["name"] for s in slices if not s["tested_task_versions"]],
            }
        )
    duplicate_groups = defaultdict(set)
    for mapping in mappings:
        duplicate_groups[(mapping["mapping"]["kind"], mapping["signature"])].add(
            mapping["mapping"]["entity_id"]
        )
    mapped_traces = {m["mapping"]["entity_id"] for m in mappings if m["mapping"]["kind"] == "trace"}
    all_traces = {r["id"] for r in TraceStore(project).iter_rows()}
    mapped_tasks = {m["mapping"]["entity_id"] for m in mappings if m["mapping"]["kind"] == "task"}
    all_tasks = {t["id"] for t in project.artifacts("tasks")}
    return {
        "taxonomy_id": taxonomy["id"],
        "taxonomy_sha256": taxonomy["sha256"],
        "taxonomy_status": taxonomy["review"]["status"],
        "generated_at": now(),
        "capabilities": capabilities,
        "unmapped_trace_ids": sorted(all_traces - mapped_traces),
        "unmapped_task_ids": sorted(all_tasks - mapped_tasks),
        "stale_mapping_ids": sorted(stale),
        "duplicate_groups": [
            {"kind": kind, "signature": signature, "entity_ids": sorted(ids)}
            for (kind, signature), ids in sorted(duplicate_groups.items())
            if len(ids) > 1
        ],
        "source": {
            "traces": TraceStore(project).inventory(),
            "mappings_sha256": digest(sorted((m["id"], m["sha256"]) for m in mappings)),
            "experiments": [{"id": e["id"], "sha256": digest(e)} for e in experiments],
        },
        "scope": (
            "Counts cover explicitly classified local records and exact executed task versions, "
            "not production prevalence or research completion. Duplicate signatures compare "
            "canonical trace content or task execution/verification semantics. Repeated passes "
            "alone do not establish saturation; review task difficulty, diversity and fresh data "
            "before retiring cases."
        ),
    }
