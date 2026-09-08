"""Traceable hypotheses, exact candidate changes, and human experiment decisions."""

from __future__ import annotations

import difflib
import hashlib
from pathlib import Path

from agent_data_workbench.execution.contracts import TargetRunner
from agent_data_workbench.execution.runners import ConfiguredRunner
from agent_data_workbench.shared.files import save
from agent_data_workbench.shared.identifiers import new_id
from agent_data_workbench.shared.json import digest, json_text, read_json
from agent_data_workbench.shared.time import now
from agent_data_workbench.workspace.project import Project


def snapshot_runner(runner: ConfiguredRunner) -> dict:
    identity = runner.identity()
    sources = {}
    source_hashes = {
        **identity["source_sha256"],
        **(identity.get("environment") or {}).get("source_sha256", {}),
        **(identity.get("simulator") or {}).get("sources", {}),
    }
    for filename, expected in source_hashes.items():
        path = Path(filename)
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("Runner source changed while capturing the candidate")
        try:
            text = content.decode("utf-8")
        except UnicodeError:
            text = None
        try:
            name = str(path.relative_to(runner.base_dir))
        except ValueError:
            name = str(path)
        sources[name] = {"sha256": expected, "content": text}
    value = {"identity": identity, "sources": sources}
    return {**value, "sha256": digest(value)}


def candidate_patch(baseline: dict, candidate: dict) -> str:
    def files(snapshot):
        return {
            **{
                name: row["content"]
                if row["content"] is not None
                else f"Binary sha256: {row['sha256']}\n"
                for name, row in snapshot["sources"].items()
            },
            "@runner-config.json": json_text(snapshot["identity"]["config"]) + "\n",
        }

    before, after = files(baseline), files(candidate)
    return "".join(
        line
        for name in sorted(set(before) | set(after))
        for line in difflib.unified_diff(
            before.get(name, "").splitlines(keepends=True),
            after.get(name, "").splitlines(keepends=True),
            fromfile="baseline/" + name,
            tofile="candidate/" + name,
        )
    )


def create_improvement(
    project: Project,
    name: str,
    hypothesis: str,
    expected_behavior: str,
    baseline: ConfiguredRunner,
    candidate: ConfiguredRunner,
    *,
    trace_ids: list[str] | None = None,
    task_ids: list[str] | None = None,
    parent_id: str | None = None,
) -> dict:
    from agent_data_workbench.data.store import TraceStore
    from agent_data_workbench.evaluation.tasks.repository import load_task, task_digest

    if not all(s.strip() for s in (name, hypothesis, expected_behavior)):
        raise ValueError("Name the change, hypothesis and expected behavior")
    traces, tasks = trace_ids or [], task_ids or []
    store = TraceStore(project)
    trace_sources = {key: store.metadata(key)["sha256"] for key in traces}
    task_sources = {key: task_digest(load_task(project, key)[1]) for key in tasks}
    before, after = snapshot_runner(baseline), snapshot_runner(candidate)
    if before["identity"]["sha256"] == after["identity"]["sha256"]:
        raise ValueError("Baseline and candidate must identify different versions")
    with project.lock():
        if parent_id:
            load_improvement(project, parent_id)
        record = {
            "id": new_id(),
            "created_at": now(),
            "name": name,
            "hypothesis": hypothesis,
            "expected_behavior": expected_behavior,
            "parent_id": parent_id,
            "trace_ids": traces,
            "task_ids": tasks,
            "trace_sources": trace_sources,
            "task_sources": task_sources,
            "baseline": before,
            "candidate": after,
            "patch": candidate_patch(before, after),
        }
        record["sha256"] = digest(record)
        record.update(experiments=[], decisions=[])
        save(project.path("improvements", record["id"]), record)
        return record


def load_improvement(project: Project, key: str) -> dict:
    record = read_json(project.path("improvements", key))
    frozen = {k: v for k, v in record.items() if k not in {"sha256", "experiments", "decisions"}}
    if digest(frozen) != record["sha256"]:
        raise ValueError("Improvement snapshot changed; create another candidate version")
    return record


def verify_candidate(project: Project, key: str, baseline: TargetRunner, candidate: TargetRunner):
    record = load_improvement(project, key)
    for variant, runner in (("baseline", baseline), ("candidate", candidate)):
        if runner.identity() != record[variant]["identity"]:
            raise ValueError(f"{variant.title()} differs from the recorded improvement version")
        if isinstance(runner, ConfiguredRunner):
            if snapshot_runner(runner) != record[variant]:
                raise ValueError("Runner sources changed since the improvement was recorded")
    return {"id": key, "sha256": record["sha256"]}


def link_experiment(project: Project, key: str, experiment: dict) -> None:
    """Called inside the experiment's project lock before any target execution."""
    record = load_improvement(project, key)
    record["experiments"].append(
        {
            "id": experiment["id"],
            "suite_id": experiment["suite_id"],
            "suite_sha256": experiment["suite_sha256"],
            "split": experiment["split"],
            "at": now(),
        }
    )
    save(project.path("improvements", key), record)


def decide_improvement(
    project: Project,
    key: str,
    experiment_id: str,
    decision: str,
    reviewer: str,
    reason: str,
) -> dict:
    if (
        decision not in {"keep", "reject", "inconclusive"}
        or not reviewer.strip()
        or not reason.strip()
    ):
        raise ValueError("Supply a keep/reject/inconclusive decision, reviewer and reason")
    with project.lock():
        record = load_improvement(project, key)
        experiment = read_json(project.path("experiments", experiment_id))
        if experiment.get("improvement") != {"id": key, "sha256": record["sha256"]}:
            raise ValueError("Experiment is not linked to this exact improvement")
        if experiment["status"] != "complete":
            raise ValueError("Finish the experiment before recording a decision")
        if experiment["candidate"] != record["candidate"]["identity"]:
            raise ValueError("Experiment used another candidate version")
        from agent_data_workbench.evaluation.calibration import calibration_summary

        calibrations = [
            {
                "id": c["id"],
                "state_sha256": c["state_sha256"],
                "summary": calibration_summary(project, c["id"]),
            }
            for c in project.artifacts("calibrations")
            if c["snapshot"]["experiment_id"] == experiment_id
        ]
        review = {
            "id": new_id(),
            "at": now(),
            "experiment_id": experiment_id,
            "experiment_sha256": digest(experiment),
            "decision": decision,
            "reviewer": reviewer,
            "reason": reason,
            "split": experiment["split"],
            "summary": experiment["summary"],
            "calibrations": calibrations,
            "scope": "Human decision about this evidence; no code is applied or deployed.",
        }
        record["decisions"].append(review)
        save(project.path("improvements", key), record)
        return record
