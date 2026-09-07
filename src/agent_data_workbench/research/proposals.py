"""Source-checked export of proposed changes."""

from pathlib import Path

from ..identifiers import canonical_uuid
from ..project import Project, digest, now, save
from ..tasks import relative_path
from .artifacts import load_investigation
from .contracts import ResearchResult


def export_proposal(
    project: Project, investigation_id: str, proposal_id: str, source_root: Path, out: Path
) -> dict:
    import difflib

    proposal_id = canonical_uuid(proposal_id)
    value = load_investigation(project, investigation_id)
    if value["status"] != "complete":
        raise ValueError("Investigation is incomplete")
    result = ResearchResult.model_validate(value["result"])
    proposal = next((p for p in result.proposals if p.id == proposal_id), None)
    if proposal is None:
        raise ValueError("Unknown proposal")
    patches, changes = [], []
    if len({e.path for e in proposal.edits}) != len(proposal.edits):
        raise ValueError("A proposal must contain at most one complete edit per path")
    for edit in proposal.edits:
        relative_path(edit.path)
        path = (source_root / edit.path).resolve()
        if not path.is_relative_to(source_root.resolve()) or not path.is_file():
            raise ValueError("Proposal targets an absent file or escapes the source root")
        before = path.read_text(encoding="utf-8")
        if before != edit.before:
            raise ValueError("Proposed old content does not match the actual source file")
        for line in difflib.unified_diff(
            before.splitlines(True),
            edit.after.splitlines(True),
            fromfile="a/" + edit.path,
            tofile="b/" + edit.path,
        ):
            patches.append(line if line.endswith("\n") else line + "\n")
            if not line.endswith("\n"):
                patches.append("\\ No newline at end of file\n")
        changes.append(
            {"path": edit.path, "before_sha256": digest(before), "after_sha256": digest(edit.after)}
        )
    if out.exists():
        raise ValueError("Proposal output directory already exists")
    out.mkdir(parents=True, mode=0o700)
    artifact = {
        "proposal": proposal.model_dump(),
        "changes": changes,
        "investigation_id": investigation_id,
        "created_at": now(),
        "applied": False,
    }
    save(out / "proposal.json", artifact)
    (out / "change.patch").write_text("".join(patches), encoding="utf-8")
    return artifact
