"""Run baseline and candidate on the same frozen task and import their evidence."""

from agent_data_workbench.evaluation.reports import experiment_report
from agent_data_workbench.evaluation.statistics import summarize
from agent_data_workbench.evaluation.tasks.repository import load_task
from agent_data_workbench.shared.files import save
from agent_data_workbench.shared.identifiers import new_id
from agent_data_workbench.shared.json import digest
from agent_data_workbench.shared.time import now
from agent_data_workbench.workspace.project import Project

from .contracts import HarborComparisonConfig, HarborExportConfig
from .exporting import export_harbor
from .results import collect_trial
from .runtime import run_harbor_export


def compare_harbor(project: Project, task_id: str, config: HarborComparisonConfig) -> dict:
    _, task = load_task(project, task_id, accepted=True)
    exported = export_harbor(
        project,
        task_id,
        HarborExportConfig(
            **config.baseline.model_dump(),
            template_directory=config.template_directory,
            environment_type=config.environment_type,
            repetitions=1,
        ),
    )
    identity = new_id()
    record = {
        "id": identity,
        "kind": "harbor",
        "created_at": now(),
        "status": "running",
        "suite_id": None,
        "suite_sha256": None,
        "split": "exploratory",
        "repeats": config.repetitions,
        "seed": None,
        "proposal": f"Harbor comparison: {task.title}",
        "conclusion": "Harbor comparison running",
        "config": config.model_dump(),
        "export_id": exported["id"],
        "bundle_sha256": exported["bundle_sha256"],
        "task_snapshots": [task.model_dump()],
        "baseline": config.baseline.model_dump(),
        "candidate": config.candidate.model_dump(),
        "judge": {
            "kind": "harbor_verifier",
            "reward_key": config.reward_key,
            "pass_threshold": config.pass_threshold,
        },
        "context_sha256": task.context_sha256,
        "host": {},
        "trials": [],
        "summary": {},
        "scope": "Exploratory comparison of a reviewed task using the supplied Harbor verifier. "
        "Pairs share the frozen task and repeat index; model randomness is not controlled. "
        "The workbench task audit does not calibrate this external verifier.",
    }
    path = project.path("experiments", identity)
    save(path, record)
    try:
        for repeat in range(config.repetitions):
            variants = ("baseline", "candidate") if repeat % 2 == 0 else ("candidate", "baseline")
            for variant in variants:
                run = run_harbor_export(
                    project,
                    exported["id"],
                    timeout=config.timeout,
                    target=getattr(config, variant),
                    single_attempt=True,
                )
                record["trials"].append(
                    collect_trial(
                        project,
                        run,
                        experiment_id=identity,
                        task=task.model_dump(),
                        variant=variant,
                        repeat=repeat,
                        config=config,
                    )
                )
                record["summary"] = summarize(record["trials"])
                save(path, record)
        record["status"] = "complete"
        summary = record["summary"]
        record["conclusion"] = (
            "Harbor comparison has invalid trials — inspect execution evidence"
            if summary["invalid_pairs"]
            else (
                f"Harbor comparison: {len(summary['improved'])} improvements, "
                f"{len(summary['regressed'])} regressions"
            )
        )
    except Exception:
        record.update(
            status="error",
            conclusion="Harbor comparison interrupted — inspect saved trials and runtime setup",
        )
        raise
    finally:
        record["finished_at"] = now()
        record["summary"] = summarize(record["trials"])
        record["sha256"] = digest({k: v for k, v in record.items() if k != "sha256"})
        save(path, record)
        project.path("experiments", identity, ".md").write_text(
            experiment_report(record), encoding="utf-8"
        )
    return record
