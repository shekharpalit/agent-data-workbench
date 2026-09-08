"""Import receipts retain source provenance outside original trace objects."""

from agent_data_workbench.data.store import TraceStore
from agent_data_workbench.integrations.huggingface import DatasetImport, HuggingFaceSource
from agent_data_workbench.shared.files import save
from agent_data_workbench.shared.identifiers import new_id
from agent_data_workbench.shared.time import now
from agent_data_workbench.workspace.project import Project


def import_dataset(project: Project, config: DatasetImport) -> dict:
    receipt = {
        "id": new_id(),
        "kind": "huggingface",
        "created_at": now(),
        "source": {
            "provider": "huggingface",
            "dataset": config.dataset,
            "revision": config.revision,
            "configuration": config.configuration,
            "split": config.split,
            "url": f"https://huggingface.co/datasets/{config.dataset}",
            "license": None,
            "features": {},
            "selection": {"limit": config.limit, "order": "dataset order"},
            "resolved": False,
        },
        "config": config.model_dump(),
        "status": "running",
        "result": None,
        "error": None,
    }
    directory = project.directory("imports")
    directory.mkdir(exist_ok=True, mode=0o700)
    path = project.path("imports", receipt["id"])
    save(path, receipt)
    try:
        source = HuggingFaceSource(config)
        receipt.update(
            source={**source.source, "resolved": True}, config=source.config.model_dump()
        )
        save(path, receipt)
        result = TraceStore(project).ingest(
            source, group_pointer=config.group_pointer, stratum_pointer=config.stratum_pointer
        )
        receipt.update(status="complete", result=result)
    except Exception as exc:
        receipt.update(status="error", error=str(exc))
        raise
    finally:
        receipt["finished_at"] = now()
        save(path, receipt)
    return receipt
