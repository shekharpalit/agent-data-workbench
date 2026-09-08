"""Build graphs from recorded trace, finding, task and experiment references."""

from agent_data_workbench.shared.identifiers import stable_id
from agent_data_workbench.shared.json import json_text
from agent_data_workbench.workspace.project import Project


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
