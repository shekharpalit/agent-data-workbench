# Legacy batch mode

Turn agent execution traces into evidence-linked findings and reviewable eval cases.

Local Python CLI and SDK. **Day-one alpha; working name.** The repository and package have not been published.

## Run it

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run agent-data-workbench demo --out runs/demo
```

Open `runs/demo/report.md`. The bundled support, coding, and research traces, analysis, and output files are **synthetic fixtures**. The demo makes no provider call and is not a performance benchmark.

Review the sample cases, then exercise the comparison:

```sh
uv run agent-data-workbench review runs/demo/cases.jsonl \
  --accept C1 --accept C2 \
  --note "Reviewed the bundled fixture setup and output assertions"
uv run agent-data-workbench compare runs/demo/cases.jsonl \
  runs/demo/baseline.jsonl runs/demo/candidate.jsonl
```

The prewritten baseline fails both cases and the prewritten candidate passes both. This demonstrates the checker, not an actual model improvement.

## Analyze your traces

Export one complete agent run per JSONL line. JSON arrays, single JSON objects, and `{"traces": [...]}` files also work. Records are preserved, so there is no required agent framework or message schema.

```json
{"trace_id":"run-1","input":"Please refund my order.","tool_result":{"status":"declined"},"output":{"refund_status":"processed"}}
```

A record needs a unique string `trace_id` or `id`; missing IDs are derived from content. Duplicate IDs, including identical records with derived IDs, are rejected. Include messages, tool arguments/results, outcome feedback, and versions when available.

```sh
uv run agent-data-workbench doctor
uv run agent-data-workbench analyze ./traces.jsonl --backend codex --out runs/first
uv run agent-data-workbench analyze ./traces.jsonl --backend claude \
  --context ./policy.md --context ./tool-contracts.json --out runs/second
```

Use `--question` to direct the investigation and `--model` to select a model supported by your installed CLI.

The adapters invoke your installed Codex or Claude Code CLI. Authentication and billing stay with that CLI: its configured account or API credentials and limits apply. This package does not extract credentials, implement a subscription proxy, or automatically switch to an API backend. Selected traces and context are sent through the selected provider's CLI; “local” describes the workflow and artifacts, not necessarily model inference.

Codex runs from a temporary directory with a read-only sandbox, user configuration excluded, shell tools disabled, and web search disabled. Its saved authentication remains available; use `--model` because the user model configuration is excluded. Claude runs with safe mode, built-in tools disabled, and an empty MCP configuration. It retains native authentication; `--bare` is deliberately not used because that mode excludes subscription login.

Command flags were checked against the installed CLIs and [official OpenAI documentation](https://learn.chatgpt.com/docs/non-interactive-mode) and [Claude Code documentation](https://code.claude.com/docs/en/headless). Provider adapters have protocol tests; live Codex verification is documented in [VALIDATION.md](VALIDATION.md). Claude live verification requires a logged-in native CLI. Update an older CLI if it rejects a flag.

### Use an existing interactive session

You can prepare input, ask an analyzer in your existing session to produce the specified JSON, and import the result:

```sh
uv run agent-data-workbench prepare ./traces.jsonl --out runs/manual
# Inspect runs/manual/prompt.txt and schema.json; produce response.json in your session.
uv run agent-data-workbench finish runs/manual ./response.json
```

`prepare` and `finish` do not call a provider. A failed `analyze` call leaves its prepared snapshot available for inspection or manual completion. There is no automatic retry or provider fallback.

## Artifacts

| File | Purpose |
| --- | --- |
| `report.md` | Findings, recommendations, candidate cases, and limits |
| `traces.md` | Trace snapshots linked from evidence citations |
| `analysis.json` | Structured, evidence-checked analysis |
| `cases.jsonl` | Candidate cases and explicit review decisions |
| `request.json` | Selected input, question, context, and content fingerprints |
| `prompt.txt`, `schema.json` | Inspectable analyzer request and output contract |
| `run.json` | Backend label and run provenance |

Evidence validation checks trace IDs, JSON pointers, exact quoted substrings, unique IDs, and case lineage. It cannot establish that a finding's interpretation or proposed test is correct. Cases start as candidates and need domain review before evaluation. Reports are immutable snapshots of the initial analysis; current review decisions live in `cases.jsonl`.

Generated runs stay under `runs/`, which is ignored by Git. They contain the supplied trace/context data and are not redacted automatically. The package has no telemetry or automatic upload/share operation.

## Evaluate an agent change

Read each case's input, required context, and assertions. Supply its fixtures in your existing agent runner, execute the agent, then export its outputs:

```json
{"case_id":"C1","output":{"refund_status":"declined","message":"The refund was declined."}}
```

Use one record per case in JSONL, or a JSON array. Review meaningful cases with `review --accept ID --note "..."`; use `--reject` for unsuitable cases. Then:

```sh
uv run agent-data-workbench evaluate runs/first/cases.jsonl ./outputs.jsonl
uv run agent-data-workbench compare runs/first/cases.jsonl ./baseline.jsonl ./candidate.jsonl
```

Assertions support RFC 6901 JSON pointers and `equals`, `contains`, `not_contains`, and `exists`. `equals.expected` is a JSON-encoded value; text operators use a literal nonempty string; `exists.expected` is empty. A missing field fails every operator. Boolean `true` does not equal numeric `1`.

Only accepted cases are scored. `compare` requires outputs for every accepted case on both sides, so missing baseline coverage cannot appear as an improvement. `evaluate` exits 1 on a failing case; `compare` exits 1 on a regression. Invalid input exits 2.

This checker evaluates submitted output fields. It does not run an agent, verify tool side effects, reconstruct an environment, or prove production improvement. Use your existing runner for execution. Workbench v0.2 adds iterative investigation, executable tasks and training-data exports through separate commands. Direct Harbor/service connectors are not bundled; see [the current README](../README.md).

## Python SDK

```python
from agent_data_workbench import CliAnalyzer, analyze_traces, load_traces
from pathlib import Path

result = analyze_traces(
    load_traces(Path("traces.jsonl")),
    CliAnalyzer("codex", timeout=300),
    question="Where do unsuccessful tool calls lead to incorrect final answers?",
    context="The application's explicit policies and tool contracts go here.",
)
print(result.model_dump_json(indent=2))
```

Custom analyzers implement `name` and `analyze(prompt, schema) -> dict`. Use `normalize(list_of_records)` for a custom trace-source adapter. The SDK validates evidence after every analyzer result.

## Alpha limits

The CLI selects the first 100 traces in export order by default; `--limit` changes this. It reports selected and total counts and makes no claim that this subset is representative. The default prepared-input limit is 120,000 characters, configurable with `--max-input-chars`. Oversized prompts fail before a provider call rather than silently truncating records. Input files are capped at 50 MiB; export smaller batches for now. These are practical alpha bounds, not large-scale data research support.

Run development checks:

```sh
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
```

MIT licensed. See [CONTRIBUTING.md](../CONTRIBUTING.md).
