"""Transport selected host trace files into a container without changing their logical names."""

from __future__ import annotations

import shutil
import tarfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import BinaryIO, Iterator

from .ingestion import SourceFile


@contextmanager
def archive_files(stream: BinaryIO) -> Iterator[list[SourceFile]]:
    """Materialize one complete archive before any database import can begin."""
    with TemporaryDirectory(prefix="workbench-import-") as directory:
        root = Path(directory)
        paths: dict[str, Path] = {}
        links: dict[str, str] = {}
        names: set[str] = set()
        try:
            with tarfile.open(fileobj=stream, mode="r|*") as archive:
                for member in archive:
                    name = PurePosixPath(member.name)
                    if name.is_absolute() or ".." in name.parts:
                        raise ValueError(
                            "Archive entries must have relative paths inside the import"
                        )
                    if member.isdir():
                        continue
                    if not (member.isfile() or member.islnk()):
                        raise ValueError(
                            "Trace archives may contain only regular files and folders"
                        )
                    if name.suffix.lower() not in {".json", ".jsonl", ".ndjson"}:
                        raise ValueError(f"Unsupported trace file in archive: {name}")
                    if str(name) in names:
                        raise ValueError(f"Duplicate trace file in archive: {name}")
                    names.add(str(name))
                    if member.islnk():
                        target = PurePosixPath(member.linkname)
                        if target.is_absolute() or ".." in target.parts:
                            raise ValueError("Archive hardlinks must point inside the import")
                        links[str(name)] = str(target)
                        continue
                    path = root.joinpath(*name.parts)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as source, path.open("wb") as destination:
                        shutil.copyfileobj(source, destination)
                    paths[str(name)] = path
        except tarfile.TarError as exc:
            raise ValueError("Supply a complete tar archive of JSON/JSONL trace files") from exc
        while links:
            resolved = {name: paths[target] for name, target in links.items() if target in paths}
            if not resolved:
                raise ValueError("Archive hardlink target is missing or cyclic")
            paths.update(resolved)
            for name in resolved:
                del links[name]
        if not paths:
            raise ValueError("The trace archive contains no JSON/JSONL files")
        # Match native discovery: aliases of one physical file count once, using the first name.
        canonical: dict[Path, str] = {}
        for name in sorted(paths):
            canonical.setdefault(paths[name], name)
        yield sorted(
            [SourceFile(path=path, source_path=name) for path, name in canonical.items()],
            key=lambda item: item.source_path,
        )
