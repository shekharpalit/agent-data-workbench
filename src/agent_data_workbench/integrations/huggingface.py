"""Stream original Hub rows with datasets metadata and synchronous Parquet batches."""

from itertools import islice

from pydantic import Field, model_validator

from agent_data_workbench.data.contracts import Trace
from agent_data_workbench.shared.contracts import Contract
from agent_data_workbench.shared.identifiers import stable_id
from agent_data_workbench.shared.json import digest, json_text, pointer_parts, pointer_value


class DatasetImport(Contract):
    dataset: str = Field(min_length=1)
    configuration: str | None = None
    split: str = Field(default="train", min_length=1)
    revision: str = Field(default="main", min_length=1)
    id_pointer: str = ""
    group_pointer: str = "/thread_id"
    stratum_pointer: str = "/agent_type"
    limit: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_pointers(self):
        for pointer in (self.id_pointer, self.group_pointer, self.stratum_pointer):
            pointer_parts(pointer)
        return self


class HuggingFaceSource:
    """One dataset row is one trace. No viewer API, text clipping or implicit row cap.

    A supplied external ID is preserved. Otherwise the pinned source and row position
    form a stable UUID, so even identical rows remain distinct attempts.
    """

    def __init__(self, config: DatasetImport):
        from datasets import load_dataset, load_dataset_builder
        from huggingface_hub import HfApi

        info = HfApi().dataset_info(config.dataset, revision=config.revision)
        self.config = config.model_copy(update={"revision": info.sha})
        builder = load_dataset_builder(config.dataset, name=config.configuration, revision=info.sha)
        self.parquet_files = (
            list(builder.config.data_files.get(config.split, []))
            if builder.info.builder_name == "parquet"
            else None
        )
        options = {}
        if builder.info.builder_name == "parquet":
            from pyarrow.dataset import ParquetFragmentScanOptions

            options["fragment_scan_options"] = ParquetFragmentScanOptions(pre_buffer=False)
        self.rows = load_dataset(
            config.dataset,
            name=config.configuration,
            split=config.split,
            revision=info.sha,
            streaming=True,
            **options,
        )
        self.source = {
            "provider": "huggingface",
            "dataset": info.id,
            "revision": info.sha,
            "configuration": self.rows.info.config_name,
            "split": config.split,
            "url": f"https://huggingface.co/datasets/{info.id}/tree/{info.sha}",
            "license": (info.card_data or {}).get("license"),
            "features": self.rows.features.to_dict() if self.rows.features else {},
            "selection": {"limit": config.limit, "order": "dataset order"},
        }

    def _records(self):
        if self.parquet_files is None:
            yield from self.rows
            return
        import fsspec
        from pyarrow.parquet import ParquetFile

        # Arrow's dataset scanner can retain asynchronous HTTP work after an early
        # stop. Its synchronous Parquet reader closes the stream at the selection
        # boundary and never leaves background requests against a closed file.
        for filename in self.parquet_files:
            with fsspec.open(filename, "rb") as stream:
                with ParquetFile(stream, pre_buffer=False) as parquet:
                    for batch in parquet.iter_batches(batch_size=64, use_threads=False):
                        yield from batch.to_pylist()

    def read(self):
        records = self._records()
        rows = records if self.config.limit is None else islice(records, self.config.limit)
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(f"Dataset row {index + 1} is not an object")
            # Canonicalization rejects non-JSON media/objects instead of silently dropping them.
            try:
                digest(row)
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"Dataset row {index + 1} contains non-JSON values; export media as references"
                ) from exc
            if self.config.id_pointer:
                key = pointer_value(row, self.config.id_pointer)
                if not isinstance(key, (str, int)) or isinstance(key, bool) or str(key) == "":
                    raise ValueError(f"Dataset row {index + 1} needs a string or integer trace ID")
                key = str(key)
            else:
                key = stable_id(
                    "huggingface-row",
                    json_text(
                        [
                            self.source["dataset"],
                            self.source["revision"],
                            self.source["configuration"],
                            self.source["split"],
                            index,
                        ]
                    ),
                )
            yield Trace(trace_id=key, data=row)
