"""Field counts and numeric summaries across the complete matching corpus."""

import json
from collections import Counter

from agent_data_workbench.data.store import TraceStore
from agent_data_workbench.exploration.schemas import SearchQuery
from agent_data_workbench.exploration.search import matching_rows
from agent_data_workbench.shared.json import json_text, pointer_parts, pointer_value


def distribution(store: TraceStore, query: SearchQuery, pointer: str) -> dict:
    pointer_parts(pointer)
    counts = Counter()
    total = missing = numeric = 0
    summed = 0
    minimum = maximum = None
    for row in matching_rows(store, query):
        total += 1
        try:
            value = pointer_value(row["data"], pointer)
        except ValueError:
            missing += 1
            continue
        if isinstance(value, (dict, list)):
            missing += 1
            continue
        counts[json_text(value)] += 1
        if type(value) in {int, float}:
            numeric += 1
            summed += value
            minimum = value if minimum is None else min(minimum, value)
            maximum = value if maximum is None else max(maximum, value)
    return {
        "pointer": pointer,
        "eligible": total,
        "missing_or_non_scalar": missing,
        "counts": [
            {"value": json.loads(key), "count": count}
            for key, count in sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:50]
        ],
        "distinct": len(counts),
        "numeric_count": numeric,
        "mean": summed / numeric if numeric else None,
        "minimum": minimum,
        "maximum": maximum,
    }
