"""Reviewed portable training records, with strict split and outcome provenance."""

from __future__ import annotations

from pathlib import Path

from agent_data_workbench.evaluation.tasks.contracts import TaskSpec
from agent_data_workbench.evaluation.tasks.repository import task_digest
from agent_data_workbench.execution.contracts import ConversationSpec, SessionReply, UserTurn
from agent_data_workbench.shared.files import save
from agent_data_workbench.shared.json import digest, parse_object, read_json
from agent_data_workbench.shared.time import now
from agent_data_workbench.workspace.project import Project


def _training_output(task: dict, row: dict) -> dict | None:
    """Copy observed turns; never infer tool calls or use verifier state as a target."""
    if row["execution"]["status"] != "completed":
        return None
    specification = task.get("conversation")
    observed = (row.get("runtime_evidence") or {}).get("conversation")
    if specification is None:
        return row["execution"]["output"] if observed is None else None
    if not isinstance(observed, dict) or observed.get("status") != "completed":
        return None
    try:
        spec = ConversationSpec.model_validate(specification)
        if observed.get("spec_sha256") != digest(spec.model_dump()):
            return None
        events = observed.get("turns")
        if not isinstance(events, list) or not events:
            return None
        turns = []
        for index, event in enumerate(events):
            if event.get("index") != index or event.get("status") != "completed":
                return None
            user = UserTurn.model_validate(event.get("user"))
            reply = SessionReply.model_validate(event.get("reply"))
            turns.append(
                {
                    "index": index,
                    "user": user.model_dump(),
                    "assistant": {
                        "message": reply.message,
                        "output": reply.output,
                        "reported_evidence": reply.evidence,
                    },
                }
            )
        if spec.simulator is None:
            if [turn["user"] for turn in turns] != [turn.model_dump() for turn in spec.turns]:
                return None
        elif turns[0]["user"] != spec.turns[0].model_dump() or (
            spec.max_turns is not None and len(turns) > spec.max_turns
        ):
            return None
        return {"format": "agent-data-workbench.trajectory.v1", "turns": turns}
    except ValueError, TypeError, AttributeError:
        return None


def _scenario(task: dict, visible_input: dict) -> dict:
    return {
        "input": visible_input,
        **{
            name: task[name]
            for name in ("conversation", "world", "environment")
            if task.get(name) is not None
        },
    }


def _runtime_provenance(experiment: dict, row: dict) -> dict:
    runtime = row.get("runtime_evidence") or {}
    environment = runtime.get("environment") or {}
    conversation = runtime.get("conversation") or {}
    return {
        "trial_sha256": digest(row),
        "runner_identity": row.get("runner_identity", experiment[row["variant"]]),
        "environment_identity": environment.get("identity"),
        "conversation": {
            "spec_sha256": conversation.get("spec_sha256"),
            "session_id": conversation.get("session_id"),
            "simulator": conversation.get("simulator"),
            "stop_reason": conversation.get("stop_reason"),
        }
        if conversation
        else None,
        "authoritative_state_sha256": digest(row["state"]) if "state" in row else None,
    }


def export_training(
    project: Project,
    experiment_id: str,
    out: Path,
    *,
    kind: str,
    review_note: str,
    permission_note: str,
) -> dict:
    if kind not in {"sft", "preference"} or not review_note.strip() or not permission_note.strip():
        raise ValueError("Supply sft/preference, a review note, and a data-use permission note")
    experiment = read_json(project.path("experiments", experiment_id))
    if experiment["status"] != "complete" or experiment["split"] != "optimization":
        raise ValueError(
            "Export only completed optimization experiments; validation/final data is excluded"
        )
    tasks = {t["id"]: t for t in experiment["task_snapshots"]}
    paired = {}
    for row in experiment["trials"]:
        paired.setdefault((row["task_id"], row["trial"]), {})[row["variant"]] = row
    records, seen = [], set()
    for (task_id, trial), variants in sorted(paired.items()):
        before, after = variants.get("baseline"), variants.get("candidate")
        if before is None or after is None:
            continue
        if "invalid" in {before["grade"]["status"], after["grade"]["status"]}:
            continue
        passes = [r for r in (after, before) if r["grade"]["status"] == "pass"]
        fails = [r for r in (after, before) if r["grade"]["status"] == "fail"]
        if not passes or kind == "preference" and not fails:
            continue
        task = tasks[task_id]
        visible_input = parse_object(task["input_json"])
        scenario = _scenario(task, visible_input)
        key = digest(scenario)
        chosen = _training_output(task, passes[0])
        rejected = _training_output(task, fails[0]) if kind == "preference" else None
        if chosen is None or kind == "preference" and (rejected is None or chosen == rejected):
            continue
        if key in seen:
            continue
        seen.add(key)
        record = {
            "input": visible_input,
            "chosen": chosen,
            "provenance": {
                "experiment_id": experiment_id,
                "task_id": task_id,
                "trace_ids": task["trace_ids"],
                "trial": trial,
                "split": "optimization",
                "label_source": "reviewed_task_verifier",
                "verifier_sha256": digest(task["criteria"]),
                "chosen_variant": passes[0]["variant"],
            },
        }
        if kind == "preference":
            record["rejected"] = rejected
        if any(task.get(name) is not None for name in ("conversation", "world", "environment")):
            record["provenance"].update(
                task_sha256=task_digest(TaskSpec.model_validate(task)),
                scenario_sha256=key,
                world=task.get("world"),
                environment_spec_sha256=digest(task["environment"])
                if task.get("environment")
                else None,
                conversation_spec_sha256=digest(task["conversation"])
                if task.get("conversation")
                else None,
                improvement=experiment.get("improvement"),
                chosen_runtime=_runtime_provenance(experiment, passes[0]),
                evidence_scope=(
                    "Assistant reported evidence is copied as observed, without inferred "
                    "tool messages. Authoritative state and verifier truth remain in "
                    "the source experiment and are referenced by hashes only."
                ),
            )
            if kind == "preference":
                record["provenance"]["rejected_runtime"] = _runtime_provenance(experiment, fails[0])
        records.append(record)
    if not records:
        raise ValueError("No eligible reviewed outcomes for this export")
    if out.exists():
        raise ValueError("Export directory already exists")
    out.mkdir(parents=True, mode=0o700)
    from agent_data_workbench.shared.json import json_text

    data = "".join(json_text(row) + "\n" for row in records)
    (out / "data.jsonl").write_text(data, encoding="utf-8")
    manifest = {
        "format": "agent-data-workbench.training.v1",
        "kind": kind,
        "created_at": now(),
        "experiment_id": experiment_id,
        "experiment_sha256": digest(experiment),
        "records": len(records),
        "data_sha256": digest(records),
        "deduplication": (
            "One chosen record per identical visible input and conversation/world/"
            "environment specification; identical preferences excluded"
        ),
        "review_note": review_note,
        "permission_note": permission_note,
        "split": "optimization",
        "scope": "Portable curated data, not a training job. "
        "Adapt input/chosen/rejected to your trainer's schema. Conversation targets contain "
        "observed user/assistant turns and assistant-reported evidence, not synthesized tool "
        "messages or verifier state. No automatic redaction.",
    }
    save(out / "manifest.json", manifest)
    return manifest
