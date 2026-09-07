"""Typed local search, bounded lexical clustering, and evidence lineage graphs."""

from __future__ import annotations

import hashlib
import heapq
import json
import math
import re
from collections import Counter, defaultdict
from functools import cmp_to_key
from typing import Literal

from pydantic import Field, model_validator

from .evaluation import json_equal
from .identifiers import stable_id
from .models import Contract, _reject_constant, json_text, pointer_parts, pointer_value
from .project import Project, digest
from .store import TraceStore


class FieldFilter(Contract):
    pointer: str = Field(max_length=300)
    operator: Literal["equals", "contains", "gte", "lte", "exists", "missing"] = "equals"
    value_json: str = Field(default="null", max_length=2000)

    @model_validator(mode="after")
    def valid(self):
        pointer_parts(self.pointer)
        value = json.loads(self.value_json, parse_constant=_reject_constant)
        json_text(value)  # Reject numeric overflow, including nested nonfinite values.
        if self.operator in {"gte", "lte"} and type(value) not in {int, float}:
            raise ValueError("Numeric comparisons require a JSON number")
        if self.operator == "contains" and not isinstance(value, str):
            raise ValueError("Contains requires a JSON string")
        return self


class SearchQuery(Contract):
    text: str = Field(default="", max_length=1000)
    stratum: str = Field(default="", max_length=200)
    filters: list[FieldFilter] = Field(default_factory=list, max_length=8)
    sort: str = Field(default="trace_id", max_length=300)
    direction: Literal["asc", "desc"] = "asc"
    limit: int = Field(default=20, ge=1, le=200)
    offset: int = Field(default=0, ge=0, le=10000)
    trace_ids: list[str] | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def valid(self):
        if self.sort not in {"trace_id", "stratum"}:
            pointer_parts(self.sort)
        return self


class ClusterQuery(Contract):
    query: SearchQuery = Field(default_factory=SearchQuery)
    pointer: str = Field(default="/input", max_length=300)
    threshold: float = Field(default=0.55, ge=0.1, le=1, allow_inf_nan=False)
    limit: int = Field(default=100, ge=2, le=200)

    @model_validator(mode="after")
    def valid(self):
        pointer_parts(self.pointer)
        return self


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


STOP_WORDS = set(
    "the and that with this from have been were your for are you was not but "
    "into about only then when will can has had our its".split()
)


CLUSTER_TEXT_LIMIT = 20_000


def text_values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from text_values(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key not in {"trace_id", "id", "thread_id", "timestamp", "created_at"}:
                yield from text_values(item)


def words(value) -> tuple[list[str], bool]:
    remaining, tokens = CLUSTER_TEXT_LIMIT, []
    for text in text_values(value):
        clipped = text[:remaining]
        tokens.extend(
            w
            for w in re.findall(r"[^\W_]{2,}", clipped.casefold())
            if w not in STOP_WORDS and not w.isdigit()
        )
        if len(text) > remaining:
            return tokens, True
        remaining -= len(text)
    return tokens, False


def cluster(store: TraceStore, request: ClusterQuery) -> dict:
    query = request.query.model_copy(
        update={"limit": request.limit, "offset": 0, "sort": "trace_id", "direction": "asc"}
    )
    page = search(store, query)
    documents, omitted, text_truncated = [], [], []
    for row in page["records"]:
        try:
            tokens, clipped = words(pointer_value(row["data"], request.pointer))
        except ValueError:
            tokens, clipped = [], False
        if clipped:
            text_truncated.append(row["trace_id"])
        if tokens:
            documents.append((row["trace_id"], Counter(tokens)))
        else:
            omitted.append(row["trace_id"])
    frequency = Counter(term for _, counts in documents for term in counts)
    vectors = []
    for _, counts in documents:
        vector = {
            term: (1 + math.log(count))
            * (1 + math.log((len(documents) + 1) / (frequency[term] + 1)))
            for term, count in counts.items()
        }
        norm = math.sqrt(sum(v * v for v in vector.values()))
        vectors.append({term: weight / norm for term, weight in vector.items()})
    parent = list(range(len(documents)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, left in enumerate(vectors):
        for j in range(i + 1, len(vectors)):
            similarity = sum(weight * vectors[j].get(term, 0) for term, weight in left.items())
            if similarity + 1e-12 >= request.threshold:
                parent[find(j)] = find(i)
    groups = defaultdict(list)
    for i in range(len(documents)):
        groups[find(i)].append(i)
    clusters = []
    for indexes in groups.values():
        terms = Counter()
        ids = [documents[i][0] for i in indexes]
        for i in indexes:
            terms.update(vectors[i])
        top = sorted(terms, key=lambda term: (-terms[term], term))[:5]
        clusters.append(
            {
                "id": stable_id("cluster", json_text(ids)),
                "trace_ids": ids,
                "count": len(ids),
                "terms": top,
                "label": " · ".join(top[:3]),
            }
        )
    clusters.sort(key=lambda c: (-c["count"], c["trace_ids"]))
    return {
        "method": "TF-IDF cosine connected components",
        "pointer": request.pointer,
        "threshold": request.threshold,
        "eligible": page["eligible"],
        "sampled": page["selected"],
        "clustered": len(documents),
        "omitted_ids": omitted,
        "text_limit_chars": CLUSTER_TEXT_LIMIT,
        "text_truncated_ids": text_truncated,
        "truncated": page["eligible"] > page["selected"],
        "source_sha256": page["source_sha256"],
        "clusters": clusters,
        "scope": "Lexical similarity on a bounded ID-ordered selection. Transitive links may "
        "join traces below the pairwise threshold. These are not semantic labels.",
    }


def lineage(project: Project, *, trace_id: str = "", limit: int = 200) -> dict:
    if not 10 <= limit <= 300:
        raise ValueError("Graph limit must be 10–300 nodes")
    nodes, edges = {}, set()

    def node(kind, key, label, **metadata):
        identity = kind + ":" + key
        nodes[identity] = {"id": identity, "kind": kind, "label": label, **metadata}
        return identity

    def trace(key):
        return node("trace", key, key, trace_id=key)

    for value in project.artifacts("investigations"):
        if value.get("result") is None:
            continue
        for finding in value["result"]["analysis"]["findings"]:
            fid = node(
                "finding",
                value["id"] + ":" + finding["id"],
                finding["title"],
                artifact_id=value["id"],
                finding_id=finding["id"],
            )
            for evidence in finding["evidence"]:
                edges.add((trace(evidence["trace_id"]), fid, "supports"))
    for value in project.artifacts("tasks"):
        task = value["spec"]
        tid = node(
            "task",
            value["id"],
            task["title"],
            artifact_id=value["id"],
            status=value["review"]["status"],
        )
        for key in task["trace_ids"]:
            edges.add((trace(key), tid, "derived from"))
        for key in task["finding_ids"]:
            fid = "finding:" + value["origin"] + ":" + key
            if fid in nodes:
                edges.add((fid, tid, "tests"))
    for value in project.artifacts("experiments"):
        eid = node(
            "experiment",
            value["id"],
            value["conclusion"],
            artifact_id=value["id"],
            status=value["status"],
        )
        for task in value["task_snapshots"]:
            tid = "task:" + task["id"]
            if tid not in nodes:
                tid = node(
                    "task", task["id"], task["title"], artifact_id=task["id"], status="historical"
                )
            edges.add((tid, eid, "evaluated in"))
    if trace_id:
        # Follow evidence downstream only: never pull unrelated siblings through an experiment.
        root = "trace:" + trace_id
        allowed = {root} if root in nodes else set()
        while True:
            connected = allowed | {b for a, b, _ in edges if a in allowed}
            if connected == allowed:
                break
            allowed = connected
        nodes = {key: value for key, value in nodes.items() if key in allowed}
    total = len(nodes)
    kinds = {"trace": 0, "finding": 1, "task": 2, "experiment": 3}
    ordered = sorted(nodes.values(), key=lambda n: (kinds[n["kind"]], n["id"]))
    # Include all layers before adding more nodes to each layer when the graph is large.
    buckets = [[n for n in ordered if n["kind"] == kind] for kind in kinds]
    selected = []
    while any(buckets) and len(selected) < limit:
        for bucket in buckets:
            if bucket and len(selected) < limit:
                selected.append(bucket.pop(0))
    keys = {n["id"] for n in selected}
    return {
        "nodes": selected,
        "edges": [
            {
                "id": stable_id("edge", json_text([a, b, label])),
                "source": a,
                "target": b,
                "label": label,
            }
            for a, b, label in sorted(edges)
            if a in keys and b in keys
        ],
        "total_nodes": total,
        "shown_nodes": len(selected),
        "truncated": total > len(selected),
        "trace_id": trace_id,
        "scope": "Recorded evidence lineage, not inferred causality. Task nodes link identities; "
        "experiment artifacts retain the exact evaluated specification snapshots.",
    }
