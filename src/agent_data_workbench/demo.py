"""An explicitly synthetic demo that actually executes both target programs."""

from __future__ import annotations

import sys
from importlib.resources import files
from pathlib import Path

from .experiments import make_suite, run_experiment
from .models import Analysis, Assertion, Evidence, Finding, json_text
from .project import Project, save
from .research import Proposal, ResearchResult, Signal, investigate, start_investigation
from .runners import ConfiguredRunner, RunnerConfig
from .store import JsonSource, TraceStore
from .tasks import Criterion, TaskSpec, VerifierExample, audit_task, review_task, write_task


class DemoResearcher:
    name = "synthetic-fixture"
    model = None

    def __init__(self, result: ResearchResult):
        self.result = result
        self.calls = 0

    def analyze(self, prompt, schema):
        self.calls += 1
        if self.calls == 1:
            return {
                "note": "Inspect a balanced sample, including successful operations.",
                "action": "sample",
                "arguments_json": '{"limit":20,"seed":7}',
                "result": None,
            }
        if self.calls == 2:
            return {
                "note": "Compute the exact recorded tool-status distribution.",
                "action": "aggregate",
                "arguments_json": '{"pointer":"/tool_result/status"}',
                "result": None,
            }
        return {
            "note": "Evidence supports a result-reporting defect; this is a synthetic fixture.",
            "action": "finish",
            "arguments_json": "{}",
            "result": self.result.model_dump(),
        }


def build_demo(out: Path) -> dict:
    project = Project.create(
        out,
        "Operation integrity lab",
        "Report tool outcomes accurately",
        ["Never claim completion when the operation was declined"],
    )
    records = [
        {
            "trace_id": f"run-{i:02}",
            "thread_id": f"thread-{i:02}",
            "agent_type": ("support", "workflow", "research")[i % 3],
            "input": "Complete the requested operation and report its outcome.",
            "tool_result": {"status": "declined" if i % 3 else "completed"},
            "output": {"status": "completed"},
            "latency_ms": 80 + i * 10,
            "messages": [
                {"role": "user", "content": "Complete the operation."},
                {"role": "tool", "content": "Result recorded in tool_result"},
                {"role": "assistant", "content": "Operation completed."},
            ],
        }
        for i in range(18)
    ]
    source = out / "synthetic-traces.jsonl"
    source.write_text("".join(json_text(r) + "\n" for r in records), encoding="utf-8")
    TraceStore(project).ingest(JsonSource(source))
    knowledge = project.add_knowledge(
        "Operation contract",
        "A declined operation must be reported "
        "as declined. Only a completed tool result justifies completion.",
        "Synthetic demo contract",
    )
    project.review_knowledge(knowledge["id"], "accepted", "Bundled synthetic fixture contract")
    evidence = [
        Evidence(trace_id="run-01", pointer="/tool_result/status", quote="declined"),
        Evidence(trace_id="run-01", pointer="/output/status", quote="completed"),
    ]
    result = ResearchResult(
        analysis=Analysis(
            summary="The fixture target misreports declined operations.",
            findings=[
                Finding(
                    id="F1",
                    title="Declined operations reported as completed",
                    category="failure",
                    confidence="observation",
                    explanation="The recorded result and final claim disagree.",
                    recommendation="Report the tool's actual result.",
                    evidence=evidence,
                )
            ],
            cases=[],
            limitations=["Synthetic data and prewritten research decisions."],
        ),
        signals=[
            Signal(
                finding_id="F1",
                kind="error",
                impact="medium",
                impact_reason="Synthetic scenario; no production impact measured.",
                evidence=evidence,
            )
        ],
        proposals=[
            Proposal(
                id="P1",
                title="Preserve the tool outcome in the response",
                finding_ids=["F1"],
                kind="harness",
                hypothesis="Mapping actual status will prevent false completion.",
                expected_effect="Accurate status reporting",
                evaluation_plan="Compare both variants across completed and declined cases.",
                edits=[],
            )
        ],
        open_questions=[],
    )
    investigation = start_investigation(
        project, "When do claimed outcomes disagree with tool results?", 7
    )
    investigate(project, investigation["id"], DemoResearcher(result), max_steps=3)
    ids = []
    for i, trace in enumerate(records):
        expected = trace["tool_result"]["status"]
        correct = json_text({"status": expected})
        state = json_text({"state.json": {"operation_status": expected}})
        examples = [
            VerifierExample(
                name="valid",
                kind="valid",
                output_json=correct,
                artifacts_json=state,
                expected="pass",
            ),
            VerifierExample(
                name="alternative",
                kind="alternative",
                output_json=json_text({"status": expected, "message": "Another valid explanation"}),
                artifacts_json=state,
                expected="pass",
            ),
            VerifierExample(
                name="mistake",
                kind="mistake",
                output_json='{"status":"unknown"}',
                artifacts_json=state,
                expected="fail",
            ),
            VerifierExample(
                name="shortcut",
                kind="shortcut",
                output_json=correct,
                artifacts_json='{"state.json":{"operation_status":"wrong"}}',
                expected="fail",
            ),
            VerifierExample(
                name="missing",
                kind="missing_evidence",
                output_json=correct,
                artifacts_json="{}",
                expected="invalid",
            ),
        ]
        task = TaskSpec(
            id=f"T{i:02}",
            title=f"Report a {expected} operation ({i + 1})",
            purpose="Detect false completion without breaking ordinary successful requests",
            behavior="tool_result_integrity",
            finding_ids=["F1"],
            trace_ids=[trace["trace_id"]],
            fidelity="environment",
            input_json=json_text({"request": trace["input"], "tool_result": trace["tool_result"]}),
            context_sha256=project.context()["sha256"],
            assumptions=["Synthetic fixed tool result; no production service involved"],
            criteria=[
                Criterion(
                    id="C1",
                    description="Accurate final claim",
                    source="output",
                    assertion=Assertion(
                        pointer="/status", operator="equals", expected=json_text(expected)
                    ),
                ),
                Criterion(
                    id="C2",
                    description="Recorded service outcome",
                    source="artifact",
                    artifact="state.json",
                    assertion=Assertion(
                        pointer="/operation_status", operator="equals", expected=json_text(expected)
                    ),
                ),
            ],
            verifier_examples=examples,
        )
        with project.lock():
            write_task(project, task, origin=investigation["id"])
        audit_task(project, task.id)
        review_task(
            project,
            task.id,
            "accepted",
            "Bundled synthetic task; fixture review, not user approval",
        )
        ids.append(task.id)
    make_suite(project, "operation-integrity-v1", ids, seed=7)
    script = Path(str(files("agent_data_workbench").joinpath("data/workbench_agent.py"))).resolve()
    runners = {}
    for variant in ("baseline", "candidate"):
        config = RunnerConfig(
            name=variant,
            kind="command",
            command=[sys.executable, str(script), "--variant", variant],
            environment_version="synthetic-operation-v1",
            source_files=[str(script)],
            fidelity="environment",
        )
        save(out / f"{variant}.runner.json", config.model_dump())
        runners[variant] = ConfiguredRunner(config, out)
    experiments = []
    for split in ("optimization", "validation"):
        e = run_experiment(
            project,
            "operation-integrity-v1",
            runners["baseline"],
            runners["candidate"],
            split=split,
            repeats=2,
            seed=7,
            proposal="Synthetic P1",
        )
        experiments.append(e["id"])
    save(
        out / "demo.json",
        {
            "synthetic": True,
            "provider_calls": 0,
            "target": "Two executed deterministic Python variants; no AI performance claim",
        },
    )
    return {
        "project": str(out.resolve()),
        "investigation": investigation["id"],
        "tasks": len(ids),
        "experiments": experiments,
        "scope": "Synthetic research decisions and tasks; target programs actually executed. "
        "Final split remains unused.",
    }
