import json

import pytest
from test_workbench_data import Source, make_project

from agent_data_workbench.explore import (
    CLUSTER_TEXT_LIMIT,
    ClusterQuery,
    FieldFilter,
    SearchQuery,
    cluster,
    distribution,
    lineage,
    search,
)
from agent_data_workbench.project import save
from agent_data_workbench.store import TraceStore


@pytest.fixture
def project(tmp_path):
    return make_project(tmp_path)


def test_combined_filters_sort_and_pagination_use_the_same_matching_corpus(project):
    # Given
    store = TraceStore(project)
    query = SearchQuery(
        text="ACTUAL",
        stratum="common",
        filters=[
            FieldFilter(pointer="/value", operator="gte", value_json="2"),
            FieldFilter(pointer="/value", operator="lte", value_json="6"),
        ],
        sort="/value",
        direction="desc",
        offset=1,
        limit=2,
    )

    # When
    page = search(store, query)
    aggregate = distribution(store, query, "/value")

    # Then
    assert {
        "ids": page["ids"],
        "eligible": page["eligible"],
        "selected": page["selected"],
        "values": [row["data"]["value"] for row in page["records"]],
        "strata": page["strata"],
        "aggregate": aggregate,
    } == {
        "ids": ["r5", "r4"],
        "eligible": 5,
        "selected": 2,
        "values": [5, 4],
        "strata": {"common": 5},
        "aggregate": {
            "pointer": "/value",
            "eligible": 5,
            "missing_or_non_scalar": 0,
            "counts": [{"value": n, "count": 1} for n in [2, 3, 4, 5, 6]],
            "distinct": 5,
            "numeric_count": 5,
            "mean": 4,
            "minimum": 2,
            "maximum": 6,
        },
    }


def test_missing_fields_types_and_cluster_membership_are_explicit(project):
    # Given
    store = TraceStore(project)
    queries = {
        "boolean": SearchQuery(filters=[FieldFilter(pointer="/value", value_json="true")]),
        "membership": SearchQuery(trace_ids=["r1", "r3"]),
        "empty_membership": SearchQuery(trace_ids=[]),
        "missing": SearchQuery(filters=[FieldFilter(pointer="/absent", operator="missing")]),
        "exists": SearchQuery(filters=[FieldFilter(pointer="/absent", operator="exists")]),
    }

    # When
    actual = {name: search(store, query)["ids"] for name, query in queries.items()}

    # Then
    assert actual == {
        "boolean": [],
        "membership": ["r1", "r3"],
        "empty_membership": [],
        "missing": [f"r{i}" for i in range(9)],
        "exists": [],
    }


@pytest.mark.parametrize(
    "direction,expected",
    [
        ("asc", ["r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8", "missing"]),
        ("desc", ["r8", "r7", "r6", "r5", "r4", "r3", "r2", "r1", "r0", "missing"]),
    ],
)
def test_sort_keeps_missing_values_last(project, direction, expected):
    # Given
    store = TraceStore(project)
    store.ingest(Source([{"trace_id": "missing"}]))

    # When
    actual = search(store, SearchQuery(sort="/value", direction=direction))

    # Then
    assert {"ids": actual["ids"], "eligible": actual["eligible"]} == {
        "ids": expected,
        "eligible": 10,
    }


def test_lexical_clustering_separates_topics_and_reports_unusable_text(project):
    # Given
    store = TraceStore(project)
    store.ingest(
        Source(
            [
                {"trace_id": "refund1", "input": "refund declined payment"},
                {"trace_id": "refund2", "input": "payment refund declined"},
                {"trace_id": "search1", "input": "search citations sources"},
                {"trace_id": "search2", "input": "sources citations search"},
                {"trace_id": "empty", "input": ""},
            ]
        )
    )
    request = ClusterQuery(
        query=SearchQuery(trace_ids=["refund1", "refund2", "search1", "search2", "empty"]),
        pointer="/input",
        threshold=0.8,
    )

    # When
    result = cluster(store, request)

    # Then
    assert {
        "groups": [{"ids": c["trace_ids"], "count": c["count"]} for c in result["clusters"]],
        "eligible": result["eligible"],
        "sampled": result["sampled"],
        "clustered": result["clustered"],
        "omitted": result["omitted_ids"],
        "truncated": result["truncated"],
    } == {
        "groups": [
            {"ids": ["refund1", "refund2"], "count": 2},
            {"ids": ["search1", "search2"], "count": 2},
        ],
        "eligible": 5,
        "sampled": 5,
        "clustered": 4,
        "omitted": ["empty"],
        "truncated": False,
    }
    assert cluster(store, request) == result


def test_clustering_bounds_are_visible_and_excluded_groups_stay_excluded(project):
    # Given
    store = TraceStore(project, exclude_groups={"g0"})
    request = ClusterQuery(pointer="/text", limit=2)

    # When
    result = cluster(store, request)

    # Then
    assert {
        "eligible": result["eligible"],
        "sampled": result["sampled"],
        "truncated": result["truncated"],
        "members": [group["trace_ids"] for group in result["clusters"]],
    } == {
        "eligible": 8,
        "sampled": 2,
        "truncated": True,
        "members": [["r1", "r2"]],
    }


def test_cluster_text_budget_is_shared_across_nested_fields_and_disclosed(project):
    # Given
    store = TraceStore(project)
    store.ingest(
        Source(
            [
                {"trace_id": "large", "input": ["refund " * CLUSTER_TEXT_LIMIT, "search"]},
                {"trace_id": "small", "input": "refund"},
            ]
        )
    )
    query = ClusterQuery(query=SearchQuery(trace_ids=["large", "small"]))

    # When
    actual = cluster(store, query)

    # Then
    assert {
        "text_limit_chars": actual["text_limit_chars"],
        "text_truncated_ids": actual["text_truncated_ids"],
        "groups": [c["trace_ids"] for c in actual["clusters"]],
        "terms": actual["clusters"][0]["terms"],
    } == {
        "text_limit_chars": CLUSTER_TEXT_LIMIT,
        "text_truncated_ids": ["large"],
        "groups": [["large", "small"]],
        "terms": ["refund"],
    }


def test_graph_focus_follows_recorded_links_without_inventing_sibling_relationships(project):
    # Given
    save(
        project.path("investigations", "I1"),
        {
            "id": "I1",
            "result": {
                "analysis": {
                    "findings": [
                        {"id": "F1", "title": "Observed failure", "evidence": [{"trace_id": "r0"}]},
                    ]
                }
            },
        },
    )
    for key, trace_id in [("T1", "r0"), ("T2", "r1")]:
        save(
            project.path("tasks", key),
            {
                "id": key,
                "origin": "I1",
                "review": {"status": "draft"},
                "spec": {
                    "title": key,
                    "trace_ids": [trace_id],
                    "finding_ids": ["F1"] if key == "T1" else [],
                },
            },
        )
    save(
        project.path("experiments", "E1"),
        {
            "id": "E1",
            "conclusion": "Observed gain",
            "status": "complete",
            "task_snapshots": [{"id": "T1"}, {"id": "T2"}],
        },
    )

    # When
    graph = lineage(project, trace_id="r0")

    # Then
    assert {
        "nodes": graph["nodes"],
        "edges": [{k: e[k] for k in ["source", "target", "label"]} for e in graph["edges"]],
        "total": graph["total_nodes"],
        "shown": graph["shown_nodes"],
        "truncated": graph["truncated"],
    } == {
        "nodes": [
            {"id": "trace:r0", "kind": "trace", "label": "r0", "trace_id": "r0"},
            {
                "id": "finding:I1:F1",
                "kind": "finding",
                "label": "Observed failure",
                "artifact_id": "I1",
                "finding_id": "F1",
            },
            {
                "id": "task:T1",
                "kind": "task",
                "label": "T1",
                "artifact_id": "T1",
                "status": "draft",
            },
            {
                "id": "experiment:E1",
                "kind": "experiment",
                "label": "Observed gain",
                "artifact_id": "E1",
                "status": "complete",
            },
        ],
        "edges": [
            {"source": "finding:I1:F1", "target": "task:T1", "label": "tests"},
            {"source": "task:T1", "target": "experiment:E1", "label": "evaluated in"},
            {"source": "trace:r0", "target": "finding:I1:F1", "label": "supports"},
            {"source": "trace:r0", "target": "task:T1", "label": "derived from"},
        ],
        "total": 4,
        "shown": 4,
        "truncated": False,
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"filters": [{"pointer": "/a~2", "operator": "exists"}]},
        {"filters": [{"pointer": "/cost", "operator": "gte", "value_json": "true"}]},
        {"filters": [{"pointer": "/cost", "operator": "gte", "value_json": "1e9999"}]},
        {"offset": -1},
        {"limit": 10000},
        {"sort": "unvalidated_column"},
    ],
)
def test_invalid_queries_fail_before_storage_access(payload):
    # Given
    encoded = json.dumps(payload)

    # When / Then
    with pytest.raises(ValueError):
        SearchQuery.model_validate_json(encoded)
