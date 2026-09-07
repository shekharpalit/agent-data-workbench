"""Grouped dataset splits and immutable, paired target-agent experiments."""

from __future__ import annotations

import math
import random
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path

from .backends import Analyzer
from .command_sources import file_sha256
from .identifiers import canonical_uuid, new_id
from .project import Project, digest, environment_identity, now, save
from .runners import ConfiguredRunner, TargetRunner, read_artifacts
from .store import TraceStore
from .tasks import grade, load_task, parse_object, task_digest
from .traces import read_json


def make_suite(project: Project, name: str, task_ids: list[str], seed: int = 0) -> dict:
    if not name.strip():
        raise ValueError("Supply a suite name")
    task_ids = [canonical_uuid(key) for key in task_ids]
    if not task_ids or len(set(task_ids)) != len(task_ids):
        raise ValueError("Provide unique task IDs")
    store = TraceStore(project)
    tasks = {key: load_task(project, key, accepted=True)[1] for key in task_ids}
    # Connected components prevent related traces OR tasks joining multiple threads from leaking.
    parent = {key: key for key in task_ids}

    def find(key):
        while parent[key] != key:
            key = parent[key]
        return key

    owner = {}
    for key, task in tasks.items():
        for trace_id in task.trace_ids:
            group = store.metadata(trace_id)["group_id"]
            if group in owner:
                parent[find(key)] = find(owner[group])
            else:
                owner[group] = key
    groups = defaultdict(list)
    for key in task_ids:
        groups[find(key)].append(key)
    if len(groups) < 3:
        raise ValueError("Need at least three independent trace groups for three dataset splits")
    strata = defaultdict(list)
    for keys in groups.values():
        signature = ",".join(sorted({tasks[key].behavior for key in keys}))
        strata[signature].append(sorted(keys))
    rng = random.Random(seed)
    ordered = []
    for stratum in sorted(strata):
        buckets = sorted(strata[stratum])
        rng.shuffle(buckets)
        ordered.extend(buckets)
    assignment = {}
    # Small suites get all three roles. Larger suites use approximately 60/20/20.
    for i, group in enumerate(ordered):
        split = ("optimization", "validation", "final", "optimization", "optimization")[i % 5]
        for key in group:
            assignment[key] = split
    old_roles = {}
    for old_suite in project.artifacts("suites"):
        for entry in old_suite["tasks"]:
            for group in entry["trace_groups"]:
                old_roles.setdefault(group, set()).add(entry["split"])
    # A native agent can read snapshot files directly, outside observable MCP reads.
    # Record availability conservatively instead of claiming those inputs were unseen.
    from .research.artifacts import investigation_directory
    from .research.dataset import Dataset

    exposed = set()
    for investigation in project.artifacts("investigations"):
        path = investigation_directory(project, investigation["id"]) / "dataset.sqlite3"
        if path.exists():
            dataset = Dataset(path)
            after = None
            while rows := dataset.rows(after=after):
                exposed.update(r["trace_id"] for r in rows)
                after = rows[-1]["trace_id"]
        else:
            exposed.update(investigation["visited_ids"])
    for export in project.artifacts("exports"):
        if export.get("kind") == "harbor":
            exposed.update(export.get("trace_ids", []))
    for key, task in tasks.items():
        for trace_id in task.trace_ids:
            roles = old_roles.get(store.metadata(trace_id)["group_id"], set())
            if roles and roles != {assignment[key]}:
                raise ValueError("Source group already belongs to another split; use fresh data")
    suite = {
        "id": new_id(),
        "name": name,
        "created_at": now(),
        "seed": seed,
        "source": store.inventory(),
        "tasks": [
            {
                "id": key,
                "split": assignment[key],
                "behavior": tasks[key].behavior,
                "spec_sha256": task_digest(tasks[key]),
                "cluster_id": find(key),
                "previously_investigated": bool(set(tasks[key].trace_ids) & exposed),
                "trace_groups": sorted(
                    {store.metadata(t)["group_id"] for t in tasks[key].trace_ids}
                ),
            }
            for key in sorted(task_ids)
        ],
        "final_exposure": None,
        "split_method": "Seeded behavioral strata, connected thread groups; approx 60/20/20",
        "holdout_scope": "Execution holdout reserved after suite creation. Prior investigation "
        "or snapshot availability is recorded; available examples are not claimed as unseen data.",
    }
    suite["sha256"] = digest(
        {k: v for k, v in suite.items() if k not in {"final_exposure", "research_exposure"}}
    )
    with project.lock():
        path = project.path("suites", suite["id"])
        save(path, suite)
    return suite


def proportion_interval(passed: int, total: int) -> list[float] | None:
    if not total:
        return None
    z, p = 1.96, passed / total
    center = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / (1 + z * z / total)
    return [max(0, center - half), min(1, center + half)]


def summarize(rows: list[dict]) -> dict:
    summary = {}
    for variant in ("baseline", "candidate"):
        selected = [r for r in rows if r["variant"] == variant]
        passed = sum(r["grade"]["status"] == "pass" for r in selected)
        failed = sum(r["grade"]["status"] == "fail" for r in selected)
        invalid = len(selected) - passed - failed
        costs = [
            r["execution"]["cost_usd"] for r in selected if r["execution"]["cost_usd"] is not None
        ]
        summary[variant] = {
            "passed": passed,
            "failed": failed,
            "invalid": invalid,
            "total": len(selected),
            "valid": passed + failed,
            "pass_rate": passed / (passed + failed) if passed + failed else None,
            "recorded_cost_usd": sum(costs) if costs else None,
            "cost_coverage": len(costs),
            "mean_latency_seconds": sum(r["execution"]["latency_seconds"] for r in selected)
            / len(selected)
            if selected
            else None,
        }
    pairs = defaultdict(dict)
    for row in rows:
        pairs[(row["task_id"], row["trial"])][row["variant"]] = row["grade"]["status"]
    improved, regressed, invalid_pairs = [], [], []
    for (key, trial), pair in pairs.items():
        item = {"task_id": key, "trial": trial}
        if set(pair) != {"baseline", "candidate"} or "invalid" in pair.values():
            invalid_pairs.append(item)
        elif pair["baseline"] == "fail" and pair["candidate"] == "pass":
            improved.append(item)
        elif pair["baseline"] == "pass" and pair["candidate"] == "fail":
            regressed.append(item)
    # Bootstrap independent source groups, preserving repeated and related tasks together.
    clusters = {r["task_id"]: r.get("cluster_id", r["task_id"]) for r in rows}
    per_task = defaultdict(list)
    for (key, _), pair in pairs.items():
        if set(pair) == {"baseline", "candidate"} and "invalid" not in pair.values():
            per_task[key].append(int(pair["candidate"] == "pass") - int(pair["baseline"] == "pass"))
    effects = [sum(v) / len(v) for _, v in sorted(per_task.items())]
    per_cluster = defaultdict(list)
    for key, values in per_task.items():
        per_cluster[clusters[key]].append(sum(values) / len(values))
    cluster_values = [v for _, v in sorted(per_cluster.items())]
    interval = None
    if len(cluster_values) >= 5:
        rng = random.Random(0)
        boots = []
        for _ in range(2000):
            selected = rng.choices(cluster_values, k=len(cluster_values))
            flat = [v for group in selected for v in group]
            boots.append(sum(flat) / len(flat))
        boots.sort()
        interval = [boots[49], boots[1949]]
    return {
        **summary,
        "improved": improved,
        "regressed": regressed,
        "invalid_pairs": invalid_pairs,
        "task_mean_delta": sum(effects) / len(effects) if effects else None,
        "task_bootstrap_95_interval": interval,
        "independent_groups": len(cluster_values),
        "uncertainty_note": "Exploratory source-group bootstrap; at least 5 valid groups required. "
        "Does not establish production generalization.",
    }


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
    from .improvements import link_experiment, verify_candidate
    from .worlds import resolve_world

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


def experiment_report(record: dict) -> str:
    from .reports import md

    summary = record["summary"]
    lines = [
        "# Agent improvement experiment",
        "",
        md(record["conclusion"]),
        "",
        f"Split: {record['split']}. Repeats: {record['repeats']}.",
        "",
        "| Variant | Pass | Fail | Invalid | Recorded cost |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for key in ("baseline", "candidate"):
        s = summary[key]
        lines.append(
            f"| {key} | {s['passed']} | {s['failed']} | {s['invalid']} | {s['recorded_cost_usd']} |"
        )
    lines.extend(
        [
            "",
            "## Per-trial results",
            "",
            "| Task | Trial | Variant | Result |",
            "| --- | ---: | --- | --- |",
        ]
    )
    for r in record["trials"]:
        lines.append(f"| {r['task_id']} | {r['trial']} | {r['variant']} | {r['grade']['status']} |")
    lines.extend(
        [
            "",
            md(summary["uncertainty_note"]),
            "",
            "Command runners execute trusted local code with fresh working directories. "
            "This does not sandbox network or host access. Environment fidelity depends on "
            "the configured runner, fixtures and independent verifier evidence.",
            "",
        ]
    )
    return "\n".join(lines)
