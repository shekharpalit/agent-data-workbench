# Agent Data Workbench

Turn agent traces into evidence, reviewed tasks, and measurable improvement experiments.

**Local Python CLI + SDK + FastAPI backend + React/TypeScript workbench. v0.2 alpha.** Bring JSONL exports, an analyzer and a target runner.

## Try the whole workflow

Requires Python 3.14+, macOS or Linux, and [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/shekharpalit/agent-data-workbench.git
cd agent-data-workbench
uv sync --locked
uv run agent-data-workbench workbench-demo runs/workbench
uv run agent-data-workbench ui runs/workbench --open-browser
```

The demo indexes 18 synthetic traces, records a scripted investigation, audits 18 tasks, and **actually executes** baseline and candidate Python programs. It runs optimization and validation splits twice and leaves the final split unused. It makes no model calls. Its gain is a deliberately constructed fixture result, not a claim about AI performance.

The **React + TypeScript UI** includes a trace explorer with combined field filters, numeric ranges, sorting and pagination; charts over the matching corpus; local lexical clusters with inspectable membership; and an interactive evidence graph. Investigations, knowledge review, editable task specs, grader audits and per-trial experiment evidence share the same workbench. It binds only to `127.0.0.1`; use the complete private URL printed by the CLI. Stop with Ctrl-C. Built assets ship with Python, so users need no cloud account, Node installation or frontend build.

Search values preserve JSON types: `true`, `1` and `"1"` differ. Up to eight field filters are combined with AND; free text is case-insensitive substring search. JSON pointers address nested fields, such as `/tool_result/status` or `/latency_ms`. Clustering uses TF-IDF cosine similarity on at most 200 ID-ordered matching traces and 20,000 text characters per trace, with all omissions and clipping disclosed. Connected groups are exploratory lexical patterns, not semantic judgments or prevalence estimates. The graph shows recorded trace → finding → task → experiment links; focus on a trace to inspect its downstream evidence.

Frontend contributors: see [ui/README.md](ui/README.md) for build/watch commands and [CONTRIBUTING.md](CONTRIBUTING.md) for Given–When–Then tests and deep object comparisons.

## What works

| Stage | Behavior |
| --- | --- |
| Import | Stream JSONL into SQLite through SQLAlchemy; preserve records; idempotent imports; reject conflicting IDs |
| Investigate | Bounded model-directed search, balanced sampling, inspection, exact aggregates, journal and resume |
| Learn context | Reviewed policies, success definitions, tool contracts and source snapshots |
| Find improvements | Evidence-linked errors, corrections, friction, recoveries, demonstrations, cost, latency and behavior hypotheses |
| Build tasks | Portable specs with visible input, trace lineage, assumptions, missing context and grading criteria |
| Audit graders | Correct results, alternatives, mistakes, misleading shortcuts and missing evidence |
| Test a change | Execute both target variants in fresh directories; preserve failures, invalid runs, regressions and uncertainty |
| Keep provenance | Grouped splits, versioned suites, fingerprints, target configurations, task snapshots and actual trial evidence |
| Export | Markdown reports, checked proposal patches, SFT/preference JSONL with provenance |
| Evaluate the analyzer | Exact evidence-span benchmark plus separate human correctness, usefulness and review-time annotations |

## Bring traces from any agent

```sh
uv run agent-data-workbench init runs/my-agent "My agent" "Report actual tool outcomes" \
  --criterion "Never claim completion after a declined operation"
uv run agent-data-workbench ingest runs/my-agent ./traces.jsonl
uv run agent-data-workbench query runs/my-agent --sample --seed 7 --limit 20
uv run agent-data-workbench query runs/my-agent --aggregate /tool_result/status
```

One run per JSONL line works well. JSON arrays, single objects and `{"traces": [...]}` also work:

```json
{"trace_id":"run-1","thread_id":"conversation-1","agent_type":"support","input":"Complete the operation","tool_result":{"status":"declined"},"output":{"status":"completed"},"latency_ms":860}
```

Use stable string `trace_id` or `id`; absent IDs are derived from content. Ingesting identical ID/content pairs is a no-op. A conflicting ID rolls back that import. Grouping defaults to `/thread_id`, falling back to the trace ID; strata default to `/agent_type`. Set `--group-pointer` and `--stratum-pointer` to match your export. Group related conversations or environment episodes together to avoid split leakage.

Custom integrations implement `TraceSource.read() -> Iterable[Trace]` and call `TraceStore(project).ingest(source)`. No runtime instrumentation is required. Direct Langfuse, OpenTelemetry and other service connectors are extension work, not bundled integrations.

## Investigate with Codex or Claude Code

```sh
uv run agent-data-workbench doctor
uv run agent-data-workbench knowledge add runs/my-agent ./policy.md "Operation policy"
# Review the saved entry, then use its returned ID.
uv run agent-data-workbench knowledge review runs/my-agent K_ID accepted "Reviewed policy and scope"
uv run agent-data-workbench investigate runs/my-agent --backend codex --steps 6 --seed 7 \
  --question "Where do tool outcomes and final claims disagree? Find counterexamples too."
# Continue a paused investigation using its returned ID.
uv run agent-data-workbench investigate runs/my-agent --backend codex --resume I_ID --steps 4
```

Use `--model` to select a model supported by your installed CLI. The researcher requests structured read actions; the host executes them. It can inspect traces in bounded pieces, aggregate JSON-pointer fields, consult accepted knowledge and review previous non-final experiments. Every completed step is saved. It stops at its call budget; corpus/context changes block incompatible resumes.

Results must cite existing trace IDs, valid JSON pointers and exact quoted text. This verifies the reference, **not the interpretation**. Balanced samples oversample small strata and cannot establish prevalence. Code-computed aggregates describe only the matching imported corpus.

Each completed investigation produces JSON and a Markdown report. Proposals remain hypotheses until an experiment tests them. Source patches can be exported only when the entire proposed old content matches the supplied file:

```sh
uv run agent-data-workbench proposal-export runs/my-agent I_ID P_ID ./agent-source ./patch-review
```

This writes a proposal and patch for inspection; it does not apply changes.

### Native login and usage

The adapters invoke your installed CLI with its native authentication. Its account, API configuration and usage limits determine billing. There is no credential extraction, subscription proxy, automatic API fallback or claim of unlimited usage. Model calls send selected trace/context data through the selected provider; local storage does not make that inference local.

Codex uses an ephemeral temporary directory, read-only sandbox, disabled shell/web search and `--ignore-user-config` while retaining native login. Claude uses safe mode, no built-in tools, empty MCP configuration and no session persistence. Update older CLIs if their flags differ. See [Codex CLI documentation](https://learn.chatgpt.com/docs/non-interactive-mode) and [Claude headless documentation](https://code.claude.com/docs/en/headless).

Live verification completed a Codex investigation and task generation. A subsequent live audit caught a shortcut that its semantic judge incorrectly accepted; the task stayed unapproved. Claude's adapter has protocol tests; live verification is pending because Claude Code reports no logged-in session. See [validation notes](docs/VALIDATION.md).

## Review tasks and graders

```sh
uv run agent-data-workbench task design runs/my-agent I_ID --backend codex
uv run agent-data-workbench schema --kind task > task.schema.json
uv run agent-data-workbench task import runs/my-agent ./task.json
uv run agent-data-workbench task replay runs/my-agent run-1 2 --title "Respond after tool result"
uv run agent-data-workbench task audit runs/my-agent T_ID
# Semantic criteria need an explicitly configured judge.
uv run agent-data-workbench task audit runs/my-agent T_ID --judge codex --model YOUR_MODEL
uv run agent-data-workbench task review runs/my-agent T_ID accepted "Reviewed task, rubric and examples"
```

The replay cutoff is exclusive: `2` includes only the first two messages, excluding the later response and unrelated trace fields. A replay starts as an incomplete draft; supply relevant tools, policy and success criteria.

Task specs separate `input_json` (the target-visible JSON object) from criteria and verifier examples. Choose fidelity honestly:

| Fidelity | What it establishes |
| --- | --- |
| `output` | Behavior on supplied input, graded from returned output |
| `next_action` | A response or decision at a saved conversation prefix |
| `environment` | Behavior executed by the configured environment runner, using its fixtures and captured state |

Deterministic criteria support JSON-pointer `equals`, `contains`, `not_contains` and `exists`. Semantic criteria require a rubric and judge, with exact grading evidence. Missing whole artifacts or failed judges yield **invalid**, separately from failed behavior. Missing expected output fields fail their assertions.

Acceptance requires a passing audit covering all five example kinds, resolved missing context and current reviewed knowledge. Audit examples are sanity checks, not proof of grader correctness. Review domain semantics and alternatives. Editing a task preserves its previous specification and resets its audit and review. Changing accepted knowledge makes tasks using the old context stale.

## Execute baseline and candidate agents

Create two runner JSON files. A command runner reads one request from stdin and returns one JSON object on stdout. Send diagnostics to stderr.

```json
{
  "name": "baseline",
  "kind": "command",
  "command": ["python3", "target.py"],
  "environment_version": "my-fixtures-v1",
  "source_files": ["target.py"],
  "fidelity": "output",
  "timeout": 120
}
```

`command` is an argv list, never a shell command. Relative file arguments resolve from the configuration file's directory. List files whose changes should invalidate the runner identity in `source_files`; environment versions and dependency pinning remain your responsibility.

Input: `{"input":{"request":"..."},"seed":7}`. Output: `{"output":{"status":"declined"},"cost_usd":0.001}`. Absent cost is **unknown**, not zero. The host measures wall-clock latency. Environment adapters can write required JSON artifacts such as `state.json` into their fresh working directory. A target-written file is not automatically independent ground truth: connect your adapter to authoritative state when correctness depends on side effects.

```sh
uv run agent-data-workbench suite runs/my-agent my-suite-v1 \
  --task-id T1 --task-id T2 --task-id T3 --seed 7
uv run agent-data-workbench experiment runs/my-agent my-suite-v1 \
  baseline.runner.json candidate.runner.json --split optimization --repeats 3 --seed 7
uv run agent-data-workbench experiment runs/my-agent my-suite-v1 \
  baseline.runner.json candidate.runner.json --split validation --repeats 3 --seed 7
```

The SDK `TargetRunner` interface supports custom harnesses. Native `codex`/`claude` target configurations require an explicit `model` and `prompt` and support output or next-action fidelity. Their adapter does not execute a tool-using environment or provide deterministic seed control. Harbor is not bundled: integrate it through a runner supplying genuine fixtures, reset behavior and captured results.

**Command runners execute trusted local code. A fresh directory is not a security sandbox.** They inherit host permissions, environment and network access. Run untrusted targets inside your own container or VM adapter. The host supplies only visible input, but this does not isolate hidden artifacts from a target with host-file access.

Suites connect tasks sharing source groups, including transitive links, then split groups roughly 60/20/20 into optimization, validation and final. At least three independent groups are required; three is not statistically sufficient.

Final source groups are reserved from subsequent investigations and excluded from experiment-history context. Final execution is consumed before the first trial, including interrupted runs, and cannot be reused under another suite name. Existing groups cannot be reassigned through a new suite. These are local bookkeeping protections, not tamper-proof secrecy. Suites record prior investigation exposure: splitting mined failures does **not** create unseen data. Collect fresh episodes for a real holdout and freeze candidate selection before `--split final`.

Experiments retain both sides of every trial, invalid runs and regressions. Confidence intervals resample independent source groups, keeping related tasks and repeats together; fewer than five valid groups produces no interval. A suite gain does not establish production generalization. Exit status is 1 for regressions/invalid trials, 2 for invalid configuration, 0 otherwise.

## Training export and analyzer evaluation

```sh
uv run agent-data-workbench training-export runs/my-agent E_ID ./training-data \
  --kind preference --review-note "Reviewed selected outcomes" \
  --permission-note "Synthetic data owned by this project"
uv run agent-data-workbench benchmark src/agent_data_workbench/data/analyzer-gold.json runs/analyzer-check \
  --backend codex
uv run agent-data-workbench benchmark-review runs/analyzer-check ./annotations.json "Reviewer name"
```

Training export accepts completed **optimization** experiments only, skips invalid pairs, deduplicates identical visible inputs and chooses the verified passing side, including baseline when the candidate regresses. SFT writes `input/chosen`; preferences add `rejected`. The manifest records review notes, data-use notes, fingerprints and trial lineage. Adapt the JSONL to your trainer. Export does not train a model, redact data or establish permission merely because a note was supplied.

The bundled analyzer gold set is a small, hand-authored synthetic smoke dataset with explicit questions. Automatic scores measure exact `(trace_id, pointer, category)` localization. Additional correct supporting spans can count as extra labels; inspect the report. Human annotations separately measure correctness, actionability, task usefulness and review time, with coverage. Use `schema --kind human-assessment` for its contract. Build independent domain gold data before comparing frontier analyzers.

## SDK, artifacts and limits

```python
from pathlib import Path
from agent_data_workbench import Project, TraceStore, JsonSource, CliAnalyzer
from agent_data_workbench import start_investigation, investigate

project = Project(Path("runs/my-agent"))
TraceStore(project).ingest(JsonSource(Path("traces.jsonl")))
run = start_investigation(project, "Which behaviors should change?", seed=7)
result = investigate(project, run["id"], CliAnalyzer("codex"), max_steps=6)
```

The project contains `project.json`, `traces.sqlite3`, `knowledge/`, `investigations/`, `tasks/`, `suites/`, `experiments/` and `exports/`. Trial evidence and Markdown reports sit beside JSON records. Fingerprints detect accidental changes, not a hostile owner. Keep private projects under `runs/` or outside version control. No automatic redaction or telemetry is included.

JSONL ingestion streams records with a 2-million-character record limit. JSON files and artifact reads are capped at 50 MiB. Search is a SQLite substring scan; inventory and sampling retain metadata in memory. Aggregates scan records. This is not distributed or billion-record analytics. Research defaults to six calls and a 120,000-character prompt budget. Semantic grading and task design each cap input at 120,000 characters.

Project mutations use a process lock. The UI runs one model job at a time; experiments execute sequentially. Completed steps survive interruption. OS-killed records may need an explicit new run. There are no upload, publish or push commands.

Legacy batch commands remain supported; their supplied-output checker is separate from executable experiments. See [batch mode](docs/BATCH.md) and [architecture](docs/ARCHITECTURE.md).

```sh
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
uv build
```

MIT licensed. See [CONTRIBUTING.md](CONTRIBUTING.md).
