"""Immutable task suites with independent source-group dataset splits."""

from __future__ import annotations

import random
from collections import defaultdict

from agent_data_workbench.data.store import TraceStore
from agent_data_workbench.evaluation.tasks.repository import load_task, task_digest
from agent_data_workbench.shared.files import save
from agent_data_workbench.shared.identifiers import canonical_uuid, new_id
from agent_data_workbench.shared.json import digest
from agent_data_workbench.shared.time import now
from agent_data_workbench.workspace.project import Project


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
    from agent_data_workbench.research.artifacts import investigation_directory
    from agent_data_workbench.research.dataset import Dataset

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
