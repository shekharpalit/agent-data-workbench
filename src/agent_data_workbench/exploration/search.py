"""Typed trace filtering and deterministic pagination over one matching corpus."""

from __future__ import annotations

import hashlib
import heapq
import json
from collections import Counter
from functools import cmp_to_key

from agent_data_workbench.data.store import TraceStore
from agent_data_workbench.exploration.schemas import FieldFilter, SearchQuery
from agent_data_workbench.shared.json import (
    _reject_constant,
    digest,
    json_equal,
    json_text,
    pointer_value,
)


def matches(data: dict, filters: list[FieldFilter]) -> bool:
    for clause in filters:
        try:
            value = pointer_value(data, clause.pointer)
        except ValueError:
            if clause.operator == "missing":
                continue
            return False
        expected = json.loads(clause.value_json, parse_constant=_reject_constant)
        if clause.operator == "missing":
            return False
        if clause.operator == "equals" and not json_equal(value, expected):
            return False
        if clause.operator == "contains" and (
            not isinstance(value, str) or expected.casefold() not in value.casefold()
        ):
            return False
        if clause.operator in {"gte", "lte"}:
            if type(value) not in {int, float}:
                return False
            if clause.operator == "gte" and value < expected:
                return False
            if clause.operator == "lte" and value > expected:
                return False
    return True


def matching_rows(store: TraceStore, query: SearchQuery):
    requested_ids = set(query.trace_ids) if query.trace_ids is not None else None
    for row in store.iter_rows(stratum=query.stratum):
        if requested_ids is not None and row["id"] not in requested_ids:
            continue
        if query.text.casefold() not in row["data"].casefold():
            continue
        data = json.loads(row["data"])
        if matches(data, query.filters):
            yield {
                "trace_id": row["id"],
                "data": data,
                "stratum": row["stratum"],
                "group_id": row["group_id"],
            }


def search(store: TraceStore, query: SearchQuery) -> dict:
    """Scan filters once and retain only the requested sorted page in the selection heap."""
    eligible, strata = 0, Counter()
    source_hash = hashlib.sha256()

    def rows():
        nonlocal eligible
        for row in matching_rows(store, query):
            eligible += 1
            strata[row["stratum"]] += 1
            source_hash.update(json_text([row["trace_id"], digest(row["data"])]).encode())
            yield row

    def sort_value(record):
        if query.sort == "trace_id":
            return (1, record["trace_id"])
        if query.sort == "stratum":
            return (1, record["stratum"])
        try:
            value = pointer_value(record["data"], query.sort)
        except ValueError:
            return None
        if value is None:
            return None
        return (0, value) if type(value) in {int, float} else (1, json_text(value))

    def compare(a, b):
        left, right = sort_value(a), sort_value(b)
        if left is None or right is None:
            order = (left is None) - (right is None)
        else:
            order = (left > right) - (left < right)
            order *= 1 if query.direction == "asc" else -1
        return order or ((a["trace_id"] > b["trace_id"]) - (a["trace_id"] < b["trace_id"]))

    selected = heapq.nsmallest(query.offset + query.limit, rows(), key=cmp_to_key(compare))
    selected = selected[query.offset :]
    return {
        "query": query.model_dump(),
        "eligible": eligible,
        "selected": len(selected),
        "ids": [r["trace_id"] for r in selected],
        "records": selected,
        "strata": dict(sorted(strata.items())),
        "source_sha256": source_hash.hexdigest(),
    }
