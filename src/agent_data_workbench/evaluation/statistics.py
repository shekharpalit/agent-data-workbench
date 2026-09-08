"""Paired experiment summaries and source-group uncertainty estimates."""

from __future__ import annotations

import math
import random
from collections import defaultdict


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
