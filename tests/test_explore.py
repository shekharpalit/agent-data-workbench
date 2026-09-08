import json

import pytest
from identities import uid
from test_workbench_data import Source, make_project

from agent_data_workbench.data.store import TraceStore
from agent_data_workbench.exploration import (
    ClusterQuery,
    FieldFilter,
    SearchQuery,
    cluster,
    distribution,
    lineage,
    search,
)
from agent_data_workbench.shared.files import save


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


def test_clustering_reads_late_events_in_long_nested_traces(project):
    # Given: the useful event occurs beyond the former 20,000-character cutoff.
    store = TraceStore(project)
    store.ingest(
        Source(
            [
                {
                    "trace_id": "large",
                    "events": [{"text": " " * 25_000}, {"text": "refund declined"}],
                },
                {"trace_id": "small", "events": [{"text": "refund declined"}]},
            ]
        )
    )
    query = ClusterQuery(query=SearchQuery(trace_ids=["large", "small"]), pointer="/events")

    # When
    actual = cluster(store, query)

    # Then
    assert {
        "text_limit_chars": actual["text_limit_chars"],
        "text_truncated_ids": actual["text_truncated_ids"],
        "groups": [c["trace_ids"] for c in actual["clusters"]],
        "terms": actual["clusters"][0]["terms"],
    } == {
        "text_limit_chars": None,
        "text_truncated_ids": [],
        "groups": [["large", "small"]],
        "terms": ["declined", "refund"],
    }


def test_default_clustering_includes_all_event_traces_beyond_a_search_page(project):
    # Given: event records with no /input and more than the old 200-trace ceiling.
    ids = [f"scan-{i:03}" for i in range(201)]
    store = TraceStore(project)
    store.ingest(
        Source(
            [
                {"trace_id": key, "events": [{"type": "turn.failed", "error": "schema rejected"}]}
                for key in ids
            ]
        )
    )
    query = SearchQuery(text="turn.failed", offset=20, limit=20)

    # When
    result = cluster(store, ClusterQuery(query=query))
    members = sorted(key for group in result["clusters"] for key in group["trace_ids"])
    selected = search(store, SearchQuery(trace_ids=members))

    # Then
    assert {
        "pointer": result["pointer"],
        "eligible": result["eligible"],
        "sampled": result["sampled"],
        "clustered": result["clustered"],
        "omitted": result["omitted_ids"],
        "truncated": result["truncated"],
        "members": members,
        "member_count": selected["eligible"],
        "source_sha256": result["source_sha256"],
    } == {
        "pointer": "",
        "eligible": 201,
        "sampled": 201,
        "clustered": 201,
        "omitted": [],
        "truncated": False,
        "members": ids,
        "member_count": 201,
        "source_sha256": search(store, query)["source_sha256"],
    }


def test_graph_shows_imported_traces_before_findings_exist(project):
    # Given
    TraceStore(project).ingest(
        Source(
            [
                {"trace_id": "scan", "source": {"path": "scans/run.jsonl"}, "events": []},
            ]
        )
    )

    # When
    graph = lineage(project)
    focused = lineage(project, trace_id="scan")
    missing = lineage(project, trace_id="unknown")
    scan = {"id": "trace:scan", "kind": "trace", "label": "scans/run.jsonl", "trace_id": "scan"}

    # Then
    assert {
        "nodes": graph["nodes"],
        "edges": graph["edges"],
        "total": graph["total_nodes"],
        "shown": graph["shown_nodes"],
        "focused": focused["nodes"],
        "missing": missing["nodes"],
    } == {
        "nodes": [
            {"id": f"trace:r{i}", "kind": "trace", "label": f"r{i}", "trace_id": f"r{i}"}
            for i in range(9)
        ]
        + [scan],
        "edges": [],
        "total": 10,
        "shown": 10,
        "focused": [scan],
        "missing": [],
    }


def test_graph_focus_follows_recorded_links_without_inventing_sibling_relationships(project):
    # Given
    save(
        project.path("investigations", uid("I1")),
        {
            "id": uid("I1"),
            "result": {
                "analysis": {
                    "findings": [
                        {
                            "id": uid("F1"),
                            "title": "Observed failure",
                            "evidence": [{"trace_id": "r0"}],
                        },
                    ]
                }
            },
        },
    )
    for key, trace_id in [
        (uid("T1"), "r0"),
        (uid("T2"), "r1"),
    ]:
        save(
            project.path("tasks", key),
            {
                "id": key,
                "origin": uid("I1"),
                "review": {"status": "draft"},
                "spec": {
                    "title": key,
                    "trace_ids": [trace_id],
                    "finding_ids": [uid("F1")] if key == uid("T1") else [],
                },
            },
        )
    save(
        project.path("experiments", uid("E1")),
        {
            "id": uid("E1"),
            "conclusion": "Observed gain",
            "status": "complete",
            "task_snapshots": [
                {"id": uid("T1")},
                {"id": uid("T2")},
            ],
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
                "id": f"finding:{uid('I1')}:{uid('F1')}",
                "kind": "finding",
                "label": "Observed failure",
                "artifact_id": uid("I1"),
                "finding_id": uid("F1"),
            },
            {
                "id": "task:c209c7a0-1bcf-5629-83bc-7e0b5f9b4fe1",
                "kind": "task",
                "label": uid("T1"),
                "artifact_id": uid("T1"),
                "status": "draft",
            },
            {
                "id": "experiment:1d9e2923-95e0-576e-96d4-e7ec66b00345",
                "kind": "experiment",
                "label": "Observed gain",
                "artifact_id": uid("E1"),
                "status": "complete",
            },
        ],
        "edges": [
            {
                "source": f"finding:{uid('I1')}:{uid('F1')}",
                "target": "task:c209c7a0-1bcf-5629-83bc-7e0b5f9b4fe1",
                "label": "tested by",
            },
            {
                "source": "task:c209c7a0-1bcf-5629-83bc-7e0b5f9b4fe1",
                "target": "experiment:1d9e2923-95e0-576e-96d4-e7ec66b00345",
                "label": "evaluated in",
            },
            {
                "source": "trace:r0",
                "target": f"finding:{uid('I1')}:{uid('F1')}",
                "label": "supports",
            },
            {
                "source": "trace:r0",
                "target": "task:c209c7a0-1bcf-5629-83bc-7e0b5f9b4fe1",
                "label": "informs",
            },
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


def test_clustering_keeps_negation_numbers_and_short_words_as_distinguishing_evidence(project):
    # Given
    store = TraceStore(project)
    store.ingest(
        Source(
            [
                {"trace_id": "approved", "input": "refund approved"},
                {"trace_id": "denied1", "input": "refund not approved"},
                {"trace_id": "denied2", "input": "not approved refund"},
                {"trace_id": "not_found", "input": "404"},
                {"trace_id": "server_error", "input": "500"},
                {"trace_id": "choice_a", "input": "A"},
                {"trace_id": "choice_b", "input": "B"},
            ]
        )
    )
    query = ClusterQuery(
        query=SearchQuery(
            trace_ids=[
                "approved",
                "denied1",
                "denied2",
                "not_found",
                "server_error",
                "choice_a",
                "choice_b",
            ]
        ),
        pointer="/input",
        threshold=1,
    )

    # When
    result = cluster(store, query)
    actual = {
        "memberships": [group["trace_ids"] for group in result["clusters"]],
        "eligible": result["eligible"],
        "clustered": result["clustered"],
        "omitted_ids": result["omitted_ids"],
        "text_truncated_ids": result["text_truncated_ids"],
    }

    # Then
    assert actual == {
        "memberships": [
            ["denied1", "denied2"],
            ["approved"],
            ["choice_a"],
            ["choice_b"],
            ["not_found"],
            ["server_error"],
        ],
        "eligible": 7,
        "clustered": 7,
        "omitted_ids": [],
        "text_truncated_ids": [],
    }


def test_selected_values_are_not_discarded_by_metadata_field_names():
    # Given
    from agent_data_workbench.exploration.clustering.tokenization import words

    selected = {
        "id": "not",
        "trace_id": "0",
        "thread_id": "A",
        "timestamp": "404",
        "created_at": "no",
        "nested": [{"value": "can't deny"}, 42, False, None],
    }

    # When
    tokens = list(words(selected))

    # Then
    assert {"tokens": tokens} == {
        "tokens": ["not", "0", "a", "404", "no", "can't", "deny", "42", "false", "null"],
    }


@pytest.mark.parametrize(
    "text,expected_tokens",
    [("refunded", ["refunded"]), ("can't", ["can't"]), ("can go", ["can", "go"])],
)
def test_clustering_preserves_complete_words_after_long_prefixes(text, expected_tokens):
    # Given
    from agent_data_workbench.exploration.clustering.tokenization import words

    selected = [" " * 25_000, text]

    # When
    tokens = list(words(selected))

    # Then
    assert {"tokens": tokens} == {
        "tokens": expected_tokens,
    }


def test_distributions_and_store_aggregates_return_every_category(project):
    # Given
    store = TraceStore(project)
    store.ingest(
        Source(
            [
                {"trace_id": f"category-fixture-{i:03}", "category": f"value-{i:03}"}
                for i in range(60)
            ]
        )
    )
    query = SearchQuery(text="category-fixture")

    # When
    aggregate = store.aggregate("/category", text=query.text)
    distribution_result = distribution(store, query, "/category")

    # Then
    expected = {
        "pointer": "/category",
        "eligible": 60,
        "missing_or_non_scalar": 0,
        "counts": [{"value": f"value-{i:03}", "count": 1} for i in range(60)],
        "distinct": 60,
        "numeric_count": 0,
        "mean": None,
        "minimum": None,
        "maximum": None,
    }
    assert {"distribution": distribution_result, "aggregate": aggregate} == {
        "distribution": expected,
        "aggregate": expected | {"filter": {"text": query.text, "stratum": ""}},
    }


def test_lineage_returns_all_nodes_unless_a_maximum_is_explicit(project):
    # Given
    store = TraceStore(project)
    ids = [f"r{i}" for i in range(9)] + [f"scan-{i:03}" for i in range(301)]
    store.ingest(Source([{"trace_id": key} for key in ids[9:]]))
    expected = [
        {"id": "trace:" + key, "kind": "trace", "label": key, "trace_id": key} for key in ids
    ]

    # When
    complete = lineage(project)
    explicit = lineage(project, limit=10)

    # Then
    assert {
        "nodes": complete["nodes"],
        "total": complete["total_nodes"],
        "shown": complete["shown_nodes"],
        "truncated": complete["truncated"],
        "limited_nodes": explicit["nodes"],
        "limited_total": explicit["total_nodes"],
        "limited_truncated": explicit["truncated"],
    } == {
        "nodes": expected,
        "total": 310,
        "shown": 310,
        "truncated": False,
        "limited_nodes": expected[:10],
        "limited_total": 310,
        "limited_truncated": True,
    }
