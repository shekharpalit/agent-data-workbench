"""Reviewed portable training records, with strict split and outcome provenance."""

from __future__ import annotations

from pathlib import Path

from .project import Project, digest, now, save
from .tasks import parse_object
from .traces import read_json


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
        visible_input = parse_object(tasks[task_id]["input_json"])
        key = digest(visible_input)
        if key in seen:
            continue
        seen.add(key)
        record = {
            "input": visible_input,
            "chosen": passes[0]["execution"]["output"],
            "provenance": {
                "experiment_id": experiment_id,
                "task_id": task_id,
                "trace_ids": tasks[task_id]["trace_ids"],
                "trial": trial,
                "split": "optimization",
                "label_source": "reviewed_task_verifier",
                "verifier_sha256": digest(tasks[task_id]["criteria"]),
                "chosen_variant": passes[0]["variant"],
            },
        }
        if kind == "preference":
            record["rejected"] = fails[0]["execution"]["output"]
        records.append(record)
    if not records:
        raise ValueError("No eligible reviewed outcomes for this export")
    if out.exists():
        raise ValueError("Export directory already exists")
    out.mkdir(parents=True, mode=0o700)
    from .models import json_text

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
        "deduplication": "One chosen record per identical visible input",
        "review_note": review_note,
        "permission_note": permission_note,
        "split": "optimization",
        "scope": "Portable curated data, not a training job. "
        "Adapt input/chosen/rejected to your trainer's schema. No automatic redaction.",
    }
    save(out / "manifest.json", manifest)
    return manifest
