---
type: integration
title: Hugging Face datasets
description: Import complete JSON-compatible dataset rows with a pinned source revision, explicit trace mappings, durable receipts and truthful local dataset charts.
tags: [huggingface, ingestion, datasets, provenance]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-08T04:50:29.215Z
sources:
  - id: openwiki-source-640deb22c8ec2b3bdf1dc354
    resource: repo://src/agent_data_workbench/api/routers/imports.py
  - id: openwiki-source-cbe654a115c60aa5ace28238
    resource: repo://src/agent_data_workbench/data/imports.py
  - id: openwiki-source-ece138f4d793e07725c336eb
    resource: repo://src/agent_data_workbench/data/store.py
  - id: openwiki-source-498ca0018399fc2b28c0ee7e
    resource: repo://src/agent_data_workbench/exploration/dataset.py
  - id: openwiki-source-c6232bf3cd579058b0c791c2
    resource: repo://src/agent_data_workbench/integrations/huggingface.py
  - id: openwiki-source-c6d4399e4032ee953ab85f39
    resource: repo://ui/src/components/traces/Conversation.tsx
  - id: openwiki-source-88e21c7fc4b0845c0f821ec9
    resource: repo://ui/src/components/traces/presentation.ts
  - id: openwiki-source-5f365ba0fbb9be69c5df3dda
    resource: repo://ui/src/views/Dataset.tsx
  - id: openwiki-source-e4f18d5ce9c7fd05cc0d3b37
    resource: repo://ui/src/views/Imports.tsx
  - id: openwiki-source-e2b9808e897a9a7a52014721
    resource: repo://ui/src/views/Search.tsx
generated: { by: "codex", at: "2026-09-08T04:50:29.215Z" }
---

# Hugging Face datasets

The Hugging Face adapter brings an existing dataset into the same local trace store used by file imports, research and evaluation. Each dataset row becomes one trace. It preserves every JSON-compatible field and nested message; it does not use a dataset-viewer preview as the source record.

## Import through the UI

Open **Import data** and enter `organization/dataset`, configuration if required, split and revision. The **Use SWE-rebench / OpenHands preset** button fills the dataset ID `nebius/SWE-rebench-openhands-trajectories` and these mappings:

| Meaning | JSON pointer |
| --- | --- |
| Unique attempt ID | `/trajectory_id` |
| Attempts for the same issue/task | `/instance_id` |
| Repository category | `/repo` |

The preset does not start a download. For another dataset, inspect its schema and choose fields that match its actual meaning. Leave the ID field empty to generate stable IDs. Default generic grouping uses `/thread_id` and category uses `/agent_type`; missing values fall back to the trace ID and `unclassified` respectively.

**Maximum rows** is optional. Blank means the complete selected split. An entered value explicitly selects the first N rows in source order and is retained in the receipt. Every selected row remains complete; choosing a row count never shortens conversations.

Click **Inspect source & schema** to resolve the revision and display the complete schema and declared license, then **Import dataset**. Inspection pins the form to the resolved revision. Imports run as a background job and refresh inventory and history on completion. History records the number added, already present, and total local traces, with exact provenance and any failure detail.

## Equivalent CLI and SDK

For a deliberate small first selection:

```sh
uv run agent-data-workbench ingest-hf runs/my-agent   nebius/SWE-rebench-openhands-trajectories   --id-pointer /trajectory_id   --group-pointer /instance_id   --stratum-pointer /repo   --limit 128
```

Omit `--limit` when the whole split is intended. Use `--revision` with a resolved commit to repeat the exact source selection; `--configuration` and `--split` choose the source configuration and split.

```python
from pathlib import Path
from agent_data_workbench import DatasetImport, Project, import_dataset

receipt = import_dataset(
    Project(Path("runs/my-agent")),
    DatasetImport(
        dataset="organization/dataset",
        revision="main",
        split="train",
        id_pointer="/trace_id",
        group_pointer="/task_id",
        stratum_pointer="/agent_name",
        limit=128,
    ),
)
```

The sample identifiers and mappings must be replaced with the chosen dataset's schema. The SDK uses the same import transaction and receipt workflow as `POST /api/imports/huggingface`. The inspection endpoint is `POST /api/imports/huggingface/inspect`.

## Identity, completeness and failure behavior

The Hub API resolves a requested revision to a commit SHA. The adapter records dataset, revision, configuration, split, schema, declared license and explicit selection separately from original row content. A configured external string or integer ID is preserved as the trace ID. Without one, the pinned source identity and row position generate a UUID, keeping even identical rows as separate attempts.

Dataset metadata comes from the Hugging Face libraries. Parquet sources use synchronous PyArrow batches over fsspec; other supported sources use the streaming datasets iterator. The internal batch size bounds intermediate memory and does not cap the number of rows. A very large individual row still needs corresponding memory. Media objects or other non-JSON values are rejected with their row position; export media as references rather than assuming arbitrary decoded video/image objects can enter the JSON trace store.

All selected rows enter one SQLAlchemy transaction. Invalid later rows, changed content under an existing ID, or a changed group/category mapping abort the whole batch. Reimporting the same IDs, full records and mappings is idempotent. To preserve source-group lineage, reuse original mappings when extending an import. Choosing a different revision can produce different generated identities.

An `imports/` receipt is written before source access, then updated with resolved provenance and completion or failure. It persists even if Hub access or schema resolution fails. The trace transaction rolls back independently; a failed receipt is not evidence of a partial successful dataset import. Source access uses the backend's normal Hugging Face environment and authentication configuration.

## Understand the imported selection

Choose **Understand this dataset** to open **Data & evidence**. Counts cover all records matching the current local filters, irrespective of explorer pagination. Explicit binary values at the chosen outcome field determine passed, failed and unknown counts. These are unverified source labels; words such as “error” in a message do not become inferred outcomes.

Repeated-task bars and tables show actual source groups and exact member counts. Click a group to inspect its full attempts. A sample with no repeated task says so. The local population is not an estimate of the complete upstream dataset. Source order and an explicit first-N selection may strongly affect its composition.

The trace detail reader recognizes common `trajectory`, `messages`, `events` and `steps` arrays, exposes full tool calls and raw metadata, and retains complete raw JSON for other schemas. Lexical clusters can help inspect similar language, but do not establish failure causes. Recorded findings, tasks and experiments later add evidence links. See [trace exploration](../workflows/traces.md).

## Verification and extension

`tests/test_huggingface.py` checks synthetic Parquet records, long nested content, stable identities, explicit selection, rollback, failed-source receipts and mapping conflicts. The adapter requires no model call. It does not automatically instrument the agent that produced the dataset or supply the agent's executable environment; use [Harbor comparisons](harbor.md) once a reviewed task and actual runnable template are available.
