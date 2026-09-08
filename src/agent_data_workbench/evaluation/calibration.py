"""Human calibration against frozen, actually executed agent attempts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from agent_data_workbench.shared.contracts import Contract
from agent_data_workbench.shared.files import save
from agent_data_workbench.shared.identifiers import UUIDString, new_id
from agent_data_workbench.shared.json import digest, read_json
from agent_data_workbench.shared.time import now
from agent_data_workbench.workspace.project import Project

Outcome = Literal["pass", "fail", "invalid"]
FailureCause = Literal[
    "agent_capability",
    "missing_information",
    "harness",
    "environment",
    "grader_false_pass",
    "grader_false_fail",
    "leakage",
    "infrastructure",
    "other",
]


class AttemptLabel(Contract):
    task_id: UUIDString
    trial: int = Field(ge=0)
    variant: Literal["baseline", "candidate"]
    evidence_sha256: str = Field(min_length=1)
    reviewer: str = Field(min_length=1)
    reviewer_kind: Literal["human", "model"] = "human"
    status: Outcome
    reason: str = Field(min_length=1)
    failure_cause: FailureCause | None = None


class AttemptAdjudication(AttemptLabel):
    labels_sha256: str = Field(min_length=1)


def _key(value: dict) -> tuple:
    return value["task_id"], value["trial"], value["variant"]


def _store(project: Project, value: dict) -> dict:
    value["state_sha256"] = digest({k: v for k, v in value.items() if k != "state_sha256"})
    save(
        project.path("calibrations", value["id"], "") / f"revision-{value['revision']}.json",
        value,
    )
    save(project.path("calibrations", value["id"]), value)
    return value


def load_calibration(project: Project, key: str) -> dict:
    value = read_json(project.path("calibrations", key))
    if value["state_sha256"] != digest(
        {k: v for k, v in value.items() if k != "state_sha256"}
    ) or value["snapshot_sha256"] != digest(value["snapshot"]):
        raise ValueError("Calibration content changed outside its revision history")
    if any(a["evidence_sha256"] != digest(a["evidence"]) for a in value["attempts"]):
        raise ValueError("Calibration attempt evidence changed")
    return value


def create_calibration(project: Project, experiment_id: str, name: str) -> dict:
    if not name.strip():
        raise ValueError("Supply a calibration name")
    with project.lock():
        experiment = read_json(project.path("experiments", experiment_id))
        if experiment["status"] not in {"complete", "interrupted"} or not experiment["trials"]:
            raise ValueError("Calibration needs recorded attempts from a finished experiment")
        tasks = {t["id"]: t for t in experiment["task_snapshots"]}
        snapshot = {
            "experiment_id": experiment["id"],
            "experiment_sha256": digest(experiment),
            "suite_id": experiment["suite_id"],
            "suite_sha256": experiment["suite_sha256"],
            "split": experiment["split"],
            "context_sha256": experiment["context_sha256"],
            "baseline": experiment["baseline"],
            "candidate": experiment["candidate"],
            "judge": experiment["judge"],
            "world_snapshots": experiment.get("world_snapshots", {}),
            "improvement": experiment.get("improvement"),
            "host": experiment.get("host"),
            "experiment_created_at": experiment["created_at"],
        }
        attempts = []
        seen = set()
        for row in experiment["trials"]:
            if _key(row) in seen or row["task_id"] not in tasks:
                raise ValueError("Experiment has duplicate attempts or missing task snapshots")
            if row["grade"]["status"] not in {"pass", "fail", "invalid"}:
                raise ValueError("Experiment has an unknown grade")
            seen.add(_key(row))
            evidence = {"task": tasks[row["task_id"]], "trial": row, "provenance": snapshot}
            attempts.append(
                {
                    "task_id": row["task_id"],
                    "trial": row["trial"],
                    "variant": row["variant"],
                    "evidence": evidence,
                    "evidence_sha256": digest(evidence),
                    "labels": [],
                    "adjudications": [],
                }
            )
        return _store(
            project,
            {
                "id": new_id(),
                "name": name,
                "created_at": now(),
                "revision": 1,
                "previous_sha256": None,
                "snapshot": snapshot,
                "snapshot_sha256": digest(snapshot),
                "attempts": attempts,
            },
        )


def _latest_labels(attempt: dict) -> list[dict]:
    latest = {
        label["reviewer"]: label
        for label in attempt["labels"]
        if label.get("reviewer_kind", "human") == "human"
    }
    return [latest[reviewer] for reviewer in sorted(latest)]


def _labels_sha256(attempt: dict) -> str:
    return digest(_latest_labels(attempt))


def _annotate(project: Project, key: str, annotation: AttemptLabel, *, adjudication: bool) -> dict:
    if not annotation.reviewer.strip() or not annotation.reason.strip():
        raise ValueError("Human review needs a reviewer and reason")
    with project.lock():
        value = load_calibration(project, key)
        attempt = next(
            (a for a in value["attempts"] if _key(a) == _key(annotation.model_dump())), None
        )
        if attempt is None:
            raise ValueError("Unknown calibration attempt")
        if annotation.evidence_sha256 != attempt["evidence_sha256"]:
            raise ValueError("Review must refer to the exact displayed attempt evidence")
        if adjudication:
            if annotation.reviewer_kind != "human":
                raise ValueError("Only a human reviewer can adjudicate calibration labels")
            if not _latest_labels(attempt):
                raise ValueError("Label an attempt before adjudicating it")
            if annotation.labels_sha256 != _labels_sha256(attempt):
                raise ValueError(
                    "Labels changed; review the current disagreement before adjudicating"
                )
        value["previous_sha256"] = value["state_sha256"]
        value["revision"] += 1
        attempt["adjudications" if adjudication else "labels"].append(
            {**annotation.model_dump(), "at": now(), "revision": value["revision"]}
        )
        return _store(project, value)


def label_attempt(project: Project, key: str, label: AttemptLabel) -> dict:
    return _annotate(project, key, label, adjudication=False)


def adjudicate_attempt(project: Project, key: str, decision: AttemptAdjudication) -> dict:
    return _annotate(project, key, decision, adjudication=True)


def calibration_summary(project: Project, key: str) -> dict:
    value = load_calibration(project, key)
    matrix = {
        machine: {human: 0 for human in ("pass", "fail", "invalid")}
        for machine in ("pass", "fail", "invalid")
    }
    rows = []
    for attempt in value["attempts"]:
        labels = _latest_labels(attempt)
        labels_sha256 = _labels_sha256(attempt)
        adjudications = [
            item for item in attempt["adjudications"] if item["labels_sha256"] == labels_sha256
        ]
        statuses = {item["status"] for item in labels}
        human = None
        if adjudications:
            human, resolution = adjudications[-1]["status"], "adjudicated"
        elif len(statuses) == 1:
            human, resolution = next(iter(statuses)), "consensus"
        else:
            resolution = "disagreement" if statuses else "unlabeled"
        causes = {item.get("failure_cause") for item in labels}
        cause = (
            adjudications[-1].get("failure_cause")
            if adjudications
            else (next(iter(causes)) if human is not None and len(causes) == 1 else None)
        )
        machine = attempt["evidence"]["trial"]["grade"]["status"]
        if human is not None:
            matrix[machine][human] += 1
        rows.append(
            {
                "task_id": attempt["task_id"],
                "trial": attempt["trial"],
                "variant": attempt["variant"],
                "evidence_sha256": attempt["evidence_sha256"],
                "labels_sha256": labels_sha256,
                "grader_status": machine,
                "human_status": human,
                "resolution": resolution,
                "reviewers": len(labels),
                "failure_cause": cause,
                "cause_disagreement": not adjudications and len(causes) > 1,
                "latest_labels": labels,
                "model_labels": [
                    item for item in attempt["labels"] if item.get("reviewer_kind") == "model"
                ],
                "adjudication": adjudications[-1] if adjudications else None,
            }
        )
    false_pass, false_fail = matrix["pass"]["fail"], matrix["fail"]["pass"]
    human_fail = matrix["pass"]["fail"] + matrix["fail"]["fail"]
    human_pass = matrix["pass"]["pass"] + matrix["fail"]["pass"]
    return {
        "calibration_id": value["id"],
        "revision": value["revision"],
        "snapshot_sha256": value["snapshot_sha256"],
        "total": len(rows),
        "resolved": sum(row["human_status"] is not None for row in rows),
        "unlabeled": sum(row["resolution"] == "unlabeled" for row in rows),
        "disagreements": sum(row["resolution"] == "disagreement" for row in rows),
        "adjudicated": sum(row["resolution"] == "adjudicated" for row in rows),
        "confusion_matrix": matrix,
        "false_pass": {
            "count": false_pass,
            "denominator": human_fail,
            "rate": false_pass / human_fail if human_fail else None,
        },
        "false_fail": {
            "count": false_fail,
            "denominator": human_pass,
            "rate": false_fail / human_pass if human_pass else None,
        },
        "invalid_disagreements": matrix["invalid"]["pass"]
        + matrix["invalid"]["fail"]
        + matrix["pass"]["invalid"]
        + matrix["fail"]["invalid"],
        "failure_causes": {
            cause: sum(row["failure_cause"] == cause for row in rows)
            for cause in sorted({row["failure_cause"] for row in rows if row["failure_cause"]})
        },
        "cause_disagreements": sum(row["cause_disagreement"] for row in rows),
        "attempts": rows,
        "scope": (
            "Agreement on these recorded attempts only. Reviewer identity and kind are declared. "
            "Only latest human labels per named reviewer count; model suggestions are excluded. "
            "Unresolved disagreements are excluded. Invalid disagreements are not capability "
            "failures. Rates exclude invalid and unresolved labels; no population accuracy claim."
        ),
    }
