"""Human-readable dataset structure computed from explicit source metadata.

No outcome inference from error-looking text. Missing labels stay unknown and
source-group membership is an exact imported relationship, not similarity.
"""

from collections import Counter

from agent_data_workbench.data.store import TraceStore
from agent_data_workbench.exploration.schemas import SearchQuery
from agent_data_workbench.exploration.search import matching_rows
from agent_data_workbench.shared.json import pointer_value


def trace_label(data: dict, fallback: str) -> str:
    for pointer in ("/instance_id", "/title", "/task/title", "/source/path", "/task_id"):
        try:
            value = pointer_value(data, pointer)
        except ValueError:
            continue
        if isinstance(value, str) and value.strip():
            return value
    return fallback


def dataset_profile(
    store: TraceStore, query: SearchQuery, outcome_pointer: str = "/resolved"
) -> dict:
    groups, outcomes = {}, Counter()
    eligible = 0
    for row in matching_rows(store, query):
        eligible += 1
        try:
            value = pointer_value(row["data"], outcome_pointer)
        except ValueError:
            value = None
        # Only a documented binary label yields pass/fail; categorical fields stay literal.
        label = (
            ("Passed" if value else "Failed")
            if type(value) in (bool, int, float) and value in (0, 1)
            else "Unknown"
        )
        outcomes[label] += 1
        group = groups.setdefault(
            row["group_id"],
            {
                "id": row["group_id"],
                "label": trace_label(row["data"], row["group_id"]),
                "strata": set(),
                "trace_ids": [],
                "outcomes": Counter(),
            },
        )
        group["strata"].add(row["stratum"])
        group["trace_ids"].append(row["trace_id"])
        group["outcomes"][label] += 1
    result = []
    for group in groups.values():
        group["strata"] = sorted(group["strata"])
        group["count"] = len(group["trace_ids"])
        group["outcomes"] = {
            label: group["outcomes"][label] for label in ("Passed", "Failed", "Unknown")
        }
        result.append(group)
    result.sort(key=lambda group: (-group["count"], group["label"], group["id"]))
    return {
        "eligible": eligible,
        "group_count": len(groups),
        "groups": result,
        "outcome_pointer": outcome_pointer,
        "outcomes": [
            {"value": label, "count": outcomes[label]} for label in ("Passed", "Failed", "Unknown")
        ],
        "scope": "All matching traces. Groups use the source-group field selected at import. "
        "Outcomes use only the selected binary source label (true/1 or false/0); "
        "missing and other values are unknown. Source labels are not independently verified. "
        "Counts describe this local import, not the entire upstream dataset.",
    }
