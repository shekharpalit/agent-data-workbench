---
type: workflow
title: Import and explore traces
description: Bring JSON or JSONL execution data into the SQLAlchemy-backed local store, then search, sample, aggregate, cluster, and follow recorded lineage.
tags: [traces, ingestion, search, clustering, lineage]
sources:
  - id: openwiki-source-2ee7fba2bd1c703c70f5f285
    resource: repo://src/agent_data_workbench/cli/project.py
  - id: openwiki-source-6e38bbd0a3d0f2e36a07885b
    resource: repo://src/agent_data_workbench/data/discovery.py
  - id: openwiki-source-a69866c703779e64969315b7
    resource: repo://src/agent_data_workbench/data/ingestion.py
  - id: openwiki-source-18ff944792b5b76d0bbb4838
    resource: repo://src/agent_data_workbench/data/normalization.py
  - id: openwiki-source-e52796c0be238f497f99e70a
    resource: repo://src/agent_data_workbench/data/sources.py
  - id: openwiki-source-ece138f4d793e07725c336eb
    resource: repo://src/agent_data_workbench/data/store.py
  - id: openwiki-source-8968831b9a7a2b5fdc98a34e
    resource: repo://src/agent_data_workbench/exploration/clustering/components.py
  - id: openwiki-source-a67878f355761044f6d5fd04
    resource: repo://src/agent_data_workbench/exploration/clustering/service.py
  - id: openwiki-source-576495909f5ee2bf8d15af81
    resource: repo://src/agent_data_workbench/exploration/clustering/tokenization.py
  - id: openwiki-source-bfac175c50d42008ed9d78c8
    resource: repo://src/agent_data_workbench/exploration/clustering/vectors.py
  - id: openwiki-source-1f1b2017c3c167f22bb29f26
    resource: repo://src/agent_data_workbench/exploration/distributions.py
  - id: openwiki-source-eab73f261f2dfa06a5a90e74
    resource: repo://src/agent_data_workbench/exploration/lineage.py
  - id: openwiki-source-8b95b7fe4c43d79511f093d7
    resource: repo://src/agent_data_workbench/exploration/schemas.py
  - id: openwiki-source-8344cc929cc5589dc5383bd2
    resource: repo://src/agent_data_workbench/exploration/search.py
  - id: openwiki-source-b9263f82c99973ba337bc796
    resource: repo://src/agent_data_workbench/shared/identifiers.py
  - id: openwiki-source-66a8a10b0365fc2079585762
    resource: repo://tests/test_explore.py
  - id: openwiki-source-7e7b3478097a461915e85751
    resource: repo://tests/test_ingestion_research.py
  - id: openwiki-source-86285276086db085f9b5f586
    resource: repo://ui/src/components/graphs/cluster-layout.ts
  - id: openwiki-source-74100799ff8e26159a68e317
    resource: repo://ui/src/components/graphs/ClusterGraph.tsx
  - id: openwiki-source-da534aa7260001f2de3cd1d5
    resource: repo://ui/src/components/graphs/NetworkCanvas.tsx
  - id: openwiki-source-13a35988ca651da931d9ecce
    resource: repo://ui/src/views/Clusters.tsx
generated: { by: "codex", at: "2026-09-08T02:26:18.735Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-08T02:26:18.735Z
---

# Import and explore traces

The default ingestion unit is an agent run file. A JSONL file holds that run's ordered events; several files become several traces in the same project. One investigation can inspect and compare the full collection. Ingestion and local exploration require no model call.

The `data/` package separates file discovery (`discovery.py`), run decoding (`ingestion.py`), record normalization (`normalization.py`), source contracts (`sources.py`), archive transport (`transport.py`) and SQLAlchemy storage (`store.py`, `database.py`). Search and visual exploration live separately in `exploration/`.

## Import multiple run files

Create a project, then choose a directory, explicit files, or a quoted glob:

```sh
uv run agent-data-workbench init runs/my-agent "My agent" "Improve reliable task completion"
uv run agent-data-workbench ingest runs/my-agent ./traces
uv run agent-data-workbench ingest runs/my-agent ./run-a.jsonl ./run-b.jsonl
uv run agent-data-workbench ingest runs/my-agent './traces/**/*.jsonl'
```

The three ingest forms are alternative selections. Directories recurse through JSON, JSONL and NDJSON files. Discovery orders files deterministically, deduplicates overlapping selections and physical aliases, and rejects unmatched selections. In Docker, use `make ingest DIR=./traces`; [container operation](../operations/containers.md) explains file selection and temporary archive transport.

For example, one run file can contain:

```jsonl
{"session_id":"run-001","type":"user","message":"Refund my order"}
{"session_id":"run-001","type":"tool","status":"declined"}
{"session_id":"run-001","type":"assistant","message":"Your refund was processed"}
```

The stored trace has ID `run-001` and data shaped as:

```json
{
  "events": [
    {"session_id":"run-001","type":"user","message":"Refund my order"},
    {"session_id":"run-001","type":"tool","status":"declined"},
    {"session_id":"run-001","type":"assistant","message":"Your refund was processed"}
  ],
  "source": {"path":"run-001.jsonl"}
}
```

Events retain their original objects, order and JSON types. Repeated event IDs remain inside the run. Evidence cites `/events/1/status` for the tool status, and `/source/path` identifies the logical file. The wrapper does not rename or flatten provider event fields. A JSON array becomes the run's event list; a JSON object is preserved as one event, including any nested messages or events it already contains. Empty runs and nonobject events are rejected with the source filename and location when available.

A consistent nonempty string `trace_id` across the events supplies the run ID; otherwise a consistent `session_id` does. Missing fields do not conflict with a value elsewhere in the file. If neither field is unambiguous, a deterministic UUIDv5 is generated from the logical file path and event content. An event's generic `id` is not treated as the whole run's identity. Consistent scalar `thread_id` and `agent_type` values are copied to the envelope for the default grouping and stratum pointers.

## Keep source roots stable

A directory selection uses that directory as its logical root. A single file uses its parent; a quoted glob uses its directory prefix before the first wildcard. Multiple inputs use the common ancestor of those roots. Names below the root become `source.path`, independent of the current working directory and temporary Docker extraction location.

For incremental selections from one larger collection, keep an explicit root:

```sh
uv run agent-data-workbench ingest runs/my-agent ./traces/nested/run-001.jsonl --source-root ./traces
uv run agent-data-workbench ingest runs/my-agent ./traces --source-root ./traces
```

The Make equivalent is `SOURCE_ROOT=./traces`. Keep logical roots and filenames stable across reimports. A changed path changes a generated identity; if a native run ID stays the same, changed provenance is different stored content and is rejected as a conflict.

## Batch consistency and capacity

All selected files feed one SQLAlchemy transaction in `traces.sqlite3`. A malformed later file or conflicting run ID rolls back new records from every file in the batch. Reimporting the same ID and data is idempotent. Output reports selected file count, layout, added/unchanged traces and total inventory.

There is no fixed file-count, event-count or corpus cap. Run mode reads files sequentially and materializes the current run's events in memory; inventory metadata also grows with the stored run count. Very large individual runs still need corresponding RAM. Docker ingestion additionally stages a host archive and extracted container files. Large-corpus throughput is not established by the synthetic tests. Prepare exports before ingestion when fields need redaction.

## Import existing record-per-line exports

Use the explicit records layout when each line already represents a complete trace:

```sh
uv run agent-data-workbench ingest runs/my-agent ./exports --layout records
make ingest DIR=./exports LAYOUT=records
```

In this layout, JSONL/NDJSON streams one nonempty object per trace. Ordinary JSON supports a single object, an array, or a `traces` array and is loaded into memory. Each original object becomes `Trace.data`; normalization preserves supplied `trace_id` or `id` and otherwise generates a UUIDv5 from canonical JSON. A source field such as `/tool/status` retains that pointer. The existing `JsonSource` SDK remains a record-export adapter. Existing stored rows are not rewritten when the CLI default changes.

## Preserve group and stratum meaning

By default, `/thread_id` supplies the source group and `/agent_type` supplies the stratum. Override both when your exporter uses different fields:

```sh
uv run agent-data-workbench ingest runs/my-agent ./traces.jsonl --layout records \
  --group-pointer /session/id --stratum-pointer /agent/name
```

Labels must be strings or integers. Missing or unsuitable group values fall back to the trace ID; strata fall back to `unclassified`. Groups later keep related tasks together in [experiment splits](experiments-and-training.md). Choose a group that captures the real dependence between records before importing them. Reimporting unchanged content does not relabel existing rows.

## Use the SDK for custom sources

Use `FilesSource` for multiple run files through the same SDK transaction:

```python
from pathlib import Path
from agent_data_workbench import FilesSource, Project, TraceStore

project = Project(Path("runs/my-agent"))
result = TraceStore(project).ingest(FilesSource(["./traces"], layout="runs"))
```

Pass `root=Path("./traces")` for a stable logical root across partial selections, or `layout="records"` for row exports. `SourceFile` carries a physical input and explicit logical path for transport adapters. The source boundary remains `TraceSource.read() -> Iterable[Trace]`. A custom exporter adapter can yield normalized records directly:

```python
from pathlib import Path
from agent_data_workbench.data.contracts import Trace
from agent_data_workbench.workspace.project import Project
from agent_data_workbench.data.store import TraceStore

class MySource:
    def read(self):
        yield Trace(
            trace_id="run-001",
            data={"thread_id": "conversation-001", "input": "Example request"},
        )

store = TraceStore(Project(Path("runs/my-agent")))
result = store.ingest(MySource())
```

This is an adapter seam, not automatic instrumentation of every agent framework. Connect your existing export or logging pipeline to it. The file adapters are `FilesSource` for selected runs/exports and `JsonSource` for a single record export.

## Search, sample, and measure

```sh
uv run agent-data-workbench query runs/my-agent --text declined --limit 20
uv run agent-data-workbench query runs/my-agent --sample --seed 7 --limit 20
uv run agent-data-workbench query runs/my-agent --aggregate /events/1/status
```

CLI search uses case-insensitive substring matching and stable ID ordering. Sampling shuffles within strata using the seed, then takes turns across strata. It deliberately favors coverage across categories and should not be used as a prevalence estimate.

Aggregates describe the matched corpus, including the eligible count, missing or non-scalar values, distinct values, and numeric summaries. The displayed value counts are capped at the top 50. Read totals alongside those counts.

The [local workbench](../operations/local-workbench.md) provides typed field search and distributions. Its shared `SearchQuery` supports up to eight AND-combined JSON-pointer filters: equality, text containment, numeric bounds, existence, and missing fields. Numeric comparison rejects booleans and nonnumeric values. Sorting supports trace ID, stratum, or a field pointer, keeping missing values last and using trace IDs to break ties.

Search pages and distribution charts use the same matching-corpus function. Pagination changes the displayed records, not the population summarized by the distribution. These scans are local operations; a bounded result page does not imply indexed query performance on an arbitrarily large corpus.

## Explore lexical clusters

Clustering uses TF-IDF cosine similarity and connected components over complete selected values. Opening Clusters automatically groups all matching traces. The default JSON pointer is empty, selecting the whole record, so event envelopes work without an `/input` field. Choose `/events` or another existing pointer to narrow the compared content. Selection follows stable trace-ID order and ignores the search page's sort, offset and page size while preserving its filters and membership selection.

The tokenizer visits every scalar value below the selected pointer, including strings under ID or timestamp field names. It retains Unicode word tokens, contractions, identifiers, numeric tokens, negation such as “not,” and single-character words. There is no handpicked English stop-word list. TF-IDF determines term weights from the selected documents; these tokens still do not encode language understanding.

There is no text-prefix cutoff or default trace-count ceiling. Tokens are streamed through a counter across all nested selected values, preserving late events in long runs. An explicit `limit` of at least two selects the first matching IDs; omit it or use null to include every match. The UI's Maximum traces field is blank by default. Results report eligible, inspected and clustered counts, missing or unusable selected values, and any corpus truncation caused by that explicit maximum. Compatibility fields `text_limit_chars` and `text_truncated_ids` return null and an empty list.

Term weights and document vectors remain in memory, and the current implementation compares every pair of documents. Very large batches therefore need more memory and computation; unlimited selection does not establish unlimited throughput. Cluster terms and labels are derived from word weights. Cluster IDs are deterministic UUIDv5 values derived from membership.

A cluster indicates lexical similarity. It does not establish a shared failure mode, causal mechanism, or semantic category. Transitive links can put two traces in the same component even when their direct similarity is below the threshold.

The Cluster map selector displays one group's members at a time. Edges connect the group to its member traces; selecting a trace opens its original evidence, and Inspect all members opens the filtered explorer. Clearing a missing text pointer recovers whole-record grouping. Membership filtering accepts groups larger than a search page. The shared React Flow canvas supplies pan, zoom and fit controls.

To change this pipeline, start with `exploration/clustering/tokenization.py` for selected-value tokens, `vectors.py` for TF-IDF normalization, `components.py` for cosine links and transitive membership, and `service.py` for selection and the response. Typed request validation lives in `exploration/schemas.py`; search, distributions and lineage have their own modules.

## Follow recorded lineage

The lineage graph starts with every imported trace, including runs with no findings or tasks. When a source path exists it labels the trace node; the original trace ID still controls navigation. The UI arranges raw trace nodes in a grid and lets developers open the original events immediately after import. Saved artifact references add trace-to-finding, trace-to-task, finding-to-task and task-to-experiment relationships. Focusing on a trace follows downstream edges; it does not add unrelated sibling tasks merely because they share an experiment. An imported but unlinked trace has a one-node focused graph.

The graph reports truncation and supports a 10–300-node limit. Task nodes link identities; experiment artifacts preserve the exact evaluated specification snapshots. Use the graph to navigate evidence, and the saved experiment to inspect what actually ran. Edges represent recorded relationships, not inferred causality. Edge IDs are deterministic UUIDv5 values; node keys include their kind and source or artifact identity so different kinds remain distinct.

Native investigations capture the full project store by default. Pass `--exclude-final` when creating an investigation to leave reserved final groups out of that snapshot. Ordinary CLI queries still use the full project store. Exposure is recorded for research; these local tools are not a hidden-data access boundary.

Search pagination and the displayed graph limit bound those views; clustering includes every match unless the developer sets its explicit maximum. They do not limit the native research corpus. `ResearchWorkspace.dataset.records()` iterates the full snapshot and native scripts can implement analyses beyond the built-in lexical clustering. Its aggregate API paginates distinct values instead of discarding all values beyond the top 50.

## Verification and next steps

`tests/test_ingestion.py`, `test_ingest_cli.py` and `test_ingest_transport.py` cover multiple selections, identity, layouts, file boundaries and rollback. `test_ingestion_research.py` verifies two ordered run files in one complete-mode research snapshot. `tests/test_workbench_data.py` covers transactional ingestion, balanced sampling, and excluded groups. `tests/test_explore.py` covers combined filters, stable sorting, corpus-consistent distributions, late-event tokenization, 201 event traces beyond search-page bounds, explicit cluster limits, imported trace visibility and focused lineage. `tests/test_api.py` verifies default event-trace clustering and graph visibility without analysis; `ui/tests/exploration.test.tsx` covers automatic grouping, missing-field recovery, graph membership and trace navigation.

Next: [investigate the evidence](investigations.md) or [open the local workbench](../operations/local-workbench.md).
