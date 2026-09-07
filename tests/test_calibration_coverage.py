import pytest
from identities import uid
from test_workbench_data import make_project, spec
from test_workbench_execution import FixedRunner, suite

from agent_data_workbench.calibration import (
    AttemptAdjudication,
    AttemptLabel,
    adjudicate_attempt,
    calibration_summary,
    create_calibration,
    label_attempt,
    load_calibration,
)
from agent_data_workbench.coverage import (
    Capability,
    CoverageMapping,
    TaxonomySpec,
    coverage_report,
    create_taxonomy,
    load_taxonomy,
    map_coverage,
    review_taxonomy,
)
from agent_data_workbench.experiments import run_experiment
from agent_data_workbench.project import digest, save
from agent_data_workbench.runners import Execution
from agent_data_workbench.tasks import replace_task
from agent_data_workbench.traces import read_json


@pytest.fixture
def project(tmp_path):
    return make_project(tmp_path)


class MixedRunner(FixedRunner):
    def run(self, visible_input, trial_dir, seed):
        self.inputs.append(visible_input)
        return Execution(
            output={"value": 0}, status="completed" if len(self.inputs) == 1 else "runner_error"
        )


def experiment(project):
    manifest = suite(project)
    return run_experiment(project, manifest["id"], FixedRunner(), MixedRunner())


def label(attempt, reviewer="Expert", status="pass"):
    return AttemptLabel(
        **{k: attempt[k] for k in ("task_id", "trial", "variant", "evidence_sha256")},
        reviewer=reviewer,
        status=status,
        reason="Reviewed the frozen transcript and authoritative evidence",
    )


def taxonomy(project):
    value = create_taxonomy(
        project,
        TaxonomySpec(
            name="Support",
            capabilities=[
                Capability(
                    id=uid("cancel"),
                    name="Cancellation",
                    description="Honor cancellation and ask for missing information",
                    required_slices=["cancel", "clarify"],
                ),
                Capability(id=uid("search"), name="Search", description="Find relevant records"),
            ],
        ),
    )
    return review_taxonomy(project, value["id"], "accepted", "Reviewed expected behavior", "Expert")


def mapping(kind, entity_id, slice="cancel"):
    return CoverageMapping(
        kind=kind,
        entity_id=entity_id,
        capability_id=uid("cancel"),
        slice=slice,
        rationale="Explicit cancellation behavior",
        source="Human review of the original trace or task",
        reviewer="Expert",
    )


def test_actual_attempt_calibration_separates_false_grades_from_invalidity(project):
    # Given: actual synthetic command-contract attempts with pass, fail and infrastructure errors.
    run = experiment(project)
    value = create_calibration(project, run["id"], "Human calibration")
    # When: an expert disagrees with the grader in both valid and invalid directions.
    for attempt, status in zip(value["attempts"], ["fail", "pass", "invalid", "fail"], strict=True):
        label_attempt(project, value["id"], label(attempt, status=status))
    summary = calibration_summary(project, value["id"])
    # Then: invalid disagreements are not folded into false passes or false failures.
    assert {
        k: summary[k]
        for k in (
            "total",
            "resolved",
            "unlabeled",
            "disagreements",
            "adjudicated",
            "confusion_matrix",
            "false_pass",
            "false_fail",
            "invalid_disagreements",
        )
    } == {
        "total": 4,
        "resolved": 4,
        "unlabeled": 0,
        "disagreements": 0,
        "adjudicated": 0,
        "confusion_matrix": {
            "pass": {"pass": 0, "fail": 1, "invalid": 1},
            "fail": {"pass": 1, "fail": 0, "invalid": 0},
            "invalid": {"pass": 0, "fail": 1, "invalid": 0},
        },
        "false_pass": {"count": 1, "denominator": 1, "rate": 1.0},
        "false_fail": {"count": 1, "denominator": 1, "rate": 1.0},
        "invalid_disagreements": 2,
    }
    assert value["attempts"][0]["evidence"] == {
        "task": next(
            t for t in run["task_snapshots"] if t["id"] == value["attempts"][0]["task_id"]
        ),
        "trial": run["trials"][0],
        "provenance": value["snapshot"],
    }


def test_human_disagreement_adjudication_is_bound_to_current_labels_and_evidence(project):
    # Given: two people disagree about the same frozen passing attempt.
    run = experiment(project)
    value = create_calibration(project, run["id"], "Disagreement")
    attempt = value["attempts"][0]
    label_attempt(project, value["id"], label(attempt, "A", "pass"))
    before = label_attempt(project, value["id"], label(attempt, "B", "fail"))
    disagreement = calibration_summary(project, value["id"])
    # When: another reviewer adjudicates, then one original reviewer submits a new review.
    decision = AttemptAdjudication(
        **label(attempt, "Arbiter", "fail").model_dump(),
        labels_sha256=disagreement["attempts"][0]["labels_sha256"],
    )
    resolved = adjudicate_attempt(project, value["id"], decision)
    resolved_summary = calibration_summary(project, value["id"])
    label_attempt(project, value["id"], label(attempt, "A", "invalid"))
    reopened = calibration_summary(project, value["id"])
    # Then: revisions preserve provenance and changed labels invalidate the old adjudication.
    assert {
        "before": {k: disagreement[k] for k in ("resolved", "disagreements", "adjudicated")},
        "adjudicated": {
            k: resolved_summary[k] for k in ("resolved", "disagreements", "adjudicated")
        },
        "after": {k: reopened[k] for k in ("resolved", "disagreements", "adjudicated")},
        "revision_link": resolved["previous_sha256"],
        "previous_hash": before["state_sha256"],
        "history": len(load_calibration(project, value["id"])["attempts"][0]["labels"]),
    } == {
        "before": {"resolved": 0, "disagreements": 1, "adjudicated": 0},
        "adjudicated": {"resolved": 1, "disagreements": 0, "adjudicated": 1},
        "after": {"resolved": 0, "disagreements": 1, "adjudicated": 0},
        "revision_link": before["state_sha256"],
        "previous_hash": before["state_sha256"],
        "history": 3,
    }
    assert read_json(project.path("calibrations", value["id"], "") / "revision-3.json") == before
    with pytest.raises(ValueError, match="Labels changed"):
        adjudicate_attempt(project, value["id"], decision)
    with pytest.raises(ValueError, match="exact displayed"):
        label_attempt(
            project, value["id"], label(attempt).model_copy(update={"evidence_sha256": "stale"})
        )


def test_calibration_preserves_old_attempt_when_live_experiment_changes(project):
    # Given: a captured actual experiment and its task/runner/judge provenance.
    run = experiment(project)
    value = create_calibration(project, run["id"], "Frozen")
    # When: the original artifact changes later.
    run["trials"][0]["execution"]["output"] = {"value": "changed after review"}
    save(project.path("experiments", run["id"]), run)
    # Then: reviews continue to reference the frozen attempt, never the current mutable file.
    assert load_calibration(project, value["id"]) == value
    # When / Then: a modified calibration payload cannot silently change the evidence.
    changed = read_json(project.path("calibrations", value["id"]))
    changed["attempts"][0]["evidence"]["trial"]["execution"]["output"] = {"value": 99}
    save(project.path("calibrations", value["id"]), changed)
    with pytest.raises(ValueError, match="changed"):
        load_calibration(project, value["id"])


def test_running_experiment_cannot_be_snapshotted_for_calibration(project):
    # Given: an experiment which is still changing.
    run = experiment(project)
    run["status"] = "running"
    save(project.path("experiments", run["id"]), run)
    # When / Then
    with pytest.raises(ValueError, match="finished experiment"):
        create_calibration(project, run["id"], "Too early")
    assert project.artifacts("calibrations") == []


def test_behavioral_coverage_counts_reviewed_slices_duplicates_and_actual_runs(project):
    # Given: nine independent but semantically duplicate tasks and a reviewed behavior taxonomy.
    manifest = suite(project)
    run_experiment(project, manifest["id"], FixedRunner(), FixedRunner())
    tax = taxonomy(project)
    # When: a human classifies all tasks and one production trace.
    for task in manifest["tasks"]:
        map_coverage(project, tax["id"], mapping("task", task["id"]))
    map_coverage(project, tax["id"], mapping("trace", "r0"))
    report = coverage_report(project, tax["id"])
    populated = {
        "traces": 1,
        "task_versions": 9,
        "accepted_tasks": 9,
        "tested_task_versions": 2,
        "unexecuted_task_versions": 7,
        "trial_results": {"pass": 4, "fail": 0, "invalid": 0},
        "all_observed_valid_attempts_passed": True,
        "independent_trace_groups": 9,
    }
    empty = {
        "traces": 0,
        "task_versions": 0,
        "accepted_tasks": 0,
        "tested_task_versions": 0,
        "unexecuted_task_versions": 0,
        "trial_results": {"pass": 0, "fail": 0, "invalid": 0},
        "all_observed_valid_attempts_passed": False,
        "independent_trace_groups": 0,
    }
    # Then: processing volume cannot fill missing behavioral slices or inflate unique cases.
    assert report["capabilities"] == [
        {
            "id": uid("cancel"),
            "name": "Cancellation",
            **populated,
            "required_slices": [{"name": "cancel", **populated}, {"name": "clarify", **empty}],
            "missing_accepted_slices": ["clarify"],
            "unexecuted_slices": ["clarify"],
        },
        {
            "id": uid("search"),
            "name": "Search",
            **empty,
            "required_slices": [],
            "missing_accepted_slices": [],
            "unexecuted_slices": [],
        },
    ]
    assert {
        "unmapped_traces": report["unmapped_trace_ids"],
        "unmapped_tasks": report["unmapped_task_ids"],
        "stale": report["stale_mapping_ids"],
        "duplicates": [
            {"kind": g["kind"], "entity_ids": g["entity_ids"]} for g in report["duplicate_groups"]
        ],
    } == {
        "unmapped_traces": [f"r{i}" for i in range(1, 9)],
        "unmapped_tasks": [],
        "stale": [],
        "duplicates": [{"kind": "task", "entity_ids": sorted(t["id"] for t in manifest["tasks"])}],
    }


def test_taxonomy_versions_preserve_review_and_require_explicit_reclassification(project):
    # Given: an accepted, mapped taxonomy.
    tax = taxonomy(project)
    old_mapping = map_coverage(project, tax["id"], mapping("trace", "r0"))
    # When: a human starts a new taxonomy revision with changed description.
    revised_spec = TaxonomySpec.model_validate(tax["spec"]).model_copy(update={"description": "V2"})
    revised = create_taxonomy(project, revised_spec, previous_id=tax["id"])
    # Then: earlier mappings stay attached to their reviewed version.
    assert {k: revised[k] for k in ("revision", "previous", "review")} == {
        "revision": 2,
        "previous": {"id": tax["id"], "sha256": tax["sha256"]},
        "review": {"status": "draft", "note": "", "reviewer": "", "spec_sha256": ""},
    }
    assert {
        "old_traces": coverage_report(project, tax["id"])["capabilities"][0]["traces"],
        "new_traces": coverage_report(project, revised["id"])["capabilities"][0]["traces"],
        "old_mapping": read_json(project.path("coverage", old_mapping["id"])),
    } == {
        "old_traces": 1,
        "new_traces": 0,
        "old_mapping": old_mapping,
    }
    with pytest.raises(ValueError, match="Review the taxonomy"):
        map_coverage(project, revised["id"], mapping("trace", "r0"))
    with pytest.raises(ValueError, match="already mapped"):
        map_coverage(project, tax["id"], mapping("trace", "r0"))
    with pytest.raises(ValueError, match="capability and slice"):
        map_coverage(project, tax["id"], mapping("trace", "r0", "invented"))
    assert load_taxonomy(project, tax["id"]) == tax


def test_stale_task_mapping_is_not_counted_as_an_accepted_current_eval(project):
    # Given: a coverage mapping of a reviewed task version.
    manifest = suite(project)
    task_id = manifest["tasks"][0]["id"]
    tax = taxonomy(project)
    mapped = map_coverage(project, tax["id"], mapping("task", task_id))
    # When: its specification changes after classification.
    updated = spec(project, key=task_id).model_copy(update={"purpose": "Changed requirement"})
    replace_task(project, task_id, updated, "Review new requirement")
    report = coverage_report(project, tax["id"])
    # Then: historical source lineage remains available, with current coverage explicitly stale.
    assert {
        "stale": report["stale_mapping_ids"],
        "accepted": report["capabilities"][0]["accepted_tasks"],
        "versions": report["capabilities"][0]["task_versions"],
        "snapshot": read_json(project.path("coverage", mapped["id"])),
    } == {
        "stale": [mapped["id"]],
        "accepted": 0,
        "versions": 1,
        "snapshot": mapped,
    }


def test_mapping_reserved_final_sources_records_exposure_before_any_evaluation(project):
    # Given: an untouched final split.
    manifest = suite(project)
    final_task = next(t for t in manifest["tasks"] if t["split"] == "final")
    tax = taxonomy(project)
    # When: a human reviews its source snapshot to classify coverage.
    mapped = map_coverage(project, tax["id"], mapping("task", final_task["id"]))
    exposed = read_json(project.path("suites", manifest["id"]))
    # Then: the original suite digest remains valid, while final-source exposure is recorded.
    assert {
        "suite_sha256": exposed["sha256"],
        "mapping_id": exposed["research_exposure"][0]["coverage_mapping_id"],
    } == {
        "suite_sha256": manifest["sha256"],
        "mapping_id": mapped["id"],
    }
    with pytest.raises(ValueError, match="already exposed"):
        run_experiment(project, manifest["id"], FixedRunner(), FixedRunner(), split="final")
    # When / Then: source snapshots cannot be silently rewritten to manufacture coverage.
    mapped["entity"]["spec"]["purpose"] = "Changed"
    save(project.path("coverage", mapped["id"]), mapped)
    with pytest.raises(ValueError, match="snapshot changed"):
        coverage_report(project, tax["id"])
    assert {
        "stored_hash": mapped["sha256"]
        == digest({k: v for k, v in mapped.items() if k != "sha256"})
    } == {"stored_hash": False}


def test_model_suggestions_do_not_count_as_human_calibration_or_adjudication(project):
    # Given: a recorded attempt with a model-generated labeling suggestion.
    run = experiment(project)
    value = create_calibration(project, run["id"], "Human only")
    attempt = value["attempts"][0]
    suggestion = label(attempt, "Judge model", "fail").model_copy(update={"reviewer_kind": "model"})
    label_attempt(project, value["id"], suggestion)
    # When: calibration agreement is computed before a human reviews it.
    summary = calibration_summary(project, value["id"])
    # Then: model suggestions remain visible but cannot certify human agreement.
    assert {
        "resolved": summary["resolved"],
        "unlabeled": summary["unlabeled"],
        "reviewers": summary["attempts"][0]["reviewers"],
        "model_suggestions": len(summary["attempts"][0]["model_labels"]),
    } == {
        "resolved": 0,
        "unlabeled": 4,
        "reviewers": 0,
        "model_suggestions": 1,
    }
    with pytest.raises(ValueError, match="Only a human"):
        adjudicate_attempt(
            project,
            value["id"],
            AttemptAdjudication(
                **suggestion.model_dump(),
                labels_sha256=summary["attempts"][0]["labels_sha256"],
            ),
        )


def test_failure_causes_are_counted_per_resolved_human_attempt(project):
    # Given: an invalid actual attempt which an expert diagnoses as infrastructure failure.
    run = experiment(project)
    value = create_calibration(project, run["id"], "Failure causes")
    attempt = value["attempts"][-1]
    assessed = label(attempt, "Expert", "invalid").model_copy(
        update={"failure_cause": "infrastructure"}
    )
    # When: the same reviewer revises their note, preserving the same diagnosis.
    label_attempt(project, value["id"], assessed)
    label_attempt(project, value["id"], assessed.model_copy(update={"reason": "Confirmed in log"}))
    summary = calibration_summary(project, value["id"])
    # Then: history preserves both annotations but one attempt contributes one diagnosis.
    assert {
        "causes": summary["failure_causes"],
        "disagreements": summary["cause_disagreements"],
        "attempt_cause": summary["attempts"][-1]["failure_cause"],
    } == {
        "causes": {"infrastructure": 1},
        "disagreements": 0,
        "attempt_cause": "infrastructure",
    }
