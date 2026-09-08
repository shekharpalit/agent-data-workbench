"""Interpret actual Harbor TrialResult files without treating CLI success as a pass."""

import math
from datetime import datetime
from pathlib import Path

from agent_data_workbench.data.contracts import Trace
from agent_data_workbench.data.store import TraceStore
from agent_data_workbench.shared.identifiers import stable_id
from agent_data_workbench.workspace.project import Project

from .artifacts import read_artifact
from .contracts import HarborComparisonConfig


def verifier_grade(raw: dict, config: HarborComparisonConfig) -> dict:
    result = raw.get("verifier_result") or {}
    reward = (result.get("rewards") or {}).get(config.reward_key)
    exception = raw.get("exception_info") or next(
        (
            step.get("exception_info")
            for step in raw.get("step_results") or []
            if step.get("exception_info")
        ),
        None,
    )
    valid = not exception and type(reward) in (int, float) and math.isfinite(reward)
    return {
        "status": ("pass" if reward >= config.pass_threshold else "fail") if valid else "invalid",
        "checks": [
            {
                "kind": "harbor_verifier",
                "reward_key": config.reward_key,
                "reward": reward,
                "operator": "gte",
                "threshold": config.pass_threshold,
                "exception": exception,
            }
        ],
        "reason": "Recorded Harbor verifier reward"
        if valid
        else "Missing/invalid verifier reward or execution exception",
    }


def _latency(raw: dict) -> float:
    timing = raw.get("agent_execution") or raw
    if timing.get("started_at") and timing.get("finished_at"):
        return max(
            0,
            (
                datetime.fromisoformat(timing["finished_at"])
                - datetime.fromisoformat(timing["started_at"])
            ).total_seconds(),
        )
    return 0.0


def collect_trial(
    project: Project,
    run: dict,
    *,
    experiment_id: str,
    task: dict,
    variant: str,
    repeat: int,
    config: HarborComparisonConfig,
) -> dict:
    directory = Path(run["job_directory"])
    paths = sorted(directory.glob("*/result.json"))
    # The comparison launches one attempt per job. Extra/missing results are invalid,
    # not silently paired with a different task or repeat.
    captured = []
    errors = []
    for path in paths:
        original, error = read_artifact(path)
        if error:
            errors.append(error)
        trajectories = []
        for item in sorted(path.parent.rglob("trajectory.json")):
            trajectory, error = read_artifact(item)
            trajectories.append(
                {"path": item.relative_to(path.parent).as_posix(), "data": trajectory}
            )
            if error:
                errors.append(error)
        captured.append((path, original, trajectories))
    raw = captured[0][1] if len(captured) == 1 else {}
    if len(paths) != 1 or run["status"] != "completed":
        raw = {
            **raw,
            "exception_info": {
                "exception_type": "WorkbenchHarborRunError",
                "exception_message": run.get("error")
                or f"Expected one trial result, found {len(paths)}",
            },
        }
    if errors:
        raw = {
            **raw,
            "exception_info": {
                "exception_type": "WorkbenchHarborArtifactError",
                "exception_message": "; ".join(errors),
            },
        }
    grade = verifier_grade(raw, config)
    trace_ids = []
    for path, original, trajectories in captured:
        key = stable_id("harbor-trial", str(path.resolve()))
        data = {
            "source": {
                "provider": "harbor",
                "experiment_id": experiment_id,
                "task_id": task["id"],
                "variant": variant,
                "run_id": run["id"],
                "path": str(path.parent),
            },
            "title": task["title"],
            "result": original,
            "trajectories": trajectories,
            "resolved": grade["status"] == "pass" if grade["status"] != "invalid" else None,
        }

        class Source:
            def read(self):
                yield Trace(trace_id=key, data=data)

        TraceStore(project).ingest(
            Source(), group_pointer="/source/task_id", stratum_pointer="/source/variant"
        )
        trace_ids.append(key)
    contexts = (
        [raw["agent_result"]]
        if raw.get("agent_result")
        else [
            step["agent_result"]
            for step in raw.get("step_results") or []
            if step.get("agent_result")
        ]
    )
    costs = [context["cost_usd"] for context in contexts if context.get("cost_usd") is not None]
    return {
        "task_id": task["id"],
        "task_title": task["title"],
        "cluster_id": task["id"],
        "trial": repeat,
        "variant": variant,
        "fidelity": "environment",
        "grade": grade,
        "execution": {
            "status": "error" if grade["status"] == "invalid" else "ok",
            "output": raw,
            "latency_seconds": _latency(raw),
            "cost_usd": sum(costs) if costs else None,
        },
        "artifacts": {
            "harbor_job_directory": str(directory),
            "result_files": [str(p) for p in paths],
        },
        "state": {},
        "runtime_evidence": {},
        "runner_identity": run,
        "trace_ids": trace_ids,
    }
