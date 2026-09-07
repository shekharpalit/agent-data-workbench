# v0.2 validation — 2026-09-07

These checks establish that the local workflow operates. They do not establish production agent improvement or competitive benchmark performance.

## Automated verification

The suite covers the original batch workflow and the new workbench: JSONL rollback/idempotency, seeded sampling, exact aggregate drill-down, final-source exclusions, resumable research, invalid evidence, changed inputs, grader alternatives/shortcuts, missing context, stale reviews, prefix leakage, semantic evidence, grouped splits, repeated-trial uncertainty, fresh target execution, timeouts, artifact capture, invalid runs, regressions, final exposure after interruption, training selection/deduplication, analyzer scoring, human annotations, checked patch export and local HTTP boundaries.

HTTP tests use only temporary synthetic projects on 127.0.0.1. Provider protocol tests are fixtures and require no login. Native model tests are separate and are never invoked by pytest.

The TypeScript migration adds typed AND filters, numeric ranges, stable sorting with missing values last, pagination, shared-corpus distributions, lexical clustering with disclosed trace/text limits, and focused lineage without invented sibling relationships. Tests cover JSON type preservation, excluded source groups, HTTP authentication and malformed queries. Frontend tests use Given–When–Then and deep object assertions for transport, query transitions, filter entry and graph layout. Python tests use the same structure and explicit object comparisons for result contracts.

## Live native CLI checks

- Codex structured output: passed a synthetic arithmetic schema check using native login.
- Codex investigation: completed five bounded model-directed steps on 18 synthetic records. It sampled 12 traces, computed exact aggregates, inspected evidence and returned validated findings.
- Codex task design: returned three schema-valid draft tasks with trace lineage. All remained drafts with recorded missing context.
- Initial deterministic-only audits of these semantic tasks stayed invalid because no judge was configured.
- A subsequent Codex semantic audit of `completed-report` matched four of five synthetic labels. It incorrectly passed a misleading shortcut; the audit failed and the task remained unapproved. This is evidence that the audit gate catches this particular inconsistency, not proof that every bad grader is detected.
- Claude Code: native auth status reported loggedIn=false. The adapter has protocol tests, but a live Claude analysis has not been verified. No credentials were copied or extracted and no API fallback was attempted.

Native tests used the CLI default model and record it that way; the exact resolved model version was not captured. Use an explicit supported model ID for comparisons. No production traces were sent in these tests.

## Executed synthetic target demo

The demo runs two deterministic Python programs through the command adapter. The baseline falsely reports completion for declined operations; the candidate reports the actual status. Each trial captures a JSON state artifact and checks both output and state. This validates the execution and grading pipeline. The fixture result must not be advertised as model improvement or independent ground-truth verification of real services.

The final execution split remains unused in the demo, and the manifest records that the demo researcher already saw its traces. It is not an unseen-data benchmark.

## Browser and package verification

The React/TypeScript build was inspected in the in-app browser against a temporary copy of the synthetic demo. Combining declined status with latency ≥200 ms returned run-17, run-16, run-14 and run-13 in descending latency order; the distribution counted the same four traces. Clustering `/tool_result/status` produced groups of 12 declined and 6 completed traces. Inspecting the completed group returned its six members. The 39-node graph rendered; focusing on run-17 showed its three-node trace/task/experiment path, and the task node opened T17. Running its deterministic audit updated the copied artifact and passed. Experiment summaries displayed the recorded baseline/candidate trial outcomes. No browser console errors or warnings remained after the fix for native fetch binding.

The wheel includes the TypeScript entry point and four hashed JavaScript/CSS resources, including the lazy graph bundle. The source archive includes `ui/src` and `package-lock.json`, excluding `node_modules`. Both build offline; packaged users do not need Node. Final checks passed: 109 Python tests, 14 Vitest tests, strict TypeScript compilation, Ruff and Prettier. An isolated wheel smoke test executed the 18-task synthetic demo, served the built assets and returned the expected four traces from a combined numeric/status query. It recorded two experiments, made zero provider calls and left final exposure unused.

## FastAPI migration verification

The migrated backend passed all 128 Python tests, Ruff checks and formatting. The 19 added tests use Given–When–Then and object comparisons for typed request validation, generated OpenAPI, unchanged error envelopes, static assets, bounded request bodies, nonblocking jobs, concurrent-operation rejection and browser startup after Uvicorn is ready. Existing loopback HTTP tests now exercise Uvicorn. The suite makes no provider calls. Starlette currently emits one upstream AnyIO deprecation warning from its TestClient import; tests use its recommended `httpx2` transport.

The existing compiled React/TypeScript UI was exercised against FastAPI with a temporary copy of the synthetic workbench. Combining declined status and latency ≥200 ms returned run-17, run-16, run-14 and run-13 in descending latency order; the distribution counted the same four records. The lazy graph bundle rendered run-17's three-node trace/task/experiment path. Opening T17 and running its deterministic audit updated the copied artifact and passed. Browser console checks returned no warnings or errors.

Both distribution archives built offline. The wheel was installed with only runtime dependencies in a separate temporary environment; its CLI entry point, bundled JavaScript/CSS, authenticated OpenAPI and filtered search worked. Its synthetic demo created 18 tasks and two experiments, made zero provider calls and left final exposure unused. Frontend source and generated assets were unchanged by this backend migration.

## SQLAlchemy migration verification

All 133 Python tests, Ruff checks and formatting pass with SQLAlchemy 2.0.52. Five new Given–When–Then tests cover the old six-column database layout, preserved canonical JSON/hashes/import timestamps, repeated and conflicting IDs within a single import, recovery after rollback, concurrent worker initialization and reads, and iteration across multiple fetch batches. Existing ingestion, exclusion, analytics and FastAPI tests also pass.

Before replacing the database layer, the old implementation recorded inventory, seeded samples, trace metadata, aggregates, filtered search, distribution and clustering from a copy of the existing 18-trace synthetic SQLite project. SQLAlchemy returned exactly equal result objects for every operation. Opening existing projects requires no reimport. Application source contains no handwritten SQL statements or direct `sqlite3` access.

The wheel and source archive built offline. An isolated runtime installation passed its CLI entry point and authenticated localhost API/asset checks, including the expected four-record search. Its synthetic demo produced 18 tasks and two experiments, with zero provider calls and unused final exposure. The existing upstream Starlette TestClient deprecation warning remains.

## Agent Data Workbench naming verification

The Python package, CLI, TypeScript source, bundled UI and documentation use Agent Data Workbench consistently. Verification passed: 133 Python tests, 14 frontend tests, strict TypeScript compilation, Ruff and Prettier. The renamed wheel installed in an isolated runtime environment; its CLI, authenticated OpenAPI, JavaScript/CSS assets and combined search query passed. The synthetic demo created 18 tasks and two experiments with zero provider calls and no final exposure. The rebuilt UI was inspected in the browser, including the sidebar name wrapping, with no console warnings or errors. The upstream Starlette TestClient deprecation warning remains.

Current limits: sequential execution, local SQLite scans, bounded prompts/artifact sizes, POSIX project locking, no direct Harbor/service connectors, no built-in secure environment sandbox and no training job executor. See the README for data and provider boundaries.
