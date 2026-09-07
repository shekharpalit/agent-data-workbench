---
type: workflow
title: Import and explore traces
description: Bring JSON or JSONL execution data into the SQLAlchemy-backed local store, then search, sample, aggregate, cluster, and follow recorded lineage.
tags: [traces, ingestion, search, clustering, lineage]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T17:18:36.762Z
sources:
  - id: openwiki-source-457345d957e5f357847df6bd
    resource: repo://src/agent_data_workbench/commands.py
  - id: openwiki-source-5673900c5660ce9e89d18d23
    resource: repo://src/agent_data_workbench/explore.py
  - id: openwiki-source-069858a5e395202064ced424
    resource: repo://src/agent_data_workbench/store.py
  - id: openwiki-source-b9538130baf947854165db93
    resource: repo://src/agent_data_workbench/traces.py
  - id: openwiki-source-66a8a10b0365fc2079585762
    resource: repo://tests/test_explore.py
  - id: openwiki-source-9dba1709c16fd704c45276e9
    resource: repo://tests/test_workbench_data.py
generated: { by: "codex", at: "2026-09-07T17:18:36.762Z" }
---

# Import and explore traces

The workbench accepts exported execution records as JSON objects. It preserves each record's structure so evidence can point to the original fields. Ingestion, search, aggregation, clustering, and lineage do not require a model call.

## Create a project and import records

Choose a new or empty directory:

```sh
uv run agent-data-workbench init runs/my-agent "My agent" \
  "Improve reliable task completion" --criterion "Preserve actual tool outcomes"
uv run agent-data-workbench ingest runs/my-agent ./traces.jsonl
```

A JSONL file contains one nonempty object per line. For example:

```json
{"trace_id":"run-001","thread_id":"conversation-001","agent_type":"support","input":"Complete the request","tool":{"status":"declined"},"output":{"status":"completed"},"latency_ms":420}
```

JSON files may hold a single record, an array, or an object with a `traces` array. JSONL and NDJSON ingestion streams records with a two-million-character line limit; ordinary JSON loading has a 50 MiB file limit. Invalid data rolls back the ingest transaction.

Normalization uses `trace_id`, falling back to `id`, or generates a content-derived ID when neither is supplied. The original object becomes `Trace.data`. Thus the sample's tool status is at `/tool/status`, not `/data/tool/status`. Supply stable IDs to make later evidence easier to inspect.

The SQLAlchemy store uses `traces.sqlite3` inside the project. Importing the same ID and content again is idempotent. A conflicting body for an existing ID rejects the batch, including new records earlier in that transaction. Trace data is not automatically redacted; prepare the export before ingestion when fields must be removed.

## Preserve group and stratum meaning

By default, `/thread_id` supplies the source group and `/agent_type` supplies the stratum. Override both when your exporter uses different fields:

```sh
uv run agent-data-workbench ingest runs/my-agent ./traces.jsonl \
  --group-pointer /session/id --stratum-pointer /agent/name
```

Labels must be strings or integers. Missing or unsuitable group values fall back to the trace ID; strata fall back to `unclassified`. Groups later keep related tasks together in [experiment splits](experiments-and-training.md). Choose a group that captures the real dependence between records before importing them. Reimporting unchanged content does not relabel existing rows.

## Use the SDK for custom sources

The source boundary is `TraceSource.read() -> Iterable[Trace]`. A custom exporter adapter can yield normalized records directly:

```python
from pathlib import Path
from agent_data_workbench.models import Trace
from agent_data_workbench.project import Project
from agent_data_workbench.store import TraceStore

class MySource:
    def read(self):
        yield Trace(
            trace_id="run-001",
            data={"thread_id": "conversation-001", "input": "Example request"},
        )

store = TraceStore(Project(Path("runs/my-agent")))
result = store.ingest(MySource())
```

This is an adapter seam, not automatic instrumentation of every agent framework. Connect your existing export or logging pipeline to it. The shipped file adapter is `JsonSource`.

## Search, sample, and measure

```sh
uv run agent-data-workbench query runs/my-agent --text declined --limit 20
uv run agent-data-workbench query runs/my-agent --sample --seed 7 --limit 20
uv run agent-data-workbench query runs/my-agent --aggregate /tool/status
```

CLI search uses case-insensitive substring matching and stable ID ordering. Sampling shuffles within strata using the seed, then takes turns across strata. It deliberately favors coverage across categories and should not be used as a prevalence estimate.

Aggregates describe the matched corpus, including the eligible count, missing or non-scalar values, distinct values, and numeric summaries. The displayed value counts are capped at the top 50. Read totals alongside those counts.

The [local workbench](../operations/local-workbench.md) provides typed field search and distributions. Its shared `SearchQuery` supports up to eight AND-combined JSON-pointer filters: equality, text containment, numeric bounds, existence, and missing fields. Numeric comparison rejects booleans and nonnumeric values. Sorting supports trace ID, stratum, or a field pointer, keeping missing values last and using trace IDs to break ties.

Search pages and distribution charts use the same matching-corpus function. Pagination changes the displayed records, not the population summarized by the distribution. These scans are local operations; a bounded result page does not imply indexed query performance on an arbitrarily large corpus.

## Explore lexical clusters

Clustering uses TF-IDF cosine similarity and connected components over a chosen text field. It examines up to 200 matching traces in ID order, independently of the search page's current sort or offset. The default field is `/input`.

A shared 20,000-character text budget applies per selected field value, including nested strings. Results identify omitted records, text truncation, and corpus truncation. Cluster terms and labels are derived from word weights.

A cluster indicates lexical similarity. It does not establish a shared failure mode, causal mechanism, or semantic category. Transitive links can put two traces in the same component even when their direct similarity is below the threshold.

## Follow recorded lineage

The lineage graph connects trace evidence to findings, tasks, and experiments using saved artifact references. Focusing on a trace follows downstream edges; it does not add unrelated sibling tasks merely because they share an experiment.

The graph reports truncation and supports a 10–300-node limit. Task nodes link identities; experiment artifacts preserve the exact evaluated specification snapshots. Use the graph to navigate evidence, and the saved experiment to inspect what actually ran. Edges represent recorded relationships, not inferred causality.

Final-set exclusions depend on the caller: model-directed investigations use a store excluding reserved final groups, while the ordinary CLI query uses the full project store. A local exploration tool is not a hidden-data access boundary.

## Verification and next steps

`tests/test_workbench_data.py` covers transactional ingestion, balanced sampling, and excluded groups. `tests/test_explore.py` covers combined filters, stable sorting, corpus-consistent distributions, explicit cluster bounds, and focused lineage.

Next: [investigate the evidence](investigations.md) or [open the local workbench](../operations/local-workbench.md).
