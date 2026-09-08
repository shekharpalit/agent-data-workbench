"""Execute paired target-agent trials against reviewed suite snapshots."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from agent_data_workbench.evaluation.reports import experiment_report
from agent_data_workbench.evaluation.statistics import summarize
from agent_data_workbench.evaluation.tasks.grading import grade
from agent_data_workbench.evaluation.tasks.repository import load_task, task_digest
from agent_data_workbench.execution.artifacts import read_artifacts
from agent_data_workbench.execution.contracts import TargetRunner
from agent_data_workbench.execution.runners import ConfiguredRunner
from agent_data_workbench.integrations.analyzers import Analyzer
from agent_data_workbench.shared.commands import file_sha256
from agent_data_workbench.shared.environment import environment_identity
from agent_data_workbench.shared.files import save
from agent_data_workbench.shared.identifiers import new_id
from agent_data_workbench.shared.json import digest, parse_object, read_json
from agent_data_workbench.shared.time import now
from agent_data_workbench.workspace.project import Project


def run_experiment(
    project: Project,
    suite_id: str,
    baseline: TargetRunner,
    candidate: TargetRunner,
    *,
    split: str = "validation",
    repeats: int = 1,
    seed: int = 0,
    proposal: str = "",
    improvement_id: str | None = None,
    judge: Analyzer | None = None,
    on_trial=None,
) -> dict:
    if split not in {"optimization", "validation", "final"} or not 1 <= repeats <= 100:
        raise ValueError("Invalid split or trial count")
    from agent_data_workbench.evaluation.improvements import link_experiment, verify_candidate
    from agent_data_workbench.evaluation.worlds import resolve_world

    with project.lock():
        improvement = (
            verify_candidate(project, improvement_id, baseline, candidate)
            if improvement_id
            else None
        )
        suite_path = project.path("suites", suite_id)
        suite = read_json(suite_path)
        expected = digest(
            {
                k: v
                for k, v in suite.items()
                if k not in {"sha256", "final_exposure", "research_exposure"}
            }
        )
        if suite["sha256"] != expected:
            raise ValueError("Suite manifest changed; create a new version")
        if split == "final" and suite["final_exposure"]:
            raise ValueError("Final test set has already been exposed; create a fresh final set")
        selected = [t for t in suite["tasks"] if t["split"] == split]
        if not selected:
            raise ValueError("This split has no tasks")
        if split == "final" and any(
            set(t["trace_groups"]) & project.final_groups(consumed=True) for t in selected
        ):
            raise ValueError("Final source groups were already exposed in research or evaluation")
        clusters = {t["id"]: t.get("cluster_id", t["id"]) for t in selected}
        tasks = {}
        task_runners = {}
        for feature in ("environment", "conversation"):
            if baseline.identity().get("config", {}).get(feature) != candidate.identity().get(
                "config", {}
            ).get(feature):
                raise ValueError(
                    "Baseline and candidate must use the same scenario defaults; "
                    "scenarios belong to reviewed tasks"
                )
        for entry in selected:
            value, task = load_task(project, entry["id"], accepted=True)
            if task_digest(task) != entry["spec_sha256"]:
                raise ValueError("Task changed after splitting; create a new suite")
            task_runners[task.id] = {}
            for variant, runner in (("baseline", baseline), ("candidate", candidate)):
                runner_config = runner.identity().get("config", {})
                fidelity = runner_config.get("fidelity")
                if fidelity and fidelity != task.fidelity:
                    raise ValueError("Runner fidelity does not match the task")
                if isinstance(runner, ConfiguredRunner):
                    effective = runner.for_task(task.environment, task.conversation)
                else:
                    effective = runner
                    for feature in ("environment", "conversation"):
                        configured = getattr(task, feature)
                        expected_config = configured.model_dump() if configured else None
                        if runner_config.get(feature) != expected_config:
                            raise ValueError(f"Custom runner {feature} does not match the task")
                task_runners[task.id][variant] = effective
            if any(c.kind == "semantic" for c in task.criteria):
                if judge is None:
                    raise ValueError("Configure a semantic judge before running these tasks")
                if value["audit"]["judge"] != judge.name or value["audit"].get(
                    "judge_model"
                ) != getattr(judge, "model", None):
                    raise ValueError("Judge differs from audited judge; re-audit the task")
            tasks[task.id] = task
        key = new_id()
        record = {
            "id": key,
            "created_at": now(),
            "suite_id": suite_id,
            "suite_sha256": suite["sha256"],
            "split": split,
            "repeats": repeats,
            "seed": seed,
            "proposal": proposal,
            "improvement": improvement,
            "previously_investigated_tasks": [
                t["id"] for t in selected if t.get("previously_investigated")
            ],
            "status": "running",
            "baseline": baseline.identity(),
            "candidate": candidate.identity(),
            "judge": {
                "name": getattr(judge, "name", "deterministic"),
                "model": getattr(judge, "model", None),
            },
            "host": environment_identity(),
            "context_sha256": project.context()["sha256"],
            "task_snapshots": [t.model_dump() for t in tasks.values()],
            "world_snapshots": {
                t.world.id: resolve_world(project, t.world) for t in tasks.values() if t.world
            },
            "trial_runner_identities": {
                task_id: {variant: runner.identity() for variant, runner in variants.items()}
                for task_id, variants in task_runners.items()
            },
            "trials": [],
            "summary": {},
            "conclusion": "Incomplete experiment",
        }
        path = project.path("experiments", key)
        save(path, record)
        if improvement_id:
            link_experiment(project, improvement_id, record)
        if split == "final":
            # Consume exposure before the first execution, including interrupted/error runs.
            suite["final_exposure"] = {"at": now(), "experiment_id": key}
            save(suite_path, suite)
        evidence_dir = project.path("experiments", key, "")
        evidence_dir.mkdir(mode=0o700)
        try:
            for task in tasks.values():
                for trial in range(repeats):
                    trial_seed = seed + trial
                    variants = list(task_runners[task.id].items())
                    if trial % 2:
                        variants.reverse()
                    for variant, runner in variants:
                        with tempfile.TemporaryDirectory(prefix="agent-data-workbench-trial-") as d:
                            trial_dir = Path(d)
                            execution = runner.run(
                                parse_object(task.input_json), trial_dir, trial_seed
                            )
                            artifacts = read_artifacts(
                                trial_dir,
                                [c.artifact for c in task.criteria if c.source == "artifact"],
                            )
                            state = (
                                runner.authoritative_artifacts(trial_dir)
                                if callable(getattr(runner, "authoritative_artifacts", None))
                                else {}
                            )
                            runtime_evidence = (
                                runner.trial_evidence(trial_dir)
                                if callable(getattr(runner, "trial_evidence", None))
                                else {}
                            )
                            result = (
                                grade(task, execution.output, artifacts, judge, state=state)
                                if execution.status == "completed"
                                else {"status": "invalid", "checks": [], "reason": execution.status}
                            )
                            files_id = new_id()
                            files_path = evidence_dir / files_id
                            shutil.copytree(trial_dir, files_path, symlinks=True)
                            captured_files = {
                                file.relative_to(files_path).as_posix(): file_sha256(file)
                                for file in files_path.rglob("*")
                                if file.is_file() and not file.is_symlink()
                            }
                            row = {
                                "task_id": task.id,
                                "cluster_id": clusters[task.id],
                                "behavior": task.behavior,
                                "trial": trial,
                                "seed": trial_seed,
                                "variant": variant,
                                "fidelity": task.fidelity,
                                "execution": execution.model_dump(),
                                "grade": result,
                                "artifacts": artifacts,
                                "state": state,
                                "runtime_evidence": runtime_evidence,
                                "runner_identity": record["trial_runner_identities"][task.id][
                                    variant
                                ],
                                "files": {"directory": files_id, "sha256": captured_files},
                            }
                            record["trials"].append(row)
                            save(evidence_dir / f"{task.id}-{trial}-{variant}.json", row)
                            save(path, record)
                            if on_trial:
                                on_trial(row)
            record["status"] = "complete"
        except Exception, KeyboardInterrupt:
            record["status"] = "interrupted"
            record["summary"] = summarize(record["trials"])
            save(path, record)
            raise
        record["summary"] = summarize(record["trials"])
        s = record["summary"]
        record["conclusion"] = (
            "Invalid runs require investigation"
            if s["invalid_pairs"]
            else "Regressions detected"
            if s["regressed"]
            else "Observed gains on this suite"
            if s["improved"]
            else "No measured gain on this suite"
        )
        save(path, record)
        (evidence_dir / "report.md").write_text(experiment_report(record), encoding="utf-8")
        return record
