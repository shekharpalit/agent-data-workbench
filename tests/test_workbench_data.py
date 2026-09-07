import json

import pytest
from identities import uid

from agent_data_workbench.models import Analysis, Assertion, Finding, Trace
from agent_data_workbench.project import Project, save
from agent_data_workbench.research import (
    ResearchResult,
    ResearchWorkspace,
    export_proposal,
    investigate,
    load_investigation,
    research_store,
    start_investigation,
)
from agent_data_workbench.store import JsonSource, TraceStore
from agent_data_workbench.tasks import (
    Criterion,
    TaskSpec,
    VerifierExample,
    audit_task,
    design_tasks,
    grade,
    load_task,
    replace_task,
    replay_task,
    review_task,
    write_task,
)


class Source:
    def __init__(self, values):
        self.values = values

    def read(self):
        return iter(Trace(trace_id=v["trace_id"], data=v) for v in self.values)


def make_project(tmp_path):
    p = Project.create(
        tmp_path / "project", "Test agent", "Report actual outcomes", ["Be accurate"]
    )
    TraceStore(p).ingest(
        Source(
            [
                {
                    "trace_id": f"r{i}",
                    "thread_id": f"g{i}",
                    "agent_type": "rare" if i == 8 else "common",
                    "value": i,
                    "text": "actual result",
                    "messages": [
                        {"role": "user", "content": "request"},
                        {"role": "tool", "content": "declined"},
                        {"role": "assistant", "content": "LEAKED FUTURE"},
                    ],
                    "hidden": "SECRET",
                }
                for i in range(9)
            ]
        )
    )
    return p


@pytest.fixture
def project(tmp_path):
    return make_project(tmp_path)


def spec(project, key=uid("T1"), trace_ids=None, artifact=False):
    criteria = [
        Criterion(
            id=uid("C1"),
            description="Actual outcome",
            source="output",
            assertion=Assertion(pointer="/value", operator="equals", expected="1"),
        )
    ]
    if artifact:
        criteria.append(
            Criterion(
                id=uid("C2"),
                description="Recorded state",
                source="artifact",
                artifact="state.json",
                assertion=Assertion(pointer="/value", operator="equals", expected="1"),
            )
        )
    state = '{"state.json":{"value":1}}' if artifact else "{}"
    examples = [
        VerifierExample(
            name="valid",
            kind="valid",
            output_json='{"value":1}',
            artifacts_json=state,
            expected="pass",
        ),
        VerifierExample(
            name="alternative",
            kind="alternative",
            output_json='{"value":1,"text":"alternative"}',
            artifacts_json=state,
            expected="pass",
        ),
        VerifierExample(
            name="mistake",
            kind="mistake",
            output_json='{"value":0}',
            artifacts_json=state,
            expected="fail",
        ),
        VerifierExample(
            name="shortcut",
            kind="shortcut",
            output_json='{"text":"value 1"}',
            artifacts_json=state,
            expected="fail",
        ),
        VerifierExample(
            name="missing",
            kind="missing_evidence",
            output_json="{}",
            expected="invalid" if artifact else "fail",
        ),
    ]
    return TaskSpec(
        id=uid(key),
        title=key,
        purpose="Test outcome",
        behavior="accuracy",
        trace_ids=trace_ids or ["r0"],
        fidelity="environment" if artifact else "output",
        input_json='{"request":"do work","expected_input":1}',
        context_sha256=project.context()["sha256"],
        criteria=criteria,
        verifier_examples=examples,
    )


def accept(project, task):
    write_task(project, task, origin="test fixture")
    assert audit_task(project, task.id)["passed"]
    review_task(project, task.id, "accepted", "Synthetic test fixture")
    return task


class Scripted:
    name = "test-fixture"
    model = "fixed"

    def __init__(self, *steps):
        self.steps = iter(steps)
        self.prompts = []

    def analyze(self, prompt, schema):
        self.prompts.append(prompt)
        value = next(self.steps)
        if isinstance(value, Exception):
            raise value
        return value


class NativeFixture:
    name = "codex"
    model = None
    timeout = None

    def __init__(self, action):
        self.action = action
        self.calls = []

    def run(self, workspace, *, session_id, attempt, prompt, on_event):
        self.calls.append({"session_id": session_id, "prompt": prompt})
        on_event({"type": "thread.started", "thread_id": uid("native-session")})
        self.action(workspace)


def result(quote="actual result", trace_id="r0"):
    return ResearchResult(
        analysis=Analysis(
            summary="An observed outcome",
            findings=[
                Finding(
                    id=uid("F1"),
                    title="Outcome",
                    category="opportunity",
                    confidence="observation",
                    explanation="Recorded text",
                    recommendation="Review",
                    evidence=[{"trace_id": trace_id, "pointer": "/text", "quote": quote}],
                )
            ],
            cases=[],
            limitations=["Synthetic fixture"],
        ),
        signals=[],
        proposals=[],
        open_questions=[],
    ).model_dump()


def test_stream_ingestion_is_idempotent_and_rolls_back_conflicts(project, tmp_path):
    # Given
    path = tmp_path / "traces.jsonl"
    path.write_text('{"trace_id":"new","value":1}\n')
    store = TraceStore(project)
    # When
    first = store.ingest(JsonSource(path))
    repeated = store.ingest(JsonSource(path))
    # Then
    assert {"added": first["added"], "unchanged": repeated["unchanged"]} == {
        "added": 1,
        "unchanged": 1,
    }
    # Given: a subsequent batch contains a conflicting record.
    path.write_text('{"trace_id":"another"}\n{"trace_id":"new","value":2}\n')
    # When / Then: the complete batch is rolled back.
    with pytest.raises(ValueError, match="different content"):
        store.ingest(JsonSource(path))
    with pytest.raises(ValueError, match="Unknown"):
        store.get("another")
    assert store.inventory()["total"] == 10


def test_invalid_jsonl_and_nonfinite_values_roll_back(project, tmp_path):
    # Given
    path = tmp_path / "traces.jsonl"
    path.write_text('{"trace_id":"new"}\n{"trace_id":"nan","value":NaN}\n')
    # When / Then
    with pytest.raises(ValueError):
        TraceStore(project).ingest(JsonSource(path))
    assert TraceStore(project).inventory()["total"] == 9


def test_balanced_sampling_and_exact_drilldown(project):
    # Given
    store = TraceStore(project)
    # When
    a = store.select(sample=True, seed=7, limit=2)
    aggregate = store.aggregate("/value")
    # Then
    assert a == store.select(sample=True, seed=7, limit=2)
    assert {
        "strata": {r["data"]["agent_type"] for r in a["records"]},
        "eligible": store.select(text="ACTUAL", limit=2)["eligible"],
        "numeric_match": store.select(equals_pointer="/value", equals_json="1")["ids"],
        "boolean_match": store.select(equals_pointer="/value", equals_json="true")["ids"],
        "mean": aggregate["mean"],
        "numeric_count": aggregate["numeric_count"],
        "missing": store.aggregate("/missing")["missing_or_non_scalar"],
    } == {
        "strata": {"common", "rare"},
        "eligible": 9,
        "numeric_match": ["r1"],
        "boolean_match": [],
        "mean": 4,
        "numeric_count": 9,
        "missing": 9,
    }


def test_all_inputs_are_available_and_final_exclusion_is_explicit(project):
    # Given
    save(
        project.path("suites", uid("reserved")),
        {
            "id": uid("reserved"),
            "tasks": [{"split": "final", "trace_groups": ["g0"]}],
            "final_exposure": None,
        },
    )
    # When
    default = start_investigation(project, "All data")
    excluded = start_investigation(project, "Keep final reserved", exclude_final=True)
    store = research_store(project, exclude_final=True)
    # Then
    assert {
        "all": default["source"]["total"],
        "excluded": excluded["source"]["total"],
        "consumed": project.final_groups(consumed=True),
        "filtered_ids": store.select()["ids"],
        "available": ResearchWorkspace(project, default["id"]).read("r0", pointer="/value"),
    } == {
        "all": 9,
        "excluded": 8,
        "consumed": {"g0"},
        "filtered_ids": [f"r{i}" for i in range(1, 9)],
        "available": {
            "trace_id": "r0",
            "pointer": "/value",
            "content": "0",
            "offset": 0,
            "total_chars": 1,
            "next_offset": None,
        },
    }
    with pytest.raises(ValueError, match="Unknown"):
        ResearchWorkspace(project, excluded["id"]).read("r0")


def test_native_session_resumes_without_rebuilding_a_step_loop(project):
    # Given
    i = start_investigation(project, "Find evidence", seed=42)
    first_agent = NativeFixture(lambda w: w.checkpoint("Saved useful progress"))
    # When
    first = investigate(project, i["id"], first_agent)
    next_agent = NativeFixture(lambda w: w.publish(result()))
    final = investigate(project, i["id"], next_agent)
    # Then
    assert {
        "first_status": first["status"],
        "seed": final["seed"],
        "status": final["status"],
        "snapshot_count": len(final["evidence_snapshot"]),
        "sessions": [c["session_id"] for a in [first_agent, next_agent] for c in a.calls],
        "journal_rebuilt": "Saved useful progress" in next_agent.calls[0]["prompt"],
        "attempts": [a["status"] for a in final["attempts"]],
    } == {
        "first_status": "paused",
        "seed": 42,
        "status": "complete",
        "snapshot_count": 1,
        "sessions": [None, uid("native-session")],
        "journal_rebuilt": False,
        "attempts": ["finished", "finished"],
    }


@pytest.mark.parametrize("bad", [result("fabricated"), result(trace_id="unknown")])
def test_fabricated_or_unknown_evidence_never_finishes(project, bad):
    # Given
    i = start_investigation(project, "Find evidence")
    model = NativeFixture(lambda w: w.publish(bad))
    # When / Then
    with pytest.raises(ValueError):
        investigate(project, i["id"], model)
    saved = load_investigation(project, i["id"])
    assert {"status": saved["status"], "result": saved["result"], "session": saved["session"]} == {
        "status": "paused",
        "result": None,
        "session": {"id": uid("native-session"), "backend": "codex", "model": None},
    }


@pytest.mark.parametrize("change", ["corpus", "knowledge"])
def test_changed_project_keeps_snapshot_and_resume_usable(project, change):
    # Given
    i = start_investigation(project, "Find evidence")
    if change == "corpus":
        TraceStore(project).ingest(Source([{"trace_id": "new"}]))
    else:
        k = project.add_knowledge("Contract", "New contract", "test")
        project.review_knowledge(k["id"], "accepted", "Reviewed")
    # When
    saved = investigate(project, i["id"], NativeFixture(lambda w: w.publish(result())))
    # Then
    assert {"status": saved["status"], "source": saved["source"], "context": saved["context"]} == {
        "status": "complete",
        "source": i["source"],
        "context": i["context"],
    }


def test_provider_failure_preserves_session_and_progress(project):
    # Given
    i = start_investigation(project, "Find evidence")

    def interrupt(workspace):
        workspace.checkpoint("Useful intermediate conclusion")
        raise RuntimeError("private provider text")

    # When / Then
    with pytest.raises(RuntimeError):
        investigate(project, i["id"], NativeFixture(interrupt))
    saved = load_investigation(project, i["id"])
    notes = ResearchWorkspace(project, i["id"]).dataset.events()["items"]
    assert {
        "status": saved["status"],
        "session": saved["session"]["id"],
        "notes": [e["note"] for e in notes if e["kind"] == "checkpoint"],
        "private_error_exposed": "private provider text" in saved["error"],
    } == {
        "status": "paused",
        "session": uid("native-session"),
        "notes": ["Useful intermediate conclusion"],
        "private_error_exposed": False,
    }


def test_audit_requires_alternatives_shortcuts_and_review(project):
    # Given
    task = spec(project, artifact=True)
    write_task(project, task, origin="test")
    # When / Then
    with pytest.raises(ValueError, match="audit"):
        review_task(project, task.id, "accepted", "Review")
    # When
    audit = audit_task(project, task.id)
    # Then
    assert {"passed": audit["passed"], "results": [r["actual"] for r in audit["results"]]} == {
        "passed": True,
        "results": ["pass", "pass", "fail", "fail", "invalid"],
    }
    # When
    review_task(project, task.id, "accepted", "Review")
    # Then
    assert load_task(project, task.id, accepted=True)[1] == task


def test_incomplete_audit_and_missing_context_block_acceptance(project):
    # Given
    task = spec(project)
    task.verifier_examples.pop(1)
    # When
    write_task(project, task, origin="test")
    # Then
    assert not audit_task(project, task.id)["passed"]
    with pytest.raises(ValueError, match="audit"):
        review_task(project, task.id, "accepted", "Review")
    # When
    changed = spec(project)
    changed.missing_context = ["Unknown policy"]
    replace_task(project, task.id, changed, "Add uncertainty")
    # Then
    assert audit_task(project, task.id)["passed"]
    with pytest.raises(ValueError, match="missing context"):
        review_task(project, task.id, "accepted", "Review")


def test_task_edit_and_context_changes_invalidate_approval(project):
    # Given
    task = accept(project, spec(project))
    changed = task.model_copy(update={"title": "Revised"})
    # When
    value = replace_task(project, task.id, changed, "Clarify")
    # Then
    assert {
        "audit": value["audit"],
        "review_status": value["review"]["status"],
        "previous_title": value["revisions"][0]["spec"]["title"],
    } == {
        "audit": None,
        "review_status": "draft",
        "previous_title": uid("T1"),
    }
    # When
    audit_task(project, task.id)
    review_task(project, task.id, "accepted", "Re-reviewed")
    k = project.add_knowledge("Contract", "Updated policy", "test")
    project.review_knowledge(k["id"], "accepted", "Reviewed")
    # Then
    with pytest.raises(ValueError, match="stale"):
        load_task(project, task.id, accepted=True)


def test_next_action_contains_only_prefix(project):
    # Given
    trace_id, prefix_length = "r0", 2
    # When
    value = replay_task(project, trace_id, prefix_length, "Before final response")
    task = TaskSpec.model_validate(value["spec"])
    # Then
    assert {
        "future_leaked": "LEAKED FUTURE" in task.input_json,
        "hidden_leaked": "SECRET" in task.input_json,
        "messages": json.loads(task.input_json)["messages"],
        "needs_context": bool(task.missing_context),
        "review": value["review"]["status"],
    } == {
        "future_leaked": False,
        "hidden_leaked": False,
        "messages": [
            {"role": "user", "content": "request"},
            {"role": "tool", "content": "declined"},
        ],
        "needs_context": True,
        "review": "draft",
    }


@pytest.mark.parametrize(
    "evidence", [[], [{"trace_id": "result", "pointer": "/text", "quote": "fabricated"}]]
)
def test_semantic_judge_must_provide_verifiable_evidence(project, evidence):
    # Given
    task = spec(project)
    task.criteria = [
        Criterion(
            id=uid("S1"),
            description="Explain outcome",
            source="output",
            kind="semantic",
            rubric="State the actual result",
        )
    ]
    judge = Scripted({"status": "pass", "explanation": "Looks good", "evidence": evidence})
    # When
    actual = grade(task, {"text": "declined"}, {}, judge)
    # Then
    assert {"status": actual["status"]} == {"status": "invalid"}


def test_task_design_stays_draft_and_checks_lineage(project):
    # Given
    i = start_investigation(project, "Find evidence")
    ResearchWorkspace(project, i["id"]).publish(result())
    task = spec(project)
    # When
    design_tasks(project, i["id"], Scripted({"tasks": [task.model_dump()], "limitations": []}))
    # Then
    assert load_task(project, task.id)[0]["review"]["status"] == "draft"
    # When
    bad = spec(project, key="bad", trace_ids=["r8"])
    # Then
    with pytest.raises(ValueError, match="outside"):
        design_tasks(project, i["id"], Scripted({"tasks": [bad.model_dump()], "limitations": []}))


def test_project_lock_releases_after_failure(project):
    # Given
    # When / Then
    with pytest.raises(RuntimeError), project.lock():
        with pytest.raises(ValueError, match="busy"), project.lock():
            pass
        raise RuntimeError("interrupt")
    with project.lock():
        pass


def test_verifier_labels_cannot_invert_their_meaning():
    # Given
    # When / Then
    with pytest.raises(ValueError, match="contradicts"):
        VerifierExample(name="alternative", kind="alternative", output_json="{}", expected="fail")


def test_proposal_export_checks_source_and_never_applies_it(project, tmp_path):
    # Given
    i = start_investigation(project, "Find evidence")
    value = result()
    value["proposals"] = [
        {
            "id": uid("P1"),
            "title": "Preserve outcome",
            "finding_ids": [uid("F1")],
            "kind": "prompt",
            "hypothesis": "Actual status improves accuracy",
            "expected_effect": "Fewer false claims",
            "evaluation_plan": "Compare the reviewed suite",
            "edits": [{"path": "prompt.txt", "before": "old", "after": "new"}],
        }
    ]
    ResearchWorkspace(project, i["id"]).publish(value)
    source = tmp_path / "source"
    source.mkdir()
    (source / "prompt.txt").write_text("old")
    out = tmp_path / "patch"
    # When
    artifact = export_proposal(project, i["id"], uid("P1"), source, out)
    # Then
    assert {
        "applied": artifact["applied"],
        "source": (source / "prompt.txt").read_text(),
        "preserves_eof": "\\ No newline at end of file" in (out / "change.patch").read_text(),
        "markdown_export": project.path("investigations", i["id"], ".md").exists(),
    } == {"applied": False, "source": "old", "preserves_eof": True, "markdown_export": True}
    # When
    (source / "prompt.txt").write_text("changed")
    # Then
    with pytest.raises(ValueError, match="does not match"):
        export_proposal(project, i["id"], uid("P1"), source, tmp_path / "patch2")
